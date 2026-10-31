import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, Copy, ExternalLink, X } from 'lucide-react';
import { api } from '../api/client';
import type { Extraction, RecordDetail, Sentence } from '../types/api';
import type { DrawerTarget } from './CitationChip';
import { LineageList } from './LineageStrip';
import { MockBadge } from './MockBadge';
import { Skeleton } from './Skeleton';

interface Props {
  target: DrawerTarget | null;
  onClose: () => void;
}

const sectionH = 'mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400';

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
      {!target && (
        <div className="p-4 text-sm text-slate-600 dark:text-slate-400">
          <p className="font-semibold text-slate-800 dark:text-slate-200">Source drawer</p>
          <p className="mt-1">Click a numbered citation chip to see the full record here with the cited sentence highlighted, its docket, Federal Register citation and the extraction rules behind each verdict.</p>
        </div>
      )}
      {target && (
        <div className="p-4">
          <div className="mb-3 flex items-start justify-between gap-2">
            <h2 ref={headingRef} tabIndex={-1} className="font-mono text-sm font-semibold">
              Source {target.evidenceId}
            </h2>
            <button type="button" onClick={onClose} aria-label="Close source drawer (Escape)" className="rounded p-1 hover:bg-slate-100 dark:hover:bg-slate-800">
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
          {isLoading && <Skeleton lines={6} label="Loading record" />}
          {error && (
            <p role="alert" className="rounded border-2 border-amber-500 p-2 text-sm">
              Could not load record {recordId}: {error.message}. The citation id above is still the exact source; open it via the Federal Register link in the result.
            </p>
          )}
          {data && <RecordBody detail={data} target={target} />}
        </div>
      )}
    </aside>
  );
}

function citedSentence(detail: RecordDetail, target: DrawerTarget): Sentence | undefined {
  return detail.sentences.find((s) => s.id === target.evidenceId);
}

function citationText(detail: RecordDetail, target: DrawerTarget): string {
  const r = detail.record;
  const s = citedSentence(detail, target);
  let quote = target.quote ?? s?.text ?? '';
  if (!target.quote && s && target.spanStart != null && target.spanEnd != null) quote = r.summary.slice(target.spanStart, target.spanEnd);
  return [
    `Docket ${r.docket}`,
    r.fr_citation ? `FR citation ${r.fr_citation}` : null,
    r.pages ? `pages ${r.pages}` : null,
    `source ${target.evidenceId}`,
    quote ? `"${quote}"` : null,
    '(proposed rulemaking, not in force)',
  ]
    .filter(Boolean)
    .join('; ');
}

function CopyCitation({ text }: { text: string }) {
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState('ok');
    } catch {
      setState('fail');
    }
  };
  return (
    <div>
      <button type="button" onClick={copy} className="inline-flex items-center gap-1 rounded border border-slate-500 px-2 py-1 text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800">
        {state === 'ok' ? <Check aria-hidden className="h-3.5 w-3.5" /> : <Copy aria-hidden className="h-3.5 w-3.5" />}
        {state === 'ok' ? 'Citation copied' : 'Copy citation'}
      </button>
      <span role="status" className="sr-only">{state === 'ok' ? 'Citation copied to clipboard' : ''}</span>
      {state === 'fail' && <p className="mt-1 select-all break-words rounded bg-slate-100 p-1 font-mono text-xs dark:bg-slate-800">{text}</p>}
    </div>
  );
}

function RecordBody({ detail, target }: { detail: RecordDetail; target: DrawerTarget }) {
  const r = detail.record;
  return (
    <div className="space-y-4 text-sm">
      {detail.mock && <MockBadge />}
      <p className="font-semibold">{r.subject_heading}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-slate-600 dark:text-slate-400">Record</dt>
        <dd className="font-mono">{r.record_id}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Docket</dt>
        <dd className="font-mono">{r.docket}</dd>
        <dt className="text-slate-600 dark:text-slate-400">FR citation</dt>
        <dd>{r.fr_citation || '—'}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Pages</dt>
        <dd>{r.pages || '—'}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Issued</dt>
        <dd>{r.issue_date ?? '—'}</dd>
        <dt className="text-slate-600 dark:text-slate-400">Status</dt>
        <dd className="font-semibold">
          {r.status_label}
          {r.withdrawn ? ' · WITHDRAWN' : ''} · comment period {r.comment_period}
          {r.comments_due ? ` (due ${r.comments_due})` : ''}
        </dd>
        <dt className="text-slate-600 dark:text-slate-400">Notice</dt>
        <dd>
          {r.url ? (
            <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-700 underline dark:text-blue-300">
              Open notice (new tab) <ExternalLink aria-hidden className="h-3 w-3" />
            </a>
          ) : (
            <span className="text-slate-600 dark:text-slate-400">No link in record</span>
          )}
        </dd>
      </dl>
      <CopyCitation text={citationText(detail, target)} />

      <section>
        <h3 className={sectionH}>Summary (full text of record)</h3>
        {r.summary_missing ? (
          <p className="italic">This record has no summary text. Only the subject heading above is available.</p>
        ) : (
          <p className="leading-relaxed">
            {detail.sentences.map((s) => (
              <SentenceSpan key={s.id} s={s} target={target} />
            ))}
          </p>
        )}
      </section>

      <section>
        <h3 className={sectionH}>Extraction rows (rules applied to this record)</h3>
        <ExtractionTable rows={detail.extractions} highlight={target.evidenceId} />
      </section>

      <section>
        <h3 className={sectionH}>Lineage</h3>
        <LineageList record={r} />
      </section>
    </div>
  );
}

function extractionValue(e: Extraction): string {
  const v = e.value_json;
  if (v == null) return '—';
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v);
}

export function ExtractionTable({ rows, highlight }: { rows: Extraction[]; highlight?: string }) {
  if (rows.length === 0) return <p className="text-slate-600 dark:text-slate-400">No rule matched this record.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-slate-300 dark:border-slate-700">
            <th scope="col" className="py-1 pr-2">Field</th>
            <th scope="col" className="py-1 pr-2">Value</th>
            <th scope="col" className="py-1 pr-2">Rule</th>
            <th scope="col" className="py-1 pr-2">Conf.</th>
            <th scope="col" className="py-1">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => {
            const hit = highlight !== undefined && e.sentence_id === highlight;
            return (
              <tr key={e.id} className={`border-b border-slate-200 align-top dark:border-slate-800 ${hit ? 'bg-yellow-50 dark:bg-yellow-900/30' : ''}`}>
                <td className="py-1 pr-2 font-mono">{e.field}</td>
                <td className="max-w-40 break-words py-1 pr-2 font-mono">{extractionValue(e)}</td>
                <td className="py-1 pr-2 font-mono">{e.rule_id}</td>
                <td className="py-1 pr-2 font-semibold">{e.confidence}</td>
                <td className="py-1 font-mono">
                  {e.sentence_id ?? e.source}
                  {hit && <span className="ml-1 font-sans font-semibold">(cited)</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
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
    <span ref={ref} className="rounded bg-yellow-100 px-0.5 text-slate-950 ring-1 ring-yellow-500 dark:bg-yellow-900/60 dark:text-yellow-50">
      <span className="sr-only">Cited sentence: </span>
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
