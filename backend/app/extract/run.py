"""Extraction stage: python -m backend.app.extract.run [--db PATH] [--no-docs]

Reads records + sentences from the ingest DB and (re)creates, idempotently:
  extractions, lineage_edges, record_flags, vocab rows of kind model/family;
  records.comments_due_effective (comment extensions applied);
  data/processed/coverage_report.json, docs/unextracted.md, docs/extraction_spotcheck.csv (only if absent).
Rules only, no LLM (SPEC H2).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.config import ROOT, repo_path
from backend.app.extract import lineage, models, serials
from backend.app.extract.types import Extraction, Sent
from backend.app.schemas import CoverageMetric, CoverageReport

UNEXTRACTED_PATH = ROOT / "docs" / "unextracted.md"
SPOTCHECK_PATH = ROOT / "docs" / "extraction_spotcheck.csv"
SPOTCHECK_SIZE = 25
SPOTCHECK_SEED = 20261031
CONF_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

SCHEMA = """
DROP TABLE IF EXISTS extractions;
DROP TABLE IF EXISTS lineage_edges;
DROP TABLE IF EXISTS record_flags;
DELETE FROM vocab WHERE kind IN ('model', 'family');
CREATE TABLE extractions (
  id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), field TEXT NOT NULL, value_json TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('column', 'summary', 'comments')), sentence_id TEXT, span_start INTEGER,
  span_end INTEGER, rule_id TEXT NOT NULL, confidence TEXT NOT NULL CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW'))
);
CREATE TABLE lineage_edges (
  id INTEGER PRIMARY KEY, src_record TEXT NOT NULL REFERENCES records(id), relation TEXT NOT NULL,
  target_ref TEXT NOT NULL, target_in_dataset INTEGER NOT NULL, target_record_id TEXT, extraction_id TEXT,
  detail TEXT
);
CREATE TABLE record_flags (
  record_id TEXT PRIMARY KEY REFERENCES records(id), model_list_confidence TEXT, models_json TEXT NOT NULL,
  families_json TEXT NOT NULL, applies_all_families_json TEXT NOT NULL, qualifier_certain INTEGER NOT NULL,
  serial_resolved INTEGER NOT NULL, svcinfo_defined INTEGER NOT NULL, is_withdrawal_notice INTEGER NOT NULL,
  withdrawn_by_json TEXT NOT NULL
);
CREATE INDEX idx_extractions_record ON extractions(record_id, field);
CREATE INDEX idx_edges_src ON lineage_edges(src_record);
CREATE INDEX idx_edges_target ON lineage_edges(target_record_id);
"""


@dataclass
class Rec:
    id: str
    docket: str
    issue_date: str | None
    model_raw: str | None
    summary: str | None
    comments: str | None
    comments_due_original: str | None
    is_duplicate: bool
    product_type: str | None
    docket_class: str
    make_canonical: str | None
    subject_heading: str | None
    ad_number: str | None
    sentences: list[Sent] = field(default_factory=list)


def load(conn: sqlite3.Connection) -> list[Rec]:
    cols = (
        "id, docket, issue_date, model_raw, summary, comments, comments_due_original, is_duplicate, product_type, "
        "docket_class, make_canonical, subject_heading, ad_number"
    )
    recs = [Rec(*row[:7], bool(row[7]), *row[8:]) for row in conn.execute(f"SELECT {cols} FROM records ORDER BY id")]
    by_id = {r.id: r for r in recs}
    query = 'SELECT id, record_id, text, "start" FROM sentences ORDER BY record_id, idx'
    for sid, rid, text, start in conn.execute(query):
        by_id[rid].sentences.append(Sent(sid, text, start))
    return recs


def extract_record(rec: Rec) -> list[Extraction]:
    out: list[Extraction] = models.models_from_column(rec.id, rec.model_raw)
    summary_models: list[Extraction] = []
    serial_ex: list[Extraction] = []
    svc: list[Extraction] = []
    other: list[Extraction] = []
    withdrawal: list[Extraction] = []
    for s in rec.sentences:
        summary_models += models.models_from_sentence(rec.id, s)
        serial_ex += serials.serials_from_sentence(rec.id, s)
        svc += serials.svcinfo_from_sentence(rec.id, s)
        other += lineage.supersession_from_sentence(rec.id, s)
        other += lineage.continuation_from_sentence(rec.id, s)
        other += lineage.applicability_change_from_sentence(rec.id, s)
        if not withdrawal:
            withdrawal = lineage.withdrawal_from_sentence(rec.id, rec.docket, s)
        if not any(e.rule_id == "extension.notice" for e in other):
            other += lineage.extension_notice_from_sentence(rec.id, s)
    resolved = [e for e in serial_ex if not e.value.get("excluded")]
    out += models.dedupe_models(summary_models) + serial_ex + ([] if resolved else svc[:1]) + other + withdrawal
    out += lineage.from_comments(rec.id, rec.comments)
    return out


def _edges(recs: list[Rec], ex: list[tuple[str, Extraction]]) -> list[dict[str, Any]]:
    by_id = {r.id: r for r in recs}
    by_docket: dict[str, list[Rec]] = defaultdict(list)
    for r in recs:
        by_docket[r.docket].append(r)
    ad_to_record = {r.ad_number: r.id for r in recs if r.ad_number}
    notices = {e.record_id for _, e in ex if e.rule_id == "withdraw.notice"}
    first_ad: dict[str, str] = {}
    for _, e in ex:
        if e.field in ("supersedes_ad", "continues_ad") and e.value.get("ad_number"):
            first_ad.setdefault(e.record_id, f"AD {e.value['ad_number']}")
    edges: list[dict[str, Any]] = []

    def add(src: str, rel: str, ref: str, target: str | None, eid: str | None, detail: Any = None) -> None:
        edges.append({"src_record": src, "relation": rel, "target_ref": ref, "target_in_dataset": target is not None,
                      "target_record_id": target, "extraction_id": eid,
                      "detail": json.dumps(detail, sort_keys=True) if detail is not None else None})  # fmt: skip

    for eid, e in ex:
        v = e.value
        if e.field in ("supersedes_ad", "continues_ad") and v.get("ad_number"):
            rel = "supersedes" if e.field == "supersedes_ad" else "continues"
            add(e.record_id, rel, f"AD {v['ad_number']}", ad_to_record.get(v["ad_number"]), eid)
        elif e.field == "applicability_change":
            rec = by_id[e.record_id]
            add(e.record_id, "applicability_change", first_ad.get(e.record_id, rec.docket), None, eid, v)
        elif e.field == "withdraws_docket":
            src = by_id[e.record_id]
            targets = [
                r for r in by_docket.get(v["docket"], [])
                if r.id != src.id and r.id not in notices and (r.issue_date or "") <= (src.issue_date or "9999")
            ]  # fmt: skip
            for t in targets:
                add(src.id, "withdraws", v["docket"], t.id, eid)
            if not targets:
                add(src.id, "withdraws", v["docket"], None, eid)
        elif e.field == "comment_extension" and v.get("self_notice"):
            src = by_id[e.record_id]
            targets = [r for r in by_docket[src.docket] if r.id != src.id and r.id not in notices]
            for t in targets:
                add(src.id, "comment_extension", src.docket, t.id, eid, v)
            if not targets:
                add(src.id, "comment_extension", src.docket, None, eid, v)
        elif e.field == "comment_extension":
            add(e.record_id, "comment_extension", by_id[e.record_id].docket, e.record_id, eid, v)
        elif e.field == "correction_of":
            base = [r for r in by_docket.get(v["docket"], [])]
            add(e.record_id, "correction_of", v["docket"], base[0].id if base else None, eid, v)
    for docket, group in sorted(by_docket.items()):
        if len(group) < 2:
            continue
        for a in group:
            for b in group:
                if a.id != b.id:
                    add(a.id, "shares_docket", docket, b.id, None, {"docket_class": a.docket_class})
    for i, e in enumerate(edges, 1):
        e["id"] = i
    return edges


def _flags(recs: list[Rec], ex: list[tuple[str, Extraction]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    per: dict[str, list[Extraction]] = defaultdict(list)
    for _, e in ex:
        per[e.record_id].append(e)
    withdrawn_by: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge["relation"] == "withdraws" and edge["target_record_id"]:
            withdrawn_by[edge["target_record_id"]].append(edge["src_record"])
    rows = []
    for r in recs:
        es = per[r.id]
        model_ex = [e for e in es if e.field == "model" and e.value.get("model")]
        best = max((CONF_RANK[e.confidence] for e in model_ex), default=0)
        conf = {3: "HIGH", 2: "MEDIUM", 1: "LOW", 0: None}[best]
        model_list: dict[str, str] = {}
        for e in model_ex:
            m = e.value["model"]
            if CONF_RANK[e.confidence] > CONF_RANK.get(model_list.get(m, "LOW"), 0) or m not in model_list:
                model_list[m] = e.confidence
        rows.append({
            "record_id": r.id,
            "model_list_confidence": conf,
            "models_json": json.dumps([{"model": m, "confidence": c} for m, c in model_list.items()]),
            "families_json": json.dumps(sorted({models.family(m) for m in model_list})),
            "applies_all_families_json": json.dumps(
                sorted({e.value["family"] for e in es if e.field == "applies_all_of_family"})
            ),
            "qualifier_certain": any(e.field == "qualifier_certain" for e in es),
            "serial_resolved": any(e.field in ("serial_range", "serial_list") for e in es),
            "svcinfo_defined": any(e.field == "applicability_defined_by_service_info" for e in es),
            "is_withdrawal_notice": any(e.field == "withdraws_docket" for e in es),
            "withdrawn_by_json": json.dumps(sorted(set(withdrawn_by.get(r.id, [])))),
        })  # fmt: skip
    return rows


def _vocab(recs: list[Rec], ex: list[tuple[str, Extraction]]) -> list[dict[str, Any]]:
    live = {r.id for r in recs if not r.is_duplicate}
    model_recs: dict[str, set[str]] = defaultdict(set)
    model_aliases: dict[str, set[str]] = defaultdict(set)
    for _, e in ex:
        if e.field == "model" and e.value.get("model") and e.confidence != "LOW" and e.record_id in live:
            model_recs[e.value["model"]].add(e.record_id)
            model_aliases[e.value["model"]].add(e.value.get("raw") or e.value["model"])
    fam_recs: dict[str, set[str]] = defaultdict(set)
    fam_models: dict[str, set[str]] = defaultdict(set)
    for m, rs in model_recs.items():
        fam_recs[models.family(m)] |= rs
        fam_models[models.family(m)].add(m)
    rows = [{"kind": "model", "canonical": m, "family": models.family(m),
             "aliases_json": json.dumps(sorted(model_aliases[m]), ensure_ascii=False), "record_count": len(rs)}
            for m, rs in sorted(model_recs.items())]  # fmt: skip
    rows += [{"kind": "family", "canonical": f, "family": f, "aliases_json": json.dumps(sorted(fam_models[f])),
              "record_count": len(rs)} for f, rs in sorted(fam_recs.items())]  # fmt: skip
    return rows


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0])
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        ([row[c] for c in cols] for row in rows),
    )


# ------------------------------------------------------------------ coverage and reports

COVERAGE_LABELS = [
    ("models_extracted", "Model list extracted (any source)"),
    ("models_high", "Model list from the Model column (HIGH)"),
    ("models_medium_only", "Model list from Summary only (MEDIUM)"),
    ("serial_resolved", "Serial constraint resolved"),
    ("svcinfo_defined", "Applicability defined by service information"),
    ("supersession_edge", "Supersession edge (numbered AD)"),
    ("empty_summary", "Empty summary"),
    ("withdrawn", "Withdrawn or a withdrawal notice"),
]


def coverage(
    recs: list[Rec], flags: list[dict[str, Any]], edges: list[dict[str, Any]], source_tag: str
) -> CoverageReport:
    live = [r for r in recs if not r.is_duplicate]
    f = {row["record_id"]: row for row in flags}
    sup = {e["src_record"] for e in edges if e["relation"] == "supersedes"}
    tests = {
        "models_extracted": lambda r: f[r.id]["model_list_confidence"] in ("HIGH", "MEDIUM"),
        "models_high": lambda r: f[r.id]["model_list_confidence"] == "HIGH",
        "models_medium_only": lambda r: f[r.id]["model_list_confidence"] == "MEDIUM",
        "serial_resolved": lambda r: bool(f[r.id]["serial_resolved"]),
        "svcinfo_defined": lambda r: bool(f[r.id]["svcinfo_defined"]),
        "supersession_edge": lambda r: r.id in sup,
        "empty_summary": lambda r: not r.summary,
        "withdrawn": lambda r: bool(f[r.id]["is_withdrawal_notice"]) or f[r.id]["withdrawn_by_json"] != "[]",
    }
    notes = {
        "models_extracted": "HIGH or MEDIUM model designators; LOW-only records (non-designator column text, "
        "orphan suffixes) do not count.",
        "serial_resolved": "No summary in the dataset states an explicit serial range or list.",
        "svcinfo_defined": "Strict wording only (products identified in service information/bulletins).",
        "supersession_edge": "Targets are never in this dataset (no NPRM's final AD number is cited).",
        "withdrawn": "Record is a withdrawal notice or is withdrawn by a later notice in the same docket.",
    }
    metrics = [
        CoverageMetric(key=k, label=label, numerator=sum(1 for r in live if tests[k](r)), denominator=len(live),
                       note=notes.get(k, ""))
        for k, label in COVERAGE_LABELS
    ]  # fmt: skip
    limits = [
        "Every record is a Notice of Proposed Rulemaking. None is in force.",
        "Only the Summary is free text; there is no full notice text, so compliance steps, part numbers and torque "
        "values cannot be answered.",
        "No summary states explicit serial ranges, so serial-level applicability is UNDETERMINED for every record.",
        "No superseded AD is in this dataset: AD Trace says 'would supersede AD X', never 'AD X is superseded'.",
        "Model lists from the Summary (MEDIUM) depend on regex rules; spot-check precision in "
        "docs/extraction_spotcheck.csv.",
        f"Denominator: {len(live)} non-duplicate records of {len(recs)}.",
    ]
    return CoverageReport(generated_at=source_tag, total_records=len(recs), metrics=metrics, limits=limits)


def coverage_table(report: CoverageReport) -> str:
    lines = [f"{'metric':52} {'n':>5} / {'d':<5} {'%':>6}"]
    for m in report.metrics:
        pct = 100 * m.numerator / m.denominator if m.denominator else 0.0
        lines.append(f"{m.label:52} {m.numerator:5d} / {m.denominator:<5d} {pct:6.1f}")
    return "\n".join(lines)


def _group_label(r: Rec, flags: dict[str, dict[str, Any]]) -> dict[str, str]:
    year = (r.issue_date or "????")[:4]
    era = "2020+" if year >= "2020" else "2010-2019" if year >= "2010" else "pre-2010"
    kind = "withdrawal notice" if flags[r.id]["is_withdrawal_notice"] else "proposal/revision/other"
    return {"product type": r.product_type or "(none)", "era": era, "notice kind": kind}


def weakness_breakdown(recs: list[Rec], flags: list[dict[str, Any]]) -> str:
    f = {row["record_id"]: row for row in flags}
    live = [r for r in recs if not r.is_duplicate]
    out = []
    for dim in ("product type", "era", "notice kind"):
        tot: Counter[str] = Counter()
        hit: Counter[str] = Counter()
        for r in live:
            g = _group_label(r, f)[dim]
            tot[g] += 1
            hit[g] += f[r.id]["model_list_confidence"] in ("HIGH", "MEDIUM")
        rows = sorted(tot, key=lambda g: hit[g] / tot[g])
        out.append(f"model list extracted, by {dim}:")
        out += [f"  {g:28} {hit[g]:4d} / {tot[g]:<4d} {100 * hit[g] / tot[g]:5.1f}%" for g in rows]
    return "\n".join(out)


def unextracted_md(recs: list[Rec], flags: list[dict[str, Any]], breakdown: str) -> str:
    f = {row["record_id"]: row for row in flags}
    rows = [r for r in recs if not r.is_duplicate and f[r.id]["model_list_confidence"] not in ("HIGH", "MEDIUM")]
    lines = [
        "# Records with no model extracted",
        "",
        "_AUTO-GENERATED by the extraction stage (`make ingest`). Non-duplicate records whose model list is empty or "
        "LOW-only._",
        "",
        f"**{len(rows)}** records. For these, applicability can only be UNDETERMINED or NOT_CHECKED.",
        "",
        "```",
        breakdown,
        "```",
        "",
        "| Record | Docket | Make | Kind | Likely reason | Summary starts |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        s = r.summary or ""
        if not s:
            reason = "empty summary"
        elif "products listed above" in s:
            reason = 'summary says "products listed above"'
        elif "Model" not in s:
            reason = "no 'Model' phrase in summary"
        else:
            reason = "Model phrase not parsed by rules"
        kind = "withdrawal notice" if f[r.id]["is_withdrawal_notice"] else "proposal/other"
        cell = s[:110].replace("|", "\\|")
        make = (r.make_canonical or "").replace("|", "\\|")
        lines.append(f"| {r.id} | {r.docket} | {make} | {kind} | {reason} | {cell} |")
    return "\n".join(lines) + "\n"


def spotcheck_rows(recs: list[Rec], ex: list[tuple[str, Extraction]]) -> list[dict[str, str]]:
    by_sent = {s.id: s.text for r in recs for s in r.sentences}
    by_id = {r.id: r for r in recs}
    rng = random.Random(SPOTCHECK_SEED)
    sample = rng.sample(ex, min(SPOTCHECK_SIZE, len(ex)))
    rows = []
    for eid, e in sorted(sample, key=lambda t: t[0]):
        if e.source == "summary":
            evidence = by_sent.get(e.sentence_id or "", "")
        elif e.source == "comments":
            evidence = by_id[e.record_id].comments or ""
        else:
            evidence = f"[Model column] {by_id[e.record_id].model_raw}"
        rows.append({"extraction_id": eid, "record_id": e.record_id, "field": e.field, "rule_id": e.rule_id,
                     "confidence": e.confidence, "evidence_text": evidence,
                     "extracted_value": json.dumps(e.value, ensure_ascii=False, sort_keys=True),
                     "correct (Y/N)": ""})  # fmt: skip
    return rows


# ------------------------------------------------------------------ entry points


@dataclass
class ExtractResult:
    extractions: list[tuple[str, Extraction]]
    edges: list[dict[str, Any]]
    flags: list[dict[str, Any]]
    report: CoverageReport
    breakdown: str
    spotcheck_written: bool


def extract_db(db_path: Path, write_docs: bool = True, coverage_path: Path | None = None) -> ExtractResult:
    conn = sqlite3.connect(db_path)
    try:
        recs = load(conn)
        all_ex = [e for r in recs for e in extract_record(r)]
        ex = [(f"E{i:05d}", e) for i, e in enumerate(all_ex, 1)]
        edges = _edges(recs, ex)
        flags = _flags(recs, ex, edges)
        vocab = _vocab(recs, ex)
        source_tag = "ingest of " + (conn.execute("SELECT value FROM ingest_meta WHERE key='source_sha1'").fetchone()
                                     or ["unknown"])[0][:12]  # fmt: skip
        conn.executescript(SCHEMA)
        _insert(conn, "extractions", [
            {"id": eid, "record_id": e.record_id, "field": e.field,
             "value_json": json.dumps(e.value, ensure_ascii=False, sort_keys=True), "source": e.source,
             "sentence_id": e.sentence_id, "span_start": e.span_start, "span_end": e.span_end, "rule_id": e.rule_id,
             "confidence": e.confidence}
            for eid, e in ex
        ])  # fmt: skip
        _insert(conn, "lineage_edges", edges)
        _insert(conn, "record_flags", flags)
        _insert(conn, "vocab", vocab)
        conn.execute("UPDATE records SET comments_due_effective = comments_due_original")
        for _, e in ex:
            if e.field == "comment_extension" and e.value.get("comments_due"):
                conn.execute("UPDATE records SET comments_due_effective = ? WHERE id = ?",
                             (e.value["comments_due"], e.record_id))  # fmt: skip
        conn.commit()
    finally:
        conn.close()

    report = coverage(recs, flags, edges, source_tag)
    breakdown = weakness_breakdown(recs, flags)
    spot_written = False
    if write_docs or coverage_path:
        path = coverage_path or repo_path("coverage_report")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    if write_docs:
        UNEXTRACTED_PATH.write_text(unextracted_md(recs, flags, breakdown), encoding="utf-8", newline="\n")
        if not SPOTCHECK_PATH.exists():  # never overwrite a hand-filled spot-check
            with SPOTCHECK_PATH.open("w", encoding="utf-8", newline="") as fh:
                rows = spotcheck_rows(recs, ex)
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            spot_written = True
    return ExtractResult(ex, edges, flags, report, breakdown, spot_written)


def summary_text(res: ExtractResult) -> str:
    rules = Counter(e.rule_id for _, e in res.extractions)
    rel = Counter(e["relation"] for e in res.edges)
    lines = ["", "=== Extraction ===", f"extractions: {len(res.extractions)}; lineage edges: {len(res.edges)}"]
    lines += [f"  {k:32} {v}" for k, v in sorted(rules.items())]
    lines += ["edges by relation: " + ", ".join(f"{k}={v}" for k, v in sorted(rel.items()))]
    lines += ["", "=== Coverage (non-duplicate records) ===", coverage_table(res.report), "", res.breakdown]
    if res.spotcheck_written:
        lines.append(f"\nwrote {SPOTCHECK_PATH.relative_to(ROOT)} (fill the 'correct (Y/N)' column by hand)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=repo_path("sqlite_path"))
    parser.add_argument("--no-docs", action="store_true")
    args = parser.parse_args(argv)
    print(summary_text(extract_db(args.db, write_docs=not args.no_docs)))


if __name__ == "__main__":
    main()
