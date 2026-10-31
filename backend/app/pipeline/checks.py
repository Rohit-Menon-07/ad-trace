"""Code-only checks before retrieval: prompt injection, out-of-scope requests, false premises (SPEC S5, H2, H10)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from backend.app.engine.applicability import evaluate
from backend.app.engine.types import LinkedConfig
from backend.app.extract.lineage import norm_ad
from backend.app.pipeline.linker import Linker

_INJECTION = re.compile(
    r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above)|disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above)"
    r"|system\s+prompt|you\s+are\s+now\b|new\s+instructions|reveal\s+(?:your|the)\s+(?:prompt|instructions)"
    r"|developer\s+mode|jailbreak|</?\s*(?:system|user_query|instructions)\s*>",
    re.IGNORECASE,
)
_OUT_OF_SCOPE = re.compile(
    r"\btorque\b|\bpart\s+numbers?\b|\bP/Ns?\b|how\s+(?:do|should|can)\s+(?:i|we)\s+comply|step[\s-]+by[\s-]+step"
    r"|\blegal(?:ly)?\b|\bliab(?:le|ility)\b|\bsue\b|\blawsuit\b",
    re.IGNORECASE,
)
# "What does the proposal say/require about X?" is a question about the record itself: in scope.
_ABOUT_PROPOSAL = re.compile(
    r"\b(?:what|which|does|do|is|are)\b[^?.]{0,60}\b(?:proposal|proposed\s+AD|NPRM|notice|summary|record)s?\b"
    r"[^?.]{0,40}\b(?:say|says|said|mention|mentions|require|requires|propose|proposes|cover|covers|about)\b"
    r"|\b(?:proposal|proposed\s+AD|NPRM|notice|summary|record)s?\b[^?.]{0,20}\b(?:say|says|mention|mentions)\b",
    re.IGNORECASE,
)


@dataclass
class Flag:
    triggered: bool
    reasons: list[str] = field(default_factory=list)
    kind: str | None = None


def detect_injection(text: str, parsed: Any) -> Flag:
    reasons = []
    if getattr(parsed, "injection_suspected", False):
        reasons.append("parser flagged an instruction inside the question")
    hits = sorted({m.group(0).lower() for m in _INJECTION.finditer(text or "")})
    if hits:
        reasons.append(f"instruction-like phrases: {', '.join(hits)}")
    return Flag(bool(reasons), reasons)


def detect_out_of_scope(text: str, parsed: Any) -> Flag:
    hits = sorted({m.group(0).lower() for m in _OUT_OF_SCOPE.finditer(text or "")})
    parser_flag = bool(getattr(parsed, "asks_out_of_scope", False))
    kind = getattr(parsed, "out_of_scope_kind", None) if parser_flag else None
    if not hits and not parser_flag:
        return Flag(False)
    if _ABOUT_PROPOSAL.search(text or ""):
        return Flag(False, ["asks what the proposal itself says: in scope"], None)
    reasons = ([f"keywords: {', '.join(hits)}"] if hits else []) + (
        ["parser flagged out-of-scope"] if parser_flag else []
    )
    if not kind or kind == "none":
        kind = next((_keyword_kind(h) for h in hits), "other_data")
    return Flag(True, reasons, kind)


def _keyword_kind(hit: str) -> str:
    if "torque" in hit:
        return "numeric_spec"
    if "part" in hit or "p/n" in hit:
        return "parts"
    if "comply" in hit or "step" in hit:
        return "compliance_steps"
    return "legal"


@dataclass
class PremiseCheck:
    ad_number: str
    claim_text: str
    status: Literal["contradicts", "consistent", "unknown_ad", "unchecked"]
    records: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def check_premises(parsed: Any, linker: Linker, as_of: date, text: str = "") -> list[PremiseCheck]:
    """For each premise naming an AD: unknown AD -> unknown_ad; engine says NOT_APPLICABLE on every record that
    describes that AD -> contradicts. Premises whose make/model cannot be linked are left unchecked."""
    out: list[PremiseCheck] = []
    for prem in merged_premises(parsed, text):
        if not prem.ad_number_text:
            continue
        m = re.search(r"\d{2,4}\s?-\s?\d{2}\s?-\s?\d{2,3}", prem.ad_number_text)
        if not m:
            continue
        ad = norm_ad(m.group(0))
        if ad not in linker.ad_index:
            out.append(PremiseCheck(ad, prem.claim_text, "unknown_ad", [], [f"AD {ad} does not appear in any record"]))
            continue
        subjects = linker.ad_subject_records.get(ad, [])
        make = linker.link_make(prem.make_text, "parsed")
        model = linker.link_model(prem.model_text, "parsed", make.canonical if make.status == "accepted" else None)
        fam = model.family or (model_family_of(prem.model_text) if model.status == "ambiguous_family" else None)
        cfg = LinkedConfig(
            make.canonical if make.status == "accepted" else None,
            model.model_norm if model.status == "accepted" else None,
            fam if model.status in ("accepted", "ambiguous_family") else None,
            None,
            as_of,
        )
        if not subjects or linker.engine_index is None or not (cfg.make_canonical or cfg.model_norm or cfg.family):
            out.append(
                PremiseCheck(
                    ad,
                    prem.claim_text,
                    "unchecked",
                    subjects,
                    [
                        "premise make/model could not be linked"
                        if subjects
                        else f"no record describes AD {ad}'s applicability"
                    ],
                )
            )
            continue
        verdicts = {rid: evaluate(cfg, linker.engine_index.records[rid]) for rid in subjects}
        if all(v.verdict == "NOT_APPLICABLE" for v in verdicts.values()):
            reasons = [f"{rid}: {v.reasons[-1]}" for rid, v in verdicts.items()]
            out.append(PremiseCheck(ad, prem.claim_text, "contradicts", subjects, reasons))
        else:
            out.append(
                PremiseCheck(
                    ad, prem.claim_text, "consistent", subjects, [f"{rid}: {v.verdict}" for rid, v in verdicts.items()]
                )
            )
    return out


_PREMISE = re.compile(
    r"\b(?:since|because|given that|as|now that)\s+(?:the\s+)?(?:AD\s+)?(?P<ad>\d{2,4}\s?-\s?\d{2}\s?-\s?\d{2,3})\s+"
    r"(?:applies|apply|is applicable|covers|affects)\s+to\s+(?:the\s+|our\s+|my\s+|all\s+)?"
    r"(?P<model>[A-Z][A-Z0-9]*-?\d[A-Z0-9-]*|\d{3}(?:-[0-9A-Z]+)*)",
    re.IGNORECASE,
)


def heuristic_premises(text: str) -> list[Any]:
    """Code-side premise detection ("since AD X applies to MODEL"): runs with or without the parser LLM, so a
    false premise is still caught when the parser is unavailable. Returns query.Premise objects."""
    from backend.app.pipeline.query import Premise

    out = []
    for m in _PREMISE.finditer(text or ""):
        out.append(
            Premise(
                make_text=None,
                model_text=m.group("model"),
                ad_number_text=m.group("ad"),
                claim_text=f"AD {norm_ad(m.group('ad'))} applies to {m.group('model')}",
            )
        )
    return out


def merged_premises(parsed: Any, text: str) -> list[Any]:
    """Parser premises plus code-detected ones (deduplicated by AD number + model)."""
    seen = set()
    out = []
    for p in list(getattr(parsed, "asserted_premises", []) or []) + heuristic_premises(text):
        key = (norm_ad(p.ad_number_text or ""), (p.model_text or "").upper())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def model_family_of(text: str | None) -> str | None:
    from backend.app.extract.models import family, norm_model

    return family(norm_model(text)) if text else None
