# AD Trace

Traceable search over FAA airworthiness directive **proposals** (NPRMs). Given a make, a model and optionally a serial, it shows which proposals concern the aircraft. Every claim is cited to its source sentence. Applicability is computed by rules, and the tool refuses when the records don't support an answer. It is decision support only: the qualified engineer decides.

Design: [docs/SPEC.md](docs/SPEC.md). Decisions and deviations: [DECISIONS.md](DECISIONS.md). Evaluation: [docs/EVAL.md](docs/EVAL.md).

## Status
- Real pipeline end to end over the 431-row spreadsheet: ingestion, rule-based extraction with provenance, applicability/status engine, hybrid retrieval, gates, generation, verification, audit log.
- **No valid Anthropic API key is configured yet**, so generation and the LLM verifier fall back to verbatim extractive answers (the UI says so on every answer). Answer-quality metrics are NOT MEASURED until a key is set in `data/.env`.
- Evaluation: frozen test split; v2 numbers are a re-test after fixes and are labelled as such. Manual cases await human review.

## Screens
Taken by `python scripts/tasks.py screens` (Playwright, 1440x900).

| Answered (extractive fallback, source drawer open) | Partial (**MOCK**: fake model output, to show the removal UI) |
|---|---|
| ![answered](docs/screens/answered.png) | ![partial](docs/screens/partial.png) |
| **Refused (out of scope)** | **Needs clarification (model family)** |
| ![refused](docs/screens/refused.png) | ![needs clarification](docs/screens/needs_clarification.png) |

Also: [dark theme at 1280x720](docs/screens/answered_1280_dark.png), [coverage page](docs/screens/coverage.png), [evaluation page](docs/screens/evaluation.png).

Without a key the real pipeline cannot produce `partial` (extractive statements are verbatim), so that one screenshot uses canned FAKE model output from `backend/tests/fixtures/screenshot_fakes.py`; the response is flagged `mock: true` and the UI shows a MOCK badge.

## Run
```bash
python -m venv .venv && . .venv/Scripts/activate   # macOS/Linux: . .venv/bin/activate
make setup     # pip + npm install
make ingest    # build data/processed/adtrace.db + dense index from data/raw/*.xlsx
make dev       # backend http://localhost:8000 (OpenAPI at /docs) + frontend http://localhost:5173
make test      # pytest (incl. TS-type drift check) + tsc
make lint      # ruff check/format + eslint + tsc
make types     # regenerate frontend/src/types/api.ts from backend/app/schemas.py
make eval      # frozen test-split evaluation -> docs/EVAL.md, data/eval/results.json
```
No `make`? Run `python scripts/tasks.py <target>`; it is the same thing. Screenshots: `python scripts/tasks.py screens` (first run `npx playwright install chromium` in `frontend/`).
