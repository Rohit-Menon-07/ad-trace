"""Engine data types. Plain frozen dataclasses: the engine is pure code over these (SPEC H2, S4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Literal

Confidence = Literal["HIGH", "MEDIUM", "LOW"]
Verdict = Literal["APPLICABLE", "NOT_APPLICABLE", "UNDETERMINED", "NOT_CHECKED"]
CONF_RANK: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


class Match(StrEnum):
    EXACT = "EXACT"
    FAMILY_ONLY = "FAMILY_ONLY"
    SERIES_OVERLAP = "SERIES_OVERLAP"  # addition to SPEC: listed "A330-900 series" vs query A330-941
    SPELLING_VARIANT = "SPELLING_VARIANT"  # addition: "SA-365N" vs "SA365N"; guards against false NO_MATCH
    NO_MATCH = "NO_MATCH"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LinkedConfig:
    make_canonical: str | None
    model_norm: str | None
    family: str | None
    serial: str | None
    as_of: date


@dataclass(frozen=True)
class Evidence:
    extraction_id: str
    evidence_id: str  # sentence id (R0001#s2) or R0001#col:Model for column extractions
    confidence: Confidence


@dataclass(frozen=True)
class ListedModel:
    model: str
    family: str
    confidence: Confidence
    series: bool  # raw text said "series"
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class SerialConstraint:
    kind: Literal["range", "list"]
    start: str | None
    end: str | None
    serials: tuple[str, ...]
    excluded: bool
    label: str  # human text, e.g. "serial numbers S-1000 through S-1500"
    evidence: Evidence


@dataclass(frozen=True)
class LineageRef:
    value: str  # AD number or docket
    extraction_id: str | None
    evidence_id: str | None
    target_in_dataset: bool = False
    target_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineRecord:
    id: str
    docket: str
    makes: tuple[str, ...]
    make_families: tuple[str, ...]
    ad_number: str | None
    citation_publish_date: str | None
    comments_due_effective: str | None
    is_duplicate: bool
    models: dict[str, ListedModel]  # HIGH/MEDIUM only
    low_tokens: tuple[str, ...]  # LOW model extractions (orphan suffixes, non-designators)
    all_families: dict[str, tuple[Evidence, ...]]  # only families listed as a whole-type designator
    certain: tuple[Evidence, ...]
    serials: tuple[SerialConstraint, ...]
    svcinfo: tuple[Evidence, ...]
    supersedes: tuple[LineageRef, ...]
    continues: tuple[LineageRef, ...]
    corrections: tuple[LineageRef, ...]
    withdraws: tuple[LineageRef, ...]  # dockets this record withdraws

    @property
    def model_list_confidence(self) -> Confidence | None:
        best = max((CONF_RANK[m.confidence] for m in self.models.values()), default=0)
        if best:
            return "HIGH" if best == 3 else "MEDIUM"
        return "LOW" if self.low_tokens else None


@dataclass(frozen=True)
class MatchResult:
    kind: Match
    reason: str
    evidence: tuple[Evidence, ...] = ()
    basis: tuple[Confidence, ...] = ()  # confidences a negative verdict rests on


@dataclass(frozen=True)
class Applicability:
    record_id: str
    verdict: Verdict
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    match: Match | None
    basis: tuple[Confidence, ...] = ()  # for NOT_APPLICABLE: confidences of the evidence it rests on
    rule: str = ""  # which verdict rule fired (for tests and the pipeline trace)


@dataclass(frozen=True)
class RecordStatus:
    status_label: Literal["PROPOSED"]
    comment_period: Literal["OPEN", "CLOSED", "UNKNOWN"]
    withdrawn: bool
    comments_due_effective: str | None
    withdrawn_by: tuple[LineageRef, ...] = ()


@dataclass(frozen=True)
class Lineage:
    supersedes_ad: tuple[LineageRef, ...]
    continues_ad: tuple[LineageRef, ...]
    superseded_by_proposal: tuple[LineageRef, ...]
    same_docket_group: tuple[str, ...]
    corrections: tuple[LineageRef, ...]
    is_latest_in_docket_group: bool
    latest_in_docket_group: tuple[str, ...] = field(default=())
