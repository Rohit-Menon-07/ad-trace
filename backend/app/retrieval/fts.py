"""SQLite FTS5 indexes (sentences and records) and the user-query sanitiser.

Tokenizer: unicode61, diacritics removed, "-" is a token character so "A330-243" and "2024-05-13" are single
tokens. A dedicated `models_norm` column holds norm_model() designators.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import defaultdict

from backend.app.extract.models import norm_model

TOKENIZE = "unicode61 remove_diacritics 2 tokenchars '-'"
SENTENCE_COLUMNS = ("sentence_text", "subject_heading", "make", "models", "models_norm")
RECORD_COLUMNS = ("subject_heading", "make", "models", "summary", "models_norm")

_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*")
STOPWORDS = frozenset(
    """a an and are as at be by can do does for from has have how i in is it its me my of on or our the their this
    to was we what which who why will with would any all there these those about into near not""".split()
)  # also neutralises FTS5 operators (and, or, not, near) that survive tokenisation


def sanitize(query: str | None) -> str | None:
    """User text -> safe FTS5 MATCH expression (OR of quoted tokens), or None if nothing searchable remains.

    Every token is wrapped in double quotes, so quotes, parentheses, '*', ':', '^' and operator words such as
    NEAR/AND/OR/NOT can never reach the FTS5 parser as syntax. Tokens containing a digit (designators, AD
    numbers) also get a prefix match so "A330" finds "A330-243", plus their norm_model() form.
    """
    if not query:
        return None
    text = unicodedata.normalize("NFKC", query)
    terms: list[str] = []
    for tok in _TOKEN.findall(text):
        low = tok.lower()
        if low in STOPWORDS or (len(low) < 2 and not low.isdigit()):
            continue
        terms.append(f'"{low}"')
        if any(ch.isdigit() for ch in low):
            terms.append(f'"{low}"*')
            normed = norm_model(tok).lower()
            if normed and normed != low and _TOKEN.fullmatch(normed):
                terms.append(f'"{normed}"')
    return " OR ".join(dict.fromkeys(terms)) or None


def _record_models(conn: sqlite3.Connection) -> dict[str, tuple[list[str], list[str]]]:
    """record_id -> (raw model strings, normalised HIGH/MEDIUM designators)."""
    raw: dict[str, list[str]] = defaultdict(list)
    norm: dict[str, list[str]] = defaultdict(list)
    for rid, value, conf in conn.execute(
        "SELECT record_id, value_json, confidence FROM extractions WHERE field = 'model' ORDER BY id"
    ):
        v = json.loads(value)
        if v.get("raw"):
            raw[rid].append(v["raw"])
        if v.get("model") and conf in ("HIGH", "MEDIUM"):
            norm[rid].append(v["model"].replace(" ", "_"))  # keep multi-word designators as one token
    return {rid: (raw.get(rid, []), list(dict.fromkeys(norm.get(rid, [])))) for rid in set(raw) | set(norm)}


def build_fts(conn: sqlite3.Connection) -> None:
    """(Re)create sentences_fts and records_fts. Idempotent: dropped and rebuilt every time."""
    conn.executescript(
        f"""
        DROP TABLE IF EXISTS sentences_fts;
        DROP TABLE IF EXISTS records_fts;
        CREATE VIRTUAL TABLE sentences_fts USING fts5(
            sentence_id UNINDEXED, record_id UNINDEXED, {", ".join(SENTENCE_COLUMNS)}, tokenize = "{TOKENIZE}");
        CREATE VIRTUAL TABLE records_fts USING fts5(
            record_id UNINDEXED, {", ".join(RECORD_COLUMNS)}, tokenize = "{TOKENIZE}");
        """
    )
    models = _record_models(conn)
    recs = {
        rid: (subject, make, model_raw, summary)
        for rid, subject, make, model_raw, summary in conn.execute(
            "SELECT id, subject_heading, make_canonical, model_raw, summary FROM records ORDER BY id"
        )
    }

    def model_cols(rid: str, model_raw: str | None) -> tuple[str, str]:
        raw, norm = models.get(rid, ([], []))
        return " ".join(([model_raw] if model_raw else []) + raw), " ".join(norm)

    rows = []
    for sid, rid, text in conn.execute("SELECT id, record_id, text FROM sentences ORDER BY id"):
        subject, make, model_raw, _ = recs[rid]
        m_raw, m_norm = model_cols(rid, model_raw)
        rows.append((sid, rid, text, subject or "", make or "", m_raw, m_norm))
    conn.executemany("INSERT INTO sentences_fts VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    record_rows = []
    for rid, (subject, make, model_raw, summary) in recs.items():
        m_raw, m_norm = model_cols(rid, model_raw)
        # column order: record_id, subject_heading, make, models, summary, models_norm
        record_rows.append((rid, subject or "", make or "", m_raw, summary or "", m_norm))
    conn.executemany("INSERT INTO records_fts VALUES (?, ?, ?, ?, ?, ?)", record_rows)
    conn.commit()


def weights_sql(weights: dict[str, float], columns: tuple[str, ...], leading_unindexed: int) -> str:
    """bm25() argument list: UNINDEXED leading columns get weight 0."""
    return ", ".join(["0.0"] * leading_unindexed + [str(float(weights.get(c, 1.0))) for c in columns])
