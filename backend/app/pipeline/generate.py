"""S6 grounded generation (SPEC H1, H2, H3, H9, H10). The model only phrases; facts come from the engine.

- build_pack(): deterministic evidence pack (<evidence>, <computed_facts>, <user_question>), all dataset and user
  text escaped so it cannot open or close tags; at most 14 sentences, ordered by record then sentence index.
- generate(): Sonnet via one `submit_answer` tool call (see llm/client.py for tool_choice/strict handling), schema +
  pack-reference validation, one retry, then LLM_ERROR -> extractive fallback.
- extractive_answer(): no LLM. Verbatim top sentence per record + computed facts. Used for mode=search_only, as
  the LLM_ERROR fallback, and as the evaluation baseline.
Verification (quote check, entity grounding, verifier model) is Prompt 9, not here.

CLI: python -m backend.app.pipeline.generate "question" --make "Airbus SAS" --model A330-243 [--mode search_only]
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.engine.types import Applicability, Lineage, RecordStatus
from backend.app.llm.client import LLMClient, LLMError, LLMResult, get_client

PROMPT_PATH = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "generate.md"
MAX_SENTENCES = 14
MAX_CLAIMS = 6
MAX_RATIONALE = 5
ANCHOR_TAGS = {"applicability", "supersession"}


# ------------------------------------------------------------------ data types


@dataclass(frozen=True)
class SentenceIn:
    id: str  # R0001#s2, or R0294#heading for a record without a summary
    idx: int
    text: str
    start: int | None
    end: int | None
    fused: float = 0.0
    tags: tuple[str, ...] = ()


@dataclass
class PackRecord:
    record_id: str
    docket: str
    ad_number: str | None
    make: str | None
    models: list[str]
    fr_citation: str | None
    pages: str | None
    sentences: list[SentenceIn]
    applicability: Applicability | None = None
    status: RecordStatus | None = None
    lineage: Lineage | None = None
    url: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    record_id: str
    idx: int
    text: str
    start: int | None
    end: int | None
    fused: float
    tags: tuple[str, ...]


@dataclass(frozen=True)
class ComputedFact:
    id: str  # F1, F2, ...
    kind: Literal["applicability", "status", "lineage"]
    record_id: str
    text: str
    refs: tuple[str, ...] = ()  # evidence ids / extraction ids the fact rests on


@dataclass
class EvidencePack:
    question: str
    evidence: list[EvidenceItem]
    facts: list[ComputedFact]
    text: str
    records: dict[str, PackRecord] = field(default_factory=dict)  # metadata for verification (H5) and citations

    @property
    def evidence_ids(self) -> set[str]:
        return {e.id for e in self.evidence}

    @property
    def fact_ids(self) -> set[str]:
        return {f.id for f in self.facts}


class ClaimOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    evidence_ids: list[str]
    quote: str | None
    fact_ids: list[str]


class SubmitAnswer(BaseModel):
    """Tool input of submit_answer. Counts are checked in Pydantic (strict tool schemas cannot carry them)."""

    model_config = ConfigDict(extra="forbid")
    cannot_answer: bool
    cannot_answer_reason: str | None
    claims: list[ClaimOut]
    rationale_steps: list[str] = Field(max_length=MAX_RATIONALE)


@dataclass
class GenerationResult:
    mode: Literal["llm", "extractive", "extractive_fallback"]
    answer: SubmitAnswer
    pack: EvidencePack
    llm: LLMResult | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ evidence pack


def esc_text(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def esc_attr(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _facts(records: list[PackRecord]) -> list[ComputedFact]:
    out: list[tuple[str, str, str, tuple[str, ...]]] = []
    for r in records:
        a = r.applicability
        if a is not None:
            refs = tuple(a.evidence_ids)
            text = f"{a.verdict} | {'; '.join(a.reasons)}" + (f" (evidence {', '.join(refs)})" if refs else "")
            out.append(("applicability", r.record_id, text, refs))
        st = r.status
        if st is not None:
            due = st.comments_due_effective
            period = f"comment period {st.comment_period}"
            if due:
                period += f" until {due}" if st.comment_period == "OPEN" else f" (closed {due})"
            text = f"PROPOSED; {period}"
            refs = tuple(w.extraction_id or "" for w in st.withdrawn_by if w.extraction_id)
            if st.withdrawn:
                text += f"; WITHDRAWN (withdrawal notice {', '.join(w.value for w in st.withdrawn_by)})"
            out.append(("status", r.record_id, text, refs))
        ln = r.lineage
        if ln is not None:
            for ref in ln.supersedes_ad:
                where = (
                    f"target in dataset: {', '.join(ref.target_record_ids)}"
                    if ref.target_in_dataset
                    else ("target not in dataset")
                )
                eid = (ref.extraction_id,) if ref.extraction_id else ()
                out.append(
                    (
                        "lineage",
                        r.record_id,
                        f"would supersede AD {ref.value} ({where}) (extraction {ref.extraction_id})",
                        eid,
                    )
                )
            for ref in ln.continues_ad:
                eid = (ref.extraction_id,) if ref.extraction_id else ()
                out.append(
                    (
                        "lineage",
                        r.record_id,
                        f"would continue to require actions of AD {ref.value} (extraction {ref.extraction_id})",
                        eid,
                    )
                )
            others = [x for x in ln.same_docket_group if x != r.record_id]
            if others:
                latest = ", ".join(ln.latest_in_docket_group) or "unknown"
                out.append(
                    (
                        "lineage",
                        r.record_id,
                        f"same docket {r.docket} as {', '.join(others)}; latest publication in the docket: {latest}",
                        (),
                    )
                )
            for ref in ln.corrections:
                out.append(
                    ("lineage", r.record_id, f"OFR correction involving {ref.value}", (ref.extraction_id or "",))
                )
    return [ComputedFact(f"F{i}", kind, rid, text, refs) for i, (kind, rid, text, refs) in enumerate(out, 1)]


def _select(records: list[PackRecord], limit: int) -> list[EvidenceItem]:
    """Round-robin across records (retrieval order). Within a record: engine anchor sentences first, then fused."""
    queues = []
    for r in records:
        ranked = sorted(r.sentences, key=lambda s: (not (set(s.tags) & ANCHOR_TAGS), -s.fused, s.idx))
        queues.append([EvidenceItem(s.id, r.record_id, s.idx, s.text, s.start, s.end, s.fused, s.tags) for s in ranked])
    chosen: list[EvidenceItem] = []
    while len(chosen) < limit and any(queues):
        for q in queues:
            if q and len(chosen) < limit:
                chosen.append(q.pop(0))
    order = {r.record_id: i for i, r in enumerate(records)}
    return sorted(chosen, key=lambda e: (order[e.record_id], e.idx))


def _short_makes(make: str | None, limit: int = 3) -> str:
    """'A | B | C | D | E' -> 'A | B | C | (+2 more)': multi-make records (R0012 lists 20) would bloat every <e>."""
    parts = [m for m in (make or "").split(" | ") if m]
    return " | ".join(parts[:limit] + ([f"(+{len(parts) - limit} more)"] if len(parts) > limit else []))


def _short_models(models: list[str], limit: int = 10) -> str:
    """Display list for the <e> attribute only; the full list stays on PackRecord for verification."""
    return ", ".join(models[:limit] + ([f"(+{len(models) - limit} more)"] if len(models) > limit else []))


def build_pack(question: str, records: list[PackRecord], max_sentences: int = MAX_SENTENCES) -> EvidencePack:
    evidence = _select(records, max_sentences)
    facts = _facts(records)
    by_id = {r.record_id: r for r in records}
    lines = ["<evidence>"]
    for e in evidence:
        r = by_id[e.record_id]
        attrs = (
            f'id="{esc_attr(e.id)}" docket="{esc_attr(r.docket)}" ad_number="{esc_attr(r.ad_number)}" '
            f'make="{esc_attr(_short_makes(r.make))}" models="{esc_attr(_short_models(r.models))}" '
            f'fr_citation="{esc_attr(r.fr_citation)}" pages="{esc_attr(r.pages)}"'
        )
        lines.append(f"<e {attrs}>{esc_text(e.text)}</e>")
    lines += ["</evidence>", "<computed_facts>"]
    lines += [f"{f.id} | {f.kind} | {f.record_id} | {esc_text(f.text)}" for f in facts]
    lines += ["</computed_facts>", f"<user_question>{esc_text(question)}</user_question>"]
    return EvidencePack(question, evidence, facts, "\n".join(lines), by_id)


# ------------------------------------------------------------------ validation against the pack

_WORDS = re.compile(r"\S+")


def pack_violations(answer: SubmitAnswer, pack: EvidencePack) -> str | None:
    """Hard rule violations that trigger the single retry (rule 5 structure, rule 8 count). None if fine."""
    problems: list[str] = []
    if answer.cannot_answer and not (answer.cannot_answer_reason or "").strip():
        problems.append("cannot_answer=true needs cannot_answer_reason")
    if len(answer.claims) > MAX_CLAIMS:
        problems.append(f"{len(answer.claims)} claims (max {MAX_CLAIMS})")
    for i, c in enumerate(answer.claims, 1):
        bad_e = [x for x in c.evidence_ids if x not in pack.evidence_ids]
        bad_f = [x for x in c.fact_ids if x not in pack.fact_ids]
        if bad_e or bad_f:
            problems.append(f"claim {i} cites unknown ids {bad_e + bad_f}")
        has_evidence = bool(c.evidence_ids and c.quote)
        if not has_evidence and not c.fact_ids:
            problems.append(f"claim {i} needs evidence_ids + quote, or fact_ids")
        if c.quote and not c.evidence_ids:
            problems.append(f"claim {i} has a quote but no evidence_ids")
    if not answer.cannot_answer and not 2 <= len(answer.rationale_steps) <= MAX_RATIONALE:
        problems.append(f"{len(answer.rationale_steps)} rationale steps (need 2-{MAX_RATIONALE})")
    return "; ".join(problems) or None


def style_warnings(answer: SubmitAnswer) -> list[str]:
    """Soft limits (rules 5 and 8): reported, not rejected. Verification (Prompt 9) decides what survives."""
    out = []
    for i, c in enumerate(answer.claims, 1):
        if len(_WORDS.findall(c.text)) > 30:
            out.append(f"claim {i} has more than 30 words")
        if c.quote and not 3 <= len(_WORDS.findall(c.quote)) <= 40:
            out.append(f"claim {i} quote is not 3-40 words")
    for i, s in enumerate(answer.rationale_steps, 1):
        if len(_WORDS.findall(s)) >= 25:
            out.append(f"rationale step {i} has 25+ words")
        if not re.search(r"\[[^\]]+\]\s*\.?\s*$", s):
            out.append(f"rationale step {i} does not end with [ids]")
    return out


# ------------------------------------------------------------------ extractive fallback (no LLM)


def extractive_answer(evidence: list[EvidenceItem], facts: list[ComputedFact], max_records: int = 3) -> SubmitAnswer:
    """For each of the top records: its most relevant sentence verbatim (quote = full sentence), then each
    computed fact as its own claim. Deterministic; no model involved."""
    record_order: list[str] = []
    for e in evidence:
        if e.record_id not in record_order:
            record_order.append(e.record_id)
    for f in facts:
        if f.record_id not in record_order:
            record_order.append(f.record_id)
    claims: list[ClaimOut] = []
    for rid in record_order[:max_records]:
        sentences = [e for e in evidence if e.record_id == rid and not e.id.endswith("#heading")]
        if sentences:
            best = max(sentences, key=lambda e: (e.fused, -e.idx))
            claims.append(ClaimOut(text=best.text, evidence_ids=[best.id], quote=best.text, fact_ids=[]))
        claims += [
            ClaimOut(text=f.text, evidence_ids=[], quote=None, fact_ids=[f.id]) for f in facts if f.record_id == rid
        ]
    if not claims:
        return SubmitAnswer(
            cannot_answer=True, cannot_answer_reason="No evidence was retrieved.", claims=[], rationale_steps=[]
        )
    return SubmitAnswer(cannot_answer=False, cannot_answer_reason=None, claims=claims, rationale_steps=[])


# ------------------------------------------------------------------ generation


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def generate(
    question: str,
    records: list[PackRecord],
    mode: Literal["answer", "search_only"] = "answer",
    client: LLMClient | None = None,
) -> GenerationResult:
    pack = build_pack(question, records)
    if mode == "search_only":
        return GenerationResult("extractive", extractive_answer(pack.evidence, pack.facts), pack)
    try:
        res = (client or get_client()).call_tool(
            purpose="generate",
            model_key="generation",
            system=system_prompt(),
            user=pack.text,
            tool_name="submit_answer",
            tool_description="Submit the grounded answer: claims with citations, and brief rationale steps.",
            output_model=SubmitAnswer,
            max_tokens_key="max_tokens_generation",
            extra_validator=lambda out: pack_violations(out, pack),
        )
    except LLMError as exc:
        return GenerationResult(
            "extractive_fallback", extractive_answer(pack.evidence, pack.facts), pack, error=str(exc)
        )
    answer: SubmitAnswer = res.output  # type: ignore[assignment]
    return GenerationResult("llm", answer, pack, res, None, style_warnings(answer))


# ------------------------------------------------------------------ wiring from retrieval + engine


def pack_records_from_retrieval(retriever: Any, result: Any, cfg: Any, k: int = 3) -> list[PackRecord]:
    """Top-k retrieved records with their evidence sentences and engine outputs (Prompt 10 reuses this)."""
    from backend.app.engine.applicability import evaluate
    from backend.app.engine.status import lineage, record_status

    out = []
    for hit in result.records[:k]:
        rid = hit.record_id
        docket, ad, make, fr, cit, pages, url = retriever.conn.execute(
            "SELECT docket, ad_number, make_canonical, fr_citation, citation_text, pages, url "
            "FROM records WHERE id = ?",
            (rid,),
        ).fetchone()
        rec = retriever.engine.records[rid]
        sentences = [
            SentenceIn(
                s.sentence_id,
                -1 if s.start is None else int(s.sentence_id.rsplit("#s", 1)[-1]),
                s.text,
                s.start,
                s.end,
                s.local or s.fused,
                tuple(s.tags),
            )
            for s in hit.sentences
        ]
        out.append(
            PackRecord(
                rid,
                docket,
                ad,
                make,
                sorted(rec.models),  # full list: verification grounds designators against it
                fr or cit,
                pages,
                sentences,
                evaluate(cfg, rec),
                record_status(rec, retriever.engine, cfg.as_of),
                lineage(rec, retriever.engine),
                url,
            )
        )
    return out


def main(argv: list[str] | None = None) -> None:
    from datetime import date

    from backend.app.config import repo_path
    from backend.app.engine.explain import link_model, resolve_make
    from backend.app.engine.types import LinkedConfig
    from backend.app.retrieval.retriever import Filters, Retriever

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question")
    p.add_argument("--make")
    p.add_argument("--model")
    p.add_argument("--serial")
    p.add_argument("--as-of")
    p.add_argument("--mode", choices=["answer", "search_only"], default="answer")
    p.add_argument("-k", type=int, default=3, help="records in the evidence pack")
    p.add_argument("--db", type=Path, default=repo_path("sqlite_path"))
    args = p.parse_args(argv)
    r = Retriever(args.db)
    make = resolve_make(args.db, args.make)
    model_norm, fam = link_model(r.engine, args.model)
    cfg = LinkedConfig(
        make, model_norm, fam, args.serial, date.fromisoformat(args.as_of) if args.as_of else date.today()
    )
    result = r.retrieve(args.question, Filters(make=make, model=model_norm, family=fam if not model_norm else None))
    gen = generate(args.question, pack_records_from_retrieval(r, result, cfg, args.k), args.mode)
    print("=" * 30, "EVIDENCE PACK (exactly as sent)", "=" * 30)
    print(gen.pack.text)
    print("=" * 30, f"ANSWER  mode={gen.mode}", "=" * 30)
    if gen.mode != "llm":
        label = (
            "search-only: extractive"
            if gen.mode == "extractive"
            else f"LLM unavailable -> extractive fallback ({gen.error})"
        )
        print(f"[{label}] sentences are quoted verbatim; no model-written summary")
    print(json.dumps(gen.answer.model_dump(), indent=2))
    if gen.llm:
        print(
            f"\n{gen.llm.model}: tokens in/out {gen.llm.input_tokens}/{gen.llm.output_tokens}, est. cost "
            f"${gen.llm.cost_usd:.5f}, cached={gen.llm.cached}, {gen.llm.latency_ms:.0f} ms"
        )
    if gen.warnings:
        print("style warnings:", gen.warnings)


if __name__ == "__main__":
    main()
