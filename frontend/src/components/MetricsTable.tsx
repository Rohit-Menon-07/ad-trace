import type { MetricDef, MetricRow } from '../types/api';

function fmt(v: number | null | undefined, unit: MetricDef['unit']): string {
  if (v == null) return 'n/a';
  if (unit === 'ratio') return `${(v * 100).toFixed(1)}%`;
  if (unit === 'ms') return `${Math.round(v)} ms`;
  return String(v);
}

interface Props {
  caption: string;
  defs: MetricDef[];
  rows: MetricRow[];
}

export function MetricsTable({ caption, defs, rows }: Props) {
  const used = defs.filter((d) => rows.some((r) => d.key in r.values));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <caption className="mb-2 text-left font-semibold">{caption}</caption>
        <thead>
          <tr className="border-b border-slate-300 dark:border-slate-700">
            <th scope="col" className="py-1 pr-3">System</th>
            {used.map((d) => (
              <th key={d.key} scope="col" className="py-1 pr-3">
                {d.label} <span className="font-normal text-slate-600 dark:text-slate-400">({d.higher_is_better ? 'higher' : 'lower'} is better)</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.system} className="border-b border-slate-200 dark:border-slate-800">
              <th scope="row" className="py-1 pr-3 font-normal">
                {r.system} {r.is_baseline && <span className="rounded border border-slate-500 px-1 text-xs font-semibold">BASELINE</span>}
              </th>
              {used.map((d) => (
                <td key={d.key} className="py-1 pr-3 font-mono">{fmt(r.values[d.key], d.unit)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
