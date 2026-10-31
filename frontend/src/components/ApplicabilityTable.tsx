import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { api } from '../api/client';
import type { ApplicabilityResult, RecordCard } from '../types/api';
import { CitationChip, type DrawerTarget } from './CitationChip';
import { Skeleton } from './Skeleton';
import { ExtractionTable } from './SourceDrawer';
import { VerdictBadge } from './VerdictBadge';

interface Props {
  rows: ApplicabilityResult[];
  records: RecordCard[];
  activeId: string | null;
  onOpen: (t: DrawerTarget) => void;
}

export function ApplicabilityTable({ rows, records, activeId, onOpen }: Props) {
  const [open, setOpen] = useState<string | null>(null);
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
              <th scope="col" className="w-6 py-1"><span className="sr-only">Expand</span></th>
              <th scope="col" className="py-1 pr-3 font-semibold">Record</th>
              <th scope="col" className="py-1 pr-3 font-semibold">Verdict</th>
              <th scope="col" className="py-1 font-semibold">Reasons</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const rec = byId.get(row.record_id);
              const expanded = open === row.record_id;
              const panelId = `app-ev-${row.record_id}`;
              return (
                <Fragment key={row.record_id}>
                  <tr className="border-b border-slate-200 align-top dark:border-slate-800">
                    <td className="py-2">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-controls={panelId}
                        aria-label={`${expanded ? 'Hide' : 'Show'} the extraction evidence behind the verdict for ${rec?.docket ?? row.record_id}`}
                        onClick={() => setOpen(expanded ? null : row.record_id)}
                        className="rounded p-0.5 hover:bg-slate-100 dark:hover:bg-slate-800"
                      >
                        {expanded ? <ChevronDown aria-hidden className="h-4 w-4" /> : <ChevronRight aria-hidden className="h-4 w-4" />}
                      </button>
                    </td>
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
                      {row.evidence_ids.length > 0 && (
                        <div className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                          Evidence:
                          {row.evidence_ids.map((id) => (
                            <CitationChip key={id} n={id.split('#')[1] ?? id} target={{ evidenceId: id }} active={activeId === id} onOpen={onOpen} />
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                  {expanded && (
                    <tr id={panelId} className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
                      <td />
                      <td colSpan={3} className="py-2 pr-2">
                        <EvidenceRows row={row} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** The extraction rows (rule id, confidence) and source sentences the engine used for this verdict. */
function EvidenceRows({ row }: { row: ApplicabilityResult }) {
  const { data, isPending, error } = useQuery({ queryKey: ['record', row.record_id], queryFn: () => api.record(row.record_id) });
  if (isPending) return <Skeleton lines={3} label="Loading extraction evidence" />;
  if (error) return <p className="text-xs">Could not load the extraction rows: {error.message}</p>;
  const ids = new Set(row.evidence_ids);
  const fromColumn = row.evidence_ids.some((id) => id.includes('#col:'));
  const used = data.extractions.filter((e) => (e.sentence_id && ids.has(e.sentence_id)) || (fromColumn && e.source === 'column'));
  const sentences = data.sentences.filter((s) => ids.has(s.id));
  return (
    <div className="space-y-2 text-xs">
      {used.length === 0 ? (
        <p>No extraction row is linked to this verdict; the reasons above are the whole basis. Read the record in the source drawer before relying on it.</p>
      ) : (
        <ExtractionTable rows={used} />
      )}
      {sentences.map((s) => (
        <p key={s.id}>
          <span className="font-mono font-semibold">{s.id}</span>: “{s.text}”
        </p>
      ))}
    </div>
  );
}
