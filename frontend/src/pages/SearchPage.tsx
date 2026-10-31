import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { DrawerTarget } from '../components/CitationChip';
import { QueryForm } from '../components/QueryForm';
import { ResultCard } from '../components/ResultCard';
import { ScenarioSwitcher } from '../components/ScenarioSwitcher';
import { SourceDrawer } from '../components/SourceDrawer';
import { DEFAULT_PRESET, SCENARIO_SWITCHER_ENABLED, type ScenarioPreset } from '../mocks/scenarioPresets';
import type { SearchRequest } from '../types/api';

const EMPTY_REQUEST: SearchRequest = { query: '', make: null, model: null, serial: null, as_of: null, mode: 'answer' };

export function SearchPage() {
  // With the dev flag on, the page opens on the first MOCK preset; otherwise on an empty form.
  const initial = SCENARIO_SWITCHER_ENABLED ? DEFAULT_PRESET.request : EMPTY_REQUEST;
  const [form, setForm] = useState<SearchRequest>(initial);
  const [submitted, setSubmitted] = useState<SearchRequest | null>(SCENARIO_SWITCHER_ENABLED ? initial : null);
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

  const pickPreset = (p: ScenarioPreset) => {
    setForm(p.request);
    run(p.request);
  };

  // A clarification choice becomes the model field and the search is re-run on the backend.
  const clarify = (option: string) => {
    const req = { ...form, model: option };
    setForm(req);
    run(req);
  };

  const closeDrawer = useCallback(() => setDrawer(null), []);

  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)_380px]">
      <div className="space-y-4">
        <QueryForm value={form} onChange={setForm} onSubmit={() => run(form)} busy={result.isFetching} />
        <ScenarioSwitcher onPick={pickPreset} />
      </div>
      <div aria-live="polite" aria-busy={result.isFetching}>
        {submitted === null && <p className="text-sm text-slate-600 dark:text-slate-400">Enter a question and aircraft configuration, then Search.</p>}
        {submitted !== null && result.isPending && <p className="text-sm">Searching…</p>}
        {result.error && (
          <p role="alert" className="rounded border-2 border-amber-500 p-3 text-sm">
            Request failed: {result.error.message}
          </p>
        )}
        {result.data && <ResultCard response={result.data} activeId={drawer?.evidenceId ?? null} onOpen={setDrawer} onClarify={clarify} />}
      </div>
      <div className="lg:sticky lg:top-4 lg:self-start">
        <SourceDrawer target={drawer} onClose={closeDrawer} />
      </div>
    </div>
  );
}
