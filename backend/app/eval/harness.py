"""Evaluation harness: systems B1-B3, S0-S2 on the same pipeline; metrics with n and bootstrap CIs; reports.

    python -m backend.app.eval dev      # dev split only; tunes LOW_RETRIEVAL_SCORE thresholds (nothing else)
    python -m backend.app.eval freeze   # hashes cases + manual decisions + config; records thresholds
    python -m backend.app.eval test     # refuses if cases changed since freeze; writes results.json + docs/EVAL.md

Cost is projected first and EVAL_MAX_USD (default 8) is enforced. Systems whose generator cannot run (no valid key)
fall back to extractive answers; their answer-quality metrics are then reported as NOT MEASURED, never estimated.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from backend.app.config import ROOT, load_config, repo_path
from backend.app.engine.applicability import evaluate
from backend.app.engine.types import LinkedConfig
from backend.app.eval.cases import CASES_PATH, EVAL_DIR, load_cases, manual_decisions, sha256
from backend.app.extract.models import family, norm_model
from backend.app.pipeline.run import Options, Pipeline
from backend.app.schemas import EvalResults, EvalSet, FailureCase, MetricDef, MetricRow, SearchRequest

FREEZE_PATH = EVAL_DIR / "freeze.json"
THRESHOLDS_PATH = EVAL_DIR / "thresholds.json"
RESULTS_PATH = EVAL_DIR / "results.json"
DETAIL_PATH = EVAL_DIR / "results_detail.json"
AUDIT_CSV = EVAL_DIR / "claim_audit.csv"
EVAL_MD = ROOT / "docs" / "EVAL.md"
REFUSING = {"refused", "needs_clarification"}
BOOT = 1000
RNG_SEED = 7


@dataclass(frozen=True)
class System:
    key: str
    label: str
    opts: Options
    uses_llm: bool


def systems(low_retrieval: dict[str, float] | None) -> list[System]:
    off = {"quotes": False, "grounding": False, "llm": False}
    det = {"quotes": True, "grounding": True, "llm": False}
    base = dict(audit=False, low_retrieval=low_retrieval)
    return [
        System(
            "B1",
            "B1 BM25 + extractive (keyword search, no LLM, no engine)",
            Options(engine=False, generation=False, retrieval_mode="bm25", llm_parser=False, verify_layers=det, **base),
            False,
        ),
        System(
            "B2",
            "B2 dense + extractive (no LLM, no engine)",
            Options(
                engine=False, generation=False, retrieval_mode="dense", llm_parser=False, verify_layers=det, **base
            ),
            False,
        ),
        System(
            "B3",
            "B3 hybrid + extractive (no LLM, no engine)",
            Options(
                engine=False, generation=False, retrieval_mode="hybrid", llm_parser=False, verify_layers=det, **base
            ),
            False,
        ),
        System(
            "S0",
            "S0 hybrid + generation, no verification, no engine (naive RAG)",
            Options(engine=False, generation=True, llm_parser=False, verify_layers=off, **base),
            True,
        ),
        System(
            "S1",
            "S1 = S0 + quote and grounding checks",
            Options(engine=False, generation=True, llm_parser=False, verify_layers=det, **base),
            True,
        ),
        System(
            "S2",
            "S2 full system: engine, gates, clarification, generation, all verification layers",
            Options(engine=True, generation=True, llm_parser=True, **base),
            True,
        ),
    ]


# ------------------------------------------------------------------ cost and LLM availability


def llm_available() -> tuple[bool, str]:
    from backend.app.llm.client import load_env_files

    if os.environ.get("LLM_MODE", "").lower() == "fake":
        return True, "FAKE LLM (LLM_MODE=fake): answers are canned, not model output"
    load_env_files()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key.startswith("sk-ant-") and not re.search(r"\s", key):
        return True, "Anthropic API key present"
    return False, "no valid ANTHROPIC_API_KEY: generation, verifier, parser and judge fall back or are skipped"


def projected_cost(n_cases: int, available: bool) -> float:
    """Upper-bound estimate per case: S0 generation (S1 reuses its cached call), S2 parse + generation + verify,
    plus an LLM-judge call per audited claim (<= 3 per case)."""
    if not available or os.environ.get("LLM_MODE", "").lower() == "fake":
        return 0.0
    price = load_config()["llm"]["pricing_usd_per_mtok"]
    sonnet, haiku = price["claude-sonnet-5-5"], price["claude-haiku-5-5"]
    gen = 4500 / 1e6 * sonnet[0] + 900 / 1e6 * sonnet[1]
    small = 1500 / 1e6 * haiku[0] + 400 / 1e6 * haiku[1]
    judge = 3 * (600 / 1e6 * sonnet[0] + 150 / 1e6 * sonnet[1])
    return round(n_cases * (2 * gen + 2 * small + judge), 2)


# ------------------------------------------------------------------ running


def run_case(pipe: Pipeline, sysd: System, c: dict[str, Any]) -> dict[str, Any]:
    cfg = c["config"]
    req = SearchRequest(
        query=c["query"],
        make=cfg["make"],
        model=cfg["model"],
        serial=cfg["serial"],
        as_of=date.fromisoformat(cfg["as_of"]),
    )
    r = pipe.run(req, sysd.opts)
    stages = {t.stage[:2]: t for t in r.trace}
    s3, s6, s7, s8 = (stages.get(k) for k in ("S3", "S6", "S7", "S8"))
    return {
        "id": c["id"],
        "category": c["category"],
        "status": r.status,
        "reason_code": r.reason_code,
        "message": r.message,
        "request_id": r.request_id,
        "retrieved": [x["record_id"] for x in s3.details["records"]] if s3 else [],
        "shown": [x.record_id for x in r.records],
        "applicability": {a.record_id: a.verdict for a in r.applicability},
        "claims": [
            {
                "text": cl.text,
                "evidence_ids": [ci.evidence_id for ci in cl.citations],
                "quotes": [ci.quote for ci in cl.citations],
            }
            for cl in r.claims
        ],
        "answer_mode": s6.details.get("answer_mode") if s6 else None,
        "s7": {
            k: s7.details.get(k)
            for k in ("claims_in", "claims_dropped", "dropped_quotes", "dropped_grounding", "dropped_llm")
        }
        if s7
        else None,
        "retrieval_ms": s3.details["timings_ms"]["total"] if s3 else None,
        "e2e_ms": r.latency_ms,
        "cost_usd": (s8.details.get("llm_cost_usd") if s8 else 0.0) or 0.0,
        "excluded": [(e.record_id, e.rule) for e in r.excluded if not e.record_id.startswith("+")],
    }


def run_all(pipe: Pipeline, cases: list[dict[str, Any]], syss: list[System]) -> dict[str, list[dict[str, Any]]]:
    return {s.key: [run_case(pipe, s, c) for c in cases] for s in syss}


# ------------------------------------------------------------------ metrics


def recall_at(c: dict[str, Any], o: dict[str, Any], k: int = 5) -> float:
    exp = set(c["expected"]["expected_record_ids"])
    return len(exp & set(o["retrieved"][:k])) / min(len(exp), k)


def rr(c: dict[str, Any], o: dict[str, Any]) -> float:
    exp = set(c["expected"]["expected_record_ids"])
    return next((1.0 / (i + 1) for i, rid in enumerate(o["retrieved"]) if rid in exp), 0.0)


def retrieval_case(c: dict[str, Any]) -> bool:
    return bool(c["expected"]["expected_record_ids"]) and c["expected"]["status"] not in REFUSING


def boot_ci(values: list[float], seed: int = RNG_SEED) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = arr[rng.integers(0, len(arr), size=(BOOT, len(arr)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def prf(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    tp = sum(s and d for s, d in pairs)
    fp = sum((not s) and d for s, d in pairs)
    fn = sum(s and not d for s, d in pairs)
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn, "n": len(pairs)}


def refusal_metrics(cases: list[dict[str, Any]], outs: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [(c, o) for c, o in zip(cases, outs, strict=True) if c["expected"]["status"] is not None]
    pairs = [(c["expected"]["status"] in REFUSING, o["status"] in REFUSING) for c, o in rows]
    m = prf(pairs)
    f1_samples = []
    rng = random.Random(RNG_SEED)
    for _ in range(BOOT):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        f1_samples.append(prf(sample)["f1"] or 0.0)
    m["f1_ci"] = (
        (float(np.percentile(f1_samples, 2.5)), float(np.percentile(f1_samples, 97.5))) if pairs else (None, None)
    )
    both = [(c, o) for c, o in rows if c["expected"]["status"] in REFUSING and o["status"] in REFUSING]
    m["reason_code_accuracy"] = (
        sum(c["expected"]["reason_code"] == o["reason_code"] for c, o in both) / len(both) if both else None
    )
    m["reason_code_n"] = len(both)
    m["false_refusals"] = [
        {"id": c["id"], "category": c["category"], "status": o["status"], "reason": o["reason_code"]}
        for c, o in rows
        if c["expected"]["status"] not in REFUSING and o["status"] in REFUSING
    ]
    answerable = [1 for c, _ in rows if c["expected"]["status"] not in REFUSING]
    m["false_refusal_rate"] = len(m["false_refusals"]) / len(answerable) if answerable else None
    m["false_refusal_n"] = len(answerable)
    return m


def fact_hits(cases: list[dict[str, Any]], outs: list[dict[str, Any]]) -> tuple[float | None, int]:
    rows = [(c, o) for c, o in zip(cases, outs, strict=True) if c["expected"]["required_fact_substrings"]]
    if not rows:
        return None, 0
    hits = []
    for c, o in rows:
        blob = " ".join([cl["text"] for cl in o["claims"]] + [q for cl in o["claims"] for q in cl["quotes"]]).lower()
        hits.append(all(s.lower() in blob for s in c["expected"]["required_fact_substrings"]))
    return sum(hits) / len(hits), len(hits)


def engine_eval(pipe: Pipeline, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Engine verdicts evaluated directly (independent of retrieval) for every case with expected verdicts."""
    labels = ["APPLICABLE", "NOT_APPLICABLE", "UNDETERMINED", "NOT_CHECKED"]
    confusion = {e: dict.fromkeys(labels, 0) for e in labels}
    rows, undetermined = [], Counter()
    for c in cases:
        for rid, expected in c["expected"]["expected_verdicts"].items():
            cfg = c["config"]
            norm = norm_model(cfg["model"]) if cfg["model"] else None
            # Same make linking as the pipeline (a case may spell a make that ingest now merges).
            ml = pipe.linker.link_make(cfg["make"], "ui")
            make = ml.canonical if ml.status == "accepted" else cfg["make"]
            lc = LinkedConfig(
                make, norm, family(norm) if norm else None, cfg["serial"], date.fromisoformat(cfg["as_of"])
            )
            a = evaluate(lc, pipe.retriever.engine.records[rid])
            confusion[expected][a.verdict] += 1
            rows.append(
                {
                    "case": c["id"],
                    "record": rid,
                    "expected": expected,
                    "got": a.verdict,
                    "rule": a.rule,
                    "reason": a.reasons[-1],
                    "provenance": c["provenance"],
                }
            )
            if a.verdict == "UNDETERMINED":
                undetermined[a.rule] += 1
    per_class = {}
    for e in labels:
        n = sum(confusion[e].values())
        if n:
            per_class[e] = {"accuracy": confusion[e][e] / n, "n": n}
    correct = [1.0 if r["expected"] == r["got"] else 0.0 for r in rows]
    return {
        "rows": rows,
        "confusion": confusion,
        "per_class": per_class,
        "accuracy": mean(correct) if correct else None,
        "accuracy_ci": boot_ci(correct),
        "n": len(rows),
        "undetermined_by_rule": dict(undetermined),
    }


