"""Builders for API payloads read from SQLite + the engine: RecordCard, RecordDetail, MetaResponse."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.config import load_config, repo_path, resolve_as_of
from backend.app.engine.data import EngineIndex
from backend.app.engine.status import record_status
from backend.app.schemas import (
    CoverageReport,
    Extraction,
    LineageEdge,
    MetaResponse,
    ModelIds,
    RecordCard,
    RecordDetail,
    RecordFull,
    Sentence,
)

_CARD_SQL = (
    "SELECT id, docket, subject_heading, make_canonical, issue_date, fr_citation, citation_text, pages, url, "
    "ad_number, summary, summary_missing, make_raw, model_raw, product_type, citation_publish_date FROM records "
    "WHERE id = ?"
)


def lineage_edges(conn: sqlite3.Connection, record_id: str) -> list[LineageEdge]:
    rows = conn.execute(
        "SELECT l.relation, l.target_ref, l.target_in_dataset, l.target_record_id, e.sentence_id "
        "FROM lineage_edges l LEFT JOIN extractions e ON e.id = l.extraction_id "
        "WHERE l.src_record = ? ORDER BY l.id",
        (record_id,),
    ).fetchall()
    return [
        LineageEdge(relation=r, target_ref=t, target_in_dataset=bool(i), target_record_id=tid, evidence_id=sid)
        for r, t, i, tid, sid in rows
    ]


def record_card(
    conn: sqlite3.Connection, engine: EngineIndex, record_id: str, as_of: date, retrieval_score: float | None = None
) -> RecordCard:
    return RecordCard.model_validate(_card_fields(conn, engine, record_id, as_of, retrieval_score)[0])


def _card_fields(
    conn: sqlite3.Connection, engine: EngineIndex, record_id: str, as_of: date, retrieval_score: float | None
) -> tuple[dict[str, Any], tuple]:
    row = conn.execute(_CARD_SQL, (record_id,)).fetchone()
    if row is None:
        raise KeyError(record_id)
    rid, docket, subject, make, issue, fr, cit, pages, url, ad = row[:10]
    rec = engine.records[rid]
    st = record_status(rec, engine, as_of)
    card = {
        "record_id": rid,
        "docket": docket,
        "subject_heading": subject or "",
        "make": make or "",
        "models": sorted(rec.models),
        "models_confidence": rec.model_list_confidence,
        "status_label": "PROPOSED",
        "withdrawn": st.withdrawn,
        "comment_period": st.comment_period,
        "comments_due": st.comments_due_effective,
        "issue_date": issue,
        "fr_citation": fr or cit or "",
        "pages": pages or "",
        "url": url,
        "ad_number": ad,
        "retrieval_score": retrieval_score,
        "lineage": [e.model_dump() for e in lineage_edges(conn, rid)],
    }
    return card, row


def record_detail(conn: sqlite3.Connection, engine: EngineIndex, record_id: str, as_of: date) -> RecordDetail:
    card, row = _card_fields(conn, engine, record_id, as_of, None)
    summary, missing, make_raw, model_raw, ptype, cpd = row[10:]
    full = RecordFull.model_validate(
        card
        | {
            "summary": summary or "",
            "summary_missing": bool(missing),
            "make_raw": make_raw or "",
            "model_raw": model_raw,
            "product_type": ptype,
            "citation_publish_date": cpd,
        }
    )
    sentences = [
        Sentence(id=i, record_id=r, idx=x, text=t, start=s, end=e)
        for i, r, x, t, s, e in conn.execute(
            'SELECT id, record_id, idx, text, "start", "end" FROM sentences WHERE record_id = ? ORDER BY idx',
            (record_id,),
        )
    ]
    extractions = [
        Extraction(
            id=i,
            record_id=r,
            field=f,
            value_json=json.loads(v),
            source=src,
            sentence_id=sid,
            span_start=a,
            span_end=b,
            rule_id=rule,
            confidence=conf,
        )
        for i, r, f, v, src, sid, a, b, rule, conf in conn.execute(
            "SELECT id, record_id, field, value_json, source, sentence_id, span_start, span_end, rule_id, confidence "
            "FROM extractions WHERE record_id = ? ORDER BY id",
            (record_id,),
        )
    ]
    return RecordDetail(record=full, sentences=sentences, extractions=extractions, lineage=full.lineage, mock=False)


def index_version(conn: sqlite3.Connection) -> str:
    src = (conn.execute("SELECT value FROM ingest_meta WHERE key='source_sha1'").fetchone() or ["?"])[0]
    dense = "none"
    meta = repo_path("embeddings_path").parent / "emb_meta.json"
    if meta.exists():
        dense = json.loads(meta.read_text(encoding="utf-8")).get("version_hash", "none")
    return f"src:{src[:12]} dense:{dense[:12]}"


def meta_response(conn: sqlite3.Connection, embedding_backend: str) -> MetaResponse:
    cfg = load_config()
    total = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    dockets = conn.execute("SELECT COUNT(DISTINCT docket) FROM records").fetchone()[0]
    cov_path = repo_path("coverage_report")
    coverage = (
        CoverageReport.model_validate_json(cov_path.read_text(encoding="utf-8"))
        if cov_path.exists()
        else CoverageReport(
            generated_at="missing: run make ingest",
            total_records=total,
            metrics=[],
            limits=["coverage_report.json not found: run make ingest"],
        )
    )
    m = cfg["models"]
    return MetaResponse(
        dataset=Path(cfg["data"]["raw_xlsx"]).name,
        total_records=total,
        unique_dockets=dockets,
        as_of=resolve_as_of(),
        models=ModelIds(generation=m["generation"], query_parser=m["query_parser"], verifier=m["verifier"]),
        embedding_backend=embedding_backend,
        index_version=index_version(conn),
        coverage=coverage,
        mock=False,
    )
