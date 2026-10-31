import { SCENARIO_PRESETS, SCENARIO_SWITCHER_ENABLED, type ScenarioPreset } from '../mocks/scenarioPresets';

interface Props {
  onPick: (preset: ScenarioPreset) => void;
}

/** Dev-only: fills the form with a real-data preset query and submits it to the pipeline. */
export function ScenarioSwitcher({ onPick }: Props) {
  if (!SCENARIO_SWITCHER_ENABLED) return null;
  return (
    <fieldset className="rounded border-2 border-dashed border-fuchsia-600 p-3">
      <legend className="flex items-center gap-2 px-1 text-xs font-semibold">
        Dev presets (real data)
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
