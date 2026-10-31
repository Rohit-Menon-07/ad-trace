// MOCK DATA. Four canned SearchResponses for UI development, selected via the dev-only
// scenario switcher. These are NOT outputs of the AD Trace pipeline and describe no real notice.

import type { SearchRequest, SearchResponse, TraceStep } from '../types/api';
import { mockCard, mockCite } from './records';

export type ScenarioKey = 'answered' | 'partial' | 'refused' | 'needs_clarification';

export interface MockScenario {
  key: ScenarioKey;
  label: string;
  request: SearchRequest;
  response: SearchResponse;
}

const MOCK_AS_OF = '2026-10-31';
const DISCLAIMER =
  'Decision support only. Verify against the Federal Register notice before acting. ' +
  'All records are proposed rulemaking (NPRM) and are not in force.';

function step(stage: string, status: TraceStep['status'], summary: string, ms: number, details: Record<string, unknown> = {}): TraceStep {
  return { stage, status, summary, ms, details };
}

const answered: MockScenario = {
  key: 'answered',
  label: 'Answered (A330-243 RMP)',
  request: {
    query: 'Which proposed ADs concern the radio management panels on our A330-243?',
    make: 'Airbus SAS',
    model: 'A330-243',
    serial: null,
    as_of: MOCK_AS_OF,
    mode: 'answer',
  },
  response: {
    request_id: 'MOCK-req-0001',
    status: 'answered',
    reason_code: null,
    message: '1 proposed AD applies to Airbus SAS A330-243; 1 is undetermined and 1 does not apply.',
    claims: [
      {
        text: 'A proposed AD would supersede AD 2023-14-05 for certain Airbus SAS Model A330-202, -203, -223, -243 and -343 airplanes.',
        citations: [mockCite('MOCK-R0001#s0', 'The FAA proposes to supersede AD 2023-14-05')],
        verification: 'verified',
      },
      {
        text: 'The proposed AD would require replacing additional radio management panels (RMPs), as specified in an EASA AD.',
        citations: [mockCite('MOCK-R0001#s3', 'This proposed AD would require replacing additional RMPs')],
        verification: 'verified',
      },
      {
        text: 'It was prompted by reports of RMP display freezes on panels not affected by AD 2023-14-05.',
        citations: [mockCite('MOCK-R0001#s2', 'reports were received of RMP display freezes on panels that were not affected by that AD')],
        verification: 'verified',
      },
    ],
    rationale_steps: [
      'The form fixes make Airbus SAS and model A330-243; both are in the vocabulary.',
      'MOCK-R0001 lists A330-243 in its model list [MOCK-R0001#s0].',
      'Its required action concerns radio management panels [MOCK-R0001#s3].',
      'It names AD 2023-14-05 as the AD it would supersede [MOCK-R0001#s0].',
    ],
    records: [mockCard('MOCK-R0001'), mockCard('MOCK-R0003'), mockCard('MOCK-R0002')],
    applicability: [
      {
        record_id: 'MOCK-R0001',
        verdict: 'APPLICABLE',
        reasons: ['A330-243 is in the extracted model list (HIGH confidence, suffix expansion of "A330-202, -203, -223, -243").'],
        evidence_ids: ['MOCK-R0001#s0'],
      },
      {
        record_id: 'MOCK-R0003',
        verdict: 'UNDETERMINED',
        reasons: ['Summary names "A330-200 series" only, not individual model designators; model list confidence LOW.'],
        evidence_ids: ['MOCK-R0003#s0'],
      },
      {
        record_id: 'MOCK-R0002',
        verdict: 'NOT_APPLICABLE',
        reasons: ['Model list (HIGH confidence) is A330-841, A330-941; A330-243 is absent.'],
        evidence_ids: ['MOCK-R0002#s0'],
      },
    ],
    excluded: [
      {
        record_id: 'MOCK-R0004',
        docket: 'MOCK-FAA-2026-0104',
        subject_heading: 'MOCK: Airbus SAS Airplanes (fuel pump canister)',
        rule: 'S3.hard_filter.model_family',
        reason: 'Model family A320 does not match the requested family A330.',
      },
    ],
    clarification_options: [],
    trace: [
      step('S1 Query understanding', 'ok', 'Intent: lookup. Form values override parsed make/model.', 412, { intent: 'lookup', make: 'Airbus SAS', model: 'A330-243' }),
      step('S2 Clarification gate', 'ok', 'Model A330-243 is an exact vocabulary match; no clarification needed.', 2),
      step('S3 Retrieval', 'ok', 'Hard filter make=Airbus SAS, family=A330 → 14 records; hybrid BM25 + dense, RRF k=60 → top 3.', 184, { candidates: 14, returned: 3, rrf_k: 60 }),
      step('S4 Applicability + revision', 'ok', '1 APPLICABLE, 1 UNDETERMINED, 1 NOT_APPLICABLE. 1 supersession edge (target not in dataset).', 6),
      step('S5 Abstention gate', 'ok', 'No reason code raised.', 1),
      step('S6 Generation', 'ok', '3 claims, 4 rationale steps from an evidence pack of 11 sentences.', 1840, { evidence_sentences: 11 }),
      step('S7 Verification', 'ok', 'Quote check 3/3, entity grounding 3/3, verifier SUPPORTED 3/3.', 690, { claims_in: 3, claims_dropped: 0 }),
      step('S8 Render + audit', 'ok', 'Answer assembled from verified claims; audit record written.', 3),
    ],
    disclaimer: DISCLAIMER,
    as_of: MOCK_AS_OF,
    latency_ms: 3138,
    mock: true,
  },
};

