import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { CoverageBars } from '../components/CoverageBars';
import { MockBadge } from '../components/MockBadge';

export function CoveragePage() {
  const { data, isPending, error } = useQuery({ queryKey: ['meta'], queryFn: api.meta });
  if (isPending) return <p className="text-sm">Loading coverage…</p>;
  if (error) return <p className="text-sm">Could not load coverage: {String(error)}</p>;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-1">
        <h2 className="flex items-center gap-2 text-xl font-semibold">Data coverage {data.mock && <MockBadge />}</h2>
        <p className="text-sm text-slate-700 dark:text-slate-300">
          {data.dataset}: {data.total_records} records, {data.unique_dockets} unique dockets. As of {data.as_of}. Embeddings: {data.embedding_backend}.
        </p>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Models: generation {data.models.generation}; parser {data.models.query_parser}; verifier {data.models.verifier}.
        </p>
      </header>
      <section aria-labelledby="cov-h" className="rounded border border-slate-300 p-4 dark:border-slate-700">
        <h3 id="cov-h" className="mb-3 font-semibold">What the pipeline could extract</h3>
        <CoverageBars metrics={data.coverage.metrics} />
      </section>
      <section aria-labelledby="lim-h" className="rounded border-2 border-amber-500 p-4">
        <h3 id="lim-h" className="mb-2 font-semibold">Limits you should know</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {data.coverage.limits.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
