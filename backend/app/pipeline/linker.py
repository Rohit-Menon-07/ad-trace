"""Closed-vocabulary entity linking (SPEC H8). Code only: the LLM proposes strings, this module accepts or rejects.

Makes: rapidfuzz token_set_ratio against canonical names and aliases.
  exact name/alias -> accepted; >= 90 -> accepted if exactly one make scores >= 90, else AMBIGUOUS_MAKE;
  75-89 -> AMBIGUOUS_MAKE (top 3); < 75 -> UNKNOWN_ENTITY with 3 nearest names as suggestions (never chosen).
Models: norm_model exact match -> accepted; a bare family with 2+ variants in the data -> AMBIGUOUS_MODEL (<= 12
  options, narrowed to the linked make when possible); otherwise UNKNOWN_ENTITY with nearest suggestions.
UI fields (make, model, serial, as_of) override parsed values; every linked value records its source.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from rapidfuzz import fuzz, process, utils

from backend.app.config import resolve_as_of
from backend.app.engine.types import LinkedConfig
from backend.app.extract.lineage import AD_NUMBER, norm_ad
from backend.app.extract.models import family as model_family
from backend.app.extract.models import norm_model
from backend.app.ingest.makes import make_family

Source = Literal["ui", "parsed"]
ACCEPT, AMBIGUOUS_FLOOR = 90, 75
MAX_FAMILY_OPTIONS = 12


@dataclass
class MakeLink:
    status: Literal["accepted", "ambiguous", "unknown", "absent"]
    text: str | None = None
    canonical: str | None = None
    score: float | None = None
    candidates: list[tuple[str, float]] = field(default_factory=list)
    source: Source | None = None


@dataclass
class ModelLink:
    status: Literal["accepted", "ambiguous_family", "unknown", "absent"]
    text: str | None = None
    model_norm: str | None = None
    family: str | None = None
    options: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    source: Source | None = None


@dataclass
class LinkedQuery:
    make: MakeLink
    model: ModelLink
    serial: str | None
    serial_source: Source | None
    as_of: date
    as_of_source: Literal["ui", "default"]
    ad_number: str | None
    date_from: date | None
    date_to: date | None

    def to_config(self) -> LinkedConfig:
        """Only ACCEPTED entities reach the engine; anything else stays None (and the gates stop earlier)."""
        make = self.make.canonical if self.make.status == "accepted" else None
        model = self.model.model_norm if self.model.status == "accepted" else None
        fam = self.model.family if self.model.status == "accepted" else None
        return LinkedConfig(make, model, fam, self.serial, self.as_of)

    def summary(self) -> dict[str, Any]:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        d["date_from"] = self.date_from.isoformat() if self.date_from else None
        d["date_to"] = self.date_to.isoformat() if self.date_to else None
        return d


@dataclass(frozen=True)
class UIFields:
    make: str | None = None
    model: str | None = None
    serial: str | None = None
    as_of: date | None = None


class Linker:
    def __init__(
        self,
        makes: dict[str, list[str]],
        models: dict[str, int],
        model_makes: dict[str, set[str]] | None = None,
        ad_index: dict[str, list[str]] | None = None,
        ad_subject_records: dict[str, list[str]] | None = None,
        engine_index: Any = None,
        record_count: int = 431,
    ) -> None:
        """makes: canonical -> aliases; models: designator -> record count; model_makes: designator -> make families;
        ad_index: AD number -> records that mention it; ad_subject_records: AD -> records whose summary describes
        that AD's applicability (supersede/continue) or whose AD Number column is it."""
        self.makes = makes
        self.models = models
        self.model_makes = model_makes or {}
        self.ad_index = ad_index or {}
        self.ad_subject_records = ad_subject_records or {}
        self.engine_index = engine_index
        self.record_count = record_count
        self._names: dict[str, str] = {}
        for canonical, aliases in makes.items():
            for name in [canonical, *aliases]:
                self._names.setdefault(name, canonical)
        self._exact = {utils.default_process(n): c for n, c in self._names.items()}
        self._by_family: dict[str, list[str]] = defaultdict(list)
        for m in models:
            self._by_family[model_family(m)].append(m)

    # ------------------------------------------------------------ construction from SQLite

    @classmethod
    def from_db(cls, db_path: Path, with_engine: bool = True) -> Linker:
        conn = sqlite3.connect(db_path)
        try:
            makes = {
                c: json.loads(a) for c, a in conn.execute("SELECT canonical, aliases_json FROM vocab WHERE kind='make'")
            }
            models = dict(conn.execute("SELECT canonical, record_count FROM vocab WHERE kind='model'").fetchall())
            model_makes: dict[str, set[str]] = defaultdict(set)
            for value, fam in conn.execute(
                "SELECT e.value_json, m.make_family FROM extractions e "
                "JOIN record_makes m ON m.record_id = e.record_id "
                "WHERE e.field = 'model' AND e.confidence IN ('HIGH', 'MEDIUM')"
            ):
                mod = json.loads(value).get("model")
                if mod:
                    model_makes[mod].add(fam)
            ad_index: dict[str, set[str]] = defaultdict(set)
            for rid, text in conn.execute("SELECT record_id, text FROM sentences"):
                for m in AD_NUMBER.finditer(text):
                    ad_index[norm_ad(m.group(1))].add(rid)
            subject: dict[str, set[str]] = defaultdict(set)
            for rid, value in conn.execute(
                "SELECT record_id, value_json FROM extractions WHERE field IN ('supersedes_ad', 'continues_ad')"
            ):
                ad = json.loads(value).get("ad_number")
                if ad:
                    subject[ad].add(rid)
                    ad_index[ad].add(rid)
            for rid, ad in conn.execute("SELECT id, ad_number FROM records WHERE ad_number IS NOT NULL"):
                subject[ad].add(rid)
                ad_index[ad].add(rid)
            n = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        finally:
            conn.close()
        engine = None
        if with_engine:
            from backend.app.engine.data import load_index

            engine = load_index(db_path)
        return cls(
            makes,
            models,
            dict(model_makes),
            {k: sorted(v) for k, v in ad_index.items()},
            {k: sorted(v) for k, v in subject.items()},
            engine,
            n,
        )

    # ------------------------------------------------------------ makes

    def link_make(self, text: str | None, source: Source | None) -> MakeLink:
        if not text or not text.strip():
            return MakeLink("absent")
        exact = self._exact.get(utils.default_process(text))
        if exact:
            return MakeLink("accepted", text, exact, 100.0, [(exact, 100.0)], source)
        scored: dict[str, float] = {}
        n_query = len(utils.default_process(text).split())
        for name, score, _ in process.extract(
            text, list(self._names), scorer=fuzz.token_set_ratio, processor=utils.default_process, limit=None
        ):
            # token_set_ratio scores any superset of a name as 100 ("Lockheed Martin Skunk" vs "Lockheed"):
            # when the query has more words than the name, extra words count against it via token_sort_ratio.
            if n_query > len(utils.default_process(name).split()):
                score = min(score, fuzz.token_sort_ratio(text, name, processor=utils.default_process))
            canonical = self._names[name]
            scored[canonical] = max(scored.get(canonical, 0.0), float(score))
        ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
        top = ranked[:3]
        high = [c for c, s in ranked if s >= ACCEPT]
        if len(high) == 1:
            return MakeLink("accepted", text, high[0], scored[high[0]], top, source)
        if high or (top and top[0][1] >= AMBIGUOUS_FLOOR):
            return MakeLink("ambiguous", text, None, top[0][1], top, source)
        return MakeLink("unknown", text, None, top[0][1] if top else None, top, source)

    # ------------------------------------------------------------ models

    def link_model(self, text: str | None, source: Source | None, make: str | None = None) -> ModelLink:
        if not text or not text.strip():
            return ModelLink("absent")
        norm = norm_model(text)
        fam = model_family(norm)
        variants = [m for m in self._by_family.get(norm, []) if m != norm]
        # A bare type with several variants ("A330", "737", "A318") needs clarification. An exact designator with at
        # most one variant ("PW4090" vs "PW4090-3") is a real model and is accepted.
        if norm == fam and variants and not (norm in self.models and len(variants) <= 1):
            if make:  # narrow to the linked manufacturer's variants when that leaves something
                fam_of_make = make_family(make)
                narrowed = [m for m in variants if fam_of_make in self.model_makes.get(m, set())]
                variants = narrowed or variants
            ranked = sorted(variants, key=lambda m: (-self.models.get(m, 0), m))[:MAX_FAMILY_OPTIONS]
            return ModelLink("ambiguous_family", text, None, norm, sorted(ranked), [], source)
        if norm in self.models:
            return ModelLink("accepted", text, norm, fam, [], [], source)
        near = [m for m, _, _ in process.extract(norm, list(self.models), scorer=fuzz.ratio, limit=3)]
        return ModelLink("unknown", text, None, None, [], near, source)


