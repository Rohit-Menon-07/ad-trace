import { SCENARIO_PRESETS, SCENARIO_SWITCHER_ENABLED, type ScenarioPreset } from '../mocks/scenarioPresets';
import { MockBadge } from './MockBadge';

interface Props {
  onPick: (preset: ScenarioPreset) => void;
}

/** Fills the form with a preset query and submits it to the real API, which routes it to a MOCK scenario. */
export function ScenarioSwitcher({ onPick }: Props) {
  if (!SCENARIO_SWITCHER_ENABLED) return null;
  return (
    <fieldset className="rounded border-2 border-dashed border-fuchsia-600 p-3">
      <legend className="flex items-center gap-2 px-1 text-xs font-semibold">
        Dev scenario presets <MockBadge label="MOCK" />
      </legend>
      <div className="flex flex-col items-start gap-1 text-sm">
        {SCENARIO_PRESETS.map((p) => (
          <button key={p.key} type="button" onClick={() => onPick(p)} data-scenario={p.key} className="underline-offset-2 hover:underline">
            {p.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
