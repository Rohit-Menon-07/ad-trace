import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { search, USE_MOCK } from '../api/client';
import type { DrawerTarget } from '../components/CitationChip';
import { QueryForm } from '../components/QueryForm';
import { ResultCard } from '../components/ResultCard';
import { ScenarioSwitcher } from '../components/ScenarioSwitcher';
import { SourceDrawer } from '../components/SourceDrawer';
import { MOCK_SCENARIOS, type ScenarioKey } from '../mocks/scenarios';
import type { SearchRequest } from '../types/api';

interface Submitted {
  req: SearchRequest;
  scenario: ScenarioKey;
}

const INITIAL: ScenarioKey = 'answered';

export function SearchPage() {
  const [scenario, setScenario] = useState<ScenarioKey>(INITIAL);
  const [form, setForm] = useState<SearchRequest>(MOCK_SCENARIOS[INITIAL].request);
  const [submitted, setSubmitted] = useState<Submitted>({ req: MOCK_SCENARIOS[INITIAL].request, scenario: INITIAL });
  const [drawer, setDrawer] = useState<DrawerTarget | null>(null);

  const result = useQuery({
    queryKey: ['search', submitted],
    queryFn: () => search(submitted.req, submitted.scenario),
  });

  const run = (req: SearchRequest, sc: ScenarioKey) => {
    setDrawer(null);
    setSubmitted({ req, scenario: sc });
  };

  const pickScenario = (k: ScenarioKey) => {
    setScenario(k);
    setForm(MOCK_SCENARIOS[k].request);
    run(MOCK_SCENARIOS[k].request, k);
  };

  // MOCK: choosing a clarification option fills the model field; the mock client then serves
  // the "answered" scenario. The real backend will re-run the pipeline with the chosen model.
  const clarify = (option: string) => {
    const req = { ...form, model: option };
    const next: ScenarioKey = USE_MOCK ? 'answered' : scenario;
    setForm(req);
    setScenario(next);
    run(req, next);
  };

  const closeDrawer = useCallback(() => setDrawer(null), []);

  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)_380px]">
      <div className="space-y-4">
        <QueryForm value={form} onChange={setForm} onSubmit={() => run(form, scenario)} busy={result.isFetching} />
        <ScenarioSwitcher value={scenario} onChange={pickScenario} />
      </div>
      <div aria-live="polite" aria-busy={result.isFetching}>
        {result.isPending && <p className="text-sm">Searching…</p>}
        {result.error && <p className="rounded border border-amber-500 p-3 text-sm">Request failed: {String(result.error)}</p>}
        {result.data && <ResultCard response={result.data} activeId={drawer?.evidenceId ?? null} onOpen={setDrawer} onClarify={clarify} />}
      </div>
      <div className="lg:sticky lg:top-4 lg:self-start">
        <SourceDrawer target={drawer} onClose={closeDrawer} />
      </div>
    </div>
  );
}
