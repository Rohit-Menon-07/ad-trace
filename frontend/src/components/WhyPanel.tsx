import { useState, type KeyboardEvent, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, OctagonX } from 'lucide-react';
import type { TraceStep } from '../types/api';
import { CitationChip, type DrawerTarget } from './CitationChip';

interface Props {
  trace: TraceStep[];
  rationale: string[];
  numbering: Map<string, number>;
  activeId: string | null;
  onOpen: (t: DrawerTarget) => void;
}

type Tab = 'trace' | 'rationale';

const STATUS_ICON = {
  ok: { Icon: CheckCircle2, label: 'OK', cls: 'text-green-700 dark:text-green-400' },
  warn: { Icon: AlertTriangle, label: 'WARN', cls: 'text-amber-600 dark:text-amber-400' },
  stop: { Icon: OctagonX, label: 'STOP', cls: 'text-amber-800 dark:text-amber-300' },
} as const;

const EVIDENCE_REF = /\[([^\]\s]+#s\d+)\]/g;
// The backend returns rationale only when at least this many steps survived verification (config verify.min_rationale_steps).
const MIN_RATIONALE_STEPS = 2;

export function WhyPanel({ trace, rationale, numbering, activeId, onOpen }: Props) {
  const showRationale = rationale.length >= MIN_RATIONALE_STEPS;
  const [tab, setTab] = useState<Tab>('trace');
  const tabs: Tab[] = showRationale ? ['trace', 'rationale'] : ['trace'];
  const current = showRationale ? tab : 'trace';

  // Arrow keys move between tabs (WAI-ARIA tabs pattern).
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const i = tabs.indexOf(current);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length] as Tab;
    setTab(next);
    document.getElementById(`tab-${next}`)?.focus();
  };

  return (
    <details className="rounded border border-slate-300 dark:border-slate-700">
      <summary className="cursor-pointer p-3 text-sm font-semibold">Why this answer</summary>
      <div className="border-t border-slate-300 p-3 dark:border-slate-700">
        <div role="tablist" aria-label="Explanation" className="mb-3 flex gap-1" onKeyDown={onKey}>
          <TabButton id="trace" tab={current} setTab={setTab}>Pipeline trace</TabButton>
          {showRationale && (
            <TabButton id="rationale" tab={current} setTab={setTab}>Model rationale</TabButton>
          )}
        </div>
        {!showRationale && (
          <p className="mb-2 text-xs text-slate-600 dark:text-slate-400">
            No model rationale shown: fewer than {MIN_RATIONALE_STEPS} model-written steps survived verification (or the model was not called).
          </p>
        )}
        {current === 'trace' ? (
          <div role="tabpanel" id="panel-trace" aria-labelledby="tab-trace">
            <p className="mb-2 text-xs text-slate-600 dark:text-slate-400">Written by code at each pipeline stage. This is the authoritative record of what was checked.</p>
            <ol className="space-y-1.5 text-sm">
              {trace.map((s, i) => (
                <TraceRow key={i} step={s} />
              ))}
            </ol>
          </div>
        ) : (
          <div role="tabpanel" id="panel-rationale" aria-labelledby="tab-rationale">
            <p className="mb-2 rounded border border-amber-500 px-2 py-1 text-xs">
              Written by the model, checked against sources. Each step points at evidence so you can check it; model self-explanations can still be wrong.
            </p>
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {rationale.map((step, i) => (
                <li key={i}>{renderWithChips(step, numbering, activeId, onOpen)}</li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </details>
  );
}

function TraceRow({ step }: { step: TraceStep }) {
  const { Icon, label, cls } = STATUS_ICON[step.status];
  const hasDetails = Object.keys(step.details).length > 0;
  return (
    <li className="flex gap-2">
      <Icon aria-hidden className={`mt-0.5 h-4 w-4 shrink-0 ${cls}`} />
      <div className="min-w-0 flex-1">
        <span className="font-semibold">{step.stage}</span> <span className="text-xs font-semibold">[{label}]</span>: {step.summary}
        {hasDetails && (
          <details className="mt-0.5">
            <summary className="cursor-pointer text-xs text-slate-600 underline-offset-2 hover:underline dark:text-slate-400">Details</summary>
            <pre className="mt-1 max-h-64 overflow-auto rounded bg-slate-100 p-2 text-xs dark:bg-slate-800">{JSON.stringify(step.details, null, 2)}</pre>
          </details>
        )}
      </div>
      <span className="shrink-0 font-mono text-xs text-slate-600 dark:text-slate-400">{step.ms} ms</span>
    </li>
  );
}

function TabButton({ id, tab, setTab, children }: { id: Tab; tab: Tab; setTab: (t: Tab) => void; children: string }) {
  const selected = tab === id;
  return (
    <button
      type="button"
      role="tab"
      id={`tab-${id}`}
      aria-selected={selected}
      aria-controls={`panel-${id}`}
      tabIndex={selected ? 0 : -1}
      onClick={() => setTab(id)}
      className={`rounded border px-3 py-1 text-sm ${selected ? 'border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900' : 'border-slate-400'}`}
    >
      {children}
    </button>
  );
}

/** Replaces "[R0001#s2]" references in model text with citation chips. */
function renderWithChips(text: string, numbering: Map<string, number>, activeId: string | null, onOpen: (t: DrawerTarget) => void) {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(EVIDENCE_REF)) {
    const id = m[1] as string;
    out.push(text.slice(last, m.index));
    out.push(<CitationChip key={`${id}-${m.index}`} n={numbering.get(id) ?? id.split('#')[1] ?? id} target={{ evidenceId: id }} active={activeId === id} onOpen={onOpen} />);
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}