def answer_quality(outs: list[dict[str, Any]]) -> dict[str, Any]:
    llm = [o for o in outs if o["answer_mode"] == "llm" and o["s7"] and o["s7"]["claims_in"]]
    if not llm:
        return {
            "measured": False,
            "n_answers": 0,
            "note": "NOT MEASURED: no answer was written by the model (generation fell back to extractive or was off).",
        }
    proposed = sum(o["s7"]["claims_in"] for o in llm)
    d = {k: sum(o["s7"][k] or 0 for o in llm) for k in ("dropped_quotes", "dropped_grounding", "dropped_llm")}
    after_q = proposed - d["dropped_quotes"]
    after_g = after_q - d["dropped_grounding"]
    return {
        "measured": True,
        "n_answers": len(llm),
        "claims_proposed": proposed,
        "quote_pass_rate": after_q / proposed if proposed else None,
        "grounding_pass_rate": after_g / after_q if after_q else None,
        "verifier_pass_rate": (after_g - d["dropped_llm"]) / after_g if after_g else None,
        "claims_kept": after_g - d["dropped_llm"],
        **d,
    }


def latency(outs: list[dict[str, Any]]) -> dict[str, Any]:
    r = [o["retrieval_ms"] for o in outs if o["retrieval_ms"] is not None]
    e = [o["e2e_ms"] for o in outs]
    pct = lambda xs, q: float(np.percentile(xs, q)) if xs else None  # noqa: E731
    return {
        "p50_retrieval_ms": pct(r, 50),
        "p95_retrieval_ms": pct(r, 95),
        "n_retrieval": len(r),
        "p50_e2e_ms": pct(e, 50),
        "p95_e2e_ms": pct(e, 95),
        "n_e2e": len(e),
        "cost_per_query": mean(o["cost_usd"] for o in outs) if outs else None,
    }


