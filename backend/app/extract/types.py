"""Shared types for rule-based extraction. Every extraction carries provenance (SPEC §5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Source = Literal["column", "summary", "comments"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True)
class Sent:
    """A stored sentence: offsets are into the record Summary."""

    id: str
    text: str
    start: int


@dataclass(frozen=True)
class Extraction:
    record_id: str
    field: str
    value: Any  # JSON-serialisable
    source: Source
    sentence_id: str | None
    span_start: int | None  # Summary offsets for source=summary; Comments offsets for source=comments
    span_end: int | None
    rule_id: str
    confidence: Confidence


def from_sentence(
    record_id: str, sent: Sent, start: int, end: int, field: str, value: Any, rule_id: str, confidence: Confidence
) -> Extraction:
    """Build a summary extraction from offsets local to `sent`."""
    return Extraction(
        record_id, field, value, "summary", sent.id, sent.start + start, sent.start + end, rule_id, confidence
    )
