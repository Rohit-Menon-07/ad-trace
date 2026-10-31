import type { MetricDef, MetricRow } from '../types/api';

function fmt(v: number | null | undefined, unit: MetricDef['unit']): string {
  if (v == null) return 'n/a';
  if (unit === 'ratio') return `${(v * 100).toFixed(1)}%`;
  if (unit === 'ms') return `${Math.round(v)} ms`;
  return String(v);
}

function fmtCi(ci: (number | null)[] | undefined, unit: MetricDef['unit']): string | null {
  if (!ci || ci.length !== 2 || ci[0] == null || ci[1] == null) return null;
  return unit === 'ratio' ? `[${Math.round(ci[0] * 100)}–${Math.round(ci[1] * 100)}%]` : `[${ci[0]}–${ci[1]}]`;
}

interface Props {
  caption: string;
  defs: MetricDef[];
  rows: MetricRow[];
}

/** Value, bootstrap 95% interval (where computed) and n for every cell. */
export function MetricsTable({ caption, defs, rows }: Props) {
  const used = defs.filter((d) => rows.some((r) => d.key in r.values));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <caption className="mb-2 text-left font-semibold">{caption}</caption>
        <thead>
          <tr className="border-b border-slate-300 align-bottom dark:border-slate-700">
            <th scope="col" className="py-1 pr-3">System</th>
            {used.map((d) => (
              <th key={d.key} scope="col" className="py-1 pr-3">
                {d.label}
                <span className="block text-xs font-normal text-slate-600 dark:text-slate-400">{d.higher_is_better ? 'higher' : 'lower'} is better</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.system} className="border-b border-slate-200 align-top dark:border-slate-800">
              <th scope="row" className="max-w-56 py-1 pr-3 text-xs font-normal">
                {r.system} {r.is_baseline && <span className="rounded border border-slate-500 px-1 text-[10px] font-semibold">BASELINE</span>}
              </th>
              {used.map((d) => {
                const ci = r.values[d.key] == null ? null : fmtCi(r.ci95?.[d.key], d.unit);
                const n = r.n?.[d.key];
                return (
                  <td key={d.key} className="py-1 pr-3 font-mono text-xs">
                    <div className="font-semibold">{fmt(r.values[d.key], d.unit)}</div>
                    {ci && <div className="text-slate-600 dark:text-slate-400">{ci}</div>}
                    {n != null && <div className="text-slate-600 dark:text-slate-400">n={n}</div>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
