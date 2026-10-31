"""SQLite persistence. Callers build into a temp file and swap it in with `swap_in` (idempotent)."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from backend.app.ingest.loader import EXPECTED_COLUMNS, raw_name

CLEAN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("id", "TEXT PRIMARY KEY"),
    ("docket", "TEXT NOT NULL"),
    ("subject_heading", "TEXT"),
    ("issue_date", "TEXT"),
    ("citation_publish_date", "TEXT"),
    ("comments_due_original", "TEXT"),
    ("comments_due_effective", "TEXT"),
    ("make_raw", "TEXT"),
    ("make_canonical", "TEXT"),
    ("make_family", "TEXT"),
    ("model_raw", "TEXT"),
    ("product_type", "TEXT"),
    ("product_subtype", "TEXT"),
    ("ad_number", "TEXT"),
    ("citation_text", "TEXT"),
    ("fr_citation", "TEXT"),
    ("pages", "TEXT"),
    ("url", "TEXT"),
    ("summary", "TEXT"),
    ("summary_missing", "INTEGER NOT NULL"),
    ("comments", "TEXT"),
    ("source_status", "TEXT"),
    ("status_label", "TEXT NOT NULL CHECK (status_label = 'PROPOSED')"),
    ("docket_class", "TEXT NOT NULL"),
    ("is_duplicate", "INTEGER NOT NULL"),
    ("duplicate_of", "TEXT"),
    ("row_hash", "TEXT NOT NULL"),
)
RECORD_COLUMNS = [c for c, _ in CLEAN_COLUMNS] + [raw_name(c) for c in EXPECTED_COLUMNS]

SCHEMA = f"""
CREATE TABLE records (
  {", ".join(f"{c} {t}" for c, t in CLEAN_COLUMNS)},
  {", ".join(f"{raw_name(c)} TEXT" for c in EXPECTED_COLUMNS)}
);
CREATE TABLE sentences (
  id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), idx INTEGER NOT NULL,
  text TEXT NOT NULL, "start" INTEGER NOT NULL, "end" INTEGER NOT NULL
);
CREATE TABLE record_makes (
  record_id TEXT NOT NULL REFERENCES records(id), position INTEGER NOT NULL,
  make_canonical TEXT NOT NULL, make_family TEXT NOT NULL, PRIMARY KEY (record_id, position)
);
CREATE TABLE vocab (
  kind TEXT NOT NULL CHECK (kind IN ('make', 'family', 'model')), canonical TEXT NOT NULL,
  family TEXT, aliases_json TEXT NOT NULL, record_count INTEGER NOT NULL, PRIMARY KEY (kind, canonical)
);
CREATE TABLE docket_groups (
  docket TEXT PRIMARY KEY, class TEXT NOT NULL, n_rows INTEGER NOT NULL, record_ids_json TEXT NOT NULL, note TEXT
);
CREATE TABLE ingest_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX idx_sentences_record ON sentences(record_id);
CREATE INDEX idx_record_makes_make ON record_makes(make_canonical);
"""


def _insert(conn: sqlite3.Connection, table: str, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    cols = ", ".join(f'"{c}"' for c in columns)
    marks = ", ".join("?" for _ in columns)
    conn.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", ([r[c] for c in columns] for r in rows))


def write_database(
    path: Path,
    records: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
    record_makes: list[dict[str, Any]],
    vocab: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    meta: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        _insert(conn, "records", RECORD_COLUMNS, records)
        _insert(conn, "sentences", ["id", "record_id", "idx", "text", "start", "end"], sentences)
        _insert(conn, "record_makes", ["record_id", "position", "make_canonical", "make_family"], record_makes)
        _insert(conn, "vocab", ["kind", "canonical", "family", "aliases_json", "record_count"], vocab)
        _insert(conn, "docket_groups", ["docket", "class", "n_rows", "record_ids_json", "note"], groups)
        _insert(conn, "ingest_meta", ["key", "value"], ({"key": k, "value": v} for k, v in sorted(meta.items())))
        conn.commit()
    finally:
        conn.close()


def temp_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".tmp")


def swap_in(tmp: Path, path: Path) -> None:
    """Atomically replace the live DB with a fully built one."""
    os.replace(tmp, path)


def dump_tables(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every table's rows in primary-key order; used to prove idempotency."""
    conn = sqlite3.connect(path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in tables}
    finally:
        conn.close()


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
