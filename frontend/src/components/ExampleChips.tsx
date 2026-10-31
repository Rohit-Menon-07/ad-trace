import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { ExampleQuery } from '../types/api';

const CATEGORY_LABEL: Record<string, string> = {
  lookup: 'lookup',
  model_applicability: 'applicability',
  serial_unresolved: 'serial',
  supersession: 'supersession',
  status: 'comment period',
  unknown_entity: 'unknown aircraft',
  ambiguous_family: 'model family',
  out_of_scope: 'out of scope',
  false_premise: 'false premise',
  injection: 'injection',
  off_topic: 'off topic',
  empty_summary: 'empty summary',
};

/** Inputs taken from the evaluation cases (GET /api/examples). Only the question and configuration are filled in;
 * every answer comes from the live pipeline, so judges can also edit them and try their own. */
export function ExampleChips({ onPick }: { onPick: (e: ExampleQuery) => void }) {
  const { data, isError } = useQuery({ queryKey: ['examples'], queryFn: api.examples, staleTime: Infinity });
  if (isError || !data || data.length === 0) return null;
  return (
    <section aria-labelledby="examples-h" className="rounded border border-slate-300 p-3 dark:border-slate-700">
      <h2 id="examples-h" className="text-sm font-semibold">Try an example</h2>
      <p className="mb-2 text-xs text-slate-600 dark:text-slate-400">Questions from our evaluation set (inputs only). Edit them or write your own.</p>
      <ul className="space-y-1">
        {data.map((e) => (
          <li key={e.case_id}>
            <button
              type="button"
              onClick={() => onPick(e)}
              title={`${e.query} (eval case ${e.case_id})`}
              className="block w-full truncate rounded border border-slate-300 px-2 py-0.5 text-left text-xs hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              <span className="font-semibold">{CATEGORY_LABEL[e.category] ?? e.category}:</span> {e.query}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
