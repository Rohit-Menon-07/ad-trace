import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, X } from 'lucide-react';
import { api } from '../api/client';
import type { RecordDetail, Sentence } from '../types/api';
import type { DrawerTarget } from './CitationChip';
import { MockBadge } from './MockBadge';

interface Props {
  target: DrawerTarget | null;
  onClose: () => void;
}

export function SourceDrawer({ target, onClose }: Props) {
  const recordId = target?.evidenceId.split('#')[0] ?? null;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ['record', recordId],
    queryFn: () => api.record(recordId as string),
    enabled: recordId !== null,
  });

  useEffect(() => {
    if (target) headingRef.current?.focus();
  }, [target]);

  useEffect(() => {
    if (!target) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [target, onClose]);

  return (
    <aside aria-label="Source drawer" className="rounded border border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900">
      {!target && <p className="p-4 text-sm text-slate-600 dark:text-slate-400">Click a numbered citation chip to see the exact source sentence here.</p>}
      {target && (
        <div className="p-4">
          <div className="mb-3 flex items-start justify-between gap-2">
            <h2 ref={headingRef} tabIndex={-1} className="font-mono text-sm font-semibold">
              Source {target.evidenceId}
            </h2>
            <button type="button" onClick={onClose} aria-label="Close source drawer" className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800">
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
          {isLoading && <p className="text-sm">Loading record…</p>}
          {error && <p className="text-sm text-amber-800">Could not load record: {String(error)}</p>}
          {data && <RecordBody detail={data} target={target} />}
        </div>
      )}
    </aside>
  );
}

function RecordBody({ detail, target }: { detail: RecordDetail; target: DrawerTarget }) {
  const r = detail.record;
  return (
    <div className="space-y-3 text-sm">
      {detail.mock && <MockBadge />}
      <p className="font-semibold">{r.subject_heading}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-slate-600 dark:text-slate-400">Record</dt>
        <dd className="font-mono">{r.record_id}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Docket</dt>
        <dd className="font-mono">{r.docket}</dd>
        <dt className="text-slate-600 dark:text-slate-400">FR citation</dt>
        <dd>{r.fr_citation}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Pages</dt>
        <dd>{r.pages}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Issued</dt>
        <dd>{r.issue_date ?? '—'}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Status</dt>
        <dd className="font-semibold">{r.status_label}{r.withdrawn ? ' · WITHDRAWN' : ''}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Notice</dt>
        <dd>
          {r.url ? (
            <a href={r.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-blue-700 underline dark:text-blue-300">
              Open notice <ExternalLink aria-hidden className="h-3 w-3" />
            </a>
          ) : (
            <span className="text-slate-600 dark:text-slate-400">No link in record</span>
          )}
        </dd>
      </dl>
      <div>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">Summary (full text of record)</p>
        {r.summary_missing ? (
          <p className="italic">This record has no summary text.</p>
        ) : (
          <p className="leading-relaxed">
            {detail.sentences.map((s) => (
              <SentenceSpan key={s.id} s={s} target={target} />
            ))}
          </p>
        )}
      </div>
    </div>
  );
}

function SentenceSpan({ s, target }: { s: Sentence; target: DrawerTarget }) {
  const cited = s.id === target.evidenceId;
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (cited) ref.current?.scrollIntoView({ block: 'nearest' });
  }, [cited]);
  if (!cited) return <span className="text-slate-600 dark:text-slate-400">{s.text} </span>;

  // Quote span (offsets into the summary) is marked inside the highlighted sentence.
  const { spanStart, spanEnd } = target;
  const hasQuote = spanStart != null && spanEnd != null && spanStart >= s.start && spanEnd <= s.end;
  const a = hasQuote ? spanStart - s.start : 0;
  const b = hasQuote ? spanEnd - s.start : 0;
  return (
    <span ref={ref} className="rounded bg-yellow-100 px-0.5 text-slate-950 ring-1 ring-yellow-500 dark:bg-yellow-900/60 dark:text-yellow-50" aria-label="Cited sentence">
      {hasQuote ? (
        <>
          {s.text.slice(0, a)}
          <mark className="bg-yellow-300 font-semibold text-slate-950 underline decoration-2 dark:bg-yellow-500">{s.text.slice(a, b)}</mark>
          {s.text.slice(b)}
        </>
      ) : (
        s.text
      )}{' '}
    </span>
  );
}