const partial: MockScenario = {
  key: 'partial',
  label: 'Partial (A320-214 MSN 1234)',
  request: {
    query: 'Any proposed ADs on the fuel pump wiring for A320-214 MSN 1234?',
    make: 'Airbus SAS',
    model: 'A320-214',
    serial: '1234',
    as_of: MOCK_AS_OF,
    mode: 'answer',
  },
  response: {
    request_id: 'MOCK-req-0002',
    status: 'partial',
    reason_code: null,
    message: 'Answer is partial: 1 of 3 generated claims was removed because the verifier could not confirm it against the cited sentence.',
    claims: [
      {
        text: 'A proposed AD covers certain Airbus SAS Model A320-214 airplanes, MSN 1000 through 1500 inclusive.',
        citations: [mockCite('MOCK-R0004#s0', 'manufacturer serial numbers (MSN) 1000 through 1500 inclusive')],
        verification: 'verified',
      },
      {
        text: 'It would require an inspection of the fuel pump canister wiring and corrective actions if necessary.',
        citations: [mockCite('MOCK-R0004#s2', 'This proposed AD would require an inspection of the canister wiring and corrective actions if necessary')],
        verification: 'partial',
      },
    ],
    rationale_steps: [
      'Serial 1234 falls inside the resolved range MSN 1000–1500 [MOCK-R0004#s0].',
      'The comment-period extension shares the same docket [MOCK-R0005#s0].',
      'The extension notice defers applicability to service information [MOCK-R0005#s1].',
    ],
    records: [mockCard('MOCK-R0004'), mockCard('MOCK-R0005')],
    applicability: [
      {
        record_id: 'MOCK-R0004',
        verdict: 'APPLICABLE',
        reasons: ['A320-214 is in the model list (MEDIUM confidence).', 'Serial 1234 is within resolved range MSN 1000–1500.'],
        evidence_ids: ['MOCK-R0004#s0'],
      },
      {
        record_id: 'MOCK-R0005',
        verdict: 'UNDETERMINED',
        reasons: ['Summary says affected airplanes are identified in service information; no serial range resolved in this record.'],
        evidence_ids: ['MOCK-R0005#s1'],
      },
    ],
    excluded: [
      {
        record_id: 'MOCK-R0001',
        docket: 'MOCK-FAA-2026-0101',
        subject_heading: 'MOCK: Airbus SAS Airplanes (radio management panels)',
        rule: 'S3.hard_filter.model_family',
        reason: 'Model family A330 does not match the requested family A320.',
      },
      {
        record_id: 'MOCK-R0002',
        docket: 'MOCK-FAA-2026-0102',
        subject_heading: 'MOCK: Airbus SAS Airplanes (trimmable horizontal stabilizer actuator)',
        rule: 'S3.hard_filter.model_family',
        reason: 'Model family A330 does not match the requested family A320.',
      },
    ],
    clarification_options: [],
    trace: [
      step('S1 Query understanding', 'ok', 'Intent: applicability. Serial "1234" parsed as MSN.', 388, { intent: 'applicability', serial: '1234' }),
      step('S2 Clarification gate', 'ok', 'Exact model match.', 2),
      step('S3 Retrieval', 'ok', 'Hard filter make=Airbus SAS, family=A320 → 9 records; top 2 above score floor.', 171, { candidates: 9, returned: 2 }),
      step('S4 Applicability + revision', 'warn', '1 APPLICABLE (serial in range), 1 UNDETERMINED (service-information applicability).', 5),
      step('S5 Abstention gate', 'ok', 'No blocking reason code.', 1),
      step('S6 Generation', 'ok', '3 claims generated.', 1712),
      step('S7 Verification', 'warn', '1 claim dropped: verifier returned UNSUPPORTED (claim named a part not in the quote).', 742, { claims_in: 3, claims_dropped: 1, dropped_by: { H4: 0, H5: 0, H6: 1 } }),
      step('S8 Render + audit', 'ok', 'Partial answer assembled from 2 surviving claims.', 3),
    ],
    disclaimer: DISCLAIMER,
    as_of: MOCK_AS_OF,
    latency_ms: 3024,
    mock: true,
  },
};

