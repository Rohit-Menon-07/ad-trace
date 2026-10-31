"""FastAPI app for AD Trace (docs/SPEC.md section 7).

Prompt 2 state: search, records, vocab and meta are served from backend/app/mocks.py and every
payload carries mock=True. Feedback is real (appended to logs/feedback.jsonl).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.app import mocks
from backend.app.config import load_config, repo_path, resolve_as_of
from backend.app.schemas import (
    EvalResults,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    MetaResponse,
    ModelIds,
    RecordDetail,
    SearchRequest,
    SearchResponse,
)

app = FastAPI(
    title="AD Trace API",
    version="0.2.0",
    description="Traceable search over FAA AD proposals (NPRMs). MOCK backend: all responses carry mock=true.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", mock=True)


@app.get("/api/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    cfg = load_config()["models"]
    return MetaResponse(
        dataset="AD Notice of Proposed Rulemaking (AD NPRM).xlsx",
        total_records=431,
        unique_dockets=323,
        as_of=resolve_as_of(),
        models=ModelIds(generation=cfg["generation"], query_parser=cfg["query_parser"], verifier=cfg["verifier"]),
        embedding_backend="MOCK (not loaded)",
        coverage=mocks.MOCK_COVERAGE,
        mock=True,
    )


@app.get("/api/vocab/makes", response_model=list[str])
def vocab_makes() -> list[str]:
    return mocks.MOCK_MAKES


@app.get("/api/vocab/models", response_model=list[str])
def vocab_models(make: str = Query(..., min_length=1)) -> list[str]:
    return mocks.MOCK_MODELS.get(make, [])


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    return mocks.mock_search(req)


@app.get("/api/records/{record_id}", response_model=RecordDetail)
def record(record_id: str) -> RecordDetail:
    detail = mocks.MOCK_RECORDS.get(record_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return detail


@app.get("/api/eval/latest", response_model=EvalResults)
def eval_latest() -> EvalResults:
    """Serve data/eval/results.json once `make eval` has produced it; until then the MOCK placeholder."""
    path = repo_path("eval_results")
    if path.exists():
        return EvalResults.model_validate_json(path.read_text(encoding="utf-8"))
    return mocks.MOCK_EVAL


@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(body: FeedbackRequest) -> FeedbackResponse:
    path = repo_path("feedback_log", section="logging")
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(UTC).isoformat(), "request_id": body.request_id, "reason": body.reason}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return FeedbackResponse(ok=True, mock=body.request_id.startswith("MOCK-"))
