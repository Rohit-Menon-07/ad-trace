import type { ExcludedRecord } from '../types/api';

export function ExcludedPanel({ excluded }: { excluded: ExcludedRecord[] }) {
  if (excluded.length === 0) return null;
  return (
    <details className="rounded border border-slate-300 p-3 dark:border-slate-700">
      <summary className="cursor-pointer text-sm font-semibold">Not shown and why ({excluded.length})</summary>
      <ul className="mt-2 space-y-2 text-sm">
        {excluded.map((x) => (
          <li key={x.record_id}>
            <span className="font-mono text-xs">{x.docket}</span> · {x.subject_heading}
            <div className="text-slate-700 dark:text-slate-300">
              {x.reason} <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">{x.rule}</code>
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}