def system_metrics(cases: list[dict[str, Any]], outs: list[dict[str, Any]]) -> dict[str, Any]:
    ret = [(c, o) for c, o in zip(cases, outs, strict=True) if retrieval_case(c)]
    r5 = [recall_at(c, o) for c, o in ret]
    mrr = [rr(c, o) for c, o in ret]
    status_rows = [(c, o) for c, o in zip(cases, outs, strict=True) if c["expected"]["status"] is not None]
    st = [
        1.0
        if (
            o["status"] in ("answered", "partial")
            if c["expected"]["status"] == "answered"
            else o["status"] == c["expected"]["status"]
        )
        else 0.0
        for c, o in status_rows
    ]
    fh, fn = fact_hits(cases, outs)
    return {
        "recall_at_5": mean(r5) if r5 else None,
        "recall_at_5_ci": boot_ci(r5),
        "mrr": mean(mrr) if mrr else None,
        "mrr_ci": boot_ci(mrr),
        "n_retrieval_cases": len(ret),
        "status_accuracy": mean(st) if st else None,
        "status_accuracy_ci": boot_ci(st),
        "n_status_cases": len(st),
        "fact_hit_rate": fh,
        "n_fact_cases": fn,
        "refusal": refusal_metrics(cases, outs),
        "answer_quality": answer_quality(outs),
        "latency": latency(outs),
        "answer_modes": dict(Counter(o["answer_mode"] for o in outs)),
    }


# ------------------------------------------------------------------ failures


def failures(cases: list[dict[str, Any]], outs: list[dict[str, Any]], eng: dict[str, Any]) -> list[dict[str, Any]]:
    """Every S2 failure, typed and graded. `visible` = the user gets a warning (refusal card, UNDETERMINED badge,
    partial status); silent failures are the dangerous kind."""
    out = []
    by_id = {c["id"]: c for c in cases}
    for c, o in zip(cases, outs, strict=True):
        e = c["expected"]
        if e["status"] in REFUSING and o["status"] not in REFUSING:
            out.append(
                dict(
                    kind="missed_refusal",
                    severity=3,
                    visible=False,
                    case=c,
                    out=o,
                    cause=f"no gate fired; expected {e['reason_code']}",
                    fix="add or widen the gate for this pattern",
                )
            )
        elif e["status"] not in (None, *REFUSING) and o["status"] in REFUSING:
            out.append(
                dict(
                    kind="false_refusal",
                    severity=1,
                    visible=True,
                    case=c,
                    out=o,
                    cause=f"gate {o['reason_code']} fired on an answerable question",
                    fix="narrow that gate (keyword list, thresholds or linking)",
                )
            )
        elif e["status"] in REFUSING and o["status"] in REFUSING and e["reason_code"] != o["reason_code"]:
            out.append(
                dict(
                    kind="wrong_reason_code",
                    severity=1,
                    visible=True,
                    case=c,
                    out=o,
                    cause=f"refused with {o['reason_code']} instead of {e['reason_code']}",
                    fix="gate order or gate coverage",
                )
            )
        elif (
            retrieval_case(c)
            and o["status"] not in REFUSING
            and not set(e["expected_record_ids"]) & set(o["retrieved"])
        ):
            out.append(
                dict(
                    kind="record_missed",
                    severity=3,
                    visible=False,
                    case=c,
                    out=o,
                    cause="expected record not in the top 8 retrieved",
                    fix="retrieval (query wording, model linking, ranking tiers)",
                )
            )
    for row in eng["rows"]:
        if row["expected"] == row["got"]:
            continue
        c = by_id[row["case"]]
        o = next(x for x in outs if x["id"] == row["case"])
        silent = row["got"] in ("APPLICABLE", "NOT_APPLICABLE")
        sev = 3 if silent else 2
        out.append(
            dict(
                kind=f"verdict_{row['expected']}_as_{row['got']}",
                severity=sev,
                visible=not silent,
                case=c,
                out=o,
                cause=f"engine rule {row['rule']}: {row['reason']}",
                fix="extraction/engine rule for this wording (see cause)",
            )
        )
    return sorted(out, key=lambda f: (-f["severity"], f["case"]["category"], f["case"]["id"]))


