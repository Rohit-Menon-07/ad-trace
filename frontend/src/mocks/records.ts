// MOCK DATA. Fictional records shaped like the AD NPRM dataset, for UI development only.
// Every id, docket and citation is prefixed MOCK so it can never be mistaken for a real notice.
// Nothing here is read from data/raw; these do NOT describe real FAA proposals.

import type { Citation, LineageEdge, RecordCard, RecordDetail, Sentence } from '../types/api';

interface MockRecordSeed {
  card: Omit<RecordCard, 'lineage'>;
  sentences: string[];
  lineage: LineageEdge[];
  make_raw: string;
  model_raw: string | null;
}

/** Joins sentences with single spaces and records [start, end) offsets into the summary. */
function buildSentences(recordId: string, parts: string[]): { summary: string; sentences: Sentence[] } {
  const sentences: Sentence[] = [];
  let summary = '';
  parts.forEach((text, idx) => {
    if (idx > 0) summary += ' ';
    const start = summary.length;
    summary += text;
    sentences.push({ id: `${recordId}#s${idx}`, record_id: recordId, idx, text, start, end: summary.length });
  });
  return { summary, sentences };
}

const SEEDS: MockRecordSeed[] = [
  {
    card: {
      record_id: 'MOCK-R0001',
      docket: 'MOCK-FAA-2026-0101',
      subject_heading: 'MOCK: Airbus SAS Airplanes (radio management panels)',
      make: 'Airbus SAS',
      models: ['A330-202', 'A330-203', 'A330-223', 'A330-243', 'A330-343'],
      models_confidence: 'HIGH',
      status_label: 'PROPOSED',
      withdrawn: false,
      comment_period: 'OPEN',
      comments_due: '2026-11-20',
      issue_date: '2026-10-06',
      fr_citation: 'MOCK 91 FR 00001',
      pages: '00001-00003',
      url: null,
      ad_number: null,
      retrieval_score: 0.0325,
    },
    make_raw: 'Airbus SAS',
    model_raw: null,
    sentences: [
      'The FAA proposes to supersede AD 2023-14-05, which applies to certain Airbus SAS Model A330-202, -203, -223, -243, and -343 airplanes.',
      'AD 2023-14-05 requires replacing certain radio management panels (RMP).',
      'Since the FAA issued AD 2023-14-05, reports were received of RMP display freezes on panels that were not affected by that AD.',
      'This proposed AD would require replacing additional RMPs, as specified in a European Union Aviation Safety Agency (EASA) AD, which is proposed for incorporation by reference.',
      'The FAA is proposing this AD to address the unsafe condition on these products.',
    ],
    lineage: [
      { relation: 'supersedes', target_ref: 'AD 2023-14-05', target_in_dataset: false, target_record_id: null, evidence_id: 'MOCK-R0001#s0' },
    ],
  },
  {
    card: {
      record_id: 'MOCK-R0002',
      docket: 'MOCK-FAA-2026-0102',
      subject_heading: 'MOCK: Airbus SAS Airplanes (trimmable horizontal stabilizer actuator)',
      make: 'Airbus SAS',
      models: ['A330-841', 'A330-941'],
      models_confidence: 'HIGH',
      status_label: 'PROPOSED',
      withdrawn: false,
      comment_period: 'CLOSED',
      comments_due: '2026-09-14',
      issue_date: '2026-07-30',
      fr_citation: 'MOCK 91 FR 00004',
      pages: '00004-00006',
      url: null,
      ad_number: null,
      retrieval_score: 0.0291,
    },
    make_raw: 'AIRBUS SAS',
    model_raw: 'A330-841, A330-941',
    sentences: [
      'The FAA proposes to adopt a new AD for certain Airbus SAS Model A330-841 and -941 airplanes.',
      'This proposed AD was prompted by a report of a trimmable horizontal stabilizer actuator (THSA) no-back brake found worn beyond limits.',
      'This proposed AD would require repetitive inspections of the THSA, as specified in an EASA AD, which is proposed for incorporation by reference.',
    ],
    lineage: [],
  },
  {
    card: {
      record_id: 'MOCK-R0003',
      docket: 'MOCK-FAA-2026-0103',
      subject_heading: 'MOCK: Airbus SAS Airplanes (cabin oxygen generators)',
      make: 'Airbus SAS',
      models: [],
      models_confidence: 'LOW',
      status_label: 'PROPOSED',
      withdrawn: false,
      comment_period: 'OPEN',
      comments_due: '2026-12-01',
      issue_date: '2026-10-15',
      fr_citation: 'MOCK 91 FR 00007',
      pages: '00007-00009',
      url: null,
      ad_number: null,
      retrieval_score: 0.0164,
    },
    make_raw: 'Airbus',
    model_raw: null,
    sentences: [
      'The FAA proposes to adopt a new AD for certain Airbus SAS Model A330-200, A330-200 Freighter, and A330-300 series airplanes.',
      'This proposed AD was prompted by reports of passenger oxygen generators that did not activate during a functional test.',
      'This proposed AD would require replacing affected oxygen generators, as specified in an EASA AD, which is proposed for incorporation by reference.',
    ],
    lineage: [],
  },
  {
    card: {
      record_id: 'MOCK-R0004',
      docket: 'MOCK-FAA-2026-0104',
      subject_heading: 'MOCK: Airbus SAS Airplanes (fuel pump canister)',
      make: 'Airbus SAS',
      models: ['A320-214', 'A320-216', 'A320-232'],
      models_confidence: 'MEDIUM',
      status_label: 'PROPOSED',
      withdrawn: false,
      comment_period: 'OPEN',
      comments_due: '2026-11-27',
      issue_date: '2026-10-09',
      fr_citation: 'MOCK 91 FR 00010',
      pages: '00010-00012',
      url: null,
      ad_number: null,
      retrieval_score: 0.0318,
    },
    make_raw: 'Airbus SAS',
    model_raw: null,
    sentences: [
      'The FAA proposes to adopt a new AD for certain Airbus SAS Model A320-214, -216, and -232 airplanes, manufacturer serial numbers (MSN) 1000 through 1500 inclusive.',
      'This proposed AD was prompted by reports of chafing on fuel pump canister wiring.',
      'This proposed AD would require an inspection of the canister wiring and corrective actions if necessary, as specified in an EASA AD, which is proposed for incorporation by reference.',
    ],
    lineage: [
      { relation: 'shares_docket', target_ref: 'MOCK-FAA-2026-0104', target_in_dataset: true, target_record_id: 'MOCK-R0005', evidence_id: null },
    ],
  },
  {
    card: {
      record_id: 'MOCK-R0005',
      docket: 'MOCK-FAA-2026-0104',
      subject_heading: 'MOCK: Airbus SAS Airplanes (fuel pump canister), comment period extension',
      make: 'Airbus SAS',
      models: ['A320-214'],
      models_confidence: 'MEDIUM',
      status_label: 'PROPOSED',
      withdrawn: false,
      comment_period: 'OPEN',
      comments_due: '2026-12-11',
      issue_date: '2026-10-20',
      fr_citation: 'MOCK 91 FR 00013',
      pages: '00013',
      url: null,
      ad_number: null,
      retrieval_score: 0.0202,
    },
    make_raw: 'AIRBUS',
    model_raw: null,
    sentences: [
      'The FAA is extending the comment period for an NPRM that applies to certain Airbus SAS Model A320-214 airplanes.',
      'The affected airplanes are identified in the service information referenced in the NPRM.',
    ],
    lineage: [
      { relation: 'comment_extension', target_ref: 'MOCK-FAA-2026-0104', target_in_dataset: true, target_record_id: 'MOCK-R0004', evidence_id: 'MOCK-R0005#s0' },
    ],
  },
];

