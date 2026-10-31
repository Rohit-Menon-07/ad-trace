"""End-to-end orchestrator S1-S8 (SPEC section 6). Code decides; the LLM only parses, phrases and audits.

S1 parse (Haiku; rule-based fallback if unavailable) -> link (H8)
S2 clarification + pre-retrieval gates (empty, injection, out of scope, entities, premises)
S3 retrieval with engine-consistent hard filters
S4 engine verdict/status/lineage per record; NOT_APPLICABLE records move to `excluded`
S5 post-retrieval gates: NO_RETRIEVAL_HIT, EMPTY_SOURCE_TEXT, LOW_RETRIEVAL_SCORE, APPLICABILITY_UNDETERMINED
S6 evidence pack + generation (Sonnet), or extractive (search_only / generation off / LLM error)
S7 verification (H4/H5/H6); verifier error -> extractive fallback
S8 SearchResponse + one audit line in logs/audit.jsonl
Every stage appends a code-built TraceStep. LLM failures never raise out of run(): they degrade with a warn step.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.config import load_config, repo_path, resolve_as_of
from backend.app.llm.client import LLMClient, LLMError, LLMResult, get_client
from backend.app.pipeline.gates import (
    GateDecision,
    gate_empty_source,
    gate_no_hit,
    refuse,
    run_pre_retrieval_gates,
)
from backend.app.pipeline.generate import (
    GenerationResult,
    PackRecord,
    extractive_answer,
    generate,
    pack_records_from_retrieval,
)
from backend.app.pipeline.linker import LinkedQuery, Linker, UIFields, link_query
from backend.app.pipeline.query import ParsedQuery, parse_query, rule_based_parse
from backend.app.pipeline.records_api import record_card
from backend.app.pipeline.verify import VerificationReport, to_api_claims, verify
from backend.app.retrieval.retriever import Filters, RetrievalResult, Retriever
from backend.app.schemas import (
    ApplicabilityResult,
    ExcludedRecord,
    SearchRequest,
    SearchResponse,
    TraceStep,
)

DISCLAIMER = (
    "Decision support only. Verify against the Federal Register notice before acting. "
    "All records are proposed rulemaking (NPRM) and are not in force."
)
MAX_EXCLUDED_PER_FILTER = 20


@dataclass
class Options:
    """Ablation switches (eval code only; the API uses config.yaml)."""

    generation: bool | None = None
    verify_layers: dict[str, bool] | None = None
    retrieval_mode: str | None = None
    low_retrieval: dict[str, float] | None = None
    audit: bool = True
    # False = "no engine" variants (B1-B3, S0, S1): no gates, no hard filters (make/model are appended to the query
    # text as a keyword-search user would type them), no verdicts and no computed facts.
    engine: bool = True
    llm_parser: bool = True  # False = rule-based parse only (no-LLM baselines)


@dataclass
class Run:
    """Mutable state of one request; also the source of the audit record."""

    request_id: str
    req: SearchRequest
    t0: float
    trace: list[TraceStep] = field(default_factory=list)
    stage_ms: dict[str, float] = field(default_factory=dict)
    llm: list[dict[str, Any]] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)
    retrieval_ms: float | None = None

    def step(self, stage: str, status: str, summary: str, started: float, **details: Any) -> None:
        ms = (time.perf_counter() - started) * 1000
        self.stage_ms[stage] = round(ms, 1)
        self.trace.append(
            TraceStep(
                stage=stage,
                status=status,
                summary=summary,
                details=_jsonable(details),  # type: ignore[arg-type]
                ms=int(round(ms)),
            )
        )

    def record_llm(self, purpose: str, res: LLMResult | None) -> None:
        if res is not None:
            self.llm.append(
                {
                    "purpose": purpose,
                    "model": res.model,
                    "input_tokens": res.input_tokens,
                    "output_tokens": res.output_tokens,
                    "cost_usd": res.cost_usd,
                    "cached": res.cached,
                    "latency_ms": round(res.latency_ms, 1),
                    "fake": res.request_id == "fake",
                }
            )


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))


def _link_summary(linked: LinkedQuery) -> str:
    src = {"ui": "UI field", "parsed": "parsed from the question"}
    mk, md = linked.make, linked.model
    parts = []
    if mk.status == "accepted":
        parts.append(f"Linked make '{mk.canonical}' ({src.get(mk.source or '', '')}).")
    elif mk.status != "absent":
        parts.append(f"Make '{mk.text}' {mk.status}.")
    if md.status == "accepted":
        parts.append(f"Linked model {md.model_norm} (exact, {src.get(md.source or '', '')}).")
    elif md.status == "ambiguous_family":
        parts.append(f"Model '{md.text}' is a family ({len(md.options)} variants).")
    elif md.status != "absent":
        parts.append(f"Model '{md.text}' {md.status}.")
    if linked.serial:
        parts.append(f"Serial {linked.serial} ({src.get(linked.serial_source or '', '')}).")
    return " ".join(parts) or "No make, model or serial given."


class Pipeline:
    def __init__(
        self,
        db_path: Path,
        retriever: Retriever | None = None,
        client: LLMClient | None = None,
        audit_path: Path | None = None,
    ) -> None:
        self.retriever = retriever or Retriever(db_path)
        self.linker = Linker.from_db(db_path, with_engine=False)
        self.linker.engine_index = self.retriever.engine
        self.client = client
        self.audit_path = audit_path or repo_path("audit_log", section="logging")

    # ------------------------------------------------------------ helpers

    def _client(self) -> LLMClient:
        return self.client or get_client()

    def _finish(
        self,
        run: Run,
        status: str,
        reason_code: str | None,
        message: str,
        *,
        claims: list | None = None,
        rationale: list[str] | None = None,
        records: list | None = None,
        applicability: list | None = None,
        excluded: list | None = None,
        options: list[str] | None = None,
        opts: Options | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        total_ms = (time.perf_counter() - run.t0) * 1000
        run.step(
            "S8 Render + audit",
            "ok",
            f"Response assembled ({status}{', ' + reason_code if reason_code else ''}); "
            f"audit record {run.request_id} written.",
            started,
            end_to_end_ms=round(total_ms, 1),
            retrieval_ms=run.retrieval_ms,
            stage_ms=run.stage_ms,
            llm_cost_usd=round(sum(c["cost_usd"] for c in run.llm), 6),
        )
        resp = SearchResponse(
            request_id=run.request_id,
            status=status,
            reason_code=reason_code,
            message=message,  # type: ignore[arg-type]
            claims=claims or [],
            rationale_steps=rationale or [],
            records=records or [],
            applicability=applicability or [],
            excluded=excluded or [],
            clarification_options=options or [],
            trace=run.trace,
            disclaimer=DISCLAIMER,
            as_of=run.req.as_of or resolve_as_of(),
            latency_ms=int(round(total_ms)),
            # LLM_MODE=fake: a canned FAKE output wrote or checked the answer, so the response is labelled MOCK.
            mock=any(c.get("fake") and c["purpose"] in ("generate", "verify") for c in run.llm),
        )
        if opts is None or opts.audit:
            self._write_audit(run, resp, total_ms)
        return resp

    def _write_audit(self, run: Run, resp: SearchResponse, total_ms: float) -> None:
        cfg = load_config()["models"]
        entry = {
            "request_id": run.request_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "request": run.req.model_dump(mode="json"),
            **run.audit,
            "status": resp.status,
            "reason_code": resp.reason_code,
            "message": resp.message,
            "claims": [c.model_dump(mode="json") for c in resp.claims],
            "rationale_steps": resp.rationale_steps,
            "model_ids": {
                "generation": cfg["generation"],
                "query_parser": cfg["query_parser"],
                "verifier": cfg["verifier"],
            },
            "llm_calls": run.llm,
            "tokens_in": sum(c["input_tokens"] for c in run.llm),
            "tokens_out": sum(c["output_tokens"] for c in run.llm),
            "cost_usd": round(sum(c["cost_usd"] for c in run.llm), 6),
            "latency_ms": {"end_to_end": round(total_ms, 1), "retrieval": run.retrieval_ms, "stages": run.stage_ms},
            "trace": [t.model_dump(mode="json") for t in resp.trace],
        }
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    # ------------------------------------------------------------ main entry

    def run(self, req: SearchRequest, opts: Options | None = None) -> SearchResponse:
        opts = opts or Options()
        cfg = load_config()
        run = Run(f"req_{uuid.uuid4().hex[:12]}", req, time.perf_counter())
        as_of = req.as_of or resolve_as_of()
        query = (req.query or "").strip()

        # ---------------- S1 query understanding + linking
        t = time.perf_counter()
        parsed: ParsedQuery | None = None
        parse_source, parse_error = "none (empty query)", None
        if query and not opts.llm_parser:
            parsed, parse_source = rule_based_parse(query), "rule-based (no-LLM variant)"
        elif query:
            try:
                res = parse_query(query, self._client())
                parsed = res.output  # type: ignore[assignment]
                parse_source = res.model
                run.record_llm("parse_query", res)
            except LLMError as exc:
                parsed, parse_source, parse_error = rule_based_parse(query), "rule-based fallback", str(exc)
        linked = link_query(parsed, UIFields(req.make, req.model, req.serial, as_of), self.linker)
        run.audit |= {
            "parsed": parsed.model_dump() if parsed else None,
            "parse_source": parse_source,
            "parse_error": parse_error,
            "linked": linked.summary(),
        }
        prefix = f"Parsed by {parse_source}." if not parse_error else "Parser LLM unavailable: rule-based parse used."
        run.step(
            "S1 Query understanding",
            "warn" if parse_error else "ok",
            f"{prefix} {_link_summary(linked)}",
            t,
            intent=getattr(parsed, "intent", None),
            parse_source=parse_source,
            parse_error=parse_error,
            make=linked.make.canonical,
            model=linked.model.model_norm,
            serial=linked.serial,
        )

        # ---------------- S2 clarification + pre-retrieval gates
        t = time.perf_counter()
        decision = run_pre_retrieval_gates(query, parsed, linked, self.linker) if opts.engine else GateDecision(False)
        run.step(
            "S2 Clarification + pre-retrieval gates",
            "stop" if decision.stop else "ok",
            decision.message
            if decision.stop
            else "No gate stopped the request (checked: empty query, "
            "injection, out of scope, entity linking, false premises).",
            t,
            reason_code=decision.reason_code,
            **decision.details,
        )
        if decision.stop:
            run.audit["gate"] = decision.as_dict()
            return self._finish(
                run,
                decision.status or "refused",
                decision.reason_code,
                decision.message,
                options=decision.options,
                opts=opts,
            )

        # ---------------- S3 retrieval
        t = time.perf_counter()
        lc = linked.to_config()
        filters = Filters(
            make=lc.make_canonical, model=lc.model_norm, date_from=linked.date_from, date_to=linked.date_to
        )
        retrieval_text = query or " ".join(x for x in (lc.make_canonical, lc.model_norm) if x)
        if not opts.engine:  # keyword-search baseline: no linking-based filters; typed fields become query words
            filters = Filters()
            retrieval_text = " ".join(x for x in (query, req.make, req.model, req.serial) if x)
        mode = opts.retrieval_mode or cfg["retrieval"].get("mode", "hybrid")
        result = self.retriever.retrieve(retrieval_text, filters, mode)  # type: ignore[arg-type]
        run.retrieval_ms = result.timings_ms["total"]
        removed = sum(f.removed for f in result.filters if f.name != "duplicates")
        top = result.features.get("top_fused") or 0.0
        run.audit |= {
            "filters": [{"name": f.name, "value": f.value, "removed": f.removed} for f in result.filters],
            "retrieved": [{"record_id": h.record_id, "score": h.score} for h in result.records],
            "retrieval_features": result.features,
            "fts_query": result.fts_query,
            "retrieval_mode": mode,
        }
        run.step(
            "S3 Retrieval",
            "ok" if result.records else "stop",
            f"Hard filters removed {removed} of {result.candidates_before} records. {mode} retrieval returned "
            f"{len(result.records)} records; top fused score {top:.3f}.",
            t,
            filters=run.audit["filters"],
            features=result.features,
            timings_ms=result.timings_ms,
            records=run.audit["retrieved"],
            embedding_backend=result.embedding_backend,
        )
        excluded = self._filter_exclusions(result)
        no_hit = gate_no_hit([h.record_id for h in result.records])
        if no_hit.stop:
            return self._finish(run, "refused", no_hit.reason_code, no_hit.message, excluded=excluded, opts=opts)

        # ---------------- S4 engine
        t = time.perf_counter()
        pack_all = pack_records_from_retrieval(self.retriever, result, lc, k=len(result.records))
        if not opts.engine:  # no verdicts, status or lineage: the pack carries evidence sentences only
            for p in pack_all:
                p.applicability = p.status = p.lineage = None
        verdicts = Counter(p.applicability.verdict for p in pack_all if p.applicability)
        remaining = [p for p in pack_all if not (p.applicability and p.applicability.verdict == "NOT_APPLICABLE")]
        for p in pack_all:
            if p.applicability and p.applicability.verdict == "NOT_APPLICABLE":
                subject = self.retriever.meta[p.record_id][2]
                excluded.insert(
                    0,
                    ExcludedRecord(
                        record_id=p.record_id,
                        docket=p.docket,
                        subject_heading=subject,
                        rule=f"S4.{p.applicability.rule}",
                        reason=p.applicability.reasons[-1],
                    ),
                )
        applicability = [
            ApplicabilityResult(
                record_id=p.record_id,
                verdict=p.applicability.verdict,
                reasons=list(p.applicability.reasons),
                evidence_ids=list(p.applicability.evidence_ids),
            )
            for p in pack_all
            if p.applicability
        ]
        records = [
            record_card(
                self.retriever.conn,
                self.retriever.engine,
                p.record_id,
                as_of,
                next(h.score for h in result.records if h.record_id == p.record_id),
            )
            for p in remaining
        ]
        counts = ", ".join(f"{n} {v}" for v, n in sorted(verdicts.items()))
        na = verdicts.get("NOT_APPLICABLE", 0)
        run.step(
            "S4 Applicability + revision",
            "ok",
            f"Engine verdicts: {counts}." + (f" {na} NOT_APPLICABLE record(s) moved to 'not shown'." if na else ""),
            t,
            verdicts=dict(verdicts),
            rules={p.record_id: p.applicability.rule for p in pack_all if p.applicability},
        )
        run.audit["engine"] = [
            {
                "record_id": p.record_id,
                "verdict": p.applicability.verdict,
                "rule": p.applicability.rule,
                "reasons": list(p.applicability.reasons),
            }
            for p in pack_all
            if p.applicability
        ]

        # ---------------- S5 post-retrieval gates
        t = time.perf_counter()
        decision = (
            self._post_gates(remaining, result, mode, parsed, lc, opts, cfg) if opts.engine else GateDecision(False)
        )
        run.step(
            "S5 Abstention gates",
            "stop" if decision.stop else "ok",
            decision.message
            if decision.stop
            else "No gate stopped the request (checked: no remaining records, "
            "empty source text, low retrieval score, all applicability undetermined).",
            t,
            reason_code=decision.reason_code,
            **decision.details,
        )
        if decision.stop:
            return self._finish(
                run,
                "refused",
                decision.reason_code,
                decision.message,
                records=records,
                applicability=applicability,
                excluded=excluded,
                opts=opts,
            )

        # ---------------- S6 generation
        t = time.perf_counter()
        pack_records = remaining[: int(cfg["generation"].get("pack_records", 4))]
        gen_on = cfg["generation"].get("enabled", True) if opts.generation is None else opts.generation
        question = query or retrieval_text
        if req.mode == "search_only" or not gen_on:
            gen = generate(question, pack_records, "search_only")
            why = "search_only" if req.mode == "search_only" else "generation disabled"
            run.step(
                "S6 Generation",
                "ok",
                f"Generation skipped ({why}): extractive answer from the top records.",
                t,
                answer_mode=gen.mode,
                evidence_sentences=len(gen.pack.evidence),
                facts=len(gen.pack.facts),
            )
        else:
            gen = generate(question, pack_records, "answer", self._client())
            run.record_llm("generate", gen.llm)
            if gen.mode == "llm":
                run.step(
                    "S6 Generation",
                    "ok",
                    f"{len(gen.answer.claims)} claims and {len(gen.answer.rationale_steps)} "
                    f"rationale steps from {len(gen.pack.evidence)} evidence sentences and {len(gen.pack.facts)} "
                    "computed facts.",
                    t,
                    answer_mode=gen.mode,
                    style_warnings=gen.warnings,
                )
            else:
                run.step(
                    "S6 Generation",
                    "warn",
                    "Answer writer unavailable: extractive answer used instead.",
                    t,
                    answer_mode=gen.mode,
                    error=gen.error,
                )
        run.audit |= {
            "evidence_pack": gen.pack.text,
            "computed_facts": [f.__dict__ for f in gen.pack.facts],
            "generation": {"mode": gen.mode, "error": gen.error, "raw_output": gen.answer.model_dump()},
        }

        # ---------------- S7 verification
        t = time.perf_counter()
        gen, report = self._verify(gen, opts, run)
        c = report.counts
        status, reason_code, message = self._status(report, gen, records, applicability, lc)
        scope = (
            "" if gen.mode == "llm" else "Deterministic layers only (verbatim extractive answer, no model wording). "
        )
        run.step(
            "S7 Verification",
            "ok" if status == "answered" else "warn",
            f"{scope}Claims {c['proposed']} proposed, {c['kept']} kept (dropped: quotes {c['dropped_quotes']}, "
            f"grounding {c['dropped_grounding']}, verifier {c['dropped_llm']}). Rationale {c['rationale_kept']}/"
            f"{c['rationale_proposed']} steps kept.",
            t,
            claims_in=c["proposed"],
            dropped_quotes=c["dropped_quotes"],
            dropped_grounding=c["dropped_grounding"],
            dropped_llm=c["dropped_llm"],
            claims_dropped=report.removed,
            dropped=[
                {
                    "claim": c.claim.text,
                    "layer": c.dropped_by,
                    "reasons": {"quotes": c.quotes, "grounding": c.grounding, "llm": c.verifier}[c.dropped_by].reasons,
                }
                for c in report.claims
                if c.dropped_by
            ],  # fmt: skip
            layers=report.layers,
            verifier_error=report.verifier_error,
            answer_mode=gen.mode,
        )
        run.audit["verification"] = _report_dict(report)
        claims = to_api_claims(report, gen.pack)
        return self._finish(
            run,
            status,
            reason_code,
            message,
            claims=claims,
            rationale=report.rationale_steps,
            records=records,
            applicability=applicability,
            excluded=excluded,
            opts=opts,
        )

    # ------------------------------------------------------------ stages

    def _filter_exclusions(self, result: RetrievalResult) -> list[ExcludedRecord]:
        out = []
        for f in result.filters:
            if f.name == "duplicates":
                continue
            for rid in f.removed_ids[:MAX_EXCLUDED_PER_FILTER]:
                out.append(
                    ExcludedRecord(
                        record_id=rid,
                        docket=self.retriever.engine.records[rid].docket,
                        subject_heading=self.retriever.meta[rid][2],
                        rule=f"S3.hard_filter.{f.name}",
                        reason=f.reason,
                    )
                )
            if f.removed > MAX_EXCLUDED_PER_FILTER:
                out.append(
                    ExcludedRecord(
                        record_id=f"+{f.removed - MAX_EXCLUDED_PER_FILTER}",
                        docket="",
                        subject_heading=f"{f.removed - MAX_EXCLUDED_PER_FILTER} more records",
                        rule=f"S3.hard_filter.{f.name}",
                        reason=f.reason,
                    )
                )
        return out

    def _post_gates(
        self,
        remaining: list[PackRecord],
        result: RetrievalResult,
        mode: str,
        parsed: Any,
        lc: Any,
        opts: Options,
        cfg: dict[str, Any],
    ) -> GateDecision:
        if not remaining:
            return refuse(
                "NO_RETRIEVAL_HIT",
                "Records matched your search, but the rules found that none of them "
                "applies to your configuration. They are listed under 'Not shown and why'.",
            )
        summary_missing = {
            rid for rid, (_, _, _) in self.retriever.meta.items() if not self.retriever.by_record.get(rid)
        }
        empty = gate_empty_source([(p.record_id, p.record_id in summary_missing) for p in remaining])
        if empty.stop:
            return empty
        th = opts.low_retrieval or cfg["thresholds"].get("low_retrieval", {})
        if result.features.get("tier0_records") in (None, 0):
            cos, bm = result.features.get("top_cosine"), result.features.get("top_bm25_norm")
            weak_cos = cos is None or cos < th.get("min_top_cosine", 0)
            weak_bm = bm is None or bm < th.get("min_top_bm25_norm", 0)
            low = {"dense": weak_cos, "bm25": weak_bm}.get(mode, weak_cos and weak_bm)
            if low:
                return refuse(
                    "LOW_RETRIEVAL_SCORE",
                    "The closest records match your question only weakly, so I did "
                    "not answer from them. Try the system or component name used in the notice, or choose "
                    "the aircraft make and model.",
                    top_cosine=cos,
                    top_bm25_norm=bm,
                    thresholds=th,
                )
        asked_applicability = getattr(parsed, "intent", None) == "applicability" or bool(lc.serial)
        verdicts = {p.applicability.verdict for p in remaining if p.applicability}
        if asked_applicability and verdicts == {"UNDETERMINED"}:
            return refuse(
                "APPLICABILITY_UNDETERMINED",
                "Records were found, but none of them lets the rules decide "
                "whether it applies to your aircraft (for example, applicability depends on serial numbers "
                "or service information the summaries do not list). See each record's reasons below.",
            )
        return GateDecision(False)

    def _verify(self, gen: GenerationResult, opts: Options, run: Run) -> tuple[GenerationResult, VerificationReport]:
        report = verify(gen.answer, gen.pack, self._client(), opts.verify_layers, extractive=gen.mode != "llm")
        run.record_llm("verify", report.verifier)
        if gen.mode == "llm" and report.verifier_error:
            ans = extractive_answer(gen.pack.evidence, gen.pack.facts)
            gen = GenerationResult("extractive_fallback", ans, gen.pack, gen.llm, f"verifier: {report.verifier_error}")
            report = verify(ans, gen.pack, self._client(), opts.verify_layers, extractive=True)
        return gen, report

    @staticmethod
    def _status(
        report: VerificationReport, gen: GenerationResult, records: list, applicability: list, lc: Any
    ) -> tuple[str, str | None, str]:
        fallback = gen.mode == "extractive_fallback"
        lead = (
            "The answer writer was unavailable, so the statements below are quoted verbatim from the records. "
            if fallback
            else ""
        )
        if report.model_cannot_answer:
            return (
                "refused",
                "NO_RETRIEVAL_HIT",
                f"The records found do not answer this question: {report.cannot_answer_reason}",
            )
        if report.status == "refused":
            return "refused", report.reason_code, report.message
        v = Counter(a.verdict for a in applicability)
        target = lc.model_norm or lc.make_canonical
        verdict_txt = (
            f" For {target}: {v.get('APPLICABLE', 0)} applicable, {v.get('UNDETERMINED', 0)} undetermined, "
            f"{v.get('NOT_APPLICABLE', 0)} not applicable."
            if target
            else ""
        )
        if report.status == "partial":
            return "partial", None, f"{lead}{report.message}{verdict_txt}"
        n = len(report.kept)
        return (
            "answered",
            None,
            f"{lead}{n} verified statement{'s' if n != 1 else ''} from {len(records)} record(s).{verdict_txt}",
        )


def _report_dict(report: VerificationReport) -> dict[str, Any]:
    return {
        "layers": report.layers,
        "counts": report.counts,
        "status": report.status,
        "reason_code": report.reason_code,
        "verifier_error": report.verifier_error,
        "claims": [
            {
                "index": c.index,
                "text": c.claim.text,
                "kept": c.kept,
                "dropped_by": c.dropped_by,
                "quotes": c.quotes.__dict__,
                "grounding": c.grounding.__dict__,
                "verifier": c.verifier.__dict__,
                "span": c.span,
            }
            for c in report.claims
        ],
        "rationale": [r.__dict__ for r in report.rationale],
    }


# ------------------------------------------------------------------ module-level singleton for the API

_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline(repo_path("sqlite_path"))
    return _pipeline


def set_pipeline(p: Pipeline | None) -> None:
    global _pipeline
    _pipeline = p


def run_search(request: SearchRequest, opts: Options | None = None) -> SearchResponse:
    return get_pipeline().run(request, opts)


def find_audit(request_id: str, path: Path | None = None) -> dict[str, Any] | None:
    p = path or repo_path("audit_log", section="logging")
    if not p.exists():
        return None
    for line in reversed(p.read_text(encoding="utf-8").splitlines()):
        if f'"request_id": "{request_id}"' in line:
            return json.loads(line)
    return None
