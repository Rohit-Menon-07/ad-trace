// Dev-only presets: real-data queries (same as scripts/demo_queries.py) that exercise each response status.
// They only fill the form; every answer comes from the real pipeline. (The file keeps its old location.)

import type { SearchRequest } from '../types/api';

export type ScenarioKey = string;

export interface ScenarioPreset {
  key: ScenarioKey;
  label: string;
  request: SearchRequest;
}

const AS_OF = '2026-10-31';
const q = (query: string, extra: Partial<SearchRequest> = {}): SearchRequest => ({
  query, make: null, model: null, serial: null, as_of: AS_OF, mode: 'answer', ...extra,
});

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  { key: 'a330', label: 'A330-243 RMP lookup', request: q('Which proposed ADs concern the radio management panels on our A330-243?', { make: 'Airbus SAS', model: 'A330-243' }) },
  { key: 'serial', label: 'PA-28-181 serial 1234 (undetermined)', request: q('Do the proposed ADs apply to our PA-28-181 serial 1234?', { make: 'Piper Aircraft, Inc.', model: 'PA-28-181', serial: '1234' }) },
  { key: 'family', label: 'Family-only "A330" (clarify)', request: q('What proposed ADs affect the A330?', { make: 'Airbus SAS', model: 'A330' }) },
  { key: 'unknown', label: 'Unknown make (refused)', request: q('Any proposed ADs for our airship?', { make: 'Zeppelin' }) },
  { key: 'torque', label: 'Torque question (out of scope)', request: q('What torque should I apply to the RMP mounting screws on our A330-243?', { make: 'Airbus SAS', model: 'A330-243' }) },
  { key: 'premise', label: 'False premise AD 2025-09-07', request: q('Since AD 2025-09-07 applies to the A320-214, what else do I need to do?', { make: 'Airbus SAS' }) },
  { key: 'pw4090', label: 'PW4090 engine lookup', request: q('What would the proposal for the PW4090 engines require?', { model: 'PW4090' }) },
  { key: 'search_only', label: 'A330-243 search-only (no LLM)', request: q('radio management panel', { make: 'Airbus SAS', model: 'A330-243', mode: 'search_only' }) },
];

export const DEFAULT_PRESET = SCENARIO_PRESETS[0] as ScenarioPreset;

/** Dev flag: shown only in `vite dev` with VITE_SCENARIO_SWITCHER=1 (see frontend/.env.development). */
export const SCENARIO_SWITCHER_ENABLED = import.meta.env.DEV && import.meta.env.VITE_SCENARIO_SWITCHER === '1';