export const MOCK_RECORDS: Record<string, RecordDetail> = Object.fromEntries(
  SEEDS.map((seed) => {
    const { summary, sentences } = buildSentences(seed.card.record_id, seed.sentences);
    const detail: RecordDetail = {
      record: {
        ...seed.card,
        lineage: seed.lineage,
        summary,
        summary_missing: summary.length === 0,
        make_raw: seed.make_raw,
        model_raw: seed.model_raw,
        product_type: 'Aircraft',
        citation_publish_date: seed.card.issue_date,
      },
      sentences,
      extractions: [],
      lineage: seed.lineage,
      mock: true,
    };
    return [seed.card.record_id, detail];
  }),
);

export function mockCard(recordId: string): RecordCard {
  const seed = SEEDS.find((s) => s.card.record_id === recordId);
  if (!seed) throw new Error(`MOCK record not found: ${recordId}`);
  return { ...seed.card, lineage: seed.lineage };
}

/**
 * Builds a Citation for a quote inside a mock sentence. Throws if the quote is not a
 * substring of the sentence, mirroring H4 so mocks cannot drift from their sources.
 */
export function mockCite(evidenceId: string, quote: string): Citation {
  const recordId = evidenceId.split('#')[0] ?? '';
  const detail = MOCK_RECORDS[recordId];
  const sentence = detail?.sentences.find((s) => s.id === evidenceId);
  if (!detail || !sentence) throw new Error(`MOCK evidence not found: ${evidenceId}`);
  const offset = sentence.text.indexOf(quote);
  if (offset < 0) throw new Error(`MOCK quote not in ${evidenceId}: ${quote}`);
  return {
    evidence_id: evidenceId,
    docket: detail.record.docket,
    quote,
    span_start: sentence.start + offset,
    span_end: sentence.start + offset + quote.length,
    fr_citation: detail.record.fr_citation,
    pages: detail.record.pages,
    url: detail.record.url,
  };
}
