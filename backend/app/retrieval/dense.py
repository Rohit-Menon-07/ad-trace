"""Dense sentence embeddings: BAAI/bge-small-en-v1.5, with a loud TF-IDF char n-gram fallback.

Documents are embedded as "Make Model | Subject Heading: <sentence>"; queries get the BGE query instruction.
Vectors are L2-normalised, so cosine = dot product. The BGE matrix is cached in data/index/ with ids.json and a
version hash of the embedded texts + model name; it is rebuilt automatically when the hash differs.
Set ADTRACE_EMBEDDINGS=tfidf to force the fallback (tests, offline machines).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from backend.app.config import ROOT, load_config

log = logging.getLogger(__name__)
INDEX_DIR = ROOT / "data" / "index"


class Embedder(Protocol):
    backend: str

    def encode_docs(self, texts: list[str]) -> Any: ...
    def encode_query(self, text: str) -> Any: ...


class BgeEmbedder:
    def __init__(self, model_name: str, instruction: str, batch_size: int) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import: only when used

        self.model = SentenceTransformer(model_name, device="cpu")
        self.instruction = instruction
        self.batch_size = batch_size
        self.backend = model_name

    def encode_docs(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False).astype(np.float32)  # fmt: skip

    def encode_query(self, text: str) -> np.ndarray:
        return self.model.encode([self.instruction + text], normalize_embeddings=True, convert_to_numpy=True)[0]


class TfidfEmbedder:
    """Character 3-5-gram TF-IDF, L2-normalised. Fitted on the documents at load time (fast)."""

    def __init__(self, reason: str) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)
        self.backend = f"tfidf_char_ngrams (fallback: {reason})"

    def encode_docs(self, texts: list[str]) -> Any:
        return self.vec.fit_transform(texts)

    def encode_query(self, text: str) -> Any:
        return self.vec.transform([text])


def make_embedder() -> Embedder:
    cfg = load_config()["embeddings"]
    if os.environ.get("ADTRACE_EMBEDDINGS", "").lower() == "tfidf":
        return TfidfEmbedder("forced by ADTRACE_EMBEDDINGS=tfidf")
    try:
        return BgeEmbedder(cfg["model"], cfg["query_instruction"], int(cfg.get("batch_size", 64)))
    except Exception as exc:  # no network / no torch: never fail silently
        log.warning("Embedding model %s unavailable (%s); falling back to TF-IDF char n-grams", cfg["model"], exc)
        return TfidfEmbedder(f"{type(exc).__name__}: {str(exc)[:120]}")


def document_texts(conn: sqlite3.Connection) -> tuple[list[str], list[str], list[str]]:
    """(sentence ids, record ids, header-prefixed texts) in sentence-id order."""
    n_models = int(load_config()["embeddings"].get("header_max_models", 10))
    models: dict[str, list[str]] = {}
    for rid, value, conf in conn.execute(
        "SELECT record_id, value_json, confidence FROM extractions WHERE field='model' ORDER BY id"
    ):
        m = json.loads(value).get("model")
        if m and conf in ("HIGH", "MEDIUM") and m not in models.setdefault(rid, []):
            models[rid].append(m)
    heads = {
        rid: f"{make or ''} {', '.join(models.get(rid, [])[:n_models])} | {subject or ''}: ".strip()
        for rid, make, subject in conn.execute("SELECT id, make_canonical, subject_heading FROM records")
    }
    ids, rids, texts = [], [], []
    for sid, rid, text in conn.execute("SELECT id, record_id, text FROM sentences ORDER BY id"):
        ids.append(sid)
        rids.append(rid)
        texts.append(heads[rid] + " " + text)
    return ids, rids, texts


def version_hash(model: str, ids: list[str], texts: list[str]) -> str:
    h = hashlib.sha1(model.encode())
    for sid, text in zip(ids, texts, strict=True):
        h.update(sid.encode())
        h.update(b"\x00")
        h.update(text.encode())
        h.update(b"\x01")
    return h.hexdigest()


@dataclass
class DenseIndex:
    ids: list[str]
    matrix: Any  # np.ndarray (BGE) or sparse matrix (TF-IDF); rows L2-normalised
    embedder: Embedder
    rebuilt: bool

    @property
    def backend(self) -> str:
        return self.embedder.backend

    def cosine(self, query: str) -> np.ndarray:
        q = self.embedder.encode_query(query)
        sims = self.matrix @ q.T if not isinstance(q, np.ndarray) else self.matrix @ q
        return np.asarray(sims.todense() if hasattr(sims, "todense") else sims).ravel()


def load_dense(conn: sqlite3.Connection, index_dir: Path = INDEX_DIR, embedder: Embedder | None = None) -> DenseIndex:
    """Load cached BGE embeddings if the version hash matches; otherwise (re)build and cache them."""
    embedder = embedder or make_embedder()
    ids, _, texts = document_texts(conn)
    if isinstance(embedder, TfidfEmbedder):
        return DenseIndex(ids, embedder.encode_docs(texts), embedder, True)
    vhash = version_hash(embedder.backend, ids, texts)
    npy, ids_path, meta_path = index_dir / "emb_sentences.npy", index_dir / "ids.json", index_dir / "emb_meta.json"
    if npy.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("version_hash") == vhash:
            return DenseIndex(ids, np.load(npy), embedder, False)
    log.info("Embedding %d sentences with %s (hash changed or no cache)", len(texts), embedder.backend)
    matrix = embedder.encode_docs(texts)
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(npy, matrix)
    ids_path.write_text(json.dumps(ids), encoding="utf-8")
    meta_path.write_text(json.dumps({"version_hash": vhash, "model": embedder.backend, "dim": int(matrix.shape[1]),
                                     "count": len(ids)}, indent=2), encoding="utf-8")  # fmt: skip
    return DenseIndex(ids, matrix, embedder, True)
