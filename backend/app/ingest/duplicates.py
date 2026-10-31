"""Duplicate-docket audit. Classifies each docket group; never deletes a row.

Classes (first match wins):
- correction: docket ends in R<n>, or Comments mention an OFR correction.
- exact_duplicate: two or more rows share every key field (KEY_FIELDS); later copies get is_duplicate=True.
- multi_product: rows in the group have different canonical make sets, or two different non-empty Model values.
- revision_series: same docket, different publications (proposal, supplemental/revised NPRM, withdrawal...).
- single: only one row.
Only exact duplicates are marked is_duplicate (excluded from retrieval by default); all rows are kept.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

KEY_FIELDS = ("make_raw", "model_raw", "subject_heading", "summary")
_CORRECTION_DOCKET = re.compile(r"R\d+$")
_OFR_CORRECTION = re.compile(r"\bOFR correction\b", re.IGNORECASE)


@dataclass
class Row:
    record_id: str
    docket: str
    issue_date: date | None
    makes: Sequence[str]
    model_raw: str | None
    comments: str | None
    key: tuple[str | None, ...]


@dataclass
class GroupResult:
    docket: str
    cls: str
    record_ids: list[str]
    duplicate_of: dict[str, str] = field(default_factory=dict)  # duplicate record -> kept record
    note: str = ""


def is_correction(docket: str, comments: str | None) -> bool:
    return bool(_CORRECTION_DOCKET.search(docket)) or bool(comments and _OFR_CORRECTION.search(comments))


def _order(r: Row) -> tuple[date, str]:
    return (r.issue_date or date.max, r.record_id)


def classify_group(docket: str, rows: Sequence[Row]) -> GroupResult:
    ids = [r.record_id for r in rows]
    if any(is_correction(r.docket, r.comments) for r in rows):
        base = _CORRECTION_DOCKET.sub("", docket)
        return GroupResult(docket, "correction", ids, note=f"Base docket {base}")
    if len(rows) == 1:
        return GroupResult(docket, "single", ids)

    dup_of: dict[str, str] = {}
    by_key: dict[tuple[str | None, ...], list[Row]] = {}
    for r in rows:
        by_key.setdefault(r.key, []).append(r)
    for same in by_key.values():
        if len(same) > 1:
            kept, *dups = sorted(same, key=_order)  # earliest issue date is kept
            dup_of.update({d.record_id: kept.record_id for d in dups})
    if dup_of:
        return GroupResult(docket, "exact_duplicate", ids, dup_of, "Earliest issue date kept; later copies marked.")

    make_sets = {tuple(sorted(r.makes)) for r in rows if r.makes}  # per row, so one "A | B" row is not multi
    models = {r.model_raw for r in rows if r.model_raw}
    if len(make_sets) > 1 or len(models) > 1:
        names = sorted(" | ".join(s) for s in make_sets)
        return GroupResult(docket, "multi_product", ids, note=f"Makes: {names}")
    return GroupResult(docket, "revision_series", ids)


def classify_all(rows: Sequence[Row]) -> list[GroupResult]:
    groups: dict[str, list[Row]] = {}
    for r in rows:
        groups.setdefault(r.docket, []).append(r)
    return [classify_group(d, g) for d, g in groups.items()]
