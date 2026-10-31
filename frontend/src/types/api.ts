// TypeScript mirrors of the Pydantic models in docs/SPEC.md section 7.
// Field names are snake_case to match the JSON the FastAPI backend will emit.
// Types not defined in SPEC.md (RecordCard, ExcludedRecord, LineageEdge, RecordDetail,
// MetaResponse, CoverageReport, EvalResults) are logged in DECISIONS.md.

/** ISO date string, e.g. "2026-10-31". Pydantic `date` serialises to this. */
export type ISODate = string;

export interface SearchRequest {
  query: string;
  make?: string | null;
  model?: string | null;
  serial?: string | null;
  as_of?: ISODate | null;
  mode?: 'answer' | 'search_only';
}

export interface Citation {
  evidence_id: string; // R0001#s2
  docket: string;
  quote: string;
  span_start: number | null; // offsets into the record Summary, for highlighting
  span_end: number | null;
  fr_citation: string;
  pages: string;
  url: string | null;
}

export interface Claim {
  text: string;
  citations: Citation[];
  verification: 'verified' | 'partial';
}

export type Verdict = 'APPLICABLE' | 'NOT_APPLICABLE' | 'UNDETERMINED' | 'NOT_CHECKED';

export interface ApplicabilityResult {
  record_id: string;
  verdict: Verdict;
  reasons: string[];
  evidence_ids: string[];
}

export interface TraceStep {
  stage: string;
  status: 'ok' | 'warn' | 'stop';
  summary: string;
  details: Record<string, unknown>;
  ms: number;
}

export type LineageRelation =
  | 'supersedes'
  | 'continues'
  | 'shares_docket'
  | 'withdraws'
  | 'comment_extension'
  | 'correction_of'
  | 'applicability_change';

export interface LineageEdge {
  relation: LineageRelation;
  target_ref: string; // e.g. "AD 2023-14-05" or a docket number
  target_in_dataset: boolean;
  target_record_id: string | null;
  evidence_id: string | null; // sentence the edge was extracted from
}

export type CommentPeriod = 'OPEN' | 'CLOSED' | 'UNKNOWN';

export interface RecordCard {
  record_id: string;
  docket: string;
  subject_heading: string;
  make: string; // canonical make
  models: string[]; // extracted + expanded model designators
  models_confidence: 'HIGH' | 'MEDIUM' | 'LOW' | null; // null = no model list found
  status_label: 'PROPOSED'; // all records are NPRMs
  withdrawn: boolean;
  comment_period: CommentPeriod; // computed against as_of
  comments_due: ISODate | null; // effective due date (after any extension)
  issue_date: ISODate | null;
  fr_citation: string;
  pages: string;
  url: string | null;
  ad_number: string | null;
  retrieval_score: number | null; // fused RRF score (H12: computed, not LLM-reported)
  lineage: LineageEdge[];
}

export interface ExcludedRecord {
  record_id: string;
  docket: string;
  subject_heading: string;
  rule: string; // machine rule id, e.g. "S3.hard_filter.model"
  reason: string; // plain-language explanation
}

export type SearchStatus = 'answered' | 'partial' | 'refused' | 'needs_clarification';

export type ReasonCode =
  | 'UNKNOWN_ENTITY'
  | 'AMBIGUOUS_MODEL'
  | 'AMBIGUOUS_MAKE'
  | 'NO_RETRIEVAL_HIT'
  | 'LOW_RETRIEVAL_SCORE'
  | 'EMPTY_SOURCE_TEXT'
  | 'APPLICABILITY_UNDETERMINED'
  | 'OUT_OF_SCOPE'
  | 'CONTRADICTS_RECORD'
  | 'CONFLICTING_EVIDENCE'
  | 'INJECTION_SUSPECTED'
  | 'VERIFICATION_FAILED'
  | 'LLM_ERROR';

export interface SearchResponse {
  request_id: string;
  status: SearchStatus;
  reason_code: ReasonCode | string | null;
  message: string;
  claims: Claim[];
  rationale_steps: string[]; // model-written, max 5, each cites evidence ids like [R0001#s2]
  records: RecordCard[];
  applicability: ApplicabilityResult[];
  excluded: ExcludedRecord[];
  clarification_options: string[];
  trace: TraceStep[]; // code-generated, authoritative
  disclaimer: string;
  as_of: ISODate;
  latency_ms: number;
  mock: boolean;
}

// ---- GET /api/records/{record_id} ----

export interface Sentence {
  id: string; // R0001#s2
  record_id: string;
  idx: number;
  text: string;
  start: number;
  end: number;
}

export interface Extraction {
  id: string;
  record_id: string;
  field: string;
  value_json: unknown;
  source: 'column' | 'summary' | 'comments';
  sentence_id: string | null;
  span_start: number | null;
  span_end: number | null;
  rule_id: string;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface RecordDetail {
  record: RecordCard & {
    summary: string;
    summary_missing: boolean;
    make_raw: string;
    model_raw: string | null;
    product_type: string | null;
    citation_publish_date: ISODate | null;
  };
  sentences: Sentence[];
  extractions: Extraction[];
  lineage: LineageEdge[];
  mock: boolean;
}

// ---- GET /api/meta ----

export interface CoverageMetric {
  key: string;
  label: string;
  numerator: number;
  denominator: number;
  note: string;
}

export interface CoverageReport {
  generated_at: string;
  total_records: number;
  metrics: CoverageMetric[];
  limits: string[]; // plain-language limits statements
}

export interface MetaResponse {
  dataset: string;
  total_records: number;
  unique_dockets: number;
  as_of: ISODate;
  models: { generation: string; query_parser: string; verifier: string };
  embedding_backend: string;
  coverage: CoverageReport;
  mock: boolean;
}

// ---- GET /api/eval/latest ----

export interface MetricRow {
  system: string; // e.g. "AD Trace (full)", "BM25 only"
  is_baseline: boolean;
  values: Record<string, number | null>; // metric key -> value (0..1 or ms)
}

export interface MetricDef {
  key: string;
  label: string;
  unit: 'ratio' | 'ms' | 'count';
  higher_is_better: boolean;
}

export interface FailureCase {
  id: string;
  query: string;
  expected: string;
  observed: string;
  cause: string;
  user_signal: string; // how the user would know something is wrong
}

export interface EvalResults {
  generated_at: string;
  eval_set: { name: string; size: number; synthetic: boolean; description: string };
  metric_defs: MetricDef[];
  systems: MetricRow[];
  ablation: MetricRow[];
  failures: FailureCase[];
  mock: boolean;
}