def normalise_serial(text: str | None) -> str | None:
    """'MSN 1234' -> '1234'; 'S/N: s-1000' -> 'S-1000'. Never validated against a model."""
    if not text or not text.strip():
        return None
    s = re.sub(
        r"(?i)\b(?:manufacturer\s+serial\s+(?:number|no\.?)|serial\s+(?:number|no\.?)|msn|s/n|sn)\b[:#\s]*", "", text
    )
    s = re.sub(r"\s+", " ", s).strip(" :#.").upper()
    return s or None


def _parse_date(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def link_query(parsed: Any, ui: UIFields, linker: Linker) -> LinkedQuery:
    """Merge UI fields (win) with parsed fields and link them. `parsed` is a ParsedQuery or None."""
    p_make = getattr(parsed, "make_text", None)
    p_model = getattr(parsed, "model_text", None)
    p_serial = getattr(parsed, "serial_text", None)
    make_text, make_src = (ui.make, "ui") if ui.make else (p_make, "parsed" if p_make else None)
    model_text, model_src = (ui.model, "ui") if ui.model else (p_model, "parsed" if p_model else None)
    serial_text, serial_src = (ui.serial, "ui") if ui.serial else (p_serial, "parsed" if p_serial else None)
    make = linker.link_make(make_text, make_src)  # type: ignore[arg-type]
    model = linker.link_model(model_text, model_src, make.canonical if make.status == "accepted" else None)  # type: ignore[arg-type]
    serial = normalise_serial(serial_text)
    ad_text = getattr(parsed, "ad_number_text", None)
    ad = None
    if ad_text:
        m = re.search(r"\d{2,4}\s?-\s?\d{2}\s?-\s?\d{2,3}", ad_text)
        ad = norm_ad(m.group(0)) if m else None
    as_of = ui.as_of or resolve_as_of()
    return LinkedQuery(
        make,
        model,
        serial,
        serial_src if serial else None,
        as_of,
        "ui" if ui.as_of else "default",
        ad,  # type: ignore[arg-type]
        _parse_date(getattr(parsed, "date_from", None)),
        _parse_date(getattr(parsed, "date_to", None)),
    )
