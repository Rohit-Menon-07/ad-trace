import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.schemas import MetaResponse, RecordDetail, SearchResponse

client = TestClient(main.app)


def test_health() -> None:
    assert client.get("/api/health").json() == {"status": "ok", "mock": True}


def test_meta_is_flagged_mock_and_uses_config_models() -> None:
    meta = MetaResponse.model_validate(client.get("/api/meta").json())
    assert meta.mock is True
    assert meta.models.generation == "claude-sonnet-5-5"


def test_vocab() -> None:
    makes = client.get("/api/vocab/makes").json()
    assert "Airbus SAS" in makes
    assert "A330-243" in client.get("/api/vocab/models", params={"make": "Airbus SAS"}).json()
    assert client.get("/api/vocab/models", params={"make": "Nope"}).json() == []
    assert client.get("/api/vocab/models").status_code == 422


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"query": "Which proposed ADs concern the RMP?", "make": "Airbus SAS", "model": "A330-243"}, "answered"),
        ({"query": "fuel pump wiring", "make": "Airbus SAS", "model": "A320-214", "serial": "1234"}, "partial"),
        ({"query": "Torque values for the nose gear actuator?"}, "refused"),
        ({"query": "anything", "model": "A350-2000"}, "refused"),
        ({"query": "What proposed ADs affect the A330?"}, "needs_clarification"),
        ({"query": "What proposed ADs affect it?", "model": "A330"}, "needs_clarification"),
        ({"query": "What proposed ADs affect the A330?", "model": "A330-243"}, "answered"),
        ({"query": "Any ADs for MSN 1234?"}, "partial"),
    ],
)
def test_search_routes_to_mock_scenarios(body: dict, status: str) -> None:
    res = client.post("/api/search", json=body)
    assert res.status_code == 200
    resp = SearchResponse.model_validate(res.json())
    assert resp.status == status
    assert resp.mock is True
    assert resp.request_id.startswith("MOCK-req-")


def test_search_request_ids_are_unique() -> None:
    ids = {client.post("/api/search", json={"query": "x"}).json()["request_id"] for _ in range(3)}
    assert len(ids) == 3


def test_search_rejects_unknown_fields() -> None:
    assert client.post("/api/search", json={"query": "x", "evil": 1}).status_code == 422


def test_records() -> None:
    detail = RecordDetail.model_validate(client.get("/api/records/MOCK-R0001").json())
    assert detail.record.docket == "MOCK-FAA-2026-0101"
    assert client.get("/api/records/R9999").status_code == 404


def test_eval_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "repo_path", lambda key, section="data": tmp_path / "missing.json")
    assert client.get("/api/eval/latest").json()["mock"] is True


def test_feedback_appends_jsonl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log = tmp_path / "logs" / "feedback.jsonl"
    monkeypatch.setattr(main, "repo_path", lambda key, section="data": log)
    res = client.post("/api/feedback", json={"request_id": "MOCK-req-1", "reason": "wrong model"})
    assert res.json() == {"ok": True, "mock": True}
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["request_id"] == "MOCK-req-1" and entry["reason"] == "wrong model"
    assert client.post("/api/feedback", json={"request_id": "x", "reason": ""}).status_code == 422


def test_openapi_lists_all_endpoints() -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths >= {
        "/api/health",
        "/api/meta",
        "/api/vocab/makes",
        "/api/vocab/models",
        "/api/search",
        "/api/records/{record_id}",
        "/api/eval/latest",
        "/api/feedback",
    }
    assert client.get("/docs").status_code == 200


def test_cors_allows_vite_dev_server() -> None:
    res = client.options(
        "/api/search",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
