"""Pydantic models for the AD Trace API (docs/SPEC.md section 7).

This module is the single source of truth for the API contract. The frontend types in
frontend/src/types/api.ts are generated from it by `python -m backend.app.export_types`;
a test fails if they drift. Models not defined in SPEC.md are logged in DECISIONS.md.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---- Named literal aliases (also emitted as named TypeScript aliases) ----

Verdict = Literal["APPLICABLE", "NOT_APPLICABLE", "UNDETERMINED", "NOT_CHECKED"]
SearchStatus = Literal["answered", "partial", "refused", "needs_clarification"]
ReasonCode = Literal[
    "UNKNOWN_ENTITY",
    "AMBIGUOUS_MODEL",
    "AMBIGUOUS_MAKE",
    "NO_RETRIEVAL_HIT",
    "LOW_RETRIEVAL_SCORE",
    "EMPTY_SOURCE_TEXT",
    "APPLICABILITY_UNDETERMINED",
    "OUT_OF_SCOPE",
    "CONTRADICTS_RECORD",
    "CONFLICTING_EVIDENCE",
    "INJECTION_SUSPECTED",
    "VERIFICATION_FAILED",
    "LLM_ERROR",
]
LineageRelation = Literal[
    "supersedes",
    "continues",
    "shares_docket",
    "withdraws",
    "comment_extension",
    "correction_of",
    "applicability_change",
]
CommentPeriod = Literal["OPEN", "CLOSED", "UNKNOWN"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
TraceStatus = Literal["ok", "warn", "stop"]


class ApiModel(BaseModel):
    """Base: reject unknown fields; fields with defaults are always present in responses."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


# ---- Requests ----


class SearchRequest(ApiModel):
    query: str
    make: str | None = None
    model: str | None = None
    serial: str | None = None
    as_of: date | None = None
    mode: Literal["answer", "search_only"] = "answer"


class FeedbackRequest(ApiModel):
    request_id: str
    reason: str = Field(min_length=1, max_length=2000)


# ---- Search response ----


class Citation(ApiModel):
    evidence_id: str = Field(description="Sentence id, e.g. R0001#s2.")
    docket: str
    quote: str
    span_start: int | None = Field(description="Offset into the record Summary, for highlighting.")
    span_end: int | None
    fr_citation: str
    pages: str
    url: str | None


class Claim(ApiModel):
    text: str
    citations: list[Citation]
    verification: Literal["verified", "partial"]


class ApplicabilityResult(ApiModel):
    record_id: str
    verdict: Verdict
    reasons: list[str]
    evidence_ids: list[str]


class TraceStep(ApiModel):
    stage: str
    status: TraceStatus
    summary: str
    details: dict[str, Any]
    ms: int


class LineageEdge(ApiModel):
    relation: LineageRelation
    target_ref: str = Field(description='e.g. "AD 2023-14-05" or a docket number.')
    target_in_dataset: bool
    target_record_id: str | None
    evidence_id: str | None = Field(description="Sentence the edge was extracted from.")


class RecordCard(ApiModel):
    record_id: str
    docket: str
    subject_heading: str
    make: str = Field(description="Canonical make.")
    models: list[str] = Field(description="Extracted and suffix-expanded model designators.")
    models_confidence: Confidence | None = Field(description="null = no model list found.")
    status_label: Literal["PROPOSED"]
    withdrawn: bool
    comment_period: CommentPeriod = Field(description="Computed against as_of.")
    comments_due: date | None = Field(description="Effective due date after any extension.")
    issue_date: date | None
    fr_citation: str
    pages: str
    url: str | None
    ad_number: str | None
    retrieval_score: float | None = Field(description="Fused RRF score. Computed, never LLM-reported (H12).")
    lineage: list[LineageEdge]
    docket_group_size: int = Field(1, description="Non-duplicate records sharing this docket (incl. this one).")
    latest_in_docket_group: bool = Field(
        True, description="Latest citation publish date in its docket group (computed by the engine)."
    )


