"""Retrieval tests. Most use the TF-IDF fallback embedder (fast, offline); one checks the cached BGE index.

The known-item test queries each record by its own Subject Heading. That is circular (the heading is indexed)
and only a smoke test that indexing, filtering and fusion are wired correctly; it says nothing about quality.
"""

from __future__ import annotations

import random
import sqlite3
import time
from datetime import date

import pytest

from backend.app.engine.applicability import make_relation, match_model
from backend.app.engine.types import LinkedConfig, Match
from backend.app.retrieval import dense as dense_mod
from backend.app.retrieval.dense import TfidfEmbedder, make_embedder
from backend.app.retrieval.fts import sanitize
from backend.app.retrieval.retriever import Filters, Retriever, p50_p95

# ------------------------------------------------------------------ sanitiser (no DB needed)

HOSTILE = [
    '"', '""', "'", "(", ")", "()", "*", "^", ":", "NEAR(a b, 2)", "a NEAR b", "a AND OR NOT b", "col:term",
    '"unbalanced quote', "a330-243\" OR 1=1 --", "'; DROP TABLE records; --", "{sentence_text}: x", "-", "--",
    "A330-243*", "^start", "\x00\x01", "😀 emoji", "   ", "",
]  # fmt: skip


@pytest.mark.parametrize("text", HOSTILE)
def test_sanitize_hostile_input_produces_safe_expression(text: str) -> None:
    expr = sanitize(text)
    if expr is None:
        return
    # only OR-joined double-quoted tokens (optionally with a trailing *) survive
    for part in expr.split(" OR "):
        assert part.startswith('"') and part.rstrip("*").endswith('"') and part.count('"') == 2, expr


def test_sanitize_empty_and_stopwords_only() -> None:
    assert sanitize("") is None and sanitize(None) is None and sanitize("   ") is None
    assert sanitize("what is the and or not near") is None


def test_sanitize_designators_get_prefix_and_norm() -> None:
    expr = sanitize("Which ADs concern the A330 and AS 365 N2?")
    assert '"a330"*' in expr and '"concern"' in expr and '"which"' not in expr


def test_hostile_inputs_execute_in_fts5(real_db) -> None:
    conn = sqlite3.connect(real_db)
    for text in HOSTILE + ["radio management panel", "PW4090", "2025-09-07"]:
        expr = sanitize(text)
        if expr:
            conn.execute("SELECT count(*) FROM sentences_fts WHERE sentences_fts MATCH ?", (expr,)).fetchone()


# ------------------------------------------------------------------ retriever on the real DB (TF-IDF dense)


@pytest.fixture(scope="module")
def retriever(real_db, tmp_path_factory) -> Retriever:
    return Retriever(real_db, embedder=TfidfEmbedder("tests"), index_dir=tmp_path_factory.mktemp("idx"))


def _known_items(r: Retriever, n: int = 15) -> list[str]:
    counts: dict[str, int] = {}
    for _, _, subject in r.meta.values():
        counts[subject] = counts.get(subject, 0) + 1
    pool = sorted(rid for rid, (_, dup, subject) in r.meta.items() if not dup and counts[subject] == 1)
    return random.Random(42).sample(pool, n)


@pytest.mark.parametrize("mode", ["bm25", "hybrid"])
def test_known_item_subject_headings_CIRCULAR_SMOKE(retriever: Retriever, mode: str) -> None:
    misses = []
    for rid in _known_items(retriever):
        res = retriever.retrieve(retriever.meta[rid][2], mode=mode)
        if rid not in [h.record_id for h in res.records]:
            misses.append(rid)
    assert not misses, f"{mode}: not in top 8: {misses}"


def test_all_modes_return_features_and_timings(retriever: Retriever) -> None:
    for mode in ("bm25", "dense", "hybrid"):
        res = retriever.retrieve("radio management panel", mode=mode)
        assert res.records and len(res.records) <= 8
        assert set(res.features) >= {"top_fused", "top_cosine", "top_bm25_norm", "gap_1_2"}
        assert res.timings_ms["total"] >= 0 and res.embedding_backend.startswith("tfidf")
    assert retriever.retrieve("radio management panel", mode="bm25").features["top_cosine"] is None


