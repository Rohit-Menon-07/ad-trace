import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { MetricsTable } from '../components/MetricsTable';
import { MockBadge } from '../components/MockBadge';
import { Skeleton } from '../components/Skeleton';

export function EvaluationPage() {
  const { data, isPending, error } = useQuery({ queryKey: ['eval'], queryFn: api.evalLatest });
  if (isPending) return <div className="mx-auto max-w-5xl"><Skeleton lines={10} label="Loading evaluation" /></div>;
  if (error)
    return (
      <p role="alert" className="mx-auto max-w-5xl rounded border-2 border-amber-500 p-3 text-sm">
        No evaluation results yet ({error.message}). Run <code>make eval</code> to produce data/eval/results.json.
      </p>
    );
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="space-y-2">
        <h2 className="flex items-center gap-2 text-xl font-semibold">Evaluation {data.mock && <MockBadge />}</h2>
        <p className="text-sm">
          Eval set: <span className="font-semibold">{data.eval_set.name}</span>, {data.eval_set.size} queries
          {data.eval_set.synthetic && <span className="ml-1 rounded border border-slate-500 px-1 text-xs font-semibold">SYNTHETIC QUERIES</span>}. Generated{' '}
          {data.generated_at}.
        </p>
        <p className="text-xs text-slate-600 dark:text-slate-400">{data.eval_set.description}</p>
      </header>

      {data.caveats.length > 0 && (
        <section aria-labelledby="cav-h" className="rounded border-2 border-amber-500 p-4">
          <h3 id="cav-h" className="mb-1 font-semibold">Read these before the numbers</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {data.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded border border-slate-300 p-4 dark:border-slate-700">
        <MetricsTable caption="System versus baselines (brackets: bootstrap 95% interval; n: cases behind the value)" defs={data.metric_defs} rows={data.systems} />
      </section>
      <section className="rounded border border-slate-300 p-4 dark:border-slate-700">
        <MetricsTable caption="Ablation S0 to S2: verification safeguards (share of model-written claims passing each layer)" defs={data.metric_defs} rows={data.ablation} />
      </section>

      <section aria-labelledby="fail-h" className="rounded border-2 border-amber-500 p-4">
        <h3 id="fail-h" className="mb-1 font-semibold">Where it fails, and how the user would know</h3>
        <p className="mb-3 text-xs text-slate-600 dark:text-slate-400">
          VISIBLE = the user sees a warning (refusal, UNDETERMINED badge, partial answer). SILENT = no warning; the dangerous kind.
        </p>
        {data.failures.length === 0 ? (
          <p className="text-sm">No failure cases in this run. That does not mean none exist: see the caveats above.</p>
        ) : (
          <ul className="space-y-4 text-sm">
            {data.failures.map((f, i) => {
              const silent = f.user_signal.startsWith('SILENT');
              return (
                <li key={`${f.id}-${i}`} className="rounded border border-slate-300 p-3 dark:border-slate-700">
                  <p className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold">{f.id}</span>
                    <span className={`rounded border px-1.5 text-xs font-bold ${silent ? 'border-amber-700 bg-amber-100 text-amber-950 dark:bg-amber-900 dark:text-amber-50' : 'border-slate-500'}`}>
                      {silent ? 'SILENT' : 'VISIBLE'}
                    </span>
                  </p>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                    <dt className="font-semibold">Query</dt>
                    <dd>{f.query}</dd>
                    <dt className="font-semibold">Expected</dt>
                    <dd className="break-words font-mono text-xs">{f.expected}</dd>
                    <dt className="font-semibold">Observed</dt>
                    <dd className="break-words font-mono text-xs">{f.observed}</dd>
                    <dt className="font-semibold">Cause</dt>
                    <dd>{f.cause}</dd>
                    <dt className="font-semibold">User signal</dt>
                    <dd>{f.user_signal}</dd>
                  </dl>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
