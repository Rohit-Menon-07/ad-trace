"""Load the NPRM workbook. Every raw column is kept untouched as raw_<snake_name>; cleaned fields are added."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.ingest.clean import clean_text, fr_citation, parse_mdy, parse_pages

log = logging.getLogger(__name__)

EXPECTED_COLUMNS = (
    "Docket Number", "Subject Heading", "Status", "CFR Part Reference", "Issue Date", "Service/Office",
    "Office of Primary Responsibility", "AD Number", "Citation Publish Date", "Comments Due Date", "Make", "Model",
    "Product Type", "Product Subtype", "AC Reference", "AIR Policy Reference", "Additional Reference",
    "Link for Submitting Public Comment", "Citation", "Page Number", "Summary", "Comments",
)  # fmt: skip

DATE_FIELDS = {
    "issue_date": "Issue Date",
    "citation_publish_date": "Citation Publish Date",
    "comments_due_original": "Comments Due Date",
}


def raw_name(column: str) -> str:
    """'Link for Submitting Public Comment' -> 'raw_link_for_submitting_public_comment'."""
    return "raw_" + re.sub(r"[^0-9a-z]+", "_", column.lower()).strip("_")


@dataclass
class DateIssue:
    record_id: str
    field: str
    raw: str


@dataclass
class LoadResult:
    records: list[dict[str, Any]]
    date_issues: list[DateIssue] = field(default_factory=list)
    date_missing: dict[str, int] = field(default_factory=dict)


def read_workbook(path: Path) -> pd.DataFrame:
    """Read the first sheet as strings. keep_default_na=False so text like "NA" is never turned into null."""
    df = pd.read_excel(path, dtype=str, keep_default_na=False, na_values=[])
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Workbook is missing columns: {missing}")
    return df


def row_hash(raw: dict[str, str | None]) -> str:
    payload = json.dumps([[c, raw[c]] for c in EXPECTED_COLUMNS], ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _raw_value(value: object) -> str | None:
    """Untouched cell text; only a truly empty cell becomes None."""
    text = "" if value is None else str(value)
    return text if text != "" else None


def build_record(idx: int, raw: dict[str, str | None], result: LoadResult) -> dict[str, Any]:
    record_id = f"R{idx + 1:04d}"
    rec: dict[str, Any] = {"id": record_id}
    rec.update({raw_name(c): raw[c] for c in EXPECTED_COLUMNS})

    for fld, col in DATE_FIELDS.items():
        cleaned = clean_text(raw[col])
        parsed: date | None = parse_mdy(cleaned)
        if cleaned is None:
            result.date_missing[fld] = result.date_missing.get(fld, 0) + 1
        elif parsed is None:
            result.date_issues.append(DateIssue(record_id, fld, cleaned))
            log.warning("%s: unparseable %s %r -> null", record_id, fld, cleaned)
        rec[fld] = parsed.isoformat() if parsed else None
    rec["comments_due_effective"] = rec["comments_due_original"]  # extensions applied in Prompt 4

    summary = clean_text(raw["Summary"])
    pages = parse_pages(clean_text(raw["Page Number"]))
    citation = clean_text(raw["Citation"])
    rec.update(
        docket=clean_text(raw["Docket Number"]),
        subject_heading=clean_text(raw["Subject Heading"]),
        source_status=clean_text(raw["Status"]),
        make_raw=clean_text(raw["Make"]),
        model_raw=clean_text(raw["Model"]),
        product_type=clean_text(raw["Product Type"]),
        product_subtype=clean_text(raw["Product Subtype"]),
        ad_number=clean_text(raw["AD Number"]),
        citation_text=citation,
        pages=pages,
        fr_citation=fr_citation(citation, pages),
        url=clean_text(raw["Link for Submitting Public Comment"]),
        summary=summary,
        summary_missing=summary is None,
        comments=clean_text(raw["Comments"]),
        status_label="PROPOSED",
        row_hash=row_hash(raw),
    )
    return rec


def load_records(path: Path) -> LoadResult:
    df = read_workbook(path)
    result = LoadResult(records=[])
    for idx, row in enumerate(df.itertuples(index=False)):
        raw = {c: _raw_value(v) for c, v in zip(df.columns, row, strict=True) if c in EXPECTED_COLUMNS}
        result.records.append(build_record(idx, raw, result))
    return result
