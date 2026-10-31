import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { DrawerTarget } from '../components/CitationChip';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { ExampleChips } from '../components/ExampleChips';
import { QueryForm } from '../components/QueryForm';
import { ResultCard } from '../components/ResultCard';
import { ResultSkeleton } from '../components/Skeleton';
import { SourceDrawer } from '../components/SourceDrawer';
import type { ExampleQuery, SearchRequest, SearchResponse } from '../types/api';

const EMPTY_REQUEST: SearchRequest = { query: '', make: null, model: null, serial: null, as_of: null, mode: 'answer' };

/** Which configuration field a clarification chip fills, from the code-written S2 trace step. */
function clarifyField(r: SearchResponse | undefined): 'make' | 'model' {
  const s2 = r?.trace.find((s) => s.stage.startsWith('S2'));
  return s2?.details['field'] === 'make' ? 'make' : 'model';
}

export function SearchPage() {
  const [form, setForm] = useState<SearchRequest>(EMPTY_REQUEST);
  const [submitted, setSubmitted] = useState<SearchRequest | null>(null);
  const [drawer, setDrawer] = useState<DrawerTarget | null>(null);

  const result = useQuery({
    queryKey: ['search', submitted],
    queryFn: () => api.search(submitted as SearchRequest),
    enabled: submitted !== null,
  });

  const run = (req: SearchRequest) => {
    setDrawer(null);
    setSubmitted(req);
  };

  const pickExample = (e: ExampleQuery) => {
    const req: SearchRequest = { ...EMPTY_REQUEST, query: e.query, make: e.make, model: e.model, serial: e.serial };
    setForm(req);
    run(req);
  };

  // A clarification or suggestion chip fills the make or model field and re-runs the search on the backend.
  const clarify = (option: string, field?: 'make' | 'model') => {
    const f = field ?? clarifyField(result.data);
    const req = f === 'make' ? { ...form, make: option, model: null } : { ...form, model: option };
    setForm(req);
    run(req);
  };

  const closeDrawer = useCallback(() => setDrawer(null), []);

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)_360px] xl:grid-cols-[300px_minmax(0,1fr)_400px]">
      <div className="space-y-4">
        <QueryForm value={form} onChange={setForm} onSubmit={() => run(form)} busy={result.isFetching} />
        <ExampleChips onPick={pickExample} />
      </div>
      <div aria-live="polite" aria-busy={result.isFetching} className="min-w-0">
        {submitted === null && <EmptyState />}
        {submitted !== null && result.isFetching && <ResultSkeleton />}
        {!result.isFetching && result.error && (
          <div role="alert" className="rounded border-2 border-amber-500 bg-amber-50 p-4 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-50">
            <p className="font-semibold">The search did not complete, so no answer is shown.</p>
            <p className="mt-1">{result.error.message}</p>
            <p className="mt-1">Next step: check that the backend is running (`make dev`), then search again.</p>
          </div>
        )}
        {!result.isFetching && result.data && (
          <ErrorBoundary resetKey={result.data.request_id}>
            <ResultCard response={result.data} activeId={drawer?.evidenceId ?? null} onOpen={setDrawer} onClarify={clarify} />
          </ErrorBoundary>
        )}
      </div>
      <div className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto">
        <ErrorBoundary resetKey={drawer?.evidenceId}>
          <SourceDrawer target={drawer} onClose={closeDrawer} />
        </ErrorBoundary>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded border border-dashed border-slate-400 p-6 text-sm text-slate-700 dark:border-slate-600 dark:text-slate-300">
      <p className="font-semibold">No search yet.</p>
      <p className="mt-1">
        Ask which FAA AD proposals concern an aircraft, then set the make, model and (optionally) serial. Or pick an example on the
        left. Answers cite the exact sentence in each proposal summary; applicability is decided by rules, not by the model.
      </p>
    </div>
  );
}
