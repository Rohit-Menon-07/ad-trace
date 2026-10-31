import { Info } from 'lucide-react';
import type { SearchResponse, TraceStep } from '../types/api';
import { reasonInfo } from './reasonCodes';

interface Props {
  response: SearchResponse;
  onChoose: (option: string, field?: 'make' | 'model') => void;
}

function gateDetails(r: SearchResponse): { field?: 'make' | 'model'; suggestions: string[] } {
  const stop = r.trace.find((s) => s.status === 'stop') ?? r.trace.find((s) => s.stage.startsWith('S2'));
  const d = stop?.details ?? {};
  const field = d['field'] === 'make' || d['field'] === 'model' ? d['field'] : undefined;
  const sugg = Array.isArray(d['suggestions']) ? d['suggestions'].filter((x): x is string => typeof x === 'string') : [];
  return { field, suggestions: sugg };
}

function checkedSteps(trace: TraceStep[]): TraceStep[] {
  return trace.filter((s) => !s.stage.startsWith('S8'));
}

const STATUS_WORD = { ok: 'passed', warn: 'warning', stop: 'stopped here' } as const;

/** Refusals and clarifications are successful outputs (H7): amber, never red, never empty. */
export function RefusalCard({ response, onChoose }: Props) {
  const info = reasonInfo(response.reason_code);
  const isClarify = response.status === 'needs_clarification';
  const { field, suggestions } = gateDetails(response);
  return (
    <section aria-labelledby="refusal-h" className="rounded border-2 border-amber-500 bg-amber-50 p-4 text-amber-950 dark:bg-amber-950/30 dark:text-amber-50">
      <div className="flex items-start gap-2">
        <Info aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0 space-y-3 text-sm">
          <h3 id="refusal-h" className="text-base font-semibold">
            {isClarify ? 'Clarification needed' : 'AD Trace cannot complete this request'}
            {info ? `: ${info.title}` : ''}
          </h3>
          <p>{response.message || 'No answer was produced. The checks below show where the request stopped.'}</p>
          <p>
            Reason code: <code className="rounded bg-amber-100 px-1 font-mono dark:bg-amber-900">{response.reason_code ?? 'none'}</code>
          </p>

          {isClarify && response.clarification_options.length > 0 && (
            <ChipGroup label={field === 'make' ? 'Which manufacturer?' : 'Which exact model?'} options={response.clarification_options} onChoose={(o) => onChoose(o, field)} />
          )}
          {!isClarify && suggestions.length > 0 && (
            <ChipGroup label={`Nearest ${field ?? 'names'} in the records (not chosen for you):`} options={suggestions} onChoose={(o) => onChoose(o, field)} />
          )}

          <p>
            <span className="font-semibold">Suggested next step:</span> {info?.nextAction ?? 'Read the cited records directly.'}
          </p>

          <div>
            <p className="font-semibold">What was checked</p>
            <ol className="mt-1 space-y-0.5">
              {checkedSteps(response.trace).map((s, i) => (
                <li key={i} className="text-xs">
                  <span className="font-semibold">{s.stage}</span> ({STATUS_WORD[s.status]}): {s.summary}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}

function ChipGroup({ label, options, onChoose }: { label: string; options: string[]; onChoose: (o: string) => void }) {
  return (
    <div>
      <p className="mb-1 font-semibold">{label}</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label={label}>
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChoose(o)}
            className="rounded-full border border-amber-700 bg-white px-3 py-1 font-mono text-sm text-slate-900 hover:bg-amber-100 dark:border-amber-400 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}
