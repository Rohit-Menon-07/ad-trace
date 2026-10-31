"""Abstention gates (SPEC S2, S5, H7). Pure functions -> GateDecision. Messages are code templates, never LLM text.

Order before retrieval: empty query -> injection -> out of scope -> entity linking (unknown / ambiguous make /
ambiguous model) -> false premises. After retrieval: NO_RETRIEVAL_HIT, EMPTY_SOURCE_TEXT.
HOOKS (Prompt 10): LOW_RETRIEVAL_SCORE and APPLICABILITY_UNDETERMINED are stubs that never stop yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.app.pipeline.checks import check_premises, detect_injection, detect_out_of_scope
from backend.app.pipeline.linker import LinkedQuery, Linker


@dataclass
class GateDecision:
    stop: bool
    status: str | None = None  # SearchStatus: refused | needs_clarification
    reason_code: str | None = None
    message: str = ""
    options: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


PASS = GateDecision(False)

_OOS_TEXT = {
    "compliance_steps": "compliance or repair procedures",
    "numeric_spec": "torque values or other numeric limits",
    "parts": "part numbers",
    "legal": "legal advice",
    "other_data": "information that is not in these records",
}


def _names(pairs: list[tuple[str, float]]) -> str:
    return ", ".join(f"'{n}'" for n, _ in pairs) or "none"


def refuse(code: str, message: str, **details: Any) -> GateDecision:
    return GateDecision(True, "refused", code, message, [], details)


def clarify(code: str, message: str, options: list[str], **details: Any) -> GateDecision:
    return GateDecision(True, "needs_clarification", code, message, options, details)


# ------------------------------------------------------------------ individual gates


def gate_empty(query: str, linked: LinkedQuery) -> GateDecision:
    has_config = linked.make.status != "absent" or linked.model.status != "absent"
    if (query or "").strip() or has_config:
        return PASS
    return refuse(
        "NO_RETRIEVAL_HIT",
        "There is nothing to search: type a question or choose an aircraft make and model.",
        empty_query=True,
    )


def gate_injection(query: str, parsed: Any) -> GateDecision:
    flag = detect_injection(query, parsed)
    if not flag.triggered:
        return PASS
    return refuse(
        "INJECTION_SUSPECTED",
        "Your question contains text that reads like instructions to the system, so I "
        "did not run it. Please ask a plain question about an aircraft and its proposed ADs.",
        reasons=flag.reasons,
    )


def gate_out_of_scope(query: str, parsed: Any) -> GateDecision:
    flag = detect_out_of_scope(query, parsed)
    if not flag.triggered:
        return PASS
    what = _OOS_TEXT.get(flag.kind or "other_data", _OOS_TEXT["other_data"])
    return refuse(
        "OUT_OF_SCOPE",
        f"These records are FAA proposal summaries. They do not contain {what}, so I cannot "
        "answer that. Use the official notice, the AMM or your organisation's procedures. I can tell you "
        "which proposals concern your aircraft and what they would require at summary level.",
        kind=flag.kind,
        reasons=flag.reasons,
    )


def gate_entities(linked: LinkedQuery, record_count: int) -> GateDecision:
    mk, md = linked.make, linked.model
    if mk.status == "unknown":
        return refuse(
            "UNKNOWN_ENTITY",
            f"I could not find the make '{mk.text}' in the {record_count} records provided. "
            f"I did not guess. Closest names: {_names(mk.candidates)}.",
            field="make",
            suggestions=[n for n, _ in mk.candidates],
            source=mk.source,
        )
    if mk.status == "ambiguous":
        return clarify(
            "AMBIGUOUS_MAKE",
            f"'{mk.text}' matches more than one manufacturer in the records. Which one do you mean?",
            [n for n, _ in mk.candidates],
            field="make",
            scores=mk.candidates,
        )
    if md.status == "unknown":
        near = ", ".join(f"'{s}'" for s in md.suggestions) or "none"
        return refuse(
            "UNKNOWN_ENTITY",
            f"I could not find the model '{md.text}' in the {record_count} records provided. "
            f"I did not guess. Closest designators: {near}.",
            field="model",
            suggestions=md.suggestions,
            source=md.source,
        )
    if md.status == "ambiguous_family":
        return clarify(
            "AMBIGUOUS_MODEL",
            f"'{md.text}' is a model family. Applicability is decided per model designator, so choose the exact model.",
            md.options,
            field="model",
            family=md.family,
        )
    return PASS


def gate_premises(parsed: Any, linked: LinkedQuery, linker: Linker, query: str = "") -> GateDecision:
    for chk in check_premises(parsed, linker, linked.as_of, query):
        if chk.status == "unknown_ad":
            return refuse(
                "UNKNOWN_ENTITY",
                f"Your question assumes something about AD {chk.ad_number}, but that AD "
                f"number does not appear in the {linker.record_count} records provided. I did not guess.",
                field="ad_number",
                premise=chk.claim_text,
            )
        if chk.status == "contradicts":
            return refuse(
                "CONTRADICTS_RECORD",
                f'Your question assumes "{chk.claim_text}", but the records that '
                f"describe AD {chk.ad_number} ({', '.join(chk.records)}) do not support that. Please check "
                "the premise before relying on it.",
                premise=chk.claim_text,
                records=chk.records,
                reasons=chk.reasons,
            )
    return PASS


def gate_no_hit(record_ids: list[str]) -> GateDecision:
    if record_ids:
        return PASS
    return refuse(
        "NO_RETRIEVAL_HIT",
        "No record in the dataset matches your question and aircraft. This does not mean "
        "no AD exists: the dataset holds 431 proposals only. Check the FAA DRS for final rules.",
    )


def gate_empty_source(records: list[tuple[str, bool]]) -> GateDecision:
    """records: (record_id, summary_missing). Stops only when every retrieved record has no summary text."""
    if not records or not all(missing for _, missing in records):
        return PASS
    ids = [rid for rid, _ in records]
    return refuse(
        "EMPTY_SOURCE_TEXT",
        f"The matching record(s) {', '.join(ids)} have no summary text, so there is "
        "nothing I can quote. Open the Federal Register notice from the record link.",
        records=ids,
    )


def gate_low_retrieval_score(features: dict[str, Any]) -> GateDecision:
    """HOOK (Prompt 10/11): thresholds are tuned on the dev split. Never stops yet."""
    return GateDecision(False, details={"hook": "LOW_RETRIEVAL_SCORE not wired yet (Prompt 10)", **features})


def gate_applicability_undetermined(verdicts: list[str]) -> GateDecision:
    """HOOK (Prompt 10): decide when an all-UNDETERMINED result should stop. Never stops yet."""
    return GateDecision(False, details={"hook": "APPLICABILITY_UNDETERMINED not wired yet (Prompt 10)"})


# ------------------------------------------------------------------ orchestration


def run_pre_retrieval_gates(query: str, parsed: Any, linked: LinkedQuery, linker: Linker) -> GateDecision:
    """First stopping decision wins. Injection is checked before anything else touches the text."""
    for gate in (
        lambda: gate_empty(query, linked),
        lambda: gate_injection(query, parsed),
        lambda: gate_out_of_scope(query, parsed),
        lambda: gate_entities(linked, linker.record_count),
        lambda: gate_premises(parsed, linked, linker, query),
    ):
        decision = gate()
        if decision.stop:
            return decision
    return PASS
