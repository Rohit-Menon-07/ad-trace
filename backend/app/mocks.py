"""MOCK DATA. Canned responses served by the API until the real pipeline exists.

Fictional records shaped like the AD NPRM dataset. Every id, docket and citation is prefixed
MOCK, and every response sets mock=True so the UI shows a MOCK tag. Nothing here is read from
data/raw and none of it describes a real FAA proposal. Delete this module once S1-S8 are built.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Literal

from backend.app.schemas import (
    ApplicabilityResult,
    Citation,
    Claim,
    CoverageMetric,
    CoverageReport,
    EvalResults,
    EvalSet,
    ExcludedRecord,
    FailureCase,
    MetricDef,
    MetricRow,
    RecordCard,
    RecordDetail,
    RecordFull,
    SearchRequest,
    SearchResponse,
    Sentence,
    TraceStep,
)

ScenarioKey = Literal["answered", "partial", "refused", "needs_clarification"]

MOCK_AS_OF = date(2026, 10, 31)
DISCLAIMER = (
    "Decision support only. Verify against the Federal Register notice before acting. "
    "All records are proposed rulemaking (NPRM) and are not in force."
)

# ---------------------------------------------------------------- records


def _card(**kw: Any) -> dict[str, Any]:
    base = {"status_label": "PROPOSED", "withdrawn": False, "url": None, "ad_number": None, "lineage": []}
    return base | kw


_SEEDS: list[dict[str, Any]] = [
    {
        "card": _card(
            record_id="MOCK-R0001",
            docket="MOCK-FAA-2026-0101",
            subject_heading="MOCK: Airbus SAS Airplanes (radio management panels)",
            make="Airbus SAS",
            models=["A330-202", "A330-203", "A330-223", "A330-243", "A330-343"],
            models_confidence="HIGH",
            comment_period="OPEN",
            comments_due="2026-11-20",
            issue_date="2026-10-06",
            fr_citation="MOCK 91 FR 00001",
            pages="00001-00003",
            retrieval_score=0.0325,
            lineage=[
                {
                    "relation": "supersedes",
                    "target_ref": "AD 2023-14-05",
                    "target_in_dataset": False,
                    "target_record_id": None,
                    "evidence_id": "MOCK-R0001#s0",
                },
            ],
        ),
        "make_raw": "Airbus SAS",
        "model_raw": None,
        "sentences": [
            "The FAA proposes to supersede AD 2023-14-05, which applies to certain Airbus SAS Model "
            "A330-202, -203, -223, -243, and -343 airplanes.",
            "AD 2023-14-05 requires replacing certain radio management panels (RMP).",
            "Since the FAA issued AD 2023-14-05, reports were received of RMP display freezes on panels "
            "that were not affected by that AD.",
            "This proposed AD would require replacing additional RMPs, as specified in a European Union "
            "Aviation Safety Agency (EASA) AD, which is proposed for incorporation by reference.",
            "The FAA is proposing this AD to address the unsafe condition on these products.",
        ],
    },
    {
        "card": _card(
            record_id="MOCK-R0002",
            docket="MOCK-FAA-2026-0102",
            subject_heading="MOCK: Airbus SAS Airplanes (trimmable horizontal stabilizer actuator)",
            make="Airbus SAS",
            models=["A330-841", "A330-941"],
            models_confidence="HIGH",
            comment_period="CLOSED",
            comments_due="2026-09-14",
            issue_date="2026-07-30",
            fr_citation="MOCK 91 FR 00004",
            pages="00004-00006",
            retrieval_score=0.0291,
        ),
        "make_raw": "AIRBUS SAS",
        "model_raw": "A330-841, A330-941",
        "sentences": [
            "The FAA proposes to adopt a new AD for certain Airbus SAS Model A330-841 and -941 airplanes.",
            "This proposed AD was prompted by a report of a trimmable horizontal stabilizer actuator (THSA) "
            "no-back brake found worn beyond limits.",
            "This proposed AD would require repetitive inspections of the THSA, as specified in an EASA AD, "
            "which is proposed for incorporation by reference.",
        ],
    },
    {
        "card": _card(
            record_id="MOCK-R0003",
            docket="MOCK-FAA-2026-0103",
            subject_heading="MOCK: Airbus SAS Airplanes (cabin oxygen generators)",
            make="Airbus SAS",
            models=[],
            models_confidence="LOW",
            comment_period="OPEN",
            comments_due="2026-12-01",
            issue_date="2026-10-15",
            fr_citation="MOCK 91 FR 00007",
            pages="00007-00009",
            retrieval_score=0.0164,
        ),
        "make_raw": "Airbus",
        "model_raw": None,
        "sentences": [
            "The FAA proposes to adopt a new AD for certain Airbus SAS Model A330-200, A330-200 Freighter, "
            "and A330-300 series airplanes.",
            "This proposed AD was prompted by reports of passenger oxygen generators that did not activate "
            "during a functional test.",
            "This proposed AD would require replacing affected oxygen generators, as specified in an EASA AD, "
            "which is proposed for incorporation by reference.",
        ],
    },
    {
        "card": _card(
            record_id="MOCK-R0004",
            docket="MOCK-FAA-2026-0104",
            subject_heading="MOCK: Airbus SAS Airplanes (fuel pump canister)",
            make="Airbus SAS",
            models=["A320-214", "A320-216", "A320-232"],
            models_confidence="MEDIUM",
            comment_period="OPEN",
            comments_due="2026-11-27",
            issue_date="2026-10-09",
            fr_citation="MOCK 91 FR 00010",
            pages="00010-00012",
            retrieval_score=0.0318,
            lineage=[
                {
                    "relation": "shares_docket",
                    "target_ref": "MOCK-FAA-2026-0104",
                    "target_in_dataset": True,
                    "target_record_id": "MOCK-R0005",
                    "evidence_id": None,
                },
            ],
        ),
        "make_raw": "Airbus SAS",
        "model_raw": None,
        "sentences": [
            "The FAA proposes to adopt a new AD for certain Airbus SAS Model A320-214, -216, and -232 "
            "airplanes, manufacturer serial numbers (MSN) 1000 through 1500 inclusive.",
            "This proposed AD was prompted by reports of chafing on fuel pump canister wiring.",
            "This proposed AD would require an inspection of the canister wiring and corrective actions if "
            "necessary, as specified in an EASA AD, which is proposed for incorporation by reference.",
        ],
    },
    {
        "card": _card(
            record_id="MOCK-R0005",
            docket="MOCK-FAA-2026-0104",
            subject_heading="MOCK: Airbus SAS Airplanes (fuel pump canister), comment period extension",
            make="Airbus SAS",
            models=["A320-214"],
            models_confidence="MEDIUM",
            comment_period="OPEN",
            comments_due="2026-12-11",
            issue_date="2026-10-20",
            fr_citation="MOCK 91 FR 00013",
            pages="00013",
            retrieval_score=0.0202,
            lineage=[
                {
                    "relation": "comment_extension",
                    "target_ref": "MOCK-FAA-2026-0104",
                    "target_in_dataset": True,
                    "target_record_id": "MOCK-R0004",
                    "evidence_id": "MOCK-R0005#s0",
                },
            ],
        ),
        "make_raw": "AIRBUS",
        "model_raw": None,
        "sentences": [
            "The FAA is extending the comment period for an NPRM that applies to certain Airbus SAS Model "
            "A320-214 airplanes.",
            "The affected airplanes are identified in the service information referenced in the NPRM.",
        ],
    },
]


def _build_sentences(record_id: str, parts: list[str]) -> tuple[str, list[Sentence]]:
    """Join sentences with single spaces and record [start, end) offsets into the summary."""
    sentences: list[Sentence] = []
    summary = ""
    for idx, text in enumerate(parts):
        if idx:
            summary += " "
        start = len(summary)
        summary += text
        sentences.append(
            Sentence(id=f"{record_id}#s{idx}", record_id=record_id, idx=idx, text=text, start=start, end=len(summary))
        )
    return summary, sentences


def _build_records() -> dict[str, RecordDetail]:
    out: dict[str, RecordDetail] = {}
    for seed in _SEEDS:
        card = seed["card"]
        summary, sentences = _build_sentences(card["record_id"], seed["sentences"])
        record = RecordFull.model_validate(
            card
            | {
                "summary": summary,
                "summary_missing": not summary,
                "make_raw": seed["make_raw"],
                "model_raw": seed["model_raw"],
                "product_type": "Aircraft",
                "citation_publish_date": card["issue_date"],
            }
        )
        out[card["record_id"]] = RecordDetail(
            record=record, sentences=sentences, extractions=[], lineage=record.lineage, mock=True
        )
    return out


MOCK_RECORDS: dict[str, RecordDetail] = _build_records()


def mock_card(record_id: str) -> RecordCard:
    full = MOCK_RECORDS[record_id].record
    return RecordCard.model_validate(full.model_dump(include=set(RecordCard.model_fields)))


def mock_cite(evidence_id: str, quote: str) -> Citation:
    """Citation for a quote inside a mock sentence. Raises if the quote is not a substring (mirrors H4)."""
    record_id = evidence_id.split("#")[0]
    detail = MOCK_RECORDS[record_id]
    sentence = next(s for s in detail.sentences if s.id == evidence_id)
    offset = sentence.text.find(quote)
    if offset < 0:
        raise ValueError(f"MOCK quote not in {evidence_id}: {quote!r}")
    return Citation(
        evidence_id=evidence_id,
        docket=detail.record.docket,
        quote=quote,
        span_start=sentence.start + offset,
        span_end=sentence.start + offset + len(quote),
        fr_citation=detail.record.fr_citation,
        pages=detail.record.pages,
        url=detail.record.url,
    )


# ---------------------------------------------------------------- scenarios


def _step(stage: str, status: str, summary: str, ms: int, **details: Any) -> TraceStep:
    return TraceStep.model_validate(
        {"stage": stage, "status": status, "summary": summary, "ms": ms, "details": details}
    )


def _response(**kw: Any) -> SearchResponse:
    base: dict[str, Any] = {
        "request_id": "MOCK-req",
        "reason_code": None,
        "claims": [],
        "rationale_steps": [],
        "records": [],
        "applicability": [],
        "excluded": [],
        "clarification_options": [],
        "disclaimer": DISCLAIMER,
        "as_of": MOCK_AS_OF,
        "mock": True,
    }
    return SearchResponse.model_validate(base | kw)


def _excluded(record_id: str, family: str, wanted: str) -> ExcludedRecord:
    rec = MOCK_RECORDS[record_id].record
    return ExcludedRecord(
        record_id=record_id,
        docket=rec.docket,
        subject_heading=rec.subject_heading,
        rule="S3.hard_filter.model_family",
        reason=f"Model family {family} does not match the requested family {wanted}.",
    )


def _answered() -> SearchResponse:
    return _response(
        status="answered",
        message="1 proposed AD applies to Airbus SAS A330-243; 1 is undetermined and 1 does not apply.",
        claims=[
            Claim(
                text="A proposed AD would supersede AD 2023-14-05 for certain Airbus SAS Model A330-202, -203, "
                "-223, -243 and -343 airplanes.",
                citations=[mock_cite("MOCK-R0001#s0", "The FAA proposes to supersede AD 2023-14-05")],
                verification="verified",
            ),
            Claim(
                text="The proposed AD would require replacing additional radio management panels (RMPs), as "
                "specified in an EASA AD.",
                citations=[mock_cite("MOCK-R0001#s3", "This proposed AD would require replacing additional RMPs")],
                verification="verified",
            ),
            Claim(
                text="It was prompted by reports of RMP display freezes on panels not affected by AD 2023-14-05.",
                citations=[
                    mock_cite(
                        "MOCK-R0001#s2",
                        "reports were received of RMP display freezes on panels that were not affected by that AD",
                    )
                ],
                verification="verified",
            ),
        ],
        rationale_steps=[
            "The form fixes make Airbus SAS and model A330-243; both are in the vocabulary.",
            "MOCK-R0001 lists A330-243 in its model list [MOCK-R0001#s0].",
            "Its required action concerns radio management panels [MOCK-R0001#s3].",
            "It names AD 2023-14-05 as the AD it would supersede [MOCK-R0001#s0].",
        ],
        records=[mock_card("MOCK-R0001"), mock_card("MOCK-R0003"), mock_card("MOCK-R0002")],
        applicability=[
            ApplicabilityResult(
                record_id="MOCK-R0001",
                verdict="APPLICABLE",
                reasons=[
                    "A330-243 is in the extracted model list (HIGH confidence, suffix expansion of "
                    '"A330-202, -203, -223, -243").'
                ],
                evidence_ids=["MOCK-R0001#s0"],
            ),
            ApplicabilityResult(
                record_id="MOCK-R0003",
                verdict="UNDETERMINED",
                reasons=[
                    'Summary names "A330-200 series" only, not individual model designators; model list confidence LOW.'
                ],
                evidence_ids=["MOCK-R0003#s0"],
            ),
            ApplicabilityResult(
                record_id="MOCK-R0002",
                verdict="NOT_APPLICABLE",
                reasons=["Model list (HIGH confidence) is A330-841, A330-941; A330-243 is absent."],
                evidence_ids=["MOCK-R0002#s0"],
            ),
        ],
        excluded=[_excluded("MOCK-R0004", "A320", "A330")],
        trace=[
            _step(
                "S1 Query understanding",
                "ok",
                "Intent: lookup. Form values override parsed make/model.",
                412,
                intent="lookup",
                make="Airbus SAS",
                model="A330-243",
            ),
            _step(
                "S2 Clarification gate",
                "ok",
                "Model A330-243 is an exact vocabulary match; no clarification needed.",
                2,
            ),
            _step(
                "S3 Retrieval",
                "ok",
                "Hard filter make=Airbus SAS, family=A330 → 14 records; hybrid BM25 + dense, RRF k=60 → top 3.",
                184,
                candidates=14,
                returned=3,
                rrf_k=60,
            ),
            _step(
                "S4 Applicability + revision",
                "ok",
                "1 APPLICABLE, 1 UNDETERMINED, 1 NOT_APPLICABLE. 1 supersession edge (target not in dataset).",
                6,
            ),
            _step("S5 Abstention gate", "ok", "No reason code raised.", 1),
            _step(
                "S6 Generation",
                "ok",
                "3 claims, 4 rationale steps from an evidence pack of 11 sentences.",
                1840,
                evidence_sentences=11,
            ),
            _step(
                "S7 Verification",
                "ok",
                "Quote check 3/3, entity grounding 3/3, verifier SUPPORTED 3/3.",
                690,
                claims_in=3,
                claims_dropped=0,
            ),
            _step("S8 Render + audit", "ok", "Answer assembled from verified claims; audit record written.", 3),
        ],
        latency_ms=3138,
    )


def _partial() -> SearchResponse:
    return _response(
        status="partial",
        message="Answer is partial: 1 of 3 generated claims was removed because the verifier could not confirm "
        "it against the cited sentence.",
        claims=[
            Claim(
                text="A proposed AD covers certain Airbus SAS Model A320-214 airplanes, MSN 1000 through 1500 "
                "inclusive.",
                citations=[mock_cite("MOCK-R0004#s0", "manufacturer serial numbers (MSN) 1000 through 1500 inclusive")],
                verification="verified",
            ),
            Claim(
                text="It would require an inspection of the fuel pump canister wiring and corrective actions if "
                "necessary.",
                citations=[
                    mock_cite(
                        "MOCK-R0004#s2",
                        "This proposed AD would require an inspection of the canister wiring and corrective "
                        "actions if necessary",
                    )
                ],
                verification="partial",
            ),
        ],
        rationale_steps=[
            "Serial 1234 falls inside the resolved range MSN 1000–1500 [MOCK-R0004#s0].",
            "The comment-period extension shares the same docket [MOCK-R0005#s0].",
            "The extension notice defers applicability to service information [MOCK-R0005#s1].",
        ],
        records=[mock_card("MOCK-R0004"), mock_card("MOCK-R0005")],
        applicability=[
            ApplicabilityResult(
                record_id="MOCK-R0004",
                verdict="APPLICABLE",
                reasons=[
                    "A320-214 is in the model list (MEDIUM confidence).",
                    "Serial 1234 is within resolved range MSN 1000–1500.",
                ],
                evidence_ids=["MOCK-R0004#s0"],
            ),
            ApplicabilityResult(
                record_id="MOCK-R0005",
                verdict="UNDETERMINED",
                reasons=[
                    "Summary says affected airplanes are identified in service information; no serial range "
                    "resolved in this record."
                ],
                evidence_ids=["MOCK-R0005#s1"],
            ),
        ],
        excluded=[_excluded("MOCK-R0001", "A330", "A320"), _excluded("MOCK-R0002", "A330", "A320")],
        trace=[
            _step(
                "S1 Query understanding",
                "ok",
                'Intent: applicability. Serial "1234" parsed as MSN.',
                388,
                intent="applicability",
                serial="1234",
            ),
            _step("S2 Clarification gate", "ok", "Exact model match.", 2),
            _step(
                "S3 Retrieval",
                "ok",
                "Hard filter make=Airbus SAS, family=A320 → 9 records; top 2 above score floor.",
                171,
                candidates=9,
                returned=2,
            ),
            _step(
                "S4 Applicability + revision",
                "warn",
                "1 APPLICABLE (serial in range), 1 UNDETERMINED (service-information applicability).",
                5,
            ),
            _step("S5 Abstention gate", "ok", "No blocking reason code.", 1),
            _step("S6 Generation", "ok", "3 claims generated.", 1712),
            _step(
                "S7 Verification",
                "warn",
                "1 claim dropped: verifier returned UNSUPPORTED (claim named a part not in the quote).",
                742,
                claims_in=3,
                claims_dropped=1,
                dropped_by={"H4": 0, "H5": 0, "H6": 1},
            ),
            _step("S8 Render + audit", "ok", "Partial answer assembled from 2 surviving claims.", 3),
        ],
        latency_ms=3024,
    )


def _refused() -> SearchResponse:
    return _response(
        status="refused",
        reason_code="UNKNOWN_ENTITY",
        message='Model "A350-2000" does not exist in the dataset vocabulary, so no record can be matched to it.',
        trace=[
            _step(
                "S1 Query understanding",
                "warn",
                'Parsed model "A350-2000". Closest vocabulary match "A350-1041" scored 71 (< 90 threshold).',
                402,
                model_text="A350-2000",
                best_match="A350-1041",
                score=71,
                threshold=90,
            ),
            _step("S5 Abstention gate", "stop", "UNKNOWN_ENTITY raised; retrieval and generation skipped.", 1),
            _step("S8 Render + audit", "ok", "Refusal rendered; audit record written.", 2),
        ],
        latency_ms=405,
    )


def _needs_clarification() -> SearchResponse:
    return _response(
        status="needs_clarification",
        reason_code="AMBIGUOUS_MODEL",
        message='"A330" is a model family. Applicability is decided per model designator, so choose the exact model.',
        clarification_options=["A330-202", "A330-203", "A330-223", "A330-243", "A330-343", "A330-841", "A330-941"],
        trace=[
            _step(
                "S1 Query understanding",
                "ok",
                'Parsed model "A330"; linked to family A330.',
                395,
                model_text="A330",
                linked_kind="family",
            ),
            _step(
                "S2 Clarification gate",
                "stop",
                "Family prefix matches 7 model designators in the vocabulary.",
                2,
                matches=7,
            ),
            _step("S8 Render + audit", "ok", "Clarification options rendered; audit record written.", 2),
        ],
        latency_ms=399,
    )


MOCK_SCENARIOS: dict[ScenarioKey, SearchResponse] = {
    "answered": _answered(),
    "partial": _partial(),
    "refused": _refused(),
    "needs_clarification": _needs_clarification(),
}

_REFUSE_WORDS = ("torque", "a350-2000", "part number")
_FAMILY_ONLY = re.compile(r"^[a-z]+\d+$")  # e.g. "a330" with no "-243" suffix
_BARE_A330 = re.compile(r"\ba330\b(?!-)")


def choose_scenario(req: SearchRequest) -> ScenarioKey:
    """MOCK routing by keyword (Prompt 2). Form fields take priority over the free-text query."""
    query = req.query.lower()
    model = (req.model or "").strip().lower()
    if any(w in f"{query} {model}" for w in _REFUSE_WORDS):
        return "refused"
    if model:
        if _FAMILY_ONLY.match(model):
            return "needs_clarification"
        return "partial" if model.startswith("a320") or req.serial else "answered"
    if _BARE_A330.search(query):
        return "needs_clarification"
    if re.search(r"\b(msn|serial|a320)\b", query) or req.serial:
        return "partial"
    return "answered"


def mock_search(req: SearchRequest) -> SearchResponse:
    """Return a copy of the chosen MOCK scenario with a fresh request id."""
    resp = MOCK_SCENARIOS[choose_scenario(req)].model_copy(deep=True)
    resp.request_id = f"MOCK-req-{uuid.uuid4().hex[:8]}"
    return resp


# ---------------------------------------------------------------- meta, vocab, eval

MOCK_MAKES = ["Airbus SAS", "Airbus Helicopters", "ATR-GIE Avions de Transport Régional", "The Boeing Company"]

MOCK_MODELS: dict[str, list[str]] = {
    "Airbus SAS": [
        "A320-214",
        "A320-216",
        "A320-232",
        "A330-202",
        "A330-203",
        "A330-223",
        "A330-243",
        "A330-343",
        "A330-841",
        "A330-941",
        "A350-941",
        "A350-1041",
    ],
    "Airbus Helicopters": ["AS350B3", "EC135T2"],
    "ATR-GIE Avions de Transport Régional": ["ATR72-212A"],
    "The Boeing Company": ["737-8", "787-9"],
}

MOCK_COVERAGE = CoverageReport(
    generated_at="MOCK",
    total_records=431,
    metrics=[
        CoverageMetric(
            key="model_column",
            label="Model column filled",
            numerator=86,
            denominator=431,
            note="Profiled from source file.",
        ),
        CoverageMetric(
            key="models_extracted",
            label="Model list extracted (any source)",
            numerator=260,
            denominator=431,
            note="MOCK placeholder; real value from ingest.",
        ),
        CoverageMetric(
            key="serial_constraints",
            label="Serial constraints resolved",
            numerator=12,
            denominator=431,
            note="MOCK placeholder. About 19 summaries mention serials.",
        ),
        CoverageMetric(
            key="supersession_edges",
            label="Records with a supersession edge",
            numerator=100,
            denominator=431,
            note="Approximate profiled count; real value from ingest.",
        ),
        CoverageMetric(
            key="ad_number", label="AD Number filled", numerator=21, denominator=431, note="Profiled from source file."
        ),
        CoverageMetric(
            key="empty_summary",
            label="Empty summaries (refused as EMPTY_SOURCE_TEXT if cited)",
            numerator=20,
            denominator=431,
            note="MOCK placeholder; real value from ingest.",
        ),
        CoverageMetric(
            key="duplicate_dockets",
            label="Rows sharing a docket with another row",
            numerator=108,
            denominator=431,
            note="Derived: 431 rows − 323 unique dockets.",
        ),
    ],
    limits=[
        "Every record is a Notice of Proposed Rulemaking. None is in force; final rules are not in this dataset.",
        "Only the Summary field is free text. There is no full notice text, so compliance steps, part numbers "
        "and torque values cannot be answered.",
        "Serial-number applicability can be checked only where a summary states serials. Elsewhere the verdict "
        "is UNDETERMINED.",
        'Most superseded ADs are not in the dataset. AD Trace says "references AD X", not "AD X is superseded", '
        "unless both records are present.",
        "There is no ground-truth Q&A. The evaluation set is hand-built by the team and is small.",
    ],
)

_RATIO = "ratio"
MOCK_EVAL = EvalResults(
    generated_at="MOCK",
    eval_set=EvalSet(
        name="MOCK eval set",
        size=0,
        synthetic=True,
        description="MOCK placeholder. The real set will be hand-written queries over the 431 records, labelled "
        "by the team.",
    ),
    metric_defs=[
        MetricDef(key="recall_at_8", label="Recall@8 (relevant record retrieved)", unit=_RATIO, higher_is_better=True),
        MetricDef(key="applicability_acc", label="Applicability verdict accuracy", unit=_RATIO, higher_is_better=True),
        MetricDef(key="unsupported_rate", label="Unsupported-claim rate", unit=_RATIO, higher_is_better=False),
        MetricDef(key="correct_refusal", label="Correct refusal rate", unit=_RATIO, higher_is_better=True),
        MetricDef(key="p95_retrieval_ms", label="p95 retrieval latency", unit="ms", higher_is_better=False),
    ],
    systems=[
        MetricRow(
            system="AD Trace (full pipeline)",
            is_baseline=False,
            values={
                "recall_at_8": 0.9,
                "applicability_acc": 0.85,
                "unsupported_rate": 0.03,
                "correct_refusal": 0.8,
                "p95_retrieval_ms": 220,
            },
        ),
        MetricRow(
            system="BM25 only (baseline)",
            is_baseline=True,
            values={
                "recall_at_8": 0.7,
                "applicability_acc": None,
                "unsupported_rate": None,
                "correct_refusal": None,
                "p95_retrieval_ms": 40,
            },
        ),
        MetricRow(
            system="LLM with no safeguards (baseline)",
            is_baseline=True,
            values={
                "recall_at_8": 0.7,
                "applicability_acc": 0.6,
                "unsupported_rate": 0.2,
                "correct_refusal": 0.3,
                "p95_retrieval_ms": 40,
            },
        ),
    ],
    ablation=[
        MetricRow(
            system="Full (H4 + H5 + H6)", is_baseline=False, values={"unsupported_rate": 0.03, "correct_refusal": 0.8}
        ),
        MetricRow(
            system="Without verifier (H6 off)",
            is_baseline=False,
            values={"unsupported_rate": 0.08, "correct_refusal": 0.75},
        ),
        MetricRow(
            system="Without quote check (H4 off)",
            is_baseline=False,
            values={"unsupported_rate": 0.12, "correct_refusal": 0.75},
        ),
    ],
    failures=[
        FailureCase(
            id="MOCK-F1",
            query="Does the oxygen generator proposal apply to our A330-243?",
            expected="APPLICABLE (A330-243 is an A330-200 series model)",
            observed="UNDETERMINED",
            cause='Summary lists "A330-200 series" not designators; the extractor does not map series names to models.',
            user_signal='Amber UNDETERMINED badge with the reason "series only, LOW confidence" and a link to the '
            "notice.",
        )
    ],
    mock=True,
)
