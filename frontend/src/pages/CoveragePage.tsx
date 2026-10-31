import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { CoverageBars } from '../components/CoverageBars';
import { MockBadge } from '../components/MockBadge';
import { Skeleton } from '../components/Skeleton';

export function CoveragePage() {
  const { data, isPending, error } = useQuery({ queryKey: ['meta'], queryFn: api.meta });
  if (isPending) return <div className="mx-auto max-w-3xl"><Skeleton lines={8} label="Loading coverage" /></div>;
  if (error)
    return (
      <p role="alert" className="mx-auto max-w-3xl rounded border-2 border-amber-500 p-3 text-sm">
        Could not load coverage from /api/meta: {error.message}. Is the backend running?
      </p>
    );
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-1">
        <h2 className="flex items-center gap-2 text-xl font-semibold">Data coverage {data.mock && <MockBadge />}</h2>
        <p className="text-sm text-slate-700 dark:text-slate-300">
          {data.dataset}: {data.total_records} records, {data.unique_dockets} unique dockets. As of {data.as_of}. Embeddings: {data.embedding_backend}.
        </p>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Models: generation {data.models.generation}; parser {data.models.query_parser}; verifier {data.models.verifier}. Index{' '}
          <span className="font-mono">{data.index_version}</span>. Coverage report generated {data.coverage.generated_at}.
        </p>
      </header>

      <section aria-labelledby="know-h" className="rounded border-2 border-amber-500 p-4">
        <h3 id="know-h" className="mb-2 font-semibold">What AD Trace cannot know</h3>
        <p className="mb-2 text-sm">
          AD Trace reads one spreadsheet of FAA Notices of Proposed Rulemaking. Each row has a short summary, not the notice itself. So it can
          tell you which proposals name your aircraft, what they would require at summary level, and how they relate to each other. It cannot
          give you compliance steps, part numbers, torque values or legal advice, and it cannot tell you whether a proposal became a final AD.
          It decides serial-number applicability only where a summary states serials, and the bars below show how rarely that happens. When
          it cannot decide, it says UNDETERMINED or declines instead of guessing.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {data.coverage.limits.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="cov-h" className="rounded border border-slate-300 p-4 dark:border-slate-700">
        <h3 id="cov-h" className="mb-3 font-semibold">What the extraction rules could read (share of records)</h3>
        <CoverageBars metrics={data.coverage.metrics} />
      </section>
    </div>
  );
}
