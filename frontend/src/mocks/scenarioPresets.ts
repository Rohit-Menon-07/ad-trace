// MOCK: dev-only form presets for the scenario switcher. Each preset is a plain SearchRequest
// whose wording routes to one MOCK scenario in backend/app/mocks.py (choose_scenario).
// The responses themselves now come from the backend.

import type { SearchRequest } from '../types/api';

export type ScenarioKey = 'answered' | 'partial' | 'refused' | 'needs_clarification';

export interface ScenarioPreset {
  key: ScenarioKey;
  label: string;
  request: SearchRequest;
}

const AS_OF = '2026-10-31';

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    key: 'answered',
    label: 'Answered (A330-243 RMP)',
    request: { query: 'Which proposed ADs concern the radio management panels on our A330-243?', make: 'Airbus SAS', model: 'A330-243', serial: null, as_of: AS_OF, mode: 'answer' },
  },
  {
    key: 'partial',
    label: 'Partial (A320-214 MSN 1234)',
    request: { query: 'Any proposed ADs on the fuel pump wiring for A320-214 MSN 1234?', make: 'Airbus SAS', model: 'A320-214', serial: '1234', as_of: AS_OF, mode: 'answer' },
  },
  {
    key: 'refused',
    label: 'Refused (UNKNOWN_ENTITY)',
    request: { query: 'Torque values for the A350-2000 nose gear actuator?', make: 'Airbus SAS', model: 'A350-2000', serial: null, as_of: AS_OF, mode: 'answer' },
  },
  {
    key: 'needs_clarification',
    label: 'Clarify (AMBIGUOUS_MODEL)',
    request: { query: 'What proposed ADs affect the A330?', make: 'Airbus SAS', model: 'A330', serial: null, as_of: AS_OF, mode: 'answer' },
  },
];

export const DEFAULT_PRESET = SCENARIO_PRESETS[0] as ScenarioPreset;

/** Dev flag: shown only in `vite dev` with VITE_SCENARIO_SWITCHER=1 (see frontend/.env.development). */
export const SCENARIO_SWITCHER_ENABLED = import.meta.env.DEV && import.meta.env.VITE_SCENARIO_SWITCHER === '1';
