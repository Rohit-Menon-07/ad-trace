import { GitBranch, Link2, Ban, Clock, CalendarPlus, FileEdit, Shuffle } from 'lucide-react';
import type { LineageEdge, LineageRelation, RecordCard } from '../types/api';
import type { DrawerTarget } from './CitationChip';

const RELATION: Record<LineageRelation, { label: string; Icon: typeof GitBranch }> = {
  supersedes: { label: 'Would supersede', Icon: GitBranch },
  continues: { label: 'Continues', Icon: GitBranch },
  shares_docket: { label: 'Shares docket with', Icon: Link2 },
  withdraws: { label: 'Withdraws', Icon: Ban },
  comment_extension: { label: 'Extends comment period of', Icon: CalendarPlus },
  correction_of: { label: 'Corrects', Icon: FileEdit },
  applicability_change: { label: 'Changes applicability of', Icon: Shuffle },
};

interface Props {
  record: RecordCard;
  onOpen: (t: DrawerTarget) => void;
}

export function LineageStrip({ record, onOpen }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-mono font-semibold">{record.docket}</span>
      <span className="rounded border border-amber-600 px-1.5 py-0.5 font-semibold text-amber-900 dark:text-amber-200">{record.status_label}</span>
      {record.withdrawn && <span className="rounded border border-slate-600 px-1.5 py-0.5 font-semibold">WITHDRAWN</span>}
      <span className="inline-flex items-center gap-1 rounded border border-slate-400 px-1.5 py-0.5">
        <Clock aria-hidden className="h-3 w-3" />
        Comment period {record.comment_period}
        {record.comments_due ? ` (due ${record.comments_due})` : ''}
      </span>
      {record.lineage.map((e, i) => (
        <Edge key={i} edge={e} onOpen={onOpen} />
      ))}
    </div>
  );
}

function Edge({ edge, onOpen }: { edge: LineageEdge; onOpen: (t: DrawerTarget) => void }) {
  const { label, Icon } = RELATION[edge.relation];
  const content = (
    <>
      <Icon aria-hidden className="h-3 w-3" />
      {label} <span className="font-mono">{edge.target_ref}</span>
      {!edge.target_in_dataset && <span className="italic">(not in dataset)</span>}
    </>
  );
  const cls = 'inline-flex items-center gap-1 rounded border border-slate-400 px-1.5 py-0.5';
  if (!edge.evidence_id) return <span className={cls}>{content}</span>;
  const evidenceId = edge.evidence_id;
  return (
    <button type="button" className={`${cls} hover:bg-slate-100 dark:hover:bg-slate-800`} onClick={() => onOpen({ evidenceId })} title={`Evidence ${evidenceId}`}>
      {content}
    </button>
  );
}