def test_empty_query_does_not_crash(retriever: Retriever) -> None:
    res = retriever.retrieve("", mode="hybrid")
    assert res.records == [] and res.fts_query is None


def test_make_filter_removes_other_makes(retriever: Retriever) -> None:
    res = retriever.retrieve("inspection cracks", Filters(make="Airbus SAS"), mode="hybrid", k=50)
    make_report = next(f for f in res.filters if f.name == "make")
    assert make_report.removed > 300
    for h in res.records:
        assert make_relation("Airbus SAS", retriever.engine.records[h.record_id]) != "different"
    removed = set(make_report.removed_ids)
    assert any("The Boeing Company" in retriever.engine.records[r].makes for r in removed)
    assert "R0244" not in removed  # a record with no make is never removed by the make filter


def test_model_filter_mirrors_engine(retriever: Retriever) -> None:
    res = retriever.retrieve("airplane flight manual", Filters(make="Airbus SAS", model="A330-243"), k=50)
    model_report = next(f for f in res.filters if f.name == "model")
    lc = LinkedConfig(None, "A330-243", "A330", None, date.today())
    for rid in model_report.removed_ids:
        rec = retriever.engine.records[rid]
        assert match_model(lc, rec).kind == Match.NO_MATCH and rec.model_list_confidence in ("HIGH", "MEDIUM")
    kept = {h.record_id for h in res.records}
    assert "R0121" not in model_report.removed_ids  # 'A330-200 series' (SERIES_OVERLAP) is kept
    assert kept & {"R0003", "R0011", "R0021", "R0061"}


def test_records_listing_the_model_rank_before_unknown_lists(retriever: Retriever) -> None:
    """REAL regression: R0002 lists PW4090 but generic words let records with no model list outrank it."""
    res = retriever.retrieve("What would the proposal for the PW4090 engines require?", Filters(model="PW4090"))
    assert res.records[0].record_id == "R0002" and res.features["tier0_records"] == 1
    res = retriever.retrieve("radio management panels", Filters(make="Airbus SAS", model="A330-243"), k=20)
    tiers = retriever.match_tiers(Filters(make="Airbus SAS", model="A330-243"), {h.record_id for h in res.records})
    order = [tiers[h.record_id] for h in res.records]
    assert order == sorted(order) and "R0012" not in [h.record_id for h in res.records[:8]]


@pytest.mark.parametrize("mode", ["hybrid", "bm25"])
def test_exact_ad_number_in_query_ranks_first(retriever: Retriever, mode: str) -> None:
    """REAL regression (eval v1 A-SUP-01/06): fusion buried the record that cites the AD number."""
    for q, rid in (("Which proposal would supersede AD 2026-09-02?", "R0002"),
                   ("Which proposal would supersede AD 2015-07-03?", "R0027")):  # fmt: skip
        res = retriever.retrieve(q, Filters(), mode)
        assert res.records[0].record_id == rid and res.features["id_matches"] >= 1
        assert any("identifier" in s.tags for s in res.records[0].sentences)


def test_docket_identifier_is_whole_token(retriever: Retriever) -> None:
    assert retriever.identifier_hits("docket FAA-2026-1181", set(retriever.meta)) == {}
    assert "R0166" in retriever.identifier_hits("FAA-2022-1308", set(retriever.meta))  # matches its R1 revision
    assert retriever.retrieve("AD 2026-09-02", Filters(), "dense").features["id_matches"] == 0  # dense ablation pure


