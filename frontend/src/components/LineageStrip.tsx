import { Ban, CalendarPlus, Clock, FileEdit, GitBranch, Layers, Link2, Shuffle } from 'lucide-react';
import type { LineageEdge, LineageRelation, RecordCard } from '../types/api';
import type { DrawerTarget } from './CitationChip';

// Every item below is computed by backend code (extraction rules + engine), never by the model.
const RELATION: Record<LineageRelation, { label: string; Icon: typeof GitBranch }> = {
  supersedes: { label: 'Would supersede', Icon: GitBranch },
  continues: { label: 'Would continue actions of', Icon: GitBranch },
  shares_docket: { label: 'Shares docket with', Icon: Link2 },
  withdraws: { label: 'Withdraws', Icon: Ban },
  comment_extension: { label: 'Extends comment period of', Icon: CalendarPlus },
  correction_of: { label: 'Corrects', Icon: FileEdit },
  applicability_change: { label: 'Changes applicability of', Icon: Shuffle },
};

const chip = 'inline-flex items-center gap-1 rounded border px-1.5 py-0.5';

function targetText(e: LineageEdge): string {
  const isAd = e.relation === 'supersedes' || e.relation === 'continues';
  return isAd ? `AD ${e.target_ref}` : e.target_ref;
}

function CommentPeriod({ record }: { record: RecordCard }) {
  const cls = record.comment_period === 'OPEN' ? 'border-green-700 text-green-900 dark:text-green-200' : 'border-slate-500';
  const when =
    record.comment_period === 'OPEN' ? ` until ${record.comments_due}` : record.comments_due ? ` (closed ${record.comments_due})` : '';
  return (
    <span className={`${chip} font-semibold ${cls}`}>
      <Clock aria-hidden className="h-3 w-3" />
      Comment period {record.comment_period}
      {when}
    </span>
  );
}

function DocketGroup({ record }: { record: RecordCard }) {
  if (record.docket_group_size <= 1) return null;
  return (
    <span className={`${chip} border-slate-400`}>
      <Layers aria-hidden className="h-3 w-3" />
      {record.docket_group_size} notices in docket ·{' '}
      <span className="font-semibold">{record.latest_in_docket_group ? 'latest in docket group' : 'NOT the latest in docket group'}</span>
    </span>
  );
}

interface Props {
  record: RecordCard;
  onOpen: (t: DrawerTarget) => void;
}

export function LineageStrip({ record, onOpen }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="font-mono font-semibold">{record.docket}</span>
      <span className={`${chip} border-amber-600 font-semibold text-amber-900 dark:text-amber-200`}>{record.status_label}</span>
      {record.withdrawn && <span className={`${chip} border-slate-700 font-bold dark:border-slate-300`}>WITHDRAWN</span>}
      <CommentPeriod record={record} />
      <DocketGroup record={record} />
      {record.lineage.map((e, i) => (
        <Edge key={i} edge={e} onOpen={onOpen} />
      ))}
    </div>
  );
}

function Edge({ edge, onOpen }: { edge: LineageEdge; onOpen?: (t: DrawerTarget) => void }) {
  const { label, Icon } = RELATION[edge.relation];
  const content = (
    <>
      <Icon aria-hidden className="h-3 w-3" />
      {label} <span className="font-mono">{targetText(edge)}</span>
      {!edge.target_in_dataset && <span className="italic">(target {edge.relation === 'supersedes' || edge.relation === 'continues' ? 'AD' : 'record'} is not in this dataset)</span>}
    </>
  );
  const cls = `${chip} border-slate-400`;
  if (!edge.evidence_id || !onOpen) return <span className={cls}>{content}</span>;
  const evidenceId = edge.evidence_id;
  return (
    <button type="button" className={`${cls} hover:bg-slate-100 dark:hover:bg-slate-800`} onClick={() => onOpen({ evidenceId })} aria-label={`${label} ${targetText(edge)}: open evidence ${evidenceId}`}>
      {content}
    </button>
  );
}

/** Vertical list for the source drawer. */
export function LineageList({ record }: { record: RecordCard }) {
  return (
    <ul className="space-y-1 text-xs">
      <li>
        <CommentPeriod record={record} />
      </li>
      {record.withdrawn && <li className="font-bold">WITHDRAWN (computed by the status rules from the withdrawal wording)</li>}
      {record.docket_group_size > 1 && (
        <li>
          <DocketGroup record={record} />
        </li>
      )}
      {record.lineage.length === 0 && <li className="text-slate-600 dark:text-slate-400">No supersession, correction or shared-docket links found by the rules.</li>}
      {record.lineage.map((e, i) => (
        <li key={i}>
          <Edge edge={e} />
          {e.evidence_id && <span className="ml-1 font-mono text-slate-600 dark:text-slate-400">evidence {e.evidence_id}</span>}
        </li>
      ))}
    </ul>
  );
}
