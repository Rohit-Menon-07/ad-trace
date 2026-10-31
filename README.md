# AD Trace

Traceable search over FAA airworthiness directive **proposals** (NPRMs). Given a make, a model and optionally a serial, it shows which proposals concern the aircraft. Every claim is cited to its source sentence. Applicability is computed by rules, and the tool refuses when the records don't support an answer. It is decision support only: the qualified engineer decides.

Design: [docs/SPEC.md](docs/SPEC.md). Decisions and deviations: [DECISIONS.md](DECISIONS.md).

## Status
- **Frontend shell on MOCK data only.** There is no backend yet. Everything the UI shows is labelled MOCK.

## Run (frontend)
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 ; use the dev scenario switcher (bottom left)
npm run lint       # eslint
npm run typecheck  # tsc
```
The Makefile wraps these (`make setup`, `make dev`, `make lint`) if GNU make is available.
