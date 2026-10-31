"""Record status and lineage (SPEC S4). Pure code over the EngineIndex; every fact carries its extraction id."""

from __future__ import annotations

from datetime import date

from backend.app.engine.data import EngineIndex
from backend.app.engine.types import EngineRecord, Lineage, LineageRef, RecordStatus


def record_status(rec: EngineRecord, index: EngineIndex, as_of: date) -> RecordStatus:
    due = rec.comments_due_effective
    if due is None:
        period = "UNKNOWN"
    else:
        period = "OPEN" if as_of <= date.fromisoformat(due) else "CLOSED"
    withdrawn_by = tuple(
        LineageRef(src, ref.extraction_id, ref.evidence_id, True, (src,))
        for src, ref in index.withdrawn_by_docket.get(rec.docket, ())
    )
    return RecordStatus("PROPOSED", period, bool(withdrawn_by), due, withdrawn_by)  # type: ignore[arg-type]


def _resolve_ads(refs: tuple[LineageRef, ...], index: EngineIndex) -> tuple[LineageRef, ...]:
    """target_in_dataset only when a record's AD Number column equals the AD; nothing is inferred otherwise."""
    out = []
    for ref in refs:
        targets = index.records_by_ad_number.get(ref.value, ())
        out.append(LineageRef(ref.value, ref.extraction_id, ref.evidence_id, bool(targets), targets))
    return tuple(out)


def latest_in_group(rec: EngineRecord, index: EngineIndex) -> tuple[str, ...]:
    """Non-duplicate record(s) with the latest citation_publish_date in the docket group (ties: all of them)."""
    live = [index.records[i] for i in index.by_docket[rec.docket] if not index.records[i].is_duplicate]
    dated = [r for r in live if r.citation_publish_date]
    if not dated:
        return ()
    newest = max(r.citation_publish_date for r in dated)  # type: ignore[type-var]
    return tuple(r.id for r in dated if r.citation_publish_date == newest)


def lineage(rec: EngineRecord, index: EngineIndex) -> Lineage:
    superseded_by: tuple[LineageRef, ...] = ()
    if rec.ad_number:
        superseded_by = tuple(
            LineageRef(src, ref.extraction_id, ref.evidence_id, True, (src,))
            for src, ref in index.supersede_refs_by_ad.get(rec.ad_number, ())
            if src != rec.id
        )
    corrections = [
        LineageRef(ref.value, ref.extraction_id, ref.evidence_id, ref.value in index.by_docket,
                   index.by_docket.get(ref.value, ()))
        for ref in rec.corrections
    ]  # fmt: skip
    corrections += [  # records in the dataset that correct this record's docket
        LineageRef(src, ref.extraction_id, ref.evidence_id, True, (src,))
        for src, ref in index.corrected_by_docket.get(rec.docket, ())
        if src != rec.id
    ]
    latest = latest_in_group(rec, index)
    return Lineage(
        supersedes_ad=_resolve_ads(rec.supersedes, index),
        continues_ad=_resolve_ads(rec.continues, index),
        superseded_by_proposal=superseded_by,
        same_docket_group=index.by_docket[rec.docket],
        corrections=tuple(corrections),
        is_latest_in_docket_group=rec.id in latest and not rec.is_duplicate,
        latest_in_docket_group=latest,
    )
