"""Ingestion + extraction CLI: python -m backend.app.ingest.run [--xlsx PATH] [--db PATH] [--no-docs]

Idempotent: rebuilds the SQLite DB from scratch (temp file + atomic swap) and regenerates
configs/alias_make.yaml, docs/make_audit.md and docs/duplicates_audit.md deterministically.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.config import ROOT, repo_path
from backend.app.extract.run import ExtractResult, extract_db, summary_text
from backend.app.ingest import audit
from backend.app.ingest.db import swap_in, temp_path, to_json, write_database
from backend.app.ingest.duplicates import GroupResult, Row, classify_all
from backend.app.ingest.loader import LoadResult, load_records
from backend.app.ingest.makes import (
    AIRBUS_PLAIN_KEY,
    AliasEntry,
    build_alias_map,
    canonicalise,
    normalise_key,
    split_makes,
)
from backend.app.ingest.makes import make_family as family_of
from backend.app.ingest.sentences import sentence_id, split_sentences
from backend.app.retrieval.dense import load_dense
from backend.app.retrieval.fts import build_fts

log = logging.getLogger("ingest")

ALIAS_PATH = ROOT / "configs" / "alias_make.yaml"
MAKE_AUDIT_PATH = ROOT / "docs" / "make_audit.md"
DUP_AUDIT_PATH = ROOT / "docs" / "duplicates_audit.md"


@dataclass
class IngestResult:
    load: LoadResult
    alias: dict[str, AliasEntry]
    groups: list[GroupResult]
    sentences: list[dict[str, Any]]
    cell_counts: Counter[str]
    extract: ExtractResult | None = None


def apply_makes(records: list[dict[str, Any]]) -> tuple[dict[str, AliasEntry], list[dict[str, Any]], Counter[str]]:
    cell_counts = Counter(r["make_raw"] for r in records if r["make_raw"])
    name_counts: Counter[str] = Counter()
    for r in records:
        name_counts.update(set(split_makes(r["make_raw"])))
    alias = build_alias_map(name_counts)
    record_makes: list[dict[str, Any]] = []
    for r in records:
        makes = canonicalise(r["make_raw"], r["subject_heading"], alias)
        families = list(dict.fromkeys(family_of(m) for m in makes))
        r["make_canonical"] = " | ".join(makes) or None
        r["make_family"] = " | ".join(families) or None
        r["_makes"] = makes
        record_makes += [
            {"record_id": r["id"], "position": i, "make_canonical": m, "make_family": family_of(m)}
            for i, m in enumerate(makes)
        ]
    return alias, record_makes, cell_counts


def apply_duplicates(records: list[dict[str, Any]]) -> list[GroupResult]:
    rows = [
        Row(
            record_id=r["id"],
            docket=r["docket"],
            issue_date=date.fromisoformat(r["issue_date"]) if r["issue_date"] else None,
            makes=r["_makes"],
            model_raw=r["model_raw"],
            comments=r["comments"],
            key=(r["make_raw"], r["model_raw"], r["subject_heading"], r["summary"]),
        )
        for r in records
    ]
    groups = classify_all(rows)
    by_id = {r["id"]: r for r in records}
    for g in groups:
        for rid in g.record_ids:
            by_id[rid]["docket_class"] = g.cls
            by_id[rid]["duplicate_of"] = g.duplicate_of.get(rid)
            by_id[rid]["is_duplicate"] = rid in g.duplicate_of
    return groups


def build_sentences(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in records:
        for s in split_sentences(r["summary"]):
            assert r["summary"][s.start : s.end] == s.text  # offset contract, checked for every sentence
            out.append(
                {"id": sentence_id(r["id"], s.idx), "record_id": r["id"], "idx": s.idx, "text": s.text,
                 "start": s.start, "end": s.end}
            )  # fmt: skip
    return out


def build_vocab(alias: dict[str, AliasEntry], record_makes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(m["make_canonical"] for m in record_makes)
    aliases: dict[str, set[str]] = {}
    for raw, e in alias.items():
        aliases.setdefault(e.canonical, set()).add(raw)
    if "Airbus SAS" in counts:  # plain "Airbus" rows merged by the conditional rule
        aliases.setdefault("Airbus SAS", set())
    return [
        {"kind": "make", "canonical": c, "family": family_of(c), "aliases_json": to_json(sorted(aliases.get(c, {c}))),
         "record_count": n}
        for c, n in sorted(counts.items())
    ]  # fmt: skip


def ingest(xlsx: Path, db_path: Path, write_docs: bool = True, extract: bool = True) -> IngestResult:
    """Build the DB in a temp file, run extraction on it, then swap it in. Re-running gives identical output."""
    load = load_records(xlsx)
    records = load.records
    alias, record_makes, cell_counts = apply_makes(records)
    groups = apply_duplicates(records)
    sentences = build_sentences(records)
    vocab = build_vocab(alias, record_makes)
    meta = {
        "source_file": xlsx.name,
        "source_sha1": hashlib.sha1(xlsx.read_bytes()).hexdigest(),
        "record_count": str(len(records)),
        "sentence_count": str(len(sentences)),
        "sentence_id_base": "1",
    }
    db_records = [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]
    groups_rows = [
        {"docket": g.docket, "class": g.cls, "n_rows": len(g.record_ids), "record_ids_json": to_json(g.record_ids),
         "note": g.note}
        for g in groups
    ]  # fmt: skip
    tmp = temp_path(db_path)
    write_database(tmp, db_records, sentences, record_makes, vocab, groups_rows, meta)
    extracted = extract_db(tmp, write_docs=write_docs) if extract else None
    if extract:
        conn = sqlite3.connect(tmp)
        try:
            build_fts(conn)  # FTS indexes read the extracted model lists
        finally:
            conn.close()
    swap_in(tmp, db_path)

    if write_docs:
        airbus_rows = [
            {"id": r["id"], "docket": r["docket"], "subject": r["subject_heading"], "canonical": r["make_canonical"]}
            for r in records
            if r["make_raw"] and normalise_key(r["make_raw"]) == AIRBUS_PLAIN_KEY
        ]
        missing = [{"id": r["id"], "docket": r["docket"], "subject": r["subject_heading"]} for r in records
                   if not r["make_raw"]]  # fmt: skip
        _write(ALIAS_PATH, audit.alias_yaml(alias))
        _write(MAKE_AUDIT_PATH, audit.make_audit_md(alias, cell_counts, airbus_rows, missing))
        _write(DUP_AUDIT_PATH, audit.duplicates_md(groups, {r["id"]: r for r in records}))
    return IngestResult(load, alias, groups, sentences, cell_counts, extracted)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def quality_summary(res: IngestResult) -> str:
    recs = res.load.records
    n = len(recs)
    cls = Counter(g.cls for g in res.groups)
    lines = ["", "=== Distinct raw Make values (cell text, rows) ==="]
    lines += [f"{c:4d}  {m}" for m, c in sorted(res.cell_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    lines += [f"{sum(1 for r in recs if not r['make_raw']):4d}  <empty>", "", "=== Data-quality summary ==="]
    lines += [
        f"records:                 {n}",
        f"unique dockets:          {len(res.groups)}",
        f"raw make cells:          {len(res.cell_counts)} distinct; canonical makes: "
        f"{len({m for r in recs for m in r['_makes']})}",
        f"rows with no make:       {sum(1 for r in recs if not r['make_raw'])}",
        f"multi-make rows:         {sum(1 for r in recs if len(r['_makes']) > 1)}",
        f"summary_missing:         {sum(1 for r in recs if r['summary_missing'])}",
        f"sentences:               {len(res.sentences)} (offsets asserted for every one)",
        f"model column filled:     {sum(1 for r in recs if r['model_raw'])}",
        f"AD number filled:        {sum(1 for r in recs if r['ad_number'])}",
        f"fr_citation unparsed:    {sum(1 for r in recs if not r['fr_citation'])}",
        f"docket classes:          {dict(sorted(cls.items()))}",
        f"is_duplicate rows:       {sum(1 for r in recs if r['is_duplicate'])}",
    ]
    for fld in ("issue_date", "citation_publish_date", "comments_due_original"):
        bad = [i for i in res.load.date_issues if i.field == fld]
        lines.append(f"{fld + ':':24s} missing {res.load.date_missing.get(fld, 0)}, unparseable {len(bad)} "
                     f"{[(i.record_id, i.raw) for i in bad]}")  # fmt: skip
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, default=repo_path("raw_xlsx"))
    parser.add_argument("--db", type=Path, default=repo_path("sqlite_path"))
    parser.add_argument("--no-docs", action="store_true", help="skip regenerating alias yaml and audit docs")
    parser.add_argument("--no-dense", action="store_true", help="skip building/refreshing the dense embeddings")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.xlsx.exists():
        raise SystemExit(f"Source workbook not found: {args.xlsx}")
    res = ingest(args.xlsx, args.db, write_docs=not args.no_docs)
    print(quality_summary(res))
    if res.extract:
        print(summary_text(res.extract))
    print(f"\nwrote {args.db.relative_to(ROOT) if args.db.is_relative_to(ROOT) else args.db} (incl. FTS5 indexes)")
    if not args.no_dense:
        conn = sqlite3.connect(args.db)
        try:
            dense = load_dense(conn)  # cached by a version hash of the embedded texts; rebuilt only when it changes
        finally:
            conn.close()
        state = "rebuilt" if dense.rebuilt else "up to date (hash match)"
        print(f"dense index: {len(dense.ids)} sentences, backend {dense.backend}, {state}")


if __name__ == "__main__":
    main()