def worst_by_category(fails: list[dict[str, Any]], k: int = 5) -> list[dict[str, Any]]:
    picked, seen = [], set()
    for f in fails:
        if f["case"]["category"] not in seen:
            picked.append(f)
            seen.add(f["case"]["category"])
        if len(picked) == k:
            return picked
    return (picked + [f for f in fails if f not in picked])[:k]


# ------------------------------------------------------------------ claim audit CSV and LLM judge


def sentence_text(conn: sqlite3.Connection, eid: str) -> str:
    row = conn.execute("SELECT text FROM sentences WHERE id = ?", (eid,)).fetchone()
    return row[0] if row else "(computed fact or record heading)"


def write_claim_audit(runs: dict[str, list[dict[str, Any]]], conn: sqlite3.Connection) -> int:
    rng = random.Random(RNG_SEED)
    rows = []
    for key in ("S0", "S2"):
        pool = [(o, cl) for o in runs.get(key, []) if o["answer_mode"] == "llm" for cl in o["claims"]]
        for o, cl in rng.sample(pool, min(20, len(pool))):
            eid = cl["evidence_ids"][0] if cl["evidence_ids"] else ""
            rows.append(
                {
                    "system": key,
                    "case_id": o["id"],
                    "claim": cl["text"],
                    "evidence_id": eid,
                    "quote": cl["quotes"][0] if cl["quotes"] else "",
                    "cited_sentence": sentence_text(conn, eid),
                    "supported (Y/N)": "",
                }
            )
    with AUDIT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["system", "case_id", "claim", "evidence_id", "quote", "cited_sentence", "supported (Y/N)"]
        )
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def llm_judge(runs: dict[str, list[dict[str, Any]]], conn: sqlite3.Connection, available: bool) -> dict[str, Any]:
    """Sonnet judges (claim, cited sentence) for up to 60 model-written claims per system. A model; can be wrong."""
    if not available:
        return {"run": False, "note": "LLM judge NOT RUN: no valid API key."}
    from backend.app.llm.client import LLMError, get_client
    from backend.app.pipeline.verify import VerifyOutput, verifier_message

    client = get_client()
    system_prompt = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / "verify.md").read_text(encoding="utf-8")
    out: dict[str, Any] = {"run": True, "judge_model": load_config()["models"]["generation"]}
    rng = random.Random(RNG_SEED + 1)
    for key in ("S0", "S1", "S2"):
        pool = [cl for o in runs.get(key, []) if o["answer_mode"] == "llm" for cl in o["claims"] if cl["evidence_ids"]]
        sample = rng.sample(pool, min(60, len(pool)))
        if not sample:
            out[key] = {"n": 0}
            continue
        items = [(f"C{i}", cl["text"], sentence_text(conn, cl["evidence_ids"][0])) for i, cl in enumerate(sample, 1)]
        try:
            res = client.call_tool(
                purpose="eval_judge",
                model_key="generation",
                system=system_prompt.strip(),
                user=verifier_message(items),
                tool_name="verify_claims",
                tool_description="Verdict per item id.",
                output_model=VerifyOutput,
                max_tokens_key="max_tokens_generation",
            )
        except LLMError as exc:
            out[key] = {"n": len(items), "error": str(exc)}
            continue
        verdicts = [r.verdict for r in res.output.results]  # type: ignore[attr-defined]
        unsupported = sum(v != "SUPPORTED" for v in verdicts)
        out[key] = {"n": len(verdicts), "unsupported_rate": unsupported / len(verdicts) if verdicts else None}
    return out


# ------------------------------------------------------------------ dev tuning, freeze, test


def make_pipeline() -> Pipeline:
    return Pipeline(repo_path("sqlite_path"), audit_path=EVAL_DIR / "eval_audit.jsonl")


def config_hash() -> str:
    h = hashlib.sha256()
    for p in (ROOT / "config.yaml", ROOT / "configs" / "rules.yaml"):
        h.update(p.read_bytes())
    return h.hexdigest()


def decisions_hash() -> str:
    return hashlib.sha256(json.dumps(manual_decisions(), sort_keys=True).encode()).hexdigest()