class ExcludedRecord(ApiModel):
    record_id: str
    docket: str
    subject_heading: str
    rule: str = Field(description='Machine rule id, e.g. "S3.hard_filter.model".')
    reason: str = Field(description="Plain-language explanation.")


class SearchResponse(ApiModel):
    request_id: str
    status: SearchStatus
    reason_code: ReasonCode | None
    message: str
    claims: list[Claim]
    rationale_steps: list[str] = Field(
        max_length=5, description="Model-written, max 5, each cites evidence ids like [R0001#s2]."
    )
    records: list[RecordCard]
    applicability: list[ApplicabilityResult]
    excluded: list[ExcludedRecord]
    clarification_options: list[str]
    trace: list[TraceStep] = Field(description="Code-generated, authoritative.")
    disclaimer: str
    as_of: date
    latency_ms: int
    mock: bool = False


# ---- GET /api/records/{record_id} ----


class Sentence(ApiModel):
    id: str
    record_id: str
    idx: int
    text: str
    start: int
    end: int


class Extraction(ApiModel):
    id: str
    record_id: str
    field: str
    value_json: Any
    source: Literal["column", "summary", "comments"]
    sentence_id: str | None
    span_start: int | None
    span_end: int | None
    rule_id: str
    confidence: Confidence


class RecordFull(RecordCard):
    summary: str
    summary_missing: bool
    make_raw: str
    model_raw: str | None
    product_type: str | None
    citation_publish_date: date | None


class RecordDetail(ApiModel):
    record: RecordFull
    sentences: list[Sentence]
    extractions: list[Extraction]
    lineage: list[LineageEdge]
    mock: bool = False


# ---- GET /api/meta ----


class CoverageMetric(ApiModel):
    key: str
    label: str
    numerator: int
    denominator: int
    note: str


class CoverageReport(ApiModel):
    generated_at: str
    total_records: int
    metrics: list[CoverageMetric]
    limits: list[str]


class ModelIds(ApiModel):
    generation: str
    query_parser: str
    verifier: str


class MetaResponse(ApiModel):
    dataset: str
    total_records: int
    unique_dockets: int
    as_of: date
    models: ModelIds
    embedding_backend: str
    index_version: str = Field(description="sha1 of the source workbook + dense index version hash (prefixes).")
    coverage: CoverageReport
    mock: bool = False


# ---- GET /api/eval/latest ----


class EvalSet(ApiModel):
    name: str
    size: int
    synthetic: bool
    description: str


class MetricDef(ApiModel):
    key: str
    label: str
    unit: Literal["ratio", "ms", "count"]
    higher_is_better: bool


class MetricRow(ApiModel):
    system: str
    is_baseline: bool
    values: dict[str, float | None]
    n: dict[str, int | None] = Field(default_factory=dict, description="Cases behind each metric value.")
    ci95: dict[str, list[float | None]] = Field(
        default_factory=dict, description="Bootstrap 95% interval [low, high] per metric, where computed."
    )


class FailureCase(ApiModel):
    id: str
    query: str
    expected: str
    observed: str
    cause: str
    user_signal: str = Field(description="How the user would know something is wrong.")


class EvalResults(ApiModel):
    generated_at: str
    eval_set: EvalSet
    metric_defs: list[MetricDef]
    systems: list[MetricRow]
    ablation: list[MetricRow]
    failures: list[FailureCase]
    caveats: list[str] = Field(default_factory=list, description="What the numbers do NOT show.")
    mock: bool = False


class ExampleQuery(ApiModel):
    """A query taken verbatim from the evaluation cases (inputs only; no expected answer is sent)."""

    case_id: str
    category: str
    query: str
    make: str | None
    model: str | None
    serial: str | None


# ---- Small responses ----


class HealthResponse(ApiModel):
    status: Literal["ok"]
    mock: bool


class FeedbackResponse(ApiModel):
    ok: bool
    mock: bool
