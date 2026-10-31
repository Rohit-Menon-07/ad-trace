"""Explain one record's verdict, status and lineage. Pure code; no LLM, no network.

    python -m backend.app.engine.explain --record R0003 --make "Airbus SAS" --model A330-243 --serial 1234 \
        --as-of 2026-10-31
    python -m backend.app.engine.explain --bench --make "Airbus SAS" --model A330-243

Make and model must be exact vocabulary values (or a known raw make alias). Fuzzy linking belongs to the
entity linker (Prompt 7), so an unknown value is rejected here rather than guessed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from backend.app.config import repo_path
from backend.app.engine.applicability import evaluate, evaluate_all
from backend.app.engine.data import EngineIndex, load_index
from backend.app.engine.status import lineage, record_status
from backend.app.engine.types import LinkedConfig
from backend.app.extract.models import family as model_family
from backend.app.extract.models import norm_model


def resolve_make(db: Path, make: str | None) -> str | None:
    if not make:
        return None
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT canonical, aliases_json FROM vocab WHERE kind='make'").fetchall()
    finally:
        conn.close()
    for canonical, aliases in rows:
        if make == canonical or make in json.loads(aliases):
            return canonical
    hints = sorted(c for c, _ in rows if make.split()[0].lower() in c.lower())[:8]
    raise SystemExit(f"Unknown make {make!r} (exact vocabulary values only). Did you mean: {hints}")


def link_model(index: EngineIndex, model: str | None) -> tuple[str | None, str | None]:
    """(model_norm, family). A bare family such as 'A330' becomes a family-only query."""
    if not model:
        return None, None
    norm = norm_model(model)
    fam = model_family(norm)
    known = {m for r in index.records.values() for m in r.models}
    variants = [m for m in known if model_family(m) == norm and m != norm]
    # Same rule as pipeline.linker: a bare type with 2+ variants is a family query; an exact designator with at
    # most one variant ("PW4090" vs "PW4090-3") is a model.
    if norm == fam and variants and not (norm in known and len(variants) <= 1):
        return None, fam
    return norm, fam


def build_config(db: Path, index: EngineIndex, args: argparse.Namespace) -> LinkedConfig:
    model_norm, fam = link_model(index, args.model)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    return LinkedConfig(resolve_make(db, args.make), model_norm, fam, args.serial, as_of)


def sentence_texts(db: Path, ids: tuple[str, ...]) -> dict[str, str]:
    conn = sqlite3.connect(db)
    try:
        q = f"SELECT id, text FROM sentences WHERE id IN ({','.join('?' for _ in ids)})"
        return dict(conn.execute(q, ids).fetchall()) if ids else {}
    finally:
        conn.close()


def explain(db: Path, index: EngineIndex, cfg: LinkedConfig, record_id: str) -> str:
    rec = index.records.get(record_id)
    if rec is None:
        raise SystemExit(f"Unknown record {record_id}")
    a = evaluate(cfg, rec)
    st = record_status(rec, index, cfg.as_of)
    ln = lineage(rec, index)
    texts = sentence_texts(db, a.evidence_ids)
    out = [
        f"{rec.id}  docket {rec.docket}  make {' | '.join(rec.makes) or '(none)'}",
        f"query: make={cfg.make_canonical} model={cfg.model_norm} family={cfg.family} serial={cfg.serial} "
        f"as_of={cfg.as_of}",
        "",
        f"VERDICT  {a.verdict}   (rule {a.rule}; model match {a.match.value if a.match else '-'})",
    ]
    out += [f"  - {r}" for r in a.reasons]
    if a.basis:
        out.append(f"  basis confidence: {', '.join(a.basis)}")
    out.append("  evidence:")
    out += [f"    [{e}] {texts.get(e, '(Model/Make column value)')}" for e in a.evidence_ids] or ["    (none)"]
    out += [
        "",
        f"STATUS   {st.status_label}; comment period {st.comment_period} (due {st.comments_due_effective}); "
        f"withdrawn={st.withdrawn}" + (f" by {[w.value for w in st.withdrawn_by]}" if st.withdrawn else ""),
        "",
        "LINEAGE",
        "  supersedes (proposed): "
        + (", ".join(f"AD {r.value} [{r.extraction_id}] in_dataset={r.target_in_dataset}" for r in ln.supersedes_ad)
           or "none"),
        "  continues: " + (", ".join(f"AD {r.value} [{r.extraction_id}]" for r in ln.continues_ad) or "none"),
        "  superseded by proposal: " + (", ".join(r.value for r in ln.superseded_by_proposal) or "none"),
        f"  same docket group: {', '.join(ln.same_docket_group)}; latest: {', '.join(ln.latest_in_docket_group)} "
        f"(this is latest: {ln.is_latest_in_docket_group})",
        "  corrections: " + (", ".join(f"{r.value} [{r.extraction_id}]" for r in ln.corrections) or "none"),
    ]  # fmt: skip
    return "\n".join(out)


def bench(index: EngineIndex, cfg: LinkedConfig, repeats: int = 5) -> float:
    """Best-of-N milliseconds to evaluate verdict + status + lineage for every record."""
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        evaluate_all(cfg, index.records)
        for r in index.records.values():
            record_status(r, index, cfg.as_of)
            lineage(r, index)
        best = min(best, (time.perf_counter() - t0) * 1000)
    return best


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="append", default=[])
    parser.add_argument("--make")
    parser.add_argument("--model")
    parser.add_argument("--serial")
    parser.add_argument("--as-of")
    parser.add_argument("--db", type=Path, default=repo_path("sqlite_path"))
    parser.add_argument("--bench", action="store_true", help="time the engine over all records")
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} not found: run `make ingest` first")
    index = load_index(args.db)
    cfg = build_config(args.db, index, args)
    for rid in args.record:
        print(explain(args.db, index, cfg, rid))
        print("-" * 100)
    if args.bench:
        print(f"engine over {len(index.records)} records: {bench(index, cfg):.2f} ms (best of 5)")
    if not args.record and not args.bench:
        parser.print_help(sys.stderr)


if __name__ == "__main__":
    main()
