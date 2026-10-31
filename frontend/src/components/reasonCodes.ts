// Plain-language copy for SPEC section 6 reason codes. UI text only: the codes themselves are
// raised by backend code (S2/S5/S7), never by the frontend.

import type { ReasonCode } from '../types/api';

interface ReasonInfo {
  title: string;
  nextAction: string;
}

export const REASON_INFO: Record<ReasonCode, ReasonInfo> = {
  UNKNOWN_ENTITY: { title: 'Make or model not found in the records', nextAction: 'Pick the make and model from the configuration dropdowns instead of typing them.' },
  AMBIGUOUS_MODEL: { title: 'Model is ambiguous', nextAction: 'Choose the exact model designator below.' },
  AMBIGUOUS_MAKE: { title: 'Make is ambiguous', nextAction: 'Choose the exact manufacturer below.' },
  NO_RETRIEVAL_HIT: { title: 'No matching records', nextAction: 'Broaden the query or remove the date range; check the official FAA DRS.' },
  LOW_RETRIEVAL_SCORE: { title: 'Matches are too weak to answer from', nextAction: 'Rephrase with the system or component name used in the notice.' },
  EMPTY_SOURCE_TEXT: { title: 'The matching record has no summary text', nextAction: 'Open the Federal Register notice via the record link.' },
  APPLICABILITY_UNDETERMINED: { title: 'Applicability cannot be determined from the records', nextAction: 'Check the referenced service information for your serial number.' },
  OUT_OF_SCOPE: { title: 'Question is outside what these records contain', nextAction: 'AD Trace covers which proposals concern an aircraft, not compliance steps, parts, torque values or legal advice. Use the AMM or official notice.' },
  CONTRADICTS_RECORD: { title: 'Question contradicts the record', nextAction: 'Review the cited record; the premise of the question may be wrong.' },
  CONFLICTING_EVIDENCE: { title: 'Records disagree', nextAction: 'Compare the conflicting records in the source drawer before acting.' },
  INJECTION_SUSPECTED: { title: 'Input looks like an instruction to the system', nextAction: 'Rephrase as a plain question about an aircraft.' },
  VERIFICATION_FAILED: { title: 'No generated claim survived verification', nextAction: 'Use search-only results and read the cited records directly.' },
  LLM_ERROR: { title: 'Language model unavailable', nextAction: 'Retry, or use search-only results.' },
};

export function reasonInfo(code: string | null): ReasonInfo | null {
  if (!code) return null;
  return (REASON_INFO as Record<string, ReasonInfo>)[code] ?? { title: code, nextAction: 'Read the cited records directly.' };
}
