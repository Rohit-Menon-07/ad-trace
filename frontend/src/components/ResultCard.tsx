import { ExternalLink } from 'lucide-react';
import type { SearchResponse } from '../types/api';
import { ApplicabilityTable } from './ApplicabilityTable';
import type { DrawerTarget } from './CitationChip';
import { ClaimList } from './ClaimList';
import { ExcludedPanel } from './ExcludedPanel';
import { FeedbackButton } from './FeedbackButton';
import { LineageStrip } from './LineageStrip';
import { MockBadge } from './MockBadge';
import { ProposedBanner } from './ProposedBanner';
import { RefusalCard } from './RefusalCard';
import { WhyPanel } from './WhyPanel';

interface Props {
  response: SearchResponse;
  activeId: string | null;
  onOpen: (t: DrawerTarget) => void;
  onClarify: (option: string) => void;
}

/** Numbers each distinct cited evidence id in order of first appearance. */
function citationNumbering(r: SearchResponse): Map<string, number> {
  const map = new Map<string, number>();
  for (const c of r.claims) for (const cit of c.citations) if (!map.has(cit.evidence_id)) map.set(cit.evidence_id, map.size + 1);
  return map;
}

function droppedClaims(r: SearchResponse): number | null {
  const s7 = r.trace.find((s) => s.stage.startsWith('S7'));
  const n = s7?.details['claims_dropped'];
  return typeof n === 'number' ? n : null;
}

/** S6 trace details.answer_mode: "llm" | "extractive" (search-only) | "extractive_fallback" (LLM failed). */
function answerMode(r: SearchResponse): { mode: string; error?: string } | null {
  const s6 = r.trace.find((s) => s.stage.startsWith('S6'));
  const mode = s6?.details['answer_mode'];
  if (typeof mode !== 'string') return null;
  const error = s6?.details['error'];
  return { mode, error: typeof error === 'string' ? error : undefined };
}

export function ResultCard({ response, activeId, onOpen, onClarify }: Props) {
  const numbering = citationNumbering(response);
  const isAnswer = response.status === 'answered' || response.status === 'partial';
  const dropped = droppedClaims(response);
  const am = answerMode(response);
  return (
    <article className="rounded border border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900">
      <ProposedBanner disclaimer={response.disclaimer} />
      <div className="space-y-5 p-4">
        <header className="flex flex-wrap items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
          {response.mock && <MockBadge label="MOCK RESPONSE" />}
          <StatusPill status={response.status} />
          <span>as of {response.as_of}</span>
          <span>· {response.latency_ms} ms</span>
          <span className="font-mono">· {response.request_id}</span>
        </header>

        {isAnswer ? (
          <>
            <p className="text-sm">{response.message}</p>
            {response.status === 'partial' && dropped !== null && (
              <p role="status" className="rounded border border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-50">
                Partial answer: {dropped} claim{dropped === 1 ? '' : 's'} removed by verification. Only verified claims are shown.
              </p>
            )}
            {am && am.mode !== 'llm' && (
              <p role="status" className="rounded border-2 border-slate-500 px-3 py-2 text-sm">
                <span className="font-semibold">{am.mode === 'extractive' ? 'Search-only answer.' : 'Extractive fallback: the answer writer was unavailable.'}</span>{' '}
                Sentences below are quoted verbatim from the records with the computed facts; no model-written summary.
                {am.error ? ` (${am.error})` : ''}
              </p>
            )}
            <ClaimList claims={response.claims} numbering={numbering} activeId={activeId} onOpen={onOpen} />
            <ApplicabilityTable rows={response.applicability} records={response.records} activeId={activeId} onOpen={onOpen} />
            <section aria-labelledby="lineage-h">
              <h3 id="lineage-h" className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">Status and lineage</h3>
              <ul className="space-y-2">
                {response.records.map((rec) => (
                  <li key={rec.record_id} className="space-y-1">
                    <LineageStrip record={rec} onOpen={onOpen} />
                    {rec.url && (
                      <a href={rec.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-blue-700 underline dark:text-blue-300">
                        Federal Register notice <ExternalLink aria-hidden className="h-3 w-3" />
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          </>
        ) : (
          <RefusalCard response={response} onChoose={onClarify} />
        )}

        <ExcludedPanel excluded={response.excluded} />
        <WhyPanel trace={response.trace} rationale={response.rationale_steps} numbering={numbering} activeId={activeId} onOpen={onOpen} />
        <FeedbackButton key={response.request_id} requestId={response.request_id} />
      </div>
    </article>
  );
}

function StatusPill({ status }: { status: SearchResponse['status'] }) {
  const label = { answered: 'ANSWERED', partial: 'PARTIAL', refused: 'REFUSED', needs_clarification: 'NEEDS CLARIFICATION' }[status];
  return <span className="rounded border border-slate-500 px-1.5 py-0.5 font-semibold text-slate-800 dark:text-slate-200">{label}</span>;
}
