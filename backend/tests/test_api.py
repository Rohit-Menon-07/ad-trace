"""API tests against the REAL pipeline (ingested workbook, TF-IDF embedder, FAKE LLM). No mocks in the live path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.llm import fake
from backend.app.schemas import MetaResponse, RecordDetail, SearchResponse


@pytest.fixture(scope="module")
def pipeline(real_db, tmp_path_factory):
    from backend.app.pipeline.run import Pipeline
    from backend.app.retrieval.dense import TfidfEmbedder
    from backend.app.retrieval.retriever import Retriever

    tmp = tmp_path_factory.mktemp("api")
    r = Retriever(real_db, embedder=TfidfEmbedder("tests"), index_dir=tmp)
    return Pipeline(real_db, retriever=r, audit_path=tmp / "audit.jsonl")


@pytest.fixture
def client(pipeline, monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODE", "fake")
    fake.clear()
    main.app.state.pipeline = pipeline
    yield TestClient(main.app)
    fake.clear()


def test_health_and_meta_are_real(client) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "mock": False}
    meta = MetaResponse.model_validate(client.get("/api/meta").json())
    assert (meta.total_records, meta.unique_dockets, meta.mock) == (431, 323, False)
    assert meta.embedding_backend.startswith("tfidf") and meta.index_version.startswith("src:")
    assert meta.models.generation == "claude-sonnet-5-5" and meta.coverage.metrics


def test_vocab_is_real(client) -> None:
    makes = client.get("/api/vocab/makes").json()
    assert "Airbus SAS" in makes and "The Boeing Company" in makes and len(makes) > 50
    models = client.get("/api/vocab/models", params={"make": "Airbus SAS"}).json()
    assert "A330-243" in models and "737-800" not in models
    assert client.get("/api/vocab/models", params={"make": "Nope"}).json() == []
    assert client.get("/api/vocab/models").status_code == 422


def test_search_returns_real_answer_without_mock(client) -> None:
    body = {"query": "Which proposed ADs concern the radio management panels on our A330-243?", "make": "Airbus SAS",
            "model": "A330-243", "as_of": "2026-10-31"}  # fmt: skip
    resp = SearchResponse.model_validate(client.post("/api/search", json=body).json())
    assert resp.mock is False and resp.status in ("answered", "partial") and resp.request_id.startswith("req_")
    assert any(r.record_id == "R0003" for r in resp.records)
    assert [t.stage[:2] for t in resp.trace] == ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]


def test_search_llm_failure_is_not_a_500(client, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")  # no fake, malformed/no key -> LLMError inside the pipeline
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not a key")
    from backend.app.llm import client as llm_client

    monkeypatch.setattr(llm_client, "_default", None)
    res = client.post(
        "/api/search", json={"query": "radio management panel", "make": "Airbus SAS", "model": "A330-243"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["message"].startswith("The answer writer was unavailable")
    assert {t["stage"][:2]: t["status"] for t in data["trace"]}["S6"] == "warn"


def test_search_rejects_unknown_fields(client) -> None:
    assert client.post("/api/search", json={"query": "x", "evil": 1}).status_code == 422


def test_records_endpoint_real(client) -> None:
    d = RecordDetail.model_validate(client.get("/api/records/R0003").json())
    assert d.record.docket == "FAA-2026-11813" and d.mock is False
    assert (
        d.sentences[0].id == "R0003#s1"
        and d.record.summary[d.sentences[0].start : d.sentences[0].end] == d.sentences[0].text
    )
    assert any(e.field == "supersedes_ad" for e in d.extractions)
    assert any(e.relation == "supersedes" and e.target_ref == "AD 2025-09-07" for e in d.lineage)
    assert client.get("/api/records/R9999").status_code == 404


def test_eval_latest_404_until_eval_runs(client, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "repo_path", lambda key, section="data": tmp_path / "missing.json")
    assert client.get("/api/eval/latest").status_code == 404


def test_feedback_appends_jsonl(client, monkeypatch, tmp_path: Path) -> None:
    log = tmp_path / "logs" / "feedback.jsonl"
    monkeypatch.setattr(main, "repo_path", lambda key, section="data": log)
    res = client.post("/api/feedback", json={"request_id": "req_abc", "reason": "wrong model"})
    assert res.json() == {"ok": True, "mock": False}
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["request_id"] == "req_abc" and entry["reason"] == "wrong model"


def test_audit_endpoint(client) -> None:
    resp = client.post("/api/search", json={"query": "radio management panel", "make": "Airbus SAS",
                                           "model": "A330-243", "mode": "search_only"}).json()  # fmt: skip
    audit = client.get(f"/api/audit/{resp['request_id']}").json()
    assert audit["request_id"] == resp["request_id"] and audit["evidence_pack"].startswith("<evidence>")
    assert client.get("/api/audit/req_nope").status_code == 404


def test_openapi_lists_all_endpoints(client) -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths >= {"/api/health", "/api/meta", "/api/vocab/makes", "/api/vocab/models", "/api/search",
                     "/api/records/{record_id}", "/api/eval/latest", "/api/feedback", "/api/audit/{request_id}"}  # fmt: skip


def test_cors_allows_vite_dev_server(client) -> None:
    res = client.options("/api/search", headers={"Origin": "http://localhost:5173",
                                                 "Access-Control-Request-Method": "POST"})  # fmt: skip
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_examples_come_from_dev_eval_cases(client) -> None:
    from backend.app.eval.cases import CASES_PATH

    if not CASES_PATH.exists():
        pytest.skip("eval cases not built")
    rows = {json.loads(x)["id"]: json.loads(x) for x in CASES_PATH.read_text(encoding="utf-8").splitlines()}
    ex = client.get("/api/examples").json()
    demo = [e for e in ex if e["category"] == "demo"]
    assert demo and demo[0]["query"].startswith("Which proposed ADs concern the radio management panels")
    ex = [e for e in ex if e["category"] != "demo"]
    assert len(ex) >= 8 and len({e["category"] for e in ex}) == len(ex)
    for e in ex:
        c = rows[e["case_id"]]
        assert c["split"] == "dev" and c["provenance"] == "auto" and e["query"] == c["query"]
        assert set(e) == {"case_id", "category", "query", "make", "model", "serial"}  # inputs only, no answers


def test_record_cards_carry_docket_group_status(client) -> None:
    body = {"query": "radio management panel", "make": "Airbus SAS", "model": "A330-243", "as_of": "2026-10-31",
            "mode": "search_only"}  # fmt: skip
    resp = SearchResponse.model_validate(client.post("/api/search", json=body).json())
    card = next(r for r in resp.records if r.record_id == "R0003")
    assert card.docket_group_size >= 1 and isinstance(card.latest_in_docket_group, bool)
