# AD Trace. Every target delegates to scripts/tasks.py so `make X` == `python scripts/tasks.py X`
# (useful on Windows, where GNU make is often missing). Activate .venv first, or pass PY=...
PY ?= python

.PHONY: setup dev test lint types ingest eval

setup:
	$(PY) scripts/tasks.py setup

dev:
	$(PY) scripts/tasks.py dev

test:
	$(PY) scripts/tasks.py test

lint:
	$(PY) scripts/tasks.py lint

types:
	$(PY) scripts/tasks.py types

ingest:
	$(PY) scripts/tasks.py ingest

eval:
	$(PY) scripts/tasks.py eval
