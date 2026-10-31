# CLAUDE.md: AD Trace project memory

Read this first in every session, then read **docs/SPEC.md** (the authoritative design: principles H1–H13, architecture, data model, pipeline S1–S8, reason codes, API contract, UI spec). If you must deviate from SPEC.md, log it in **DECISIONS.md** first.

## Event and challenge
Autonomous SG 2026 (Acacia Hackathon Society x NUS Product Club), AI & Aerospace track, hosted with Airbus. 6-hour build. Challenge #4: "How might AI help people find, understand, and verify regulated technical information?"

GenAI hallucinates or blends instructions across equipment types; mechanics need answers they can trust. The organisers want a traceable, context-aware search engine that ingests technical documents, parses exact applicability rules, answers natural-language queries with citations, and refuses on ambiguity. Requirements:
- **Specific references**: every claim links to exact source metadata.
- **Zero hallucination**: we do NOT claim zero. We measure and report the unsupported-claim rate with and without safeguards.
- **Configuration filtering**: conditional applicability (e.g. serials S-1000 to S-1500) evaluated methodically, in code.
- **Revision logic**: user sees multiple versions and which is latest (supersession).
- **Uncertainty**: out-of-scope, contradictory or ambiguous prompts get a clear "cannot complete" message.
- **Sub-3-second retrieval.**
- **Avoid**: LLM guessing from pre-trained memory; unstructured free-text output.

## Judging rubric (3 judges, 1–5 each, weighted)
- **Problem realism 20%**: named user, narrow workflow, clear status quo and cost. Weak = generic aviation chatbot.
- **Technical soundness 25%**: working end-to-end; right method per task (LLM for reading/retrieval/explanation; rules/code for compliance logic). Handles input beyond the scripted demo. Weak = LLM-only legality checks, opaque scores, hard-coded demo.
- **Honest evaluation 20%**: metrics, test data, baseline, failure cases. Label synthetic data. Show at least one wrong/uncertain/declined case and how the user would know.
- **Trust and traceability 20%**: qualified person can verify before acting; trace to document, revision, section; handle applicability and missing evidence; human in control.
- **Impact 10%**: measured or reasoned improvement over baseline; distinguish measured from estimated.
- **Time discipline 5%**: early submission, demo ≤ 3 minutes.
- Judges reward sound restraint over polish: "Where does this fail, and how would your user know?"

## Data facts (one file: `data/raw/AD Notice of Proposed Rulemaking (AD NPRM).xlsx`)
One sheet, 431 rows, 22 columns: Docket Number, Subject Heading, Status, CFR Part Reference, Issue Date, Service/Office, Office of Primary Responsibility, AD Number, Citation Publish Date, Comments Due Date, Make, Model, Product Type, Product Subtype, AC Reference, AIR Policy Reference, Additional Reference, Link for Submitting Public Comment, Citation, Page Number, Summary, Comments.
- All rows are **NPRMs (PROPOSED, not in force)**. Always "the proposed AD would require", never "the AD requires".
- Summary is the only free text (~800 chars, some empty). No full text. No ground-truth Q&A.
- Model filled in only 86 rows; AD Number only 21; ~100 summaries mention superseding an AD; ~19 mention serial numbers.
- Make has 91 spellings; 323 unique dockets over 431 rows; Comments filled in 5 rows.
- Issue dates run to 2026-10-15; an `as_of` date drives comment-period status.
- These limits are part of the story; report them honestly (Coverage page).

## Product
**AD Trace.** User: B1 licensed engineer or continuing-airworthiness planner at an MRO. Workflow: given make, model and optional serial, find which FAA AD proposals concern it, what they would require (summary level), supersession and status.
**Must refuse**: compliance steps, torque values, part numbers, anything not in the records, legal advice. The tool narrows and cites; the human decides.

## Working agreements
- Build in the order of the user's prompts. Do not build ahead.
- Stack: Python 3.11+, FastAPI, pydantic v2, SQLite FTS5; React 18 + Vite + TypeScript + Tailwind + TanStack Query (+ lucide-react icons). No other infrastructure.
- No hard-coded demo answers outside `frontend/src/mocks` and tests. Anything fake is labelled MOCK in code and visibly in the UI.
- Every module gets pytest tests. Small typed functions. Run ruff and tsc (and eslint) before reporting done.
- Never put the LLM in charge of a rule-based decision (applicability, status, supersession, dates, counts).
- After each task report: what changed, how to run it, what was verified, what could NOT be verified.
- Commit after every prompt with a clear message.
- Ambiguity: don't ask; choose the most conservative option and log it in DECISIONS.md with a one-line reason.

