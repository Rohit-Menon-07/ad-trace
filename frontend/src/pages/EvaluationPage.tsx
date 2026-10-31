import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { MetricsTable } from '../components/MetricsTable';
import { MockBadge } from '../components/MockBadge';

export function EvaluationPage() {
  const { data, isPending, error } = useQuery({ queryKey: ['eval'], queryFn: api.evalLatest });
  if (isPending) return <p className="text-sm">Loading evaluation…</p>;
  if (error) return <p className="text-sm">Could not load evaluation: {String(error)}</p>;
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-2">
        <h2 className="flex items-center gap-2 text-xl font-semibold">Evaluation {data.mock && <MockBadge />}</h2>
        {data.mock && (
          <p role="alert" className="rounded border-2 border-dashed border-fuchsia-600 p-3 text-sm font-semibold">
            MOCK placeholder numbers. Nothing on this page has been measured yet.
          </p>
        )}
        <p className="text-sm">
          Eval set: <span className="font-semibold">{data.eval_set.name}</span>, {data.eval_set.size} queries
          {data.eval_set.synthetic && <span className="ml-1 rounded border border-slate-500 px-1 text-xs font-semibold">SYNTHETIC</span>}. {data.eval_set.description}
        </p>
      </header>
      <section className="rounded border border-slate-300 p-4 dark:border-slate-700">
        <MetricsTable caption="System versus baselines" defs={data.metric_defs} rows={data.systems} />
      </section>
      <section className="rounded border border-slate-300 p-4 dark:border-slate-700">
        <MetricsTable caption="Ablation: verification safeguards" defs={data.metric_defs} rows={data.ablation} />
      </section>
      <section aria-labelledby="fail-h" className="rounded border-2 border-amber-500 p-4">
        <h3 id="fail-h" className="mb-2 font-semibold">Where it fails</h3>
        <ul className="space-y-4 text-sm">
          {data.failures.map((f) => (
            <li key={f.id}>
              <p className="font-mono text-xs">{f.id}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                <dt className="font-semibold">Query</dt>
                <dd>{f.query}</dd>
                <dt className="font-semibold">Expected</dt>
                <dd>{f.expected}</dd>
                <dt className="font-semibold">Observed</dt>
                <dd>{f.observed}</dd>
                <dt className="font-semibold">Cause</dt>
                <dd>{f.cause}</dd>
                <dt className="font-semibold">How the user knows</dt>
                <dd>{f.user_signal}</dd>
              </dl>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
