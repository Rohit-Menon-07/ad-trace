// MOCK DATA. Placeholder meta, coverage, vocabulary and evaluation payloads for UI development.
// Coverage numerators marked "profiled" come from the dataset profiling notes in CLAUDE.md;
// all other numbers are invented placeholders and are NOT measured results.

import type { EvalResults, MetaResponse } from '../types/api';

export const MOCK_META: MetaResponse = {
  dataset: 'AD Notice of Proposed Rulemaking (AD NPRM).xlsx',
  total_records: 431,
  unique_dockets: 323,
  as_of: '2026-10-31',
  models: { generation: 'claude-sonnet-5-5', query_parser: 'claude-haiku-5-5', verifier: 'claude-haiku-5-5' },
  embedding_backend: 'MOCK (not loaded)',
  coverage: {
    generated_at: 'MOCK',
    total_records: 431,
    metrics: [
      { key: 'model_column', label: 'Model column filled', numerator: 86, denominator: 431, note: 'Profiled from source file.' },
      { key: 'models_extracted', label: 'Model list extracted (any source)', numerator: 260, denominator: 431, note: 'MOCK placeholder; real value from ingest.' },
      { key: 'serial_constraints', label: 'Serial constraints resolved', numerator: 12, denominator: 431, note: 'MOCK placeholder. About 19 summaries mention serials.' },
      { key: 'supersession_edges', label: 'Records with a supersession edge', numerator: 100, denominator: 431, note: 'Approximate profiled count; real value from ingest.' },
      { key: 'ad_number', label: 'AD Number filled', numerator: 21, denominator: 431, note: 'Profiled from source file.' },
      { key: 'empty_summary', label: 'Empty summaries (refused as EMPTY_SOURCE_TEXT if cited)', numerator: 20, denominator: 431, note: 'MOCK placeholder; real value from ingest.' },
      { key: 'duplicate_dockets', label: 'Rows sharing a docket with another row', numerator: 108, denominator: 431, note: 'Derived: 431 rows − 323 unique dockets.' },
    ],
    limits: [
      'Every record is a Notice of Proposed Rulemaking. None is in force; final rules are not in this dataset.',
      'Only the Summary field is free text. There is no full notice text, so compliance steps, part numbers and torque values cannot be answered.',
      'Serial-number applicability can be checked only where a summary states serials. Elsewhere the verdict is UNDETERMINED.',
      'Most superseded ADs are not in the dataset. AD Trace says "references AD X", not "AD X is superseded", unless both records are present.',
      'There is no ground-truth Q&A. The evaluation set is hand-built by the team and is small.',
    ],
  },
  mock: true,
};

export const MOCK_MAKES = ['Airbus SAS', 'Airbus Helicopters', 'ATR-GIE Avions de Transport Régional', 'The Boeing Company'];

export const MOCK_MODELS: Record<string, string[]> = {
  'Airbus SAS': ['A320-214', 'A320-216', 'A320-232', 'A330-202', 'A330-203', 'A330-223', 'A330-243', 'A330-343', 'A330-841', 'A330-941', 'A350-941', 'A350-1041'],
  'Airbus Helicopters': ['AS350B3', 'EC135T2'],
  'ATR-GIE Avions de Transport Régional': ['ATR72-212A'],
  'The Boeing Company': ['737-8', '787-9'],
};

export const MOCK_EVAL: EvalResults = {
  generated_at: 'MOCK',
  eval_set: {
    name: 'MOCK eval set',
    size: 0,
    synthetic: true,
    description: 'MOCK placeholder. The real set will be hand-written queries over the 431 records, labelled by the team.',
  },
  metric_defs: [
    { key: 'recall_at_8', label: 'Recall@8 (relevant record retrieved)', unit: 'ratio', higher_is_better: true },
    { key: 'applicability_acc', label: 'Applicability verdict accuracy', unit: 'ratio', higher_is_better: true },
    { key: 'unsupported_rate', label: 'Unsupported-claim rate', unit: 'ratio', higher_is_better: false },
    { key: 'correct_refusal', label: 'Correct refusal rate', unit: 'ratio', higher_is_better: true },
    { key: 'p95_retrieval_ms', label: 'p95 retrieval latency', unit: 'ms', higher_is_better: false },
  ],
  systems: [
    { system: 'AD Trace (full pipeline)', is_baseline: false, values: { recall_at_8: 0.9, applicability_acc: 0.85, unsupported_rate: 0.03, correct_refusal: 0.8, p95_retrieval_ms: 220 } },
    { system: 'BM25 only (baseline)', is_baseline: true, values: { recall_at_8: 0.7, applicability_acc: null, unsupported_rate: null, correct_refusal: null, p95_retrieval_ms: 40 } },
    { system: 'LLM with no safeguards (baseline)', is_baseline: true, values: { recall_at_8: 0.7, applicability_acc: 0.6, unsupported_rate: 0.2, correct_refusal: 0.3, p95_retrieval_ms: 40 } },
  ],
  ablation: [
    { system: 'Full (H4 + H5 + H6)', is_baseline: false, values: { unsupported_rate: 0.03, correct_refusal: 0.8 } },
    { system: 'Without verifier (H6 off)', is_baseline: false, values: { unsupported_rate: 0.08, correct_refusal: 0.75 } },
    { system: 'Without quote check (H4 off)', is_baseline: false, values: { unsupported_rate: 0.12, correct_refusal: 0.75 } },
  ],
  failures: [
    {
      id: 'MOCK-F1',
      query: 'Does the oxygen generator proposal apply to our A330-243?',
      expected: 'APPLICABLE (A330-243 is an A330-200 series model)',
      observed: 'UNDETERMINED',
      cause: 'Summary lists "A330-200 series" not designators; the extractor does not map series names to models.',
      user_signal: 'Amber UNDETERMINED badge with the reason "series only, LOW confidence" and a link to the notice.',
    },
  ],
  mock: true,
};