## Repo map
- `config.yaml`: pinned model IDs, thresholds, `as_of` (null = today). Loaded by `backend/app/config.py`.
- `backend/app/schemas.py`: **single source of truth for the API contract** (SPEC §7 + extras). After changing it run `python scripts/tasks.py types` (regenerates `frontend/src/types/api.ts` + `docs/api.schema.json`); a pytest fails on drift. Never hand-edit `api.ts`.
- `backend/app/main.py`: FastAPI endpoints. `backend/app/mocks.py`: MOCK data + keyword routing (delete once S1–S8 exist).
- `frontend/src/api/client.ts`: the only data layer (`api.*` fetch wrappers; Vite proxies /api → :8000). `frontend/src/mocks/scenarioPresets.ts`: dev-only request presets.
- `scripts/tasks.py`: task runner behind the Makefile. Windows dev box has no `make`: use `.venv/Scripts/python scripts/tasks.py {setup,dev,test,lint,types}`.
- Python venv: `.venv/` (Python 3.14 locally; code targets 3.11+).
- `backend/app/ingest/`: loader (raw_* kept untouched), clean, makes (alias rules), duplicates (docket classes), sentences (offset-exact splitter, ids `R0001#s1`), db, audit, run (CLI `python -m backend.app.ingest.run` = `make ingest`, idempotent). Output: `data/processed/adtrace.db` (tables records, sentences, record_makes, vocab[kind=make], docket_groups, ingest_meta) plus generated `configs/alias_make.yaml`, `docs/make_audit.md`, `docs/duplicates_audit.md`.
- Ingest facts: 431 records, 323 dockets, 2102 sentences, 99 canonical makes, 1 empty summary, 1 is_duplicate (R0195), docket classes single 220 / revision_series 93 / multi_product 5 / correction 4 / exact_duplicate 1. Same-docket rows are mostly NPRM → SNPRM → withdrawal lineage (to be parsed in Prompt 4). Source has PDF artifacts like "AD 2024- 05-13" that extraction must tolerate.
- `backend/app/extract/`: rule-only extraction (models, serials, lineage, run). Tables: extractions (provenance: source, sentence_id, span, rule_id, confidence), lineage_edges, record_flags (per-record model list/confidence, withdrawn status: S4 inputs), vocab kinds model/family. Outputs `data/processed/coverage_report.json` (CoverageReport schema), `docs/unextracted.md`, `docs/extraction_spotcheck.csv` (hand-labelled by the user; NEVER fill or overwrite it), precision via `scripts/spotcheck_precision.py`.
- Extraction facts (430 non-dup records): model list 88.6% (HIGH column 19.8%, MEDIUM summary 68.8%); serial constraints 0% (no summary states serials); service-info applicability 0%; numbered supersession 17.9% (targets never in dataset); withdrawn or withdrawal notice 49.8% (123 records ARE withdrawal notices). Weakest: Appliance/Propeller 0%, Engines 56%, pre-2020 ~80%, withdrawal notices 81%.

- `backend/app/engine/`: PURE-code S4. `data.load_index(db)` → EngineIndex of frozen EngineRecords (~20 ms); `applicability.evaluate(LinkedConfig, record)` → verdict/rule/reasons/evidence_ids/basis; `status.record_status` / `status.lineage`. Rules and reason texts in `configs/rules.yaml`. Safety invariant: NOT_APPLICABLE only on HIGH/MEDIUM basis (property + sweep tests). Match kinds add SERIES_OVERLAP and SPELLING_VARIANT (→ UNDETERMINED). CLI `python -m backend.app.engine.explain --record R0003 --make "Airbus SAS" --model A330-243 [--serial] [--as-of] [--bench]`. All 431 records in ~2.5 ms.

## Progress log
- Prompt 1: repo scaffold, CLAUDE.md, DECISIONS.md, frontend shell on MOCK data with dev scenario switcher.
- Prompt 2: Pydantic schemas + generated TS types, FastAPI mock backend (all 8 endpoints, mock=true), UI wired to the API, pytest suite, `make dev` runs both servers.
- Prompt 3: ingestion + cleaning into SQLite, make alias map + audit, duplicate-docket audit, sentence splitter, 85 tests.
- Prompt 4: rule-based extraction with provenance (25 rule_ids, golden REAL + SYNTHETIC tests), lineage edges, coverage report, spot-check CSV; `make ingest` runs ingest+extract idempotently; 139 tests.
- Prompt 5: deterministic applicability/status/lineage engine + explain CLI; 34 synthetic + 20 real verdict cases, safety-invariant property tests; 213 tests.
