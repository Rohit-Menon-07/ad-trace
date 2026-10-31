"""Load records + extractions from SQLite into immutable EngineRecords, plus cross-record indexes."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.engine.types import (
    CONF_RANK,
    EngineRecord,
    Evidence,
    LineageRef,
    ListedModel,
    SerialConstraint,
)
from backend.app.extract.models import family as model_family

_KIND_LABEL = {"msn": "MSN", "serial_number": "serial numbers", "line_number": "line numbers"}


_COLUMN_LABEL = {"model": "Model", "withdraws_docket": "Subject Heading"}


def _evidence(row: dict[str, Any]) -> Evidence:
    """Sentence id for Summary extractions; '<record>#col:<Column>' for column and Comments extractions."""
    if row["sentence_id"]:
        return Evidence(row["id"], row["sentence_id"], row["confidence"])
    col = "Comments" if row["source"] == "comments" else _COLUMN_LABEL.get(row["field"], "column")
    return Evidence(row["id"], f"{row['record_id']}#col:{col}", row["confidence"])


def _serial(row: dict[str, Any], v: dict[str, Any]) -> SerialConstraint:
    kind = _KIND_LABEL.get(v.get("kind", ""), "serial numbers")
    if row["field"] == "serial_range":
        label = f"{kind} {v['start']} through {v['end']}"
        return SerialConstraint("range", v["start"], v["end"], (), bool(v.get("excluded")), label, _evidence(row))
    serials = tuple(v.get("serials", []))
    label = f"{kind} {', '.join(serials)}"
    return SerialConstraint("list", None, None, serials, bool(v.get("excluded")), label, _evidence(row))


def build_record(base: dict[str, Any], makes: list[tuple[str, str]], rows: list[dict[str, Any]]) -> EngineRecord:
    """Assemble one EngineRecord from its record row, record_makes rows and extraction rows."""
    models: dict[str, dict[str, Any]] = {}
    low: list[str] = []
    all_fam: dict[str, list[Evidence]] = defaultdict(list)
    certain, svc, serials = [], [], []
    sup, cont, corr, wdr = [], [], [], []
    for row in rows:
        v = row["value"]
        f = row["field"]
        if f == "model":
            if row["confidence"] == "LOW" or not v.get("model"):
                low.append(v.get("model") or v.get("raw") or "?")
                continue
            m = models.setdefault(v["model"], {"conf": row["confidence"], "series": False, "ev": []})
            if CONF_RANK[row["confidence"]] > CONF_RANK[m["conf"]]:
                m["conf"] = row["confidence"]
            m["series"] |= "series" in (v.get("raw") or "").lower()
            m["ev"].append(_evidence(row))
        elif f == "applies_all_of_family":
            all_fam[v["family"]].append(_evidence(row))
        elif f == "qualifier_certain":
            certain.append(_evidence(row))
        elif f in ("serial_range", "serial_list"):
            serials.append(_serial(row, v))
        elif f == "applicability_defined_by_service_info":
            svc.append(_evidence(row))
        elif f in ("supersedes_ad", "continues_ad") and v.get("ad_number"):
            ref = LineageRef(v["ad_number"], row["id"], _evidence(row).evidence_id)
            (sup if f == "supersedes_ad" else cont).append(ref)
        elif f == "correction_of":
            corr.append(LineageRef(v["docket"], row["id"], _evidence(row).evidence_id))
        elif f == "withdraws_docket":
            wdr.append(LineageRef(v["docket"], row["id"], _evidence(row).evidence_id))
    listed = {
        name: ListedModel(name, model_family(name), m["conf"], m["series"], tuple(m["ev"]))
        for name, m in models.items()
    }
    # "all ... Model X" counts family-wide only when X itself is a whole-type designator (model == family),
    # e.g. "all Model A318 series". "all Model A330-243, A330-243F" must NOT cover A330-202.
    whole_types = {name for name in listed if listed[name].family == name}
    all_families = {fam: tuple(ev) for fam, ev in all_fam.items() if fam in whole_types}
    return EngineRecord(
        id=base["id"],
        docket=base["docket"],
        makes=tuple(m for m, _ in makes),
        make_families=tuple(dict.fromkeys(f for _, f in makes)),
        ad_number=base["ad_number"],
        citation_publish_date=base["citation_publish_date"],
        comments_due_effective=base["comments_due_effective"],
        is_duplicate=bool(base["is_duplicate"]),
        models=listed,
        low_tokens=tuple(low),
        all_families=all_families,
        certain=tuple(certain),
        serials=tuple(serials),
        svcinfo=tuple(svc),
        supersedes=tuple(sup),
        continues=tuple(cont),
        corrections=tuple(corr),
        withdraws=tuple(wdr),
    )


@dataclass(frozen=True)
class EngineIndex:
    records: dict[str, EngineRecord]
    by_docket: dict[str, tuple[str, ...]]
    withdrawn_by_docket: dict[str, tuple[tuple[str, LineageRef], ...]]  # docket -> (withdrawing record, ref)
    records_by_ad_number: dict[str, tuple[str, ...]]  # AD Number column -> record ids
    supersede_refs_by_ad: dict[str, tuple[tuple[str, LineageRef], ...]]  # AD -> (proposing record, ref)
    corrected_by_docket: dict[str, tuple[tuple[str, LineageRef], ...]]  # base docket -> (correcting record, ref)


def build_index(records: dict[str, EngineRecord]) -> EngineIndex:
    by_docket: dict[str, list[str]] = defaultdict(list)
    withdrawn: dict[str, list[tuple[str, LineageRef]]] = defaultdict(list)
    by_ad: dict[str, list[str]] = defaultdict(list)
    sup_by_ad: dict[str, list[tuple[str, LineageRef]]] = defaultdict(list)
    corrected: dict[str, list[tuple[str, LineageRef]]] = defaultdict(list)
    for r in records.values():
        for ref in r.corrections:
            corrected[ref.value].append((r.id, ref))
        by_docket[r.docket].append(r.id)
        if r.ad_number:
            by_ad[r.ad_number].append(r.id)
        for ref in r.withdraws:
            withdrawn[ref.value].append((r.id, ref))
        if not r.is_duplicate:
            for ref in r.supersedes:
                sup_by_ad[ref.value].append((r.id, ref))
    return EngineIndex(
        records=records,
        by_docket={k: tuple(v) for k, v in by_docket.items()},
        withdrawn_by_docket={k: tuple(v) for k, v in withdrawn.items()},
        records_by_ad_number={k: tuple(v) for k, v in by_ad.items()},
        supersede_refs_by_ad={k: tuple(v) for k, v in sup_by_ad.items()},
        corrected_by_docket={k: tuple(v) for k, v in corrected.items()},
    )


def load_index(db_path: Path) -> EngineIndex:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        bases = {
            r["id"]: dict(r)
            for r in conn.execute(
                "SELECT id, docket, ad_number, citation_publish_date, comments_due_effective, is_duplicate "
                "FROM records ORDER BY id"
            )
        }
        makes: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for r in conn.execute(
            "SELECT record_id, make_canonical, make_family FROM record_makes ORDER BY record_id, position"
        ):
            makes[r["record_id"]].append((r["make_canonical"], r["make_family"]))
        rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            "SELECT id, record_id, field, value_json, source, sentence_id, rule_id, confidence "
            "FROM extractions ORDER BY id"
        ):
            d = dict(r)
            d["value"] = json.loads(d.pop("value_json"))
            rows[d["record_id"]].append(d)
    finally:
        conn.close()
    records = {rid: build_record(base, makes.get(rid, []), rows.get(rid, [])) for rid, base in bases.items()}
    return build_index(records)
