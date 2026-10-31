"""Retrieval CLI (no LLM).

    python -m backend.app.retrieval.search "radio management panel" --mode hybrid --make "Airbus SAS"
    python -m backend.app.retrieval.search --bench 50            # p50/p95 latency over 50 queries
    python -m backend.app.retrieval.search --compare "query"     # bm25 vs dense vs hybrid top records

Make/model are exact vocabulary values (or a known raw make alias); fuzzy linking is Prompt 7.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date
from pathlib import Path

from backend.app.config import repo_path
from backend.app.engine.explain import link_model, resolve_make
from backend.app.retrieval.retriever import Filters, RetrievalResult, Retriever, p50_p95


def _fmt(x: float | None, nd: int = 3) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def render(res: RetrievalResult, show_sentences: bool = True) -> str:
    out = [
        f"query: {res.query!r}  mode={res.mode}  backend={res.embedding_backend}",
        f"fts: {res.fts_query}",
        f"candidates {res.candidates_after}/{res.candidates_before} after filters; timings ms {res.timings_ms}",
    ]
    for f in res.filters:
        out.append(f"  filter {f.name}={f.value}: removed {f.removed} ({f.reason})")
    out.append(
        "features: " + ", ".join(f"{k}={_fmt(v) if isinstance(v, float) else v}" for k, v in res.features.items())
    )
    for r in res.records:
        out.append(f"\n#{r.rank} {r.record_id}  score {r.score:.4f}")
        if show_sentences:
            for s in r.sentences:
                out.append(
                    f"   [{s.sentence_id}] {','.join(s.tags):26} bm25 {_fmt(s.bm25, 2):>6} (r{s.bm25_rank or '-'}) "
                    f"cos {_fmt(s.cosine)} (r{s.dense_rank or '-'}) fused {s.fused:.4f}\n      {s.text[:160]}"
                )
    return "\n".join(out)


def bench_queries(r: Retriever, n: int) -> list[str]:
    """50 queries: 10 hand-written + the first 8 words of seeded random sentences (labelled synthetic)."""
    hand = [
        "radio management panel A330",
        "fuel pump wiring chafing A320",
        "main rotor servo control torque",
        "cracks in the wing spar fitting",
        "evacuation slide fails to inflate",
        "engine high-pressure turbine blade inspection",
        "withdrawn proposal Boeing 737",
        "supersede AD 2025-09-07",
        "oxygen generator replacement",
        "airworthiness limitations section revision Leonardo AW139",
    ]
    rnd = random.Random(7)
    sids = sorted(r.sentences)
    extra = [" ".join(r.sentences[s][1].split()[:8]) for s in rnd.sample(sids, max(0, n - len(hand)))]
    return (hand + extra)[:n]


def run_bench(r: Retriever, n: int, mode: str) -> tuple[float, float]:
    r.retrieve("warm up", mode=mode)  # type: ignore[arg-type]
    times = []
    for q in bench_queries(r, n):
        t0 = time.perf_counter()
        r.retrieve(q, mode=mode)  # type: ignore[arg-type]
        times.append((time.perf_counter() - t0) * 1000)
    return p50_p95(times)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="hybrid")
    p.add_argument("--make")
    p.add_argument("--model")
    p.add_argument("--date-from")
    p.add_argument("--date-to")
    p.add_argument("--include-duplicates", action="store_true")
    p.add_argument("-k", type=int, default=None)
    p.add_argument("--db", type=Path, default=repo_path("sqlite_path"))
    p.add_argument("--bench", type=int, default=0, help="run N benchmark queries and print p50/p95 per mode")
    p.add_argument("--compare", action="store_true", help="show the top records of all three modes")
    args = p.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} not found: run `make ingest` first")
    t0 = time.perf_counter()
    r = Retriever(args.db)
    print(f"warm-up (indexes + {r.dense.backend}): {(time.perf_counter() - t0):.1f} s")
    model_norm, fam = link_model(r.engine, args.model)
    filters = Filters(
        make=resolve_make(args.db, args.make), model=model_norm, family=fam if model_norm is None else None,
        date_from=date.fromisoformat(args.date_from) if args.date_from else None,
        date_to=date.fromisoformat(args.date_to) if args.date_to else None,
        include_duplicates=args.include_duplicates,
    )  # fmt: skip
    if args.bench:
        for mode in ("bm25", "dense", "hybrid"):
            p50, p95 = run_bench(r, args.bench, mode)
            print(f"{mode:7} {args.bench} queries: p50 {p50:.1f} ms, p95 {p95:.1f} ms")
    if args.compare and args.query:
        for mode in ("bm25", "dense", "hybrid"):
            res = r.retrieve(args.query, filters, mode, args.k)  # type: ignore[arg-type]
            print(f"{mode:7}: " + "  ".join(f"{h.record_id}({h.score:.3f})" for h in res.records))
    elif args.query:
        print(render(r.retrieve(args.query, filters, args.mode, args.k)))
    elif not args.bench:
        p.print_help(sys.stderr)


if __name__ == "__main__":
    main()
