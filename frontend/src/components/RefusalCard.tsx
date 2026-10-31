import { Info } from 'lucide-react';
import type { SearchResponse } from '../types/api';
import { reasonInfo } from './reasonCodes';

interface Props {
  response: SearchResponse;
  onChoose: (option: string) => void;
}

/** Refusals and clarifications are successful outputs (H7): amber, never red. */
export function RefusalCard({ response, onChoose }: Props) {
  const info = reasonInfo(response.reason_code);
  const isClarify = response.status === 'needs_clarification';
  const checked = response.trace.map((s) => s.stage);
  return (
    <section aria-labelledby="refusal-h" className="rounded border-2 border-amber-500 bg-amber-50 p-4 text-amber-950 dark:bg-amber-950/30 dark:text-amber-50">
      <div className="flex items-start gap-2">
        <Info aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="space-y-2 text-sm">
          <h3 id="refusal-h" className="text-base font-semibold">
            {isClarify ? 'Clarification needed' : 'AD Trace cannot answer this'}: {info?.title}
          </h3>
          <p>{response.message}</p>
          <p>
            Reason code: <code className="rounded bg-amber-100 px-1 font-mono dark:bg-amber-900">{response.reason_code ?? 'none'}</code>
          </p>
          <p>
            <span className="font-semibold">What was checked:</span> {checked.join(' → ')}
          </p>
          {isClarify && <ClarificationChips options={response.clarification_options} onChoose={onChoose} />}
          {info && (
            <p>
              <span className="font-semibold">Suggested next step:</span> {info.nextAction}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function ClarificationChips({ options, onChoose }: { options: string[]; onChoose: (o: string) => void }) {
  return (
    <div>
      <p className="mb-1 font-semibold">Did you mean:</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Clarification options">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChoose(o)}
            className="rounded-full border border-amber-700 bg-white px-3 py-1 font-mono text-sm hover:bg-amber-100 dark:bg-slate-900 dark:hover:bg-slate-800"
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}
