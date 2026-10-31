"""Hybrid retrieval (SPEC S3): hard filters -> sentence BM25 + dense -> RRF -> records -> evidence. No LLM.

Hard filters mirror the applicability engine, so retrieval never hides a record the engine would keep:
a make filter removes only records the engine calls a "different" manufacturer (related spellings and records
with no make stay), and a model filter removes only records whose HIGH/MEDIUM, complete model list does not
match. Every removal is reported (record ids + reason) for the "excluded" panel and the pipeline trace.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np

from backend.app.config import load_config
from backend.app.engine.applicability import make_relation, match_model
from backend.app.engine.data import load_index
from backend.app.engine.types import LinkedConfig, Match
from backend.app.extract.models import family as model_family
from backend.app.retrieval.dense import INDEX_DIR, DenseIndex, Embedder, load_dense
from backend.app.retrieval.fts import RECORD_COLUMNS, SENTENCE_COLUMNS, sanitize, weights_sql

Mode = Literal["bm25", "dense", "hybrid"]
APPLICABILITY_FIELDS = {"model", "applies_all_of_family", "qualifier_certain", "serial_range", "serial_list",
                        "applicability_defined_by_service_info"}  # fmt: skip
SUPERSESSION_FIELDS = {"supersedes_ad", "continues_ad"}
# Exact identifiers in a query (AD numbers, FAA dockets). Spaces around hyphens tolerated ("AD 2024- 05-13").
RX_QUERY_ID = re.compile(
    r"(?<![\w-])\d{4}\s?-\s?\d{2}\s?-\s?\d{2,3}(?![\w-])|\bFAA[\s-]?\d{4}-\d{3,5}(?:R\d+)?\b"
    r"|\b\d{2,4}-[A-Z]{2,3}-\d{1,3}-AD\b",
    re.IGNORECASE,
)


def norm_identifier(text: str) -> str:
    return re.sub(r"\s*-\s*", "-", re.sub(r"^FAA\s", "FAA-", text.strip(), flags=re.IGNORECASE)).upper()


@dataclass(frozen=True)
class Filters:
    make: str | None = None  # canonical make
    make_family: str | None = None
    model: str | None = None  # norm_model() designator
    family: str | None = None  # model family (family-only query)
    date_from: date | None = None
    date_to: date | None = None
    include_duplicates: bool = False


@dataclass
class FilterReport:
    name: str
    value: str
    removed: int
    removed_ids: list[str]
    reason: str


@dataclass
class SentenceHit:
    sentence_id: str
    text: str
    start: int | None
    end: int | None
    bm25: float | None  # raw score, higher = better (negated SQLite bm25())
    bm25_norm: float | None  # s / (1 + s)
    cosine: float | None
    bm25_rank: int | None
    dense_rank: int | None
    fused: float
    tags: list[str] = field(default_factory=list)  # top | identifier | applicability | supersession | heading
    local: float = 0.0  # within-record relevance: RRF of sentence-text-only BM25 and cosine (evidence ranking)


@dataclass
class RecordHit:
    record_id: str
    rank: int
    score: float
    sentences: list[SentenceHit]


@dataclass
class RetrievalResult:
    query: str
    mode: Mode
    fts_query: str | None
    records: list[RecordHit]
    filters: list[FilterReport]
    candidates_before: int
    candidates_after: int
    features: dict[str, float | int | None]
    timings_ms: dict[str, float]
    embedding_backend: str


class Retriever:
    """Holds the DB connection, engine index, sentence table and dense matrix in memory (warm at startup)."""

    def __init__(self, db_path: Path, embedder: Embedder | None = None, index_dir: Path = INDEX_DIR) -> None:
        self.cfg = load_config()
        self.rcfg = self.cfg["retrieval"]
        self.rrf_k = int(self.cfg["thresholds"]["rrf_k"])
        self.top_k = int(self.cfg["thresholds"]["top_k_records"])
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.engine = load_index(db_path)
        self.sentences: dict[str, tuple[str, str, int, int]] = {}
        self.by_record: dict[str, list[str]] = defaultdict(list)
        for sid, rid, text, s, e in self.conn.execute(
            'SELECT id, record_id, text, "start", "end" FROM sentences ORDER BY record_id, idx'
        ):
            self.sentences[sid] = (rid, text, s, e)
            self.by_record[rid].append(sid)
        self.meta = {
            rid: (issue, bool(dup), subject or "")
            for rid, issue, dup, subject in self.conn.execute(
                "SELECT id, issue_date, is_duplicate, subject_heading FROM records"
            )
        }
        # Record-level identifiers: docket and AD Number columns (sentence text is searched per query).
        self.record_ids: dict[str, set[str]] = {
            rid: {norm_identifier(x) for x in (docket, ad) if x}
            for rid, docket, ad in self.conn.execute("SELECT id, docket, ad_number FROM records")
        }
        self.anchors: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: {"applicability": set(), "supersession": set()}
        )
        for rid, fld, sid in self.conn.execute(
            "SELECT record_id, field, sentence_id FROM extractions WHERE sentence_id IS NOT NULL"
        ):
            if fld in APPLICABILITY_FIELDS:
                self.anchors[rid]["applicability"].add(sid)
            elif fld in SUPERSESSION_FIELDS:
                self.anchors[rid]["supersession"].add(sid)
        self.dense: DenseIndex = load_dense(self.conn, index_dir, embedder)
        self.dense_row = {sid: i for i, sid in enumerate(self.dense.ids)}
        self._s_weights = weights_sql(self.rcfg["fts_sentence_weights"], SENTENCE_COLUMNS, 2)
        self._r_weights = weights_sql(self.rcfg["fts_record_weights"], RECORD_COLUMNS, 1)
        self._reranker = None

    # ------------------------------------------------------------ filters

    def match_tiers(self, f: Filters, cands: set[str]) -> dict[str, int]:
        """0 = the record lists the requested model (EXACT / whole type / all-family) and its make matches;
        1 = possible match (series overlap, spelling variant, family-only); 2 = no usable model list or no make.
        Records kept only because nothing excludes them must not outrank records that actually list the aircraft."""
        if not (f.make or f.model or f.family):
            return {}
        fam = f.family or (model_family(f.model) if f.model else None)
        lc = LinkedConfig(None, f.model, fam, None, date.today())
        tiers: dict[str, int] = {}
        for r in cands:
            rec = self.engine.records[r]
            tier = 0
            if f.model or f.family:
                kind = match_model(lc, rec).kind
                tier = 0 if kind == Match.EXACT else 2 if kind in (Match.UNKNOWN, Match.NO_MATCH) else 1
            if f.make and make_relation(f.make, rec) == "missing":
                tier = max(tier, 2)
            tiers[r] = tier
        return tiers

    def identifier_hits(self, query: str, cands: set[str]) -> dict[str, list[str]]:
        """record id -> sentence ids that contain an AD number / docket written in the query (exact, spacing-
        tolerant). A record whose docket or AD Number column matches is included with no sentence."""
        wanted = {re.sub(r"R\d+$", "", norm_identifier(m.group(0))) for m in RX_QUERY_ID.finditer(query or "")}
        if not wanted:
            return {}
        # Whole-identifier match: "FAA-2026-1181" must not hit "FAA-2026-11814"; a docket matches its R<n> revisions.
        rx = re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, sorted(wanted))) + r")(?:R\d+)?(?![\w-])")
        out: dict[str, list[str]] = {}
        for rid in cands:
            sids = [s for s in self.by_record.get(rid, ()) if rx.search(norm_identifier(self.sentences[s][1]))]
            if sids or any(rx.fullmatch(x) for x in self.record_ids.get(rid, ())):
                out[rid] = sids[:2]
        return out

    def apply_filters(self, f: Filters) -> tuple[set[str], list[FilterReport]]:
        cands = set(self.meta)
        reports: list[FilterReport] = []

        def drop(name: str, value: str, ids: list[str], reason: str) -> None:
            nonlocal cands
            ids = sorted(set(ids) & cands)
            cands -= set(ids)
            reports.append(FilterReport(name, value, len(ids), ids, reason))

        if not f.include_duplicates:
            drop("duplicates", "excluded", [r for r, m in self.meta.items() if m[1]],
                 "exact duplicate of another record (docs/duplicates_audit.md)")  # fmt: skip
        if f.make:
            gone = [r for r in cands if make_relation(f.make, self.engine.records[r]) == "different"]
            drop("make", f.make, gone, f"record concerns a different manufacturer than {f.make}")
        if f.make_family:
            gone = [r for r in cands if self.engine.records[r].make_families
                    and f.make_family not in self.engine.records[r].make_families]  # fmt: skip
            drop("make_family", f.make_family, gone, f"record's make family is not {f.make_family}")
        if f.model or f.family:
            fam = f.family or (model_family(f.model) if f.model else None)
            lc = LinkedConfig(None, f.model, fam, None, date.today())
            gone = []
            for r in cands:
                rec = self.engine.records[r]
                m = match_model(lc, rec)
                if m.kind == Match.NO_MATCH and not rec.low_tokens and rec.model_list_confidence in ("HIGH", "MEDIUM"):
                    gone.append(r)
            drop("model", f.model or fam or "", gone, "model list (HIGH/MEDIUM confidence) does not include it")
        if f.date_from or f.date_to:
            lo, hi = (f.date_from or date.min).isoformat(), (f.date_to or date.max).isoformat()
            gone = [r for r in cands if self.meta[r][0] and not lo <= self.meta[r][0] <= hi]
            drop("date", f"{lo}..{hi}", gone, "issue date outside the requested range (undated records kept)")
        return cands, reports

    # ------------------------------------------------------------ rankings

    def _bm25(self, fts_query: str | None, cands: set[str]) -> dict[str, float]:
        """unit id -> positive BM25 score (sentences; '<rid>#heading' for records without a summary)."""
        if not fts_query:
            return {}
        out: dict[str, float] = {}
        sql = (
            f"SELECT sentence_id, record_id, bm25(sentences_fts, {self._s_weights}) "
            "FROM sentences_fts WHERE sentences_fts MATCH ?"
        )
        for sid, rid, score in self.conn.execute(sql, (fts_query,)):
            if rid in cands:
                out[sid] = -score
        empty = [r for r in cands if not self.by_record.get(r)]
        if empty:
            sql = f"SELECT record_id, bm25(records_fts, {self._r_weights}) FROM records_fts WHERE records_fts MATCH ?"
            for rid, score in self.conn.execute(sql, (fts_query,)):
                if rid in empty:
                    out[f"{rid}#heading"] = -score
        return out

    def _dense(self, query: str, cands: set[str]) -> dict[str, float]:
        sims = self.dense.cosine(query)
        return {sid: float(sims[i]) for sid, i in self.dense_row.items() if self.sentences[sid][0] in cands}

    @staticmethod
    def _ranks(scores: dict[str, float], depth: int) -> dict[str, int]:
        ordered = sorted(scores, key=lambda u: (-scores[u], u))[:depth]
        return {u: i + 1 for i, u in enumerate(ordered)}

    # ------------------------------------------------------------ main entry

    def retrieve(self, query: str, filters: Filters | None = None, mode: Mode = "hybrid",
                 k: int | None = None) -> RetrievalResult:  # fmt: skip
        t0 = time.perf_counter()
        filters = filters or Filters()
        k = k or self.top_k
        cands, reports = self.apply_filters(filters)
        t1 = time.perf_counter()
        fts_query = sanitize(query)
        bm25 = self._bm25(fts_query, cands) if mode in ("bm25", "hybrid") else {}
        t2 = time.perf_counter()
        cos = self._dense(query, cands) if mode in ("dense", "hybrid") and query.strip() else {}
        t3 = time.perf_counter()
        b_rank = self._ranks(bm25, int(self.rcfg["bm25_depth"]))
        d_rank = self._ranks(cos, int(self.rcfg["dense_depth"]))
        fused: dict[str, float] = defaultdict(float)
        for ranks in (b_rank, d_rank):
            for unit, r in ranks.items():
                fused[unit] += 1.0 / (self.rrf_k + r)
        per_record: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for unit, s in fused.items():
            per_record[unit.split("#")[0]].append((s, unit))
        bonus = float(self.rcfg["extra_sentence_bonus"])
        scored = []
        for rid, units in per_record.items():
            units.sort(key=lambda t: (-t[0], t[1]))
            scored.append((units[0][0] + bonus * sum(s for s, _ in units[1:3]), rid))
        tiers = self.match_tiers(filters, cands)
        # Lexical modes only: a record containing an AD number / docket typed in the query ranks first within its
        # model tier (fusion alone can bury an exact BM25 hit under semantically similar sentences).
        id_hits = self.identifier_hits(query, cands) if mode in ("bm25", "hybrid") else {}
        for rid, sids in id_hits.items():
            if rid not in per_record:
                units = [(0.0, s) for s in sids] or [(0.0, f"{rid}#heading")]
                per_record[rid] = units
                scored.append((0.0, rid))
        scored.sort(key=lambda t: (tiers.get(t[1], 0), 0 if t[1] in id_hits else 1, -t[0], t[1]))
        scored = self._maybe_rerank(query, scored, per_record)
        top_ids = [rid for _, rid in scored[:k]]
        text_bm25 = self._bm25_text_only(fts_query, set(top_ids)) if mode in ("bm25", "hybrid") else {}
        if mode in ("dense", "hybrid") and not cos and query.strip():
            cos = self._dense(query, set(top_ids))
        records = [
            RecordHit(rid, i + 1, round(score, 6),
                      self._evidence(rid, per_record[rid], bm25, cos, b_rank, d_rank, text_bm25, id_hits.get(rid)))
            for i, (score, rid) in enumerate(scored[:k])
        ]  # fmt: skip
        t4 = time.perf_counter()
        b_norm = [s / (1 + s) for s in bm25.values() if s > 0]
        features = {
            "top_fused": scored[0][0] if scored else 0.0,
            "top_cosine": max(cos.values()) if cos else None,
            "top_bm25_norm": max(b_norm) if b_norm else None,
            "gap_1_2": (scored[0][0] - scored[1][0]) if len(scored) > 1 else (scored[0][0] if scored else 0.0),
            "bm25_hits": len(bm25),
            "candidates": len(cands),
            "tier0_records": sum(1 for v in tiers.values() if v == 0) if tiers else None,
            "id_matches": len(id_hits),
        }
        timings = {"filters": (t1 - t0) * 1e3, "bm25": (t2 - t1) * 1e3, "dense": (t3 - t2) * 1e3,
                   "fuse_and_evidence": (t4 - t3) * 1e3, "total": (t4 - t0) * 1e3}  # fmt: skip
        return RetrievalResult(query, mode, fts_query, records, reports, len(self.meta), len(cands), features,
                               {key: round(v, 2) for key, v in timings.items()}, self.dense.backend)  # fmt: skip

    def _hit(self, unit: str, bm25: dict[str, float], cos: dict[str, float], b_rank: dict[str, int],
             d_rank: dict[str, int], fused: float, tags: list[str]) -> SentenceHit:  # fmt: skip
        if unit.endswith("#heading"):
            rid = unit.split("#")[0]
            text, start, end = self.meta[rid][2], None, None
        else:
            _, text, start, end = self.sentences[unit]
        b = bm25.get(unit)
        return SentenceHit(unit, text, start, end, b, (b / (1 + b)) if b and b > 0 else None, cos.get(unit),
                           b_rank.get(unit), d_rank.get(unit), round(fused, 6), tags)  # fmt: skip

    def _bm25_text_only(self, fts_query: str | None, rids: set[str]) -> dict[str, float]:
        """BM25 on sentence_text alone (record-level columns weighted 0) for the top records' sentences.

        Every sentence row repeats its record's make/models/subject, so a model in the query lifts all of a
        record's sentences equally and length normalisation then favours the shortest ones. Ranking sentences
        *within* a record therefore uses the sentence text only."""
        if not fts_query or not rids:
            return {}
        weights = weights_sql({"sentence_text": 1.0, "subject_heading": 0.0, "make": 0.0, "models": 0.0,
                               "models_norm": 0.0}, SENTENCE_COLUMNS, 2)  # fmt: skip
        sql = (
            f"SELECT sentence_id, record_id, bm25(sentences_fts, {weights}) "
            "FROM sentences_fts WHERE sentences_fts MATCH ?"
        )
        return {sid: -s for sid, rid, s in self.conn.execute(sql, (fts_query,)) if rid in rids and s < 0}

    def _local_scores(self, rid: str, text_bm25: dict[str, float], cos: dict[str, float]) -> dict[str, float]:
        """Within-record RRF of sentence-text BM25 rank and cosine rank (header is identical, so cosine
        differences within a record come from the sentence text)."""
        sids = self.by_record.get(rid, [])
        local: dict[str, float] = defaultdict(float)
        for scores in ({s: text_bm25[s] for s in sids if s in text_bm25}, {s: cos[s] for s in sids if s in cos}):
            for r, s in enumerate(sorted(scores, key=lambda x: (-scores[x], x)), 1):
                local[s] += 1.0 / (self.rrf_k + r)
        return local

    def _evidence(self, rid: str, units: list[tuple[float, str]], bm25: dict[str, float], cos: dict[str, float],
                  b_rank: dict[str, int], d_rank: dict[str, int],
                  text_bm25: dict[str, float] | None = None,
                  id_sids: list[str] | None = None) -> list[SentenceHit]:  # fmt: skip
        """Top-N sentences by within-record relevance + every sentence the engine relies on (applicability,
        supersession). A record without sentences contributes its heading unit."""
        fused = {u: s for s, u in units}
        local = self._local_scores(rid, text_bm25 or {}, cos)
        chosen: dict[str, list[str]] = {}
        if not self.by_record.get(rid):
            for _, u in units[:1]:
                chosen.setdefault(u, []).append("heading")
        ranked = sorted(self.by_record.get(rid, []), key=lambda s: (-local.get(s, 0.0), -fused.get(s, 0.0), s))
        for sid in ranked[: int(self.rcfg["evidence_top_sentences"])]:
            if local.get(sid, 0.0) > 0 or fused.get(sid, 0.0) > 0:
                chosen.setdefault(sid, []).append("top")
        for sid in id_sids or []:
            chosen.setdefault(sid, []).append("identifier")
        for tag in ("applicability", "supersession"):
            for sid in sorted(self.anchors[rid][tag]):
                chosen.setdefault(sid, []).append(tag)
        hits = []
        for u, tags in chosen.items():
            h = self._hit(u, bm25, cos, b_rank, d_rank, fused.get(u, 0.0), tags)
            h.local = round(local.get(u, 0.0), 6)
            hits.append(h)
        return sorted(hits, key=lambda h: (-h.local, -h.fused, h.sentence_id))

    def _maybe_rerank(self, query: str, scored: list[tuple[float, str]],
                      per_record: dict[str, list[tuple[float, str]]]) -> list[tuple[float, str]]:  # fmt: skip
        """Optional cross-encoder rerank of the top records (config retrieval.rerank.enabled, default off)."""
        if not self.rcfg.get("rerank", {}).get("enabled") or not scored:
            return scored
        from sentence_transformers import CrossEncoder

        if self._reranker is None:
            self._reranker = CrossEncoder(self.rcfg["rerank"]["model"], device="cpu")
        head = scored[: self.top_k * 2]
        texts = [self._hit(per_record[rid][0][1], {}, {}, {}, {}, 0, []).text for _, rid in head]
        ce = self._reranker.predict([(query, t) for t in texts])
        reranked = sorted(zip(ce, head, strict=True), key=lambda t: -float(t[0]))
        return [pair for _, pair in reranked] + scored[len(head) :]

    def features_json(self, result: RetrievalResult) -> str:
        return json.dumps(result.features, sort_keys=True)


def p50_p95(samples: list[float]) -> tuple[float, float]:
    arr = np.asarray(samples)
    return float(np.percentile(arr, 50)), float(np.percentile(arr, 95))
