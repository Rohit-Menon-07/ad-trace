# DECISIONS.md

Deviations from docs/SPEC.md and choices made where it was ambiguous. One line each: decision, then reason. Newest at the bottom.

## Prompt 1: scaffold + frontend shell

1. **Raw file name.** The real file is `data/raw/AD Notice of Proposed Rulemaking (AD NPRM).xlsx` (spaces and parentheses), not the underscored name in SPEC §2. `config.yaml` points at the real name. *Reason: match what is on disk; don't rename source data.*
2. **`RecordCard` and `ExcludedRecord` defined by us.** SPEC §7 uses them but doesn't define them. Fields are in `frontend/src/types/api.ts`. RecordCard holds status, comment period, lineage, models, model-list confidence and retrieval score. ExcludedRecord holds record id, docket, rule id and reason. *Reason: smallest shape that covers the UI spec in §8.*
3. **Extra API types defined:** `LineageEdge`, `RecordDetail` (for `/api/records/{id}`), `MetaResponse`, `CoverageReport`, `EvalResults`. *Reason: SPEC lists these endpoints without response schemas; the backend must match these types or update them.*
4. **No count of dropped claims in `SearchResponse`.** The UI reads `trace[S7].details.claims_dropped` for the "N claims removed" notice. *Reason: no schema change needed, and the code-generated trace already carries it.*
5. **Reason-code copy (title and suggested next action) lives in the frontend** (`components/reasonCodes.ts`). The codes themselves still come only from the backend. *Reason: the refusal card needs a "next action" (§8), but SearchResponse has no field for it; this is UI text, not a decision.*
6. **Source drawer is a fixed right column, not an overlay.** On narrow screens it stacks below the result. *Reason: §8 says "Right: source drawer"; a fixed column is simpler and works with the keyboard (Esc closes it, focus moves to it).*
7. **No router.** Search, Coverage and Evaluation are switched with local state. *Reason: react-router is not in the allowed stack.*
8. **Tailwind v4** (`@tailwindcss/vite`), with class-based dark mode via `@custom-variant`. *Reason: current major version; no PostCSS config needed.*
9. **MOCK labelling.** Mock records use ids `MOCK-R000n`, dockets `MOCK-FAA-…` and citations `MOCK 91 FR …`, with `url: null`. A fuchsia dashed MOCK badge appears in the header, on every mock response, in the source drawer and on Coverage/Evaluation. *Reason: fake data must never look like a real FAA notice.*
10. **Mock evaluation numbers are placeholders.** The Evaluation page shows a "MOCK placeholder numbers. Nothing has been measured" alert. *Reason: the tables must exist now, but no metric has been measured.*
11. **Mock citations are checked at load time.** `mockCite()` throws if a quote is not a substring of its sentence (mirrors H4). *Reason: stops mock quotes drifting from their sources.*
12. **Clarification chip in MOCK mode** fills the model field and serves the "answered" scenario. The real backend will re-run the pipeline. *Reason: mocks can't compute; the behaviour is marked in code.*
13. **`config.yaml` `as_of: null` means "today at request time".** The resolved date is echoed in `SearchResponse.as_of` and in the audit log. *Reason: as_of defaults to today but stays visible and reproducible per request.*
14. **Generated data is git-ignored:** `data/raw/`, `data/processed/*`, `data/index/*`, `logs/*`, and `.env` at any depth (including the existing `data/.env`). *Reason: the source file is not redistributed, derived files are rebuilt by `make ingest`, and logs contain user queries.*
15. **Makefile written, but `make` is not installed on the dev machine (Windows).** Run the commands directly; CLAUDE.md says so. Backend targets in the Makefile are placeholders until the backend exists. *Reason: keep the repo standard without blocking work.*
16. **Applicability verdict for a "series" designation (e.g. "A330-200 series") is UNDETERMINED in the mocks.** It is not treated as APPLICABLE. *Reason: the conservative reading of SPEC S4; the backend will apply the same rule.*
