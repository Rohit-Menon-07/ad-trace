"""FastAPI app for AD Trace (docs/SPEC.md section 7). Every endpoint serves real data from the ingested DB.

Startup warms the pipeline once: SQLite + FTS5, engine index, entity vocabulary, embedding model and dense matrix.
POST /api/search never returns 500 for an LLM failure: the pipeline degrades (rule-based parse, extractive answer).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import load_config, repo_path, resolve_as_of
from backend.app.ingest.makes import make_family
from backend.app.pipeline.records_api import meta_response, record_detail
from backend.app.pipeline.run import Pipeline, find_audit, set_pipeline
from backend.app.schemas import (
    EvalResults,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    MetaResponse,
    RecordDetail,
    SearchRequest,
    SearchResponse,
)

log = logging.getLogger("adtrace")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm the whole pipeline once at startup. Failures are reported via /api/health and /api/meta."""
    app.state.pipeline = None
    app.state.startup_error = None
    if os.environ.get("ADTRACE_SKIP_WARM") != "1":
        db = repo_path("sqlite_path")
        if db.exists():
            try:
                set_pipeline(Pipeline(db))
                from backend.app.pipeline.run import get_pipeline

                app.state.pipeline = get_pipeline()
                log.info("pipeline warm: %s", app.state.pipeline.retriever.dense.backend)
            except Exception as exc:  # never fail silently
                app.state.startup_error = f"{type(exc).__name__}: {exc}"
                log.exception("pipeline failed to load")
        else:
            app.state.startup_error = f"{db} not found: run `make ingest`"
    yield


app = FastAPI(
    title="AD Trace API",
    version="1.0.0",
    description="Traceable search over FAA AD proposals (NPRMs): rules decide applicability, the model only "
    "phrases, every claim is verified and cited.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def pipeline() -> Pipeline:
    p = getattr(app.state, "pipeline", None)
    if p is None:
        raise HTTPException(503, detail=getattr(app.state, "startup_error", None) or "pipeline not loaded")
    return p


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    pipeline()
    return HealthResponse(status="ok", mock=False)


@app.get("/api/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    p = pipeline()
    return meta_response(p.retriever.conn, p.retriever.dense.backend)


@app.get("/api/vocab/makes", response_model=list[str])
def vocab_makes() -> list[str]:
    return sorted(pipeline().linker.makes, key=str.casefold)


@app.get("/api/vocab/models", response_model=list[str])
def vocab_models(make: str = Query(..., min_length=1)) -> list[str]:
    linker = pipeline().linker
    if make not in linker.makes:
        return []
    fam = make_family(make)
    return sorted((m for m, fams in linker.model_makes.items() if fam in fams), key=str.casefold)


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    return pipeline().run(req)


@app.get("/api/records/{record_id}", response_model=RecordDetail)
def record(record_id: str) -> RecordDetail:
    p = pipeline()
    if record_id not in p.retriever.engine.records:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return record_detail(p.retriever.conn, p.retriever.engine, record_id, resolve_as_of())


@app.get("/api/eval/latest", response_model=EvalResults)
def eval_latest() -> EvalResults:
    path = repo_path("eval_results")
    if not path.exists():
        raise HTTPException(status_code=404, detail="No evaluation results yet: run `make eval`.")
    return EvalResults.model_validate_json(path.read_text(encoding="utf-8"))


@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(body: FeedbackRequest) -> FeedbackResponse:
    path = repo_path("feedback_log", section="logging")
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(UTC).isoformat(), "request_id": body.request_id, "reason": body.reason}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return FeedbackResponse(ok=True, mock=False)


@app.get("/api/audit/{request_id}")
def audit(request_id: str) -> dict[str, Any]:
    """Dev-only (config dev.audit_endpoint): the full audit record of one request."""
    if not load_config().get("dev", {}).get("audit_endpoint", False):
        raise HTTPException(status_code=404, detail="audit endpoint disabled")
    entry = find_audit(request_id, pipeline().audit_path)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No audit record for {request_id}")
    return entry
