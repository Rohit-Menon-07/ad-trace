import { MOCK_SCENARIOS, SCENARIO_ORDER, type ScenarioKey } from '../mocks/scenarios';
import { MockBadge } from './MockBadge';

interface Props {
  value: ScenarioKey;
  onChange: (k: ScenarioKey) => void;
}

/** Dev-only: picks which MOCK response the mock client returns. Not rendered in production builds. */
export function ScenarioSwitcher({ value, onChange }: Props) {
  if (!import.meta.env.DEV) return null;
  return (
    <fieldset className="rounded border-2 border-dashed border-fuchsia-600 p-3">
      <legend className="flex items-center gap-2 px-1 text-xs font-semibold">
        Dev scenario switcher <MockBadge label="MOCK" />
      </legend>
      <div className="flex flex-col gap-1 text-sm">
        {SCENARIO_ORDER.map((k) => (
          <label key={k} className="flex items-center gap-2">
            <input type="radio" name="scenario" value={k} checked={value === k} onChange={() => onChange(k)} />
            {MOCK_SCENARIOS[k].label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
