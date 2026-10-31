"""S7 verification (SPEC H4, H5, H6, H9). Every generated claim must survive all enabled layers; built adversarially.

Layer 1 quotes (H4, code): the normalised quote is a contiguous substring of ONE cited sentence that exists in the
  pack, with >= 3 words. Spans are mapped back to Summary offsets for highlighting.
Layer 2 grounding (H5, code): every AD number, docket, designator, date and number in the claim appears in its
  cited sentences, cited records' metadata or cited fact lines; no in-force mandate wording; claim verdict wording
  does not contradict a cited applicability fact (keyword table in configs/rules.yaml).
Layer 3 verifier (H6, Haiku, one batched forced tool call): sees ONLY each claim and its excerpt; only SUPPORTED
  survives. Claims identical to their quote are SUPPORTED without a call (verbatim).
Each layer is switchable (config.yaml `verify.*`) for the ablation study.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from backend.app.config import load_config
from backend.app.engine.applicability import rules as engine_rules
from backend.app.extract.models import norm_model
from backend.app.llm.client import LLMClient, LLMError, LLMResult, get_client
from backend.app.pipeline.generate import ClaimOut, EvidencePack, SubmitAnswer
from backend.app.schemas import Citation, Claim

PROMPT_PATH = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "verify.md"
LayerStatus = Literal["pass", "fail", "skipped", "n/a"]

# ------------------------------------------------------------------ normalisation (with an index map)

_QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "`": "'"}
_DASHES = "‐‑‒–—―−﹘﹣－"
_EDGE = set(" \t\n.,;:!?\"'()[]{}<>")


def _norm_char(ch: str) -> str:
    out = unicodedata.normalize("NFKC", ch)
    out = "".join(_QUOTES.get(c, "-" if c in _DASHES else c) for c in out).casefold()
    return " " if out.isspace() else out


def norm_with_map(text: str) -> tuple[str, list[int]]:
    """Normalised text plus, for each output char, the index of the original char it came from."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(html.unescape(text) if "&" in text else text):
        for c in _norm_char(ch):
            if c == " " and (not out or out[-1] == " "):
                continue
            out.append(c)
            idx.append(i)
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def norm(text: str) -> str:
    return norm_with_map(text)[0]


def norm_quote(text: str) -> str:
    """Quote normalisation also strips surrounding punctuation (rule: 'strip surrounding punctuation')."""
    s = norm(text)
    a, b = 0, len(s)
    while a < b and s[a] in _EDGE:
        a += 1
    while b > a and s[b - 1] in _EDGE:
        b -= 1
    return s[a:b]


def word_count(text: str) -> int:
    return len(re.findall(r"[0-9A-Za-zÀ-￿]+", text))


# ------------------------------------------------------------------ entity extraction (H5)

_MONTHS = {
    m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)
}
_MONTH = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?"
    r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