def run_dev() -> dict[str, Any]:
    """Tune LOW_RETRIEVAL_SCORE thresholds on the dev split (S2 with generation off: thresholds only affect gates)."""
    cases = load_cases("dev")
    pipe = make_pipeline()
    grid = []
    for cos in (0.50, 0.55, 0.58, 0.60, 0.62, 0.64, 0.66, 0.68, 0.70):
        for bm in (0.80, 0.85, 0.88, 0.90, 0.92, 0.95):
            th = {"min_top_cosine": cos, "min_top_bm25_norm": bm}
            opts = Options(engine=True, generation=False, audit=False, low_retrieval=th)
            outs = [run_case(pipe, System("S2", "", opts, False), c) for c in cases]
            m = refusal_metrics(cases, outs)
            grid.append(
                {
                    **th,
                    "f1": m["f1"] or 0.0,
                    "false_refusals": len(m["false_refusals"]),
                    "recall": m["recall"],
                    "precision": m["precision"],
                }
            )
    current = load_config()["thresholds"]["low_retrieval"]
    best_f1 = max(g["f1"] for g in grid)
    tied = [g for g in grid if g["f1"] == best_f1]
    min_fr = min(g["false_refusals"] for g in tied)
    tied = [g for g in tied if g["false_refusals"] == min_fr]
    chosen = min(
        tied,
        key=lambda g: (
            abs(g["min_top_cosine"] - current["min_top_cosine"])
            + abs(g["min_top_bm25_norm"] - current["min_top_bm25_norm"])
        ),
    )
    result = {
        "n_dev_cases": len(cases),
        "grid": grid,
        "chosen": {k: chosen[k] for k in ("min_top_cosine", "min_top_bm25_norm")},
        "chosen_f1": chosen["f1"],
        "tied_settings": len(tied),
        "previous": current,
        "rule": "max dev refusal F1; ties -> fewest false refusals; then closest to the previous placeholder",
    }
    (EVAL_DIR / "dev_tuning.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    THRESHOLDS_PATH.write_text(json.dumps(result["chosen"], indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


def freeze() -> dict[str, Any]:
    thresholds = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8")) if THRESHOLDS_PATH.exists() else None
    if thresholds is None:
        raise SystemExit("Run `make eval-dev` first: no tuned thresholds.")
    rec = {
        "cases_sha256": sha256(CASES_PATH),
        "manual_decisions_sha256": decisions_hash(),
        "config_sha256": config_hash(),
        "thresholds": thresholds,
        "frozen_at": datetime.now(UTC).isoformat(),
        "manual_confirmed": sum(v == "CONFIRMED" for v in manual_decisions().values()),
    }
    FREEZE_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
    return rec


def run_test() -> dict[str, Any]:
    if not FREEZE_PATH.exists():
        raise SystemExit("Not frozen: run `make eval-freeze` first.")
    fz = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    if sha256(CASES_PATH) != fz["cases_sha256"]:
        raise SystemExit("REFUSED: data/eval/cases.jsonl changed after freezing. Re-freeze deliberately.")
    if decisions_hash() != fz["manual_decisions_sha256"]:
        raise SystemExit("REFUSED: manual review decisions changed after freezing. Re-freeze deliberately.")
    cfg_changed = config_hash() != fz["config_sha256"]
    cases = load_cases("test")
    available, why = llm_available()
    cost = projected_cost(len(cases), available)
    limit = float(os.environ.get("EVAL_MAX_USD", "8"))
    print(f"test cases: {len(cases)}; LLM: {why}; projected cost ${cost:.2f} (limit ${limit:.2f})")
    if cost > limit:
        raise SystemExit(f"ABORTED: projected cost ${cost:.2f} exceeds EVAL_MAX_USD=${limit:.2f}")
    pipe = make_pipeline()
    syss = systems(fz["thresholds"])
    runs = run_all(pipe, cases, syss)
    metrics = {s.key: system_metrics(cases, runs[s.key]) for s in syss}
    eng = engine_eval(pipe, cases)
    fails = failures(cases, runs["S2"], eng)
    # Manual test cases a human has NOT confirmed yet: run on S2 and reported separately, never in a headline.
    decisions = manual_decisions()
    unconf = [c for c in load_cases("test", include_unconfirmed_manual=True)
              if c["provenance"] == "manual" and decisions.get(c["id"]) != "CONFIRMED"]  # fmt: skip
    s2 = [s for s in syss if s.key == "S2"]
    unconf_out = run_all(pipe, unconf, s2)["S2"] if unconf else []
    unconf_metrics = system_metrics(unconf, unconf_out) if unconf else None
    unconf_eng = engine_eval(pipe, unconf) if unconf else None
    unconf_fails = failures(unconf, unconf_out, unconf_eng) if unconf_eng else []
    n_audit = write_claim_audit(runs, pipe.retriever.conn)
    judge = llm_judge(runs, pipe.retriever.conn, available and os.environ.get("LLM_MODE") != "fake")
    detail = {
        "generated_at": datetime.now(UTC).isoformat(),
        "freeze": fz,
        "config_changed_since_freeze": cfg_changed,
        "llm": {"available": available, "why": why, "projected_cost_usd": cost},
        "n_test_cases": len(cases),
        "categories": dict(Counter(c["category"] for c in cases)),
        "provenance": dict(Counter(c["provenance"] for c in cases)),
        "manual_pending": sum(v == "PENDING" for v in manual_decisions().values()),
        "systems": {s.key: {"label": s.label, **metrics[s.key]} for s in syss},
        "engine": eng,
        "failures": [
            {
                "id": f["case"]["id"],
                "category": f["case"]["category"],
                "kind": f["kind"],
                "severity": f["severity"],
                "visible": f["visible"],
                "query": f["case"]["query"],
                "expected": f["case"]["expected"],
                "observed": {
                    "status": f["out"]["status"],
                    "reason": f["out"]["reason_code"],
                    "retrieved": f["out"]["retrieved"][:5],
                },
                "cause": f["cause"],
                "fix": f["fix"],
            }
            for f in fails
        ],
        "worst5": [f["case"]["id"] + ":" + f["kind"] for f in worst_by_category(fails)],
        "claim_audit_rows": n_audit,
        "llm_judge": judge,
        "unconfirmed_manual": {
            "n": len(unconf),
            "label": "UNCONFIRMED (machine-checked only): expected answers drafted by Claude Code, source sentences "
            "verified verbatim by code, NOT yet confirmed by a human. Not part of any headline number.",
            "recall_at_5": unconf_metrics["recall_at_5"] if unconf_metrics else None,
            "n_retrieval_cases": unconf_metrics["n_retrieval_cases"] if unconf_metrics else 0,
            "status_accuracy": unconf_metrics["status_accuracy"] if unconf_metrics else None,
            "n_status_cases": unconf_metrics["n_status_cases"] if unconf_metrics else 0,
            "engine": unconf_eng["per_class"] if unconf_eng else None,
            "failures": [
                {
                    "id": f["case"]["id"],
                    "kind": f["kind"],
                    "visible": f["visible"],
                    "query": f["case"]["query"],
                    "expected": json.dumps({k: v for k, v in f["case"]["expected"].items() if v}),
                    "observed": f"{f['out']['status']} {f['out']['reason_code'] or ''}".strip(),
                    "cause": f["cause"],
                }
                for f in unconf_fails
            ],  # fmt: skip
        },
    }
    DETAIL_PATH.write_text(json.dumps(detail, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    results = to_results(detail, worst_by_category(fails))
    RESULTS_PATH.write_text(results.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    EVAL_MD.write_text(eval_md(detail, worst_by_category(fails)), encoding="utf-8", newline="\n")
    with (EVAL_DIR / "test_runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "at": detail["generated_at"],
                    "freeze": fz["frozen_at"],
                    "n": len(cases),
                    "llm_available": available,
                    "config_changed_since_freeze": cfg_changed,
                }
            )
            + "\n"
        )
    return detail


# ------------------------------------------------------------------ results.json (served by /api/eval/latest)

METRICS = [
    MetricDef(key="recall_at_5", label="Recall@5", unit="ratio", higher_is_better=True),
    MetricDef(key="mrr", label="MRR", unit="ratio", higher_is_better=True),
    MetricDef(key="status_accuracy", label="Status accuracy", unit="ratio", higher_is_better=True),
    MetricDef(key="refusal_f1", label="Refusal F1", unit="ratio", higher_is_better=True),
    MetricDef(key="false_refusal_rate", label="False refusal rate", unit="ratio", higher_is_better=False),
    MetricDef(key="fact_hit_rate", label="Required facts present", unit="ratio", higher_is_better=True),
    MetricDef(key="p95_retrieval_ms", label="p95 retrieval", unit="ms", higher_is_better=False),
    MetricDef(key="p95_e2e_ms", label="p95 end-to-end", unit="ms", higher_is_better=False),
    MetricDef(key="quote_pass_rate", label="Quote check pass", unit="ratio", higher_is_better=True),
    MetricDef(key="grounding_pass_rate", label="Grounding pass", unit="ratio", higher_is_better=True),
    MetricDef(key="verifier_pass_rate", label="Verifier pass", unit="ratio", higher_is_better=True),
]


def to_results(d: dict[str, Any], worst: list[dict[str, Any]]) -> EvalResults:
    rows, ablation = [], []
    for key, m in d["systems"].items():
        vals = {
            "recall_at_5": m["recall_at_5"],
            "mrr": m["mrr"],
            "status_accuracy": m["status_accuracy"],
            "refusal_f1": m["refusal"]["f1"],
            "false_refusal_rate": m["refusal"]["false_refusal_rate"],
            "fact_hit_rate": m["fact_hit_rate"],
            "p95_retrieval_ms": m["latency"]["p95_retrieval_ms"],
            "p95_e2e_ms": m["latency"]["p95_e2e_ms"],
        }
        r = m["refusal"]
        n = {
            "recall_at_5": m["n_retrieval_cases"],
            "mrr": m["n_retrieval_cases"],
            "status_accuracy": m["n_status_cases"],
            "refusal_f1": r["n"],
            "false_refusal_rate": r["false_refusal_n"],
            "fact_hit_rate": m["n_fact_cases"],
            "p95_retrieval_ms": m["latency"]["n_retrieval"],
            "p95_e2e_ms": m["latency"]["n_e2e"],
        }
        ci = {
            "recall_at_5": list(m["recall_at_5_ci"]),
            "mrr": list(m["mrr_ci"]),
            "status_accuracy": list(m["status_accuracy_ci"]),
            "refusal_f1": list(r["f1_ci"]),
        }
        rows.append(MetricRow(system=m["label"], is_baseline=key.startswith("B"), values=vals, n=n, ci95=ci))
        if key.startswith("S"):
            aq = m["answer_quality"]
            ablation.append(
                MetricRow(
                    system=m["label"] + ("" if aq["measured"] else " [NOT MEASURED: no model-written answers]"),
                    is_baseline=False,
                    values={k: aq.get(k) for k in ("quote_pass_rate", "grounding_pass_rate", "verifier_pass_rate")},
                    n=dict.fromkeys(
                        ("quote_pass_rate", "grounding_pass_rate", "verifier_pass_rate"), aq.get("claims_proposed")
                    ),  # fmt: skip
                )
            )
    fcs = [
        FailureCase(
            id=f["case"]["id"],
            query=f["case"]["query"],
            expected=json.dumps({k: v for k, v in f["case"]["expected"].items() if v}),
            observed=f"{f['out']['status']} {f['out']['reason_code'] or ''} top: {f['out']['retrieved'][:3]}",
            cause=f"[{f['kind']}] {f['cause']}. Fix: {f['fix']}",
            user_signal=(
                "VISIBLE: the user sees a warning (refusal/UNDETERMINED/partial)"
                if f["visible"]
                else "SILENT: no warning shown; dangerous kind"
            ),
        )
        for f in worst
    ]
    um = d.get("unconfirmed_manual") or {}
    fcs += [
        FailureCase(
            id=f"{f['id']} (UNCONFIRMED manual case)",
            query=f["query"],
            expected=f.get("expected") or "see data/eval/manual_review.md (not yet confirmed by a human)",
            observed=f["observed"],
            cause=f"[{f['kind']}] {f['cause']}",
            user_signal=(
                "VISIBLE: the user sees a warning (refusal/UNDETERMINED/partial)"
                if f["visible"]
                else "SILENT: no warning shown; dangerous kind"
            ),
        )
        for f in um.get("failures", [])
    ]
    desc = (
        f"{d['n_test_cases']} test cases ({d['provenance']}); categories {d['categories']}. AUTO cases are generated "
        f"from structured fields and are partly circular. {d['manual_pending']} manual cases await human review and "
        f"are excluded. LLM: {d['llm']['why']}."
    )
    return EvalResults(
        generated_at=d["generated_at"],
        eval_set=EvalSet(
            name="AD Trace eval v2 (test split, re-frozen)", size=d["n_test_cases"], synthetic=True, description=desc
        ),
        metric_defs=METRICS,
        systems=rows,
        ablation=ablation,
        failures=fcs,
        caveats=[
            "The test split was re-run after fixes motivated by the v1 test failures: these numbers are an "
            "optimistic re-test, not an unbiased held-out estimate (see docs/EVAL.md, analyst notes).",
            "AUTO cases are generated from structured fields and are partly circular. Manual cases are not yet "
            "confirmed by a human; they appear only as failure cases labelled UNCONFIRMED.",
            f"Answer quality is NOT MEASURED in this run ({d['llm']['why']}).",
            "No user study: time savings are not measured.",
        ],
        mock=False,
    )


# ------------------------------------------------------------------ EVAL.md


def _f(x: Any, pct: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{100 * x:.1f}%" if pct else f"{x:.1f}"


def _ci(ci: Any) -> str:
    return "" if not ci or ci[0] is None else f" [{100 * ci[0]:.0f}-{100 * ci[1]:.0f}%]"


def eval_md(d: dict[str, Any], worst: list[dict[str, Any]]) -> str:
    S = d["systems"]
    L = [
        "# AD Trace evaluation (test split)",
        "",
        f"_Generated {d['generated_at']} by `make eval-test`. Frozen {d['freeze']['frozen_at']}; cases sha256 "
        f"`{d['freeze']['cases_sha256'][:16]}`; thresholds {d['freeze']['thresholds']}._",
        "",
        "## Setup",
        "",
        f"- **Test cases: n = {d['n_test_cases']}** {d['categories']}; provenance {d['provenance']}.",
        f"- **Manual cases: {d['manual_pending']} drafted cases are AWAITING HUMAN REVIEW** "
        "(data/eval/manual_review.md) "
        "and are NOT included in any headline number below (they appear only in the separately labelled "
        "UNCONFIRMED section).",
        "- **Circularity caveat:** auto cases are generated from structured fields (Model column, raw summary text, "
        "raw dates). They test the pipeline, not extraction quality. "
        "Model-applicability auto cases are partly circular: "
        "the engine reads the same Model column. Treat high scores on them as plumbing checks, not accuracy evidence.",
        f"- **LLM availability:** {d['llm']['why']}. Projected cost ${d['llm']['projected_cost_usd']:.2f}.",
        "- Systems: " + "; ".join(f"**{k}** {v['label']}" for k, v in S.items()) + ".",
        f"- Thresholds tuned on the dev split only: {d['freeze']['thresholds']} (see DECISIONS.md).",
        "- Brackets are bootstrap 95% CIs (1000 resamples). n is shown next to every metric.",
        "",
    ]
    L += [
        "## Retrieval (answerable cases with expected records)",
        "",
        "| System | Recall@5 | MRR | n |",
        "|---|---|---|---|",
    ]
    for k in ("B1", "B2", "B3", "S2"):
        m = S[k]
        L.append(
            f"| {k} | {_f(m['recall_at_5'])}{_ci(m['recall_at_5_ci'])} | {_f(m['mrr'])}{_ci(m['mrr_ci'])} | "
            f"{m['n_retrieval_cases']} |"
        )
    L += [
        "",
        "S2 retrieves with engine-consistent hard filters (make/model), so its numbers are not a pure ranking "
        "comparison.",
        "",
    ]
    e = d["engine"]
    L += [
        "## Applicability engine (direct evaluation, independent of retrieval)",
        "",
        f"Accuracy {_f(e['accuracy'])}{_ci(e['accuracy_ci'])}, n = {e['n']}.",
        "",
        "| Expected \\ Got | " + " | ".join(e["confusion"]) + " |",
        "|---" * (len(e["confusion"]) + 1) + "|",
    ]
    for exp, row in e["confusion"].items():
        if sum(row.values()):
            L.append(f"| {exp} | " + " | ".join(str(v) for v in row.values()) + " |")
    L += [
        "",
        "Per class: "
        + json.dumps({k: {"acc": round(v["accuracy"], 3), "n": v["n"]} for k, v in e["per_class"].items()}),
        f"UNDETERMINED by engine rule: {e['undetermined_by_rule'] or 'none'}. Coverage matters more than accuracy "
        "here: UNDETERMINED is a visible, safe outcome.",
        "",
    ]
    L += [
        "## Refusal behaviour (should refuse/clarify vs did)",
        "",
        "| System | Precision | Recall | F1 | Reason-code acc. | False refusals | n |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, m in S.items():
        r = m["refusal"]
        L.append(
            f"| {k} | {_f(r['precision'])} | {_f(r['recall'])} | {_f(r['f1'])}{_ci(r['f1_ci'])} | "
            f"{_f(r['reason_code_accuracy'])} (n={r['reason_code_n']}) | "
            f"{len(r['false_refusals'])}/{r['false_refusal_n']} | {r['n']} |"
        )
    fr = S["S2"]["refusal"]["false_refusals"]
    L += ["", f"S2 false refusals (answerable cases refused): {fr or 'none'}.", ""]
    L += ["## Answer quality and ablation (S0 to S2)", ""]
    for k in ("S0", "S1", "S2"):
        aq = S[k]["answer_quality"]
        if not aq["measured"]:
            L.append(f"- **{k}: {aq['note']}** Answer modes: {S[k]['answer_modes']}.")
        else:
            L.append(
                f"- **{k}** (n answers = {aq['n_answers']}, claims = {aq['claims_proposed']}): quote pass "
                f"{_f(aq['quote_pass_rate'])}, grounding pass {_f(aq['grounding_pass_rate'])}, verifier pass "
                f"{_f(aq['verifier_pass_rate'])}, kept {aq['claims_kept']}."
            )
    L += [
        "",
        f"- **Unsupported-claim rate (headline, human audit): AWAITING HUMAN REVIEW.** "
        f"data/eval/claim_audit.csv has {d['claim_audit_rows']} rows (20 from S0 and 20 from S2 when available); "
        "compute with `python scripts/claim_audit_rate.py`.",
        f"- LLM judge (a model; it can be wrong): {json.dumps(d['llm_judge'])}.",
        "",
    ]
    L += [
        "## Latency and cost",
        "",
        "| System | p50 retrieval | p95 retrieval | p50 end-to-end | p95 end-to-end | cost/query | n |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, m in S.items():
        lt = m["latency"]
        L.append(
            f"| {k} | {_f(lt['p50_retrieval_ms'], False)} ms | {_f(lt['p95_retrieval_ms'], False)} ms | "
            f"{_f(lt['p50_e2e_ms'], False)} ms | {_f(lt['p95_e2e_ms'], False)} ms | "
            f"${lt['cost_per_query'] or 0:.4f} | {lt['n_e2e']} |"
        )
    L += [
        "",
        "End-to-end is low because no LLM call succeeded in this run; it is not representative of a run with a "
        "working key."
        if not d["llm"]["available"]
        else "",
        "",
    ]
    L += [
        "## Failure analysis (S2, worst per category)",
        "",
        "VISIBLE = the user sees a warning (refusal card, UNDETERMINED badge, partial). **SILENT = no warning: the "
        "dangerous kind; we report it.**",
        "",
    ]
    for f in worst:
        L += [
            f"### {f['case']['id']} ({f['case']['category']}): {f['kind']} ({'VISIBLE' if f['visible'] else 'SILENT'})",
            f"- Query: {f['case']['query']}",
            f"- Expected: {json.dumps({k: v for k, v in f['case']['expected'].items() if v})}",
            f"- Observed: {f['out']['status']} {f['out']['reason_code'] or ''}; "
            f"top retrieved {f['out']['retrieved'][:3]}",
            f"- Probable cause: {f['cause']}",
            f"- Fix: {f['fix']}",
            "",
        ]
    n_silent = sum(1 for f in d["failures"] if not f["visible"])
    L += [f"All S2 failures: {len(d['failures'])} ({n_silent} silent). Full list in data/eval/results_detail.json.", ""]
    um = d.get("unconfirmed_manual")
    if um and um["n"]:
        L += [
            "## UNCONFIRMED manual cases (machine-checked only; NOT in any number above)",
            "",
            f"{um['label']} n = {um['n']} (S2 only).",
            "",
            f"- Recall@5 {_f(um['recall_at_5'])} (n={um['n_retrieval_cases']}); status accuracy "
            f"{_f(um['status_accuracy'])} (n={um['n_status_cases']}); engine per class {json.dumps(um['engine'])}.",
        ]
        L += [
            f"- {f['id']}: {f['kind']} ({'VISIBLE' if f['visible'] else 'SILENT'}); observed {f['observed']}; "
            f"cause: {f['cause']}"
            for f in um["failures"]
        ] or ["- No failures on these cases."]
        L += [""]
    L += [
        "## Limitations",
        "",
        f"- Small n (test n = {d['n_test_cases']}); confidence intervals are wide and most systems cannot be separated "
        "statistically where the CIs overlap.",
        "- One dataset: 431 FAA NPRM summaries (proposals, not final ADs), no full notice text.",
        "- Extraction is regex-based; see data/processed/coverage_report.json (e.g. no summary states serial ranges, "
        "so serial applicability is never resolved).",
        "- Auto cases are partly circular; manual cases are pending human review.",
        "- Answer-quality and unsupported-claim metrics need a working LLM key and a human audit; until then they are "
        "NOT MEASURED.",
        "- No user study and no measured time savings: any impact claim is an estimate, not a measurement.",
    ]
    notes = EVAL_DIR / "analyst_notes.md"
    if notes.exists():
        L += ["", notes.read_text(encoding="utf-8").strip()]
    return "\n".join(L) + "\n"


def regenerate_report() -> None:
    """Rebuild docs/EVAL.md and results.json from results_detail.json + analyst notes, without re-running the test."""
    d = json.loads(DETAIL_PATH.read_text(encoding="utf-8"))
    worst = [_detail_failure(f) for f in d["failures"] if f"{f['id']}:{f['kind']}" in d["worst5"]]
    EVAL_MD.write_text(eval_md(d, worst), encoding="utf-8", newline="\n")
    RESULTS_PATH.write_text(to_results(d, worst).model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def _detail_failure(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": {"id": f["id"], "category": f["category"], "query": f["query"], "expected": f["expected"]},
        "out": {
            "status": f["observed"]["status"],
            "reason_code": f["observed"]["reason"],
            "retrieved": f["observed"]["retrieved"],
        },
        "kind": f["kind"],
        "visible": f["visible"],
        "cause": f["cause"],
        "fix": f["fix"],
    }
