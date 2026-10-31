import type { ApplicabilityResult, RecordCard } from '../types/api';
import { CitationChip, type DrawerTarget } from './CitationChip';
import { VerdictBadge } from './VerdictBadge';

interface Props {
  rows: ApplicabilityResult[];
  records: RecordCard[];
  activeId: string | null;
  onOpen: (t: DrawerTarget) => void;
}

export function ApplicabilityTable({ rows, records, activeId, onOpen }: Props) {
  if (rows.length === 0) return null;
  const byId = new Map(records.map((r) => [r.record_id, r]));
  return (
    <section aria-labelledby="app-h">
      <h3 id="app-h" className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
        Applicability (computed by rules, not the model)
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-300 dark:border-slate-700">
              <th scope="col" className="py-1 pr-3 font-semibold">Record</th>
              <th scope="col" className="py-1 pr-3 font-semibold">Verdict</th>
              <th scope="col" className="py-1 font-semibold">Reasons and evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const rec = byId.get(row.record_id);
              return (
                <tr key={row.record_id} className="border-b border-slate-200 align-top dark:border-slate-800">
                  <td className="py-2 pr-3">
                    <div className="font-mono text-xs">{rec?.docket ?? row.record_id}</div>
                    <div className="text-xs text-slate-600 dark:text-slate-400">{rec?.subject_heading}</div>
                  </td>
                  <td className="py-2 pr-3">
                    <VerdictBadge verdict={row.verdict} />
                  </td>
                  <td className="py-2">
                    <ul className="list-disc pl-4">
                      {row.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                    {row.evidence_ids.map((id) => (
                      <CitationChip key={id} n={id.split('#')[1] ?? id} target={{ evidenceId: id }} active={activeId === id} onOpen={onOpen} />
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