RX_CODE = re.compile(r"(?<![\w-])(\d{2,4})\s?-\s?(\d{2})\s?-\s?(\d{2,3})(?:\s+(R\d+))?(?![\w-])")  # AD nos / ISO dates
RX_DOCKET = re.compile(r"\bFAA[-\s]?\d{4}-\d{3,5}(?:R\d+)?\b|\b\d{2,4}-[A-Z]{2,3}-\d{1,3}-AD(?:-W)?\b", re.IGNORECASE)
RX_DATE_MDY_NAME = re.compile(rf"\b{_MONTH}\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE)
RX_DATE_DMY_NAME = re.compile(rf"\b(\d{{1,2}})\s+{_MONTH}\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
RX_DATE_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
RX_DESIGNATOR = re.compile(
    r"(?<![\w-])[A-Z][A-Z0-9]*\d[A-Z0-9]*(?:-[A-Z0-9]+)*|(?<![\w-])\d{2,4}(?:-[0-9A-Z]+)+(?![\w-])"
)
RX_SUFFIX = re.compile(r"(?<![\w-])-\s?\d{2,4}[A-Z]{0,3}\b")
RX_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")
# Spelled-out counts ("three inspections") must be grounded like digits. "one" is excluded: too often a pronoun.
_UNITS = {w: i for i, w in enumerate("two three four five six seven eight nine".split(), 2)}
_TEENS = {
    w: i
    for i, w in enumerate("ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), 10)
}
_TENS = {w: i * 10 for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)}
RX_NUMBER_WORD = re.compile(
    rf"\b(?:({'|'.join(_TENS)})(?:[-\s]({'|'.join(_UNITS)}|one))?|({'|'.join(_TEENS)})|({'|'.join(_UNITS)}))\b",
    re.IGNORECASE,
)


def number_words(text: str) -> set[str]:
    """Digit strings for spelled-out numbers 2-99 ('twenty-five' -> '25')."""
    out: set[str] = set()
    for m in RX_NUMBER_WORD.finditer(text):
        tens, unit, teen, single = (g.lower() if g else None for g in m.groups())
        if tens:
            out.add(str(_TENS[tens] + (1 if unit == "one" else _UNITS.get(unit or "", 0))))
        elif teen:
            out.add(str(_TEENS[teen]))
        elif single:
            out.add(str(_UNITS[single]))
    return out


@dataclass
class Entities:
    codes: set[str] = field(default_factory=set)  # AD numbers and ISO dates (same YYYY-NN-NN shape)
    dockets: set[str] = field(default_factory=set)
    designators: set[str] = field(default_factory=set)
    suffixes: set[str] = field(default_factory=set)
    numbers: set[str] = field(default_factory=set)

    def items(self) -> list[tuple[str, str]]:
        return (
            [("code", x) for x in sorted(self.codes)]
            + [("docket", x) for x in sorted(self.dockets)]
            + [("designator", x) for x in sorted(self.designators)]
            + [("suffix", x) for x in sorted(self.suffixes)]
            + [("number", x) for x in sorted(self.numbers)]
        )


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    return "".join(chars)


def extract_entities(text: str) -> Entities:
    """Entities that must be grounded. Matched spans are masked so a date is not also counted as numbers."""
    text = html.unescape(text)
    ents = Entities()
    spans: list[tuple[int, int]] = []
    for m in RX_DOCKET.finditer(text):
        ents.dockets.add(re.sub(r"^FAA[\s-]?", "FAA-", m.group(0).upper()))
        spans.append(m.span())
    t1 = _mask(text, spans)
    for m in RX_CODE.finditer(t1):
        code = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" + (f" {m.group(4).upper()}" if m.group(4) else "")
        ents.codes.add(code)
        spans.append(m.span())
    for rx, order in ((RX_DATE_MDY_NAME, "mdy"), (RX_DATE_DMY_NAME, "dmy")):
        for m in rx.finditer(_mask(text, spans)):
            if order == "mdy":
                mon, day, yr = m.group(1), m.group(2), m.group(3)
            else:
                day, mon, yr = m.group(1), m.group(2), m.group(3)
            iso = _iso(int(yr), _MONTHS[mon[:3].lower()], int(day))
            ents.codes.add(iso or m.group(0))
            spans.append(m.span())
    for m in RX_DATE_NUM.finditer(_mask(text, spans)):
        iso = _iso(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        ents.codes.add(iso or m.group(0))
        spans.append(m.span())
    t2 = _mask(text, spans)
    for m in RX_DESIGNATOR.finditer(t2):
        ents.designators.add(norm_model(m.group(0)))
        spans.append(m.span())
    for m in RX_SUFFIX.finditer(_mask(text, spans)):
        ents.suffixes.add(m.group(0).replace(" ", "").upper())
        spans.append(m.span())
    for m in RX_NUMBER.finditer(_mask(text, spans)):
        ents.numbers.add(m.group(0).replace(",", ""))
    ents.numbers |= number_words(_mask(text, spans))
    return ents


@dataclass
class Haystack:
    """Everything a claim may legitimately mention: cited sentences, cited records' metadata, cited fact lines."""

    ents: Entities
    digits: set[str]
    loose: set[str]

    @classmethod
    def build(cls, texts: list[str], models: list[str], extra_codes: list[str]) -> Haystack:
        ents = Entities()
        for t in texts:
            e = extract_entities(t)
            ents.codes |= e.codes
            ents.dockets |= e.dockets
            ents.designators |= e.designators
            ents.suffixes |= e.suffixes
            ents.numbers |= e.numbers
        ents.designators |= {norm_model(m) for m in models}
        ents.codes |= {c for c in extra_codes if c}
        digits = {d for t in texts for d in re.findall(r"\d+(?:\.\d+)?", html.unescape(t).replace(",", ""))}
        digits |= {d for m in models for d in re.findall(r"\d+", m)}
        digits |= {d for t in texts for d in number_words(html.unescape(t))}
        loose = {re.sub(r"[^A-Z0-9]", "", d) for d in ents.designators}
        return cls(ents, digits, loose)

    def missing(self, claim: Entities) -> list[str]:
        out = []
        for kind, value in claim.items():
            if kind == "code" and value not in self.ents.codes:
                out.append(f"{'AD/date' if len(value) >= 8 else 'code'} {value}")
            elif kind == "docket" and value not in self.ents.dockets:
                out.append(f"docket {value}")
            elif (
                kind == "designator"
                and value not in self.ents.designators
                and re.sub(r"[^A-Z0-9]", "", value) not in self.loose
            ):
                out.append(f"designator {value}")
            elif kind == "suffix" and value not in self.ents.suffixes:
                out.append(f"suffix {value}")
            elif kind == "number" and value not in self.digits:
                out.append(f"number {value}")
        return out


# ------------------------------------------------------------------ report types


@dataclass
class LayerResult:
    status: LayerStatus
    reasons: list[str] = field(default_factory=list)


@dataclass
class ClaimCheck:
    index: int
    claim: ClaimOut
    quotes: LayerResult
    grounding: LayerResult
    verifier: LayerResult
    kept: bool = False
    dropped_by: str | None = None  # quotes | grounding | llm
    quote_evidence_id: str | None = None
    span: tuple[int, int] | None = None  # into the record Summary


@dataclass
class RationaleCheck:
    text: str
    kept: bool
    reasons: list[str]


@dataclass
class VerificationReport:
    claims: list[ClaimCheck]
    rationale: list[RationaleCheck]
    layers: dict[str, bool]
    status: Literal["answered", "partial", "refused"]
    reason_code: str | None
    model_cannot_answer: bool = False
    cannot_answer_reason: str | None = None
    verifier: LLMResult | None = None
    verifier_error: str | None = None

    @property
    def kept(self) -> list[ClaimCheck]:
        return [c for c in self.claims if c.kept]

    @property
    def counts(self) -> dict[str, int]:
        dropped = {k: sum(1 for c in self.claims if c.dropped_by == k) for k in ("quotes", "grounding", "llm")}
        return {
            "proposed": len(self.claims),
            "kept": len(self.kept),
            **{f"dropped_{k}": v for k, v in dropped.items()},
            "rationale_proposed": len(self.rationale),
            "rationale_kept": sum(r.kept for r in self.rationale),
        }

    @property
    def removed(self) -> int:
        return len(self.claims) - len(self.kept)

    @property
    def rationale_steps(self) -> list[str]:
        kept = [r.text for r in self.rationale if r.kept]
        return kept if len(kept) >= int(load_config().get("verify", {}).get("min_rationale_steps", 2)) else []

    @property
    def message(self) -> str:
        if self.status == "partial":
            noun = "statement" if self.removed == 1 else "statements"
            return f"{self.removed} {noun} removed because they could not be verified."
        if self.reason_code == "VERIFICATION_FAILED":
            return "None of the generated statements could be verified against the cited sources, so none are shown."
        return ""


# ------------------------------------------------------------------ layer 1: quotes


def check_quote(c: ClaimOut, pack: EvidencePack) -> tuple[LayerResult, str | None, tuple[int, int] | None]:
    if not c.evidence_ids and not c.quote:
        return LayerResult("n/a", ["fact-only claim"]), None, None
    unknown = [e for e in c.evidence_ids if e not in pack.evidence_ids]
    if unknown:
        return LayerResult("fail", [f"EVIDENCE_ID_UNKNOWN: {', '.join(unknown)}"]), None, None
    if not c.quote:
        return LayerResult("fail", ["QUOTE_MISSING: evidence cited without a quote"]), None, None
    if word_count(c.quote) < 3:
        return LayerResult("fail", [f"QUOTE_TOO_SHORT: {word_count(c.quote)} words"]), None, None
    q = norm_quote(c.quote)
    if not q:
        return LayerResult("fail", ["QUOTE_TOO_SHORT: empty after normalisation"]), None, None
    by_id = {e.id: e for e in pack.evidence}
    for eid in c.evidence_ids:
        ev = by_id[eid]
        s, idx = norm_with_map(ev.text)
        pos = s.find(q)
        if pos >= 0:
            a, b = idx[pos], idx[pos + len(q) - 1] + 1
            span = (ev.start + a, ev.start + b) if ev.start is not None else None
            return LayerResult("pass", [f"quote found in {eid}"]), eid, span
    return LayerResult("fail", [f"QUOTE_NOT_SUBSTRING: not found in {', '.join(c.evidence_ids)}"]), None, None


# ------------------------------------------------------------------ layer 2: grounding


@lru_cache(maxsize=1)
def _vrules() -> dict[str, Any]:
    return engine_rules()["verify"]


def haystack_for(evidence_ids: list[str], fact_ids: list[str], pack: EvidencePack) -> Haystack:
    by_e = {e.id: e for e in pack.evidence}
    by_f = {f.id: f for f in pack.facts}
    texts: list[str] = []
    rids: set[str] = set()
    for eid in evidence_ids:
        if eid in by_e:
            texts.append(by_e[eid].text)
            rids.add(by_e[eid].record_id)
            texts.append(eid)
    for fid in fact_ids:
        if fid in by_f:
            f = by_f[fid]
            texts.append(f"{f.id} | {f.kind} | {f.record_id} | {f.text}")
            rids.add(f.record_id)
    models: list[str] = []
    codes: list[str] = []
    for rid in rids:
        r = pack.records.get(rid)
        texts.append(rid)
        if r is None:
            continue
        texts += [x for x in (r.docket, r.fr_citation, r.pages, r.make) if x]
        models += r.models
        codes.append(r.ad_number or "")
    return Haystack.build(texts, models, codes)


def mandate_problem(text: str) -> str | None:
    vr = _vrules()
    low = text.casefold()
    stripped = re.sub(vr["existing_ad_subject"], " ", text, flags=re.IGNORECASE).casefold()
    words = [w for w in vr["mandate_words"] if re.search(rf"\b{re.escape(w)}\b", stripped)]
    if not words:
        return None
    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in vr["proposal_words"]):
        return None
    return f"MANDATE_LANGUAGE: '{words[0]}' without proposal wording"


def claim_stance(text: str) -> str | None:
    low = text.casefold()
    for verdict in ("NOT_APPLICABLE", "UNDETERMINED", "APPLICABLE"):
        if any(p in low for p in _vrules()["verdict_phrases"][verdict]):
            return verdict
    return None


# claim stance -> computed verdicts it contradicts (a cautious downgrade APPLICABLE -> "may apply" is allowed)
_CONFLICTS = {
    "APPLICABLE": {"NOT_APPLICABLE", "UNDETERMINED", "NOT_CHECKED"},
    "NOT_APPLICABLE": {"APPLICABLE", "UNDETERMINED", "NOT_CHECKED"},
    "UNDETERMINED": {"NOT_APPLICABLE"},
}


def check_grounding(c: ClaimOut, pack: EvidencePack) -> LayerResult:
    reasons: list[str] = []
    hay = haystack_for(c.evidence_ids, c.fact_ids, pack)
    missing = hay.missing(extract_entities(c.text))
    if missing:
        reasons.append(f"ENTITY_NOT_GROUNDED: {', '.join(missing)}")
    if m := mandate_problem(c.text):
        reasons.append(m)
    stance = claim_stance(c.text)
    if stance:
        by_f = {f.id: f for f in pack.facts}
        for fid in c.fact_ids:
            f = by_f.get(fid)
            if f and f.kind == "applicability":
                verdict = f.text.split(" | ", 1)[0].strip()
                if verdict in _CONFLICTS.get(stance, set()):
                    reasons.append(f"FACT_CONTRADICTION: claim says {stance}, {fid} computed {verdict}")
    return LayerResult("fail" if reasons else "pass", reasons)


# ------------------------------------------------------------------ layer 3: independent verifier


class VerifyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    verdict: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
    issue: str | None


class VerifyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[VerifyItem]


def excerpt_for(c: ClaimOut, pack: EvidencePack) -> str:
    """Only the quote and/or the cited fact lines: no question, no other evidence (the verifier must not be able
    to rescue a weak claim from context)."""
    parts = [c.quote] if c.quote else []
    by_f = {f.id: f for f in pack.facts}
    parts += [f"{by_f[x].record_id}: {by_f[x].text}" for x in c.fact_ids if x in by_f]
    return " / ".join(p for p in parts if p)


def verifier_message(items: list[tuple[str, str, str]]) -> str:
    esc = lambda s: html.escape(s, quote=False)  # noqa: E731
    body = "\n".join(
        f'<item id="{i}"><claim>{esc(cl)}</claim><excerpt>{esc(ex)}</excerpt></item>' for i, cl, ex in items
    )
    return f"<items>\n{body}\n</items>"


def run_verifier(items: list[tuple[str, str, str]], client: LLMClient) -> tuple[dict[str, VerifyItem], LLMResult]:
    expected = {i for i, _, _ in items}

    def ids_match(out: Any) -> str | None:
        got = [r.id for r in out.results]
        if set(got) != expected or len(got) != len(expected):
            return f"results must cover exactly ids {sorted(expected)}, got {got}"
        return None

    res = client.call_tool(
        purpose="verify",
        model_key="verifier",
        system=PROMPT_PATH.read_text(encoding="utf-8").strip(),
        user=verifier_message(items),
        tool_name="verify_claims",
        tool_description="Record a verdict (SUPPORTED, PARTIAL or UNSUPPORTED) and a short issue for every item id.",
        output_model=VerifyOutput,
        max_tokens_key="max_tokens_verifier",
        extra_validator=ids_match,
    )
    out: VerifyOutput = res.output  # type: ignore[assignment]
    return {r.id: r for r in out.results}, res


# ------------------------------------------------------------------ rationale steps


_IDS = re.compile(r"\[([^\]]+)\]")


def check_rationale(step: str, pack: EvidencePack, grounding: bool) -> RationaleCheck:
    ids = [x.strip() for grp in _IDS.findall(step) for x in grp.split(",") if x.strip()]
    known_e = [x for x in ids if x in pack.evidence_ids]
    known_f = [x for x in ids if x in pack.fact_ids]
    if not known_e and not known_f:
        return RationaleCheck(step, False, ["RATIONALE_NO_VALID_ID" if not ids else f"RATIONALE_UNKNOWN_ID: {ids}"])
    if grounding:
        body = _IDS.sub(" ", step)
        missing = haystack_for(known_e, known_f, pack).missing(extract_entities(body))
        if missing:
            return RationaleCheck(step, False, [f"ENTITY_NOT_GROUNDED: {', '.join(missing)}"])
    return RationaleCheck(step, True, [])


# ------------------------------------------------------------------ orchestration


def layer_switches(overrides: dict[str, bool] | None = None) -> dict[str, bool]:
    cfg = load_config().get("verify", {})
    layers = {k: bool(cfg.get(k, True)) for k in ("quotes", "grounding", "llm")}
    return layers | (overrides or {})


def verify(
    answer: SubmitAnswer,
    pack: EvidencePack,
    client: LLMClient | None = None,
    layers: dict[str, bool] | None = None,
    extractive: bool = False,
) -> VerificationReport:
    """Run the enabled layers. `extractive=True` (verbatim sentences + computed facts) skips the LLM layer: there is
    no model wording to audit."""
    sw = layer_switches(layers)
    checks: list[ClaimCheck] = []
    for i, c in enumerate(answer.claims, 1):
        q, src, span = check_quote(c, pack)
        if not sw["quotes"]:  # ablated: never drops, but a findable quote still gets its highlight span
            q = LayerResult("skipped")
        chk = ClaimCheck(i, c, q, LayerResult("skipped"), LayerResult("skipped"), quote_evidence_id=src, span=span)
        if q.status == "fail":
            chk.dropped_by = "quotes"
        elif sw["grounding"]:
            chk.grounding = check_grounding(c, pack)
            if chk.grounding.status == "fail":
                chk.dropped_by = "grounding"
        checks.append(chk)

    report_verifier: LLMResult | None = None
    verifier_error: str | None = None
    survivors = [c for c in checks if c.dropped_by is None]
    if sw["llm"] and not extractive and survivors:
        to_ask = []
        for c in survivors:
            if c.claim.quote and norm_quote(c.claim.text) == norm_quote(c.claim.quote) and not c.claim.fact_ids:
                c.verifier = LayerResult("pass", ["verbatim: claim text is the quote"])
            else:
                to_ask.append((f"C{c.index}", c.claim.text, excerpt_for(c.claim, pack)))
        if to_ask:
            try:
                verdicts, report_verifier = run_verifier(to_ask, client or get_client())
            except LLMError as exc:
                verifier_error = str(exc)
                verdicts = {}
            for c in survivors:
                if c.verifier.status == "pass":
                    continue
                v = verdicts.get(f"C{c.index}")
                if v is None:
                    c.verifier = LayerResult("fail", [f"VERIFIER_ERROR: {verifier_error or 'no verdict'}"])
                elif v.verdict == "SUPPORTED":
                    c.verifier = LayerResult("pass", [v.issue] if v.issue else [])
                else:
                    c.verifier = LayerResult("fail", [f"{v.verdict}: {v.issue or 'no issue given'}"])
                if c.verifier.status == "fail":
                    c.dropped_by = "llm"
    for c in checks:
        c.kept = c.dropped_by is None

    rationale = [check_rationale(s, pack, sw["grounding"]) for s in answer.rationale_steps]
    proposed, kept = len(checks), sum(c.kept for c in checks)
    if answer.cannot_answer or proposed == 0:
        status, code = "refused", None
    elif kept == proposed:
        status, code = "answered", None
    elif kept:
        status, code = "partial", None
    else:
        status, code = "refused", "VERIFICATION_FAILED"
    return VerificationReport(
        checks,
        rationale,
        sw,
        status,
        code,
        answer.cannot_answer,  # type: ignore[arg-type]
        answer.cannot_answer_reason,
        report_verifier,
        verifier_error,
    )


# ------------------------------------------------------------------ API claims (only verified ones)


def to_api_claims(report: VerificationReport, pack: EvidencePack) -> list[Claim]:
    by_e = {e.id: e for e in pack.evidence}
    by_f = {f.id: f for f in pack.facts}
    out: list[Claim] = []
    for c in report.kept:
        cites: list[Citation] = []
        for eid in c.claim.evidence_ids:
            ev = by_e[eid]
            r = pack.records.get(ev.record_id)
            is_src = eid == c.quote_evidence_id
            cites.append(
                Citation(
                    evidence_id=eid,
                    docket=r.docket if r else "",
                    quote=c.claim.quote if is_src and c.claim.quote else ev.text,
                    span_start=c.span[0] if is_src and c.span else ev.start,
                    span_end=c.span[1] if is_src and c.span else ev.end,
                    fr_citation=(r.fr_citation if r else None) or "",
                    pages=(r.pages if r else None) or "",
                    url=r.url if r else None,
                )
            )
        for fid in c.claim.fact_ids:
            f = by_f.get(fid)
            if f is None:
                continue
            r = pack.records.get(f.record_id)
            cites.append(
                Citation(
                    evidence_id=f"{f.record_id}#{fid}",
                    docket=r.docket if r else "",
                    quote=f.text,
                    span_start=None,
                    span_end=None,
                    fr_citation=(r.fr_citation if r else None) or "",
                    pages=(r.pages if r else None) or "",
                    url=r.url if r else None,
                )
            )
        out.append(Claim(text=c.claim.text, citations=cites, verification="verified"))
    return out
