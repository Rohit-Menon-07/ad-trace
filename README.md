# AD Trace

Traceable search over FAA airworthiness directive **proposals** (NPRMs). Given a make, a model and optionally a serial, it shows which proposals concern the aircraft. Every claim is cited to its source sentence. Applicability is computed by rules, and the tool refuses when the records don't support an answer. It is decision support only: the qualified engineer decides.

Design: [docs/SPEC.md](docs/SPEC.md). Decisions and deviations: [DECISIONS.md](DECISIONS.md).

## Status
- **MOCK backend.** FastAPI serves all SPEC §7 endpoints, but search, records, vocab, meta and eval return canned MOCK data (`mock: true`, shown as a MOCK tag in the UI). There is no ingestion or pipeline yet.

## Run
```bash
python -m venv .venv && . .venv/Scripts/activate   # macOS/Linux: . .venv/bin/activate
make setup     # pip + npm install
make dev       # backend http://localhost:8000 (OpenAPI at /docs) + frontend http://localhost:5173
make test      # pytest (incl. TS-type drift check) + tsc
make lint      # ruff check/format + eslint + tsc
make types     # regenerate frontend/src/types/api.ts from backend/app/schemas.py
```
No `make`? Run `python scripts/tasks.py <target>`; it is the same thing.