const refused: MockScenario = {
  key: 'refused',
  label: 'Refused (UNKNOWN_ENTITY)',
  request: {
    query: 'Torque values for the A350-2000 nose gear actuator?',
    make: 'Airbus SAS',
    model: 'A350-2000',
    serial: null,
    as_of: MOCK_AS_OF,
    mode: 'answer',
  },
  response: {
    request_id: 'MOCK-req-0003',
    status: 'refused',
    reason_code: 'UNKNOWN_ENTITY',
    message: 'Model "A350-2000" does not exist in the dataset vocabulary, so no record can be matched to it.',
    claims: [],
    rationale_steps: [],
    records: [],
    applicability: [],
    excluded: [],
    clarification_options: [],
    trace: [
      step('S1 Query understanding', 'warn', 'Parsed model "A350-2000". Closest vocabulary match "A350-1041" scored 71 (< 90 threshold).', 402, {
        model_text: 'A350-2000',
        best_match: 'A350-1041',
        score: 71,
        threshold: 90,
      }),
      step('S5 Abstention gate', 'stop', 'UNKNOWN_ENTITY raised; retrieval and generation skipped.', 1),
      step('S8 Render + audit', 'ok', 'Refusal rendered; audit record written.', 2),
    ],
    disclaimer: DISCLAIMER,
    as_of: MOCK_AS_OF,
    latency_ms: 405,
    mock: true,
  },
};

const needsClarification: MockScenario = {
  key: 'needs_clarification',
  label: 'Clarify (AMBIGUOUS_MODEL)',
  request: {
    query: 'What proposed ADs affect the A330?',
    make: 'Airbus SAS',
    model: 'A330',
    serial: null,
    as_of: MOCK_AS_OF,
    mode: 'answer',
  },
  response: {
    request_id: 'MOCK-req-0004',
    status: 'needs_clarification',
    reason_code: 'AMBIGUOUS_MODEL',
    message: '"A330" is a model family. Applicability is decided per model designator, so choose the exact model.',
    claims: [],
    rationale_steps: [],
    records: [],
    applicability: [],
    excluded: [],
    clarification_options: ['A330-202', 'A330-203', 'A330-223', 'A330-243', 'A330-343', 'A330-841', 'A330-941'],
    trace: [
      step('S1 Query understanding', 'ok', 'Parsed model "A330"; linked to family A330.', 395, { model_text: 'A330', linked_kind: 'family' }),
      step('S2 Clarification gate', 'stop', 'Family prefix matches 7 model designators in the vocabulary.', 2, { matches: 7 }),
      step('S8 Render + audit', 'ok', 'Clarification options rendered; audit record written.', 2),
    ],
    disclaimer: DISCLAIMER,
    as_of: MOCK_AS_OF,
    latency_ms: 399,
    mock: true,
  },
};

export const MOCK_SCENARIOS: Record<ScenarioKey, MockScenario> = {
  answered,
  partial,
  refused,
  needs_clarification: needsClarification,
};

export const SCENARIO_ORDER: ScenarioKey[] = ['answered', 'partial', 'refused', 'needs_clarification'];
