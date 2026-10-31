# AD Trace. Requires GNU make (on Windows: Git Bash + `choco install make`, or run the commands directly).
PY ?= python
FRONTEND := frontend

.PHONY: setup dev dev-frontend dev-backend test ingest eval lint

setup:
	$(PY) -m pip install -r backend/requirements.txt || echo "backend/requirements.txt not created yet (backend not built)"
	cd $(FRONTEND) && npm install

dev: dev-frontend

dev-frontend:
	cd $(FRONTEND) && npm run dev

dev-backend:
	$(PY) -m uvicorn backend.app.main:app --reload --port 8000

test:
	$(PY) -m pytest backend/tests -q || echo "no backend tests yet"
	cd $(FRONTEND) && npm run typecheck

ingest:
	$(PY) -m backend.app.ingest

eval:
	$(PY) -m backend.app.eval

lint:
	$(PY) -m ruff check backend || echo "ruff: backend not built yet"
	cd $(FRONTEND) && npm run lint && npm run typecheck
