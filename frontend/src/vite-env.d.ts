/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" shows the dev-only MOCK scenario switcher (see .env.development). */
  readonly VITE_SCENARIO_SWITCHER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