def test_within_record_evidence_uses_sentence_text(retriever: Retriever) -> None:
    """REAL regression: the radio-management-panel sentence R0003#s2 must be chosen as evidence even though every
    R0003 sentence matches the model columns equally."""
    q = "Which proposed ADs concern the radio management panels on our A330-243?"
    hit = next(h for h in retriever.retrieve(q, Filters(make="Airbus SAS", model="A330-243")).records
               if h.record_id == "R0003")  # fmt: skip
    top = [s.sentence_id for s in hit.sentences if "top" in s.tags]
    assert "R0003#s2" in top


def test_explain_link_model_matches_pipeline_linker(retriever: Retriever) -> None:
    from backend.app.engine.explain import link_model

    assert link_model(retriever.engine, "PW4090") == ("PW4090", "PW4090")
    assert link_model(retriever.engine, "A330") == (None, "A330")


def test_duplicates_excluded_by_default_and_includable(retriever: Retriever) -> None:
    q = retriever.meta["R0195"][2]
    assert "R0195" not in [h.record_id for h in retriever.retrieve(q, k=50).records]
    with_dups = retriever.retrieve(q, Filters(include_duplicates=True), k=50)
    assert "R0195" in [h.record_id for h in with_dups.records]
    assert all(f.name != "duplicates" for f in with_dups.filters)


def test_date_filter(retriever: Retriever) -> None:
    res = retriever.retrieve("inspection", Filters(date_from=date(2026, 1, 1)), k=50)
    assert all(retriever.meta[h.record_id][0] >= "2026-01-01" for h in res.records)


def test_evidence_includes_engine_anchor_sentences(retriever: Retriever) -> None:
    res = retriever.retrieve("radio management panel", Filters(make="Airbus SAS"))
    hit = next(h for h in res.records if h.record_id == "R0003")
    tags = {s.sentence_id: s.tags for s in hit.sentences}
    assert "applicability" in tags["R0003#s1"] and "supersession" in tags["R0003#s1"]
    for s in hit.sentences:
        if s.start is not None:
            assert retriever.sentences[s.sentence_id][1] == s.text


def test_empty_summary_record_reachable_via_heading(retriever: Retriever) -> None:
    res = retriever.retrieve("Withdrawal Empresa Brasileira EMB-120", mode="bm25", k=20)
    hit = next((h for h in res.records if h.record_id == "R0294"), None)
    assert hit is not None and hit.sentences[0].tags == ["heading"] and hit.sentences[0].start is None


def test_hybrid_latency_p95_under_300ms(retriever: Retriever) -> None:
    from backend.app.retrieval.search import bench_queries

    times = []
    for q in bench_queries(retriever, 50):
        t0 = time.perf_counter()
        retriever.retrieve(q, mode="hybrid")
        times.append((time.perf_counter() - t0) * 1000)
    _, p95 = p50_p95(times)
    assert p95 < 300, p95


# ------------------------------------------------------------------ embedding backend selection


def test_fallback_is_loud_not_silent(monkeypatch, caplog) -> None:
    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.delenv("ADTRACE_EMBEDDINGS", raising=False)
    monkeypatch.setattr(dense_mod, "BgeEmbedder", boom)
    with caplog.at_level("WARNING"):
        emb = make_embedder()
    assert isinstance(emb, TfidfEmbedder) and "fallback" in emb.backend and "no network" in emb.backend
    assert any("falling back" in r.message for r in caplog.records)


def test_forced_fallback_env(monkeypatch) -> None:
    monkeypatch.setenv("ADTRACE_EMBEDDINGS", "tfidf")
    assert make_embedder().backend.startswith("tfidf_char_ngrams (fallback: forced")


def test_bge_cache_matches_current_sentences(real_db) -> None:
    """If the BGE index was built by `make ingest`, its version hash must match the sentences table."""
    import json

    meta_path = dense_mod.INDEX_DIR / "emb_meta.json"
    if not meta_path.exists():
        pytest.skip("dense index not built yet")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    conn = sqlite3.connect(real_db)
    ids, _, texts = dense_mod.document_texts(conn)
    assert meta["version_hash"] == dense_mod.version_hash(meta["model"], ids, texts)
    assert meta["count"] == len(ids) and meta["dim"] == 384
