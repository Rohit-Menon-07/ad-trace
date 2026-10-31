import type { CoverageMetric } from '../types/api';

export function CoverageBars({ metrics }: { metrics: CoverageMetric[] }) {
  return (
    <ul className="space-y-3">
      {metrics.map((m) => {
        const pct = m.denominator > 0 ? (100 * m.numerator) / m.denominator : 0;
        return (
          <li key={m.key}>
            <div className="mb-1 flex justify-between gap-2 text-sm">
              <span className="font-semibold">{m.label}</span>
              <span className="font-mono">
                {m.numerator} / {m.denominator} ({pct.toFixed(1)}%)
              </span>
            </div>
            <div className="h-3 w-full rounded bg-slate-200 dark:bg-slate-800" role="meter" aria-label={m.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
              <div className="h-3 rounded bg-slate-700 dark:bg-slate-300" style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{m.note}</p>
          </li>
        );
      })}
    </ul>
  );
}
