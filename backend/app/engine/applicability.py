"""Deterministic applicability verdicts (SPEC S4). Pure functions; rules and reason texts in configs/rules.yaml.

Verdict rules (Prompt 5, in order):
 1. no make and no model                     -> NOT_CHECKED
 2. make differs (canonical and family)       -> NOT_APPLICABLE;  record make missing -> UNDETERMINED
    make given, no model                      -> UNDETERMINED (nothing to match a model against)
 3. model: EXACT -> serial logic; FAMILY_ONLY / SERIES_OVERLAP / SPELLING_VARIANT / UNKNOWN -> UNDETERMINED;
    NO_MATCH -> NOT_APPLICABLE only if the list is HIGH/MEDIUM and complete, else UNDETERMINED
 4. serial logic (see _serial_verdict)
 5. safety invariant: NOT_APPLICABLE never rests on LOW-confidence or missing extractions
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import yaml

from backend.app.config import ROOT
from backend.app.engine.types import (
    Applicability,
    EngineRecord,
    Evidence,
    LinkedConfig,
    ListedModel,
    Match,
    MatchResult,
)
from backend.app.extract.models import family as model_family
from backend.app.extract.serials import parse_serial, serial_in_range
from backend.app.ingest.makes import make_family, normalise_key

RULES_PATH = ROOT / "configs" / "rules.yaml"


@lru_cache(maxsize=1)
def rules() -> dict[str, Any]:
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reason(key: str, **kw: Any) -> str:
    return rules()["reasons"][key].format(**kw)


def _source(ev: tuple[Evidence, ...]) -> str:
    return "Model column" if any("#col:" in e.evidence_id for e in ev) else "Summary"


def _ids(evs: tuple[Evidence, ...] | list[Evidence]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(e.evidence_id for e in evs))


# ------------------------------------------------------------------ make


def make_relation(query_make: str, rec: EngineRecord) -> str:
    """same | related | different | missing."""
    if not rec.makes:
        return "missing"
    if query_make in rec.makes or make_family(query_make) in rec.make_families:
        return "same"
    if rules().get("related_make_same_first_key_token"):
        q = normalise_key(query_make).split()[:1]
        if q and any(normalise_key(m).split()[:1] == q for m in rec.makes):
            return "related"
    return "different"


# ------------------------------------------------------------------ model


def _loose(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _spelling_variant(query: str, listed: str) -> bool:
    """Same designator up to punctuation or a leading name ("SA-365N"/"SA365N", "GULFSTREAM G150"/"G150")."""
    if query == listed:
        return False
    a, b = _loose(query), _loose(listed)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 3 and any(ch.isdigit() for ch in short) and long_.endswith(short)


def _series_overlap(query: str, query_family: str, listed: ListedModel) -> bool:
    """Listed 'A330-200' (series) vs query 'A330-243': the query may belong to the series."""
    if listed.family != query_family or listed.model == query or not query.startswith(query_family + "-"):
        return False
    lv = listed.model[len(listed.family) + 1 :]
    qv = query[len(query_family) + 1 :]
    if not lv or not qv or lv[0] != qv[0]:
        return False
    return bool(re.match(rules()["series_variant_pattern"], lv)) or listed.series


def match_model(cfg: LinkedConfig, rec: EngineRecord) -> MatchResult:
    q_model = cfg.model_norm
    q_fam = cfg.family or (model_family(q_model) if q_model else None)
    if not rec.models:
        return MatchResult(Match.UNKNOWN, reason("unknown_models"))
    # "all" counts family-wide only when the whole type itself is listed (guard also applied in the loader).
    if q_fam and q_fam in rec.all_families and q_fam in rec.models:
        noun = "airplanes"
        return MatchResult(Match.EXACT, reason("all_family", family=q_fam, noun=noun), rec.all_families[q_fam])
    if q_model and q_model in rec.models:
        lm = rec.models[q_model]
        return MatchResult(
            Match.EXACT,
            reason("exact", model=q_model, confidence=lm.confidence, source=_source(lm.evidence)),
            lm.evidence,
        )
    if q_fam and q_fam in rec.models and (q_model is None or q_model != q_fam):
        lm = rec.models[q_fam]  # the record lists the whole type, e.g. "Model A330 and A340 airplanes"
        return MatchResult(Match.EXACT, reason("family_level", family=q_fam, model=q_model or q_fam), lm.evidence)
    same_family = [m for m in rec.models.values() if m.family == q_fam and m.model != q_model]
    # Family-only: no variant given, or the query is a bare type ("A330") while the record lists its variants.
    # A hyphenless designator such as "SA365N" equals its own family but is NOT a family query.
    if (q_model is None or q_model == q_fam) and same_family:
        return MatchResult(Match.FAMILY_ONLY, reason("family_only"), _flatten(same_family))
    if q_model is not None:
        series = [m for m in same_family if _series_overlap(q_model, q_fam or "", m)]
        if series:
            return MatchResult(
                Match.SERIES_OVERLAP, reason("series_overlap", series=series[0].model, model=q_model), _flatten(series)
            )
        variants = [m for m in rec.models.values() if _spelling_variant(q_model, m.model)]
        if variants:
            return MatchResult(
                Match.SPELLING_VARIANT, reason("spelling_variant", listed=variants[0].model, model=q_model),
                _flatten(variants),
            )  # fmt: skip
    conf = rec.model_list_confidence or "LOW"
    listed = ", ".join(sorted(rec.models)[:12]) + (" …" if len(rec.models) > 12 else "")
    ev = _flatten(list(rec.models.values()))
    return MatchResult(
        Match.NO_MATCH, reason("no_match", model=q_model or q_fam, confidence=conf, listed=listed), ev, (conf,)
    )


def _flatten(models: list[ListedModel]) -> tuple[Evidence, ...]:
    return tuple(e for m in models for e in m.evidence)


# ------------------------------------------------------------------ serial


def _serial_eq(a: str, b: str) -> bool:
    pa, pb = parse_serial(a.upper()), parse_serial(b.upper())
    if pa["number"] is not None and pb["number"] is not None:
        return pa["prefix"] == pb["prefix"] and pa["number"] == pb["number"] and pa.get("suffix") == pb.get("suffix")
    return a.strip().upper() == b.strip().upper()


def _in_constraint(serial: str, c: Any) -> bool | None:
    if c.kind == "range":
        return serial_in_range(serial.upper(), c.start.upper(), c.end.upper())
    return any(_serial_eq(serial, s) for s in c.serials)


def _serial_verdict(cfg: LinkedConfig, rec: EngineRecord, ev: list[Evidence]) -> tuple[str, str, str, tuple[str, ...]]:
    """Returns (verdict, rule, reason, basis) once the model has matched."""
    if not cfg.serial:
        ev.extend(rec.certain)
        if rec.certain:
            return "APPLICABLE", "serial.none.certain", reason("certain_no_serial"), ()
        return "APPLICABLE", "serial.none", reason("no_serial"), ()
    serial = cfg.serial.strip()
    for c in (c for c in rec.serials if c.excluded):
        if _in_constraint(serial, c):
            ev.append(c.evidence)
            return (
                "NOT_APPLICABLE",
                "serial.excluded",
                reason("serial_excluded", serial=serial, constraint=c.label),
                (c.evidence.confidence,),
            )
    inclusions = [c for c in rec.serials if not c.excluded]
    if inclusions:
        ev.extend(c.evidence for c in inclusions)
        results = [(c, _in_constraint(serial, c)) for c in inclusions]
        hit = next((c for c, r in results if r), None)
        if hit:
            return "APPLICABLE", "serial.in", reason("serial_in", serial=serial, constraint=hit.label), ()
        if all(r is False for _, r in results):
            labels = "; ".join(c.label for c in inclusions)
            basis = tuple(c.evidence.confidence for c in inclusions)
            return "NOT_APPLICABLE", "serial.out", reason("serial_out", serial=serial, constraint=labels), basis
        c = next(c for c, r in results if r is None)
        return (
            "UNDETERMINED",
            "serial.incomparable",
            reason("serial_incomparable", serial=serial, constraint=c.label),
            (),
        )
    if rec.svcinfo:
        ev.extend(rec.svcinfo)
        return "UNDETERMINED", "serial.svcinfo", reason("svcinfo"), ()
    if rec.certain:
        ev.extend(rec.certain)
        return "UNDETERMINED", "serial.certain", reason("certain_serial"), ()
    return "APPLICABLE", "serial.unlimited", reason("no_serial_limit"), ()


# ------------------------------------------------------------------ verdict


def evaluate(cfg: LinkedConfig, rec: EngineRecord) -> Applicability:
    reasons: list[str] = []
    ev: list[Evidence] = []

    def done(
        verdict: str, rule: str, why: str, match: Match | None = None, basis: tuple[str, ...] = ()
    ) -> Applicability:
        reasons.append(why)
        return Applicability(rec.id, verdict, tuple(reasons), _ids(ev), match, basis, rule)  # type: ignore[arg-type]

    has_model = bool(cfg.model_norm or cfg.family)
    if not cfg.make_canonical and not has_model:
        return done("NOT_CHECKED", "not_checked", reason("not_checked"))
    if cfg.make_canonical:
        rel = make_relation(cfg.make_canonical, rec)
        if rel == "missing":
            return done("UNDETERMINED", "make.missing", reason("missing_make"))
        if rel == "different":
            why = reason("different_make", record_make=" | ".join(rec.makes), query_make=cfg.make_canonical)
            return done("NOT_APPLICABLE", "make.different", why, basis=("HIGH",))  # Make column = HIGH
        if rel == "related":
            reasons.append(reason("related_make", record_make=" | ".join(rec.makes)))
        if not has_model:
            return done("UNDETERMINED", "make.only", reason("make_only"))
    m = match_model(cfg, rec)
    ev.extend(m.evidence)
    if m.kind == Match.EXACT:
        reasons.append(m.reason)
        verdict, rule, why, basis = _serial_verdict(cfg, rec, ev)
        return done(verdict, rule, why, m.kind, basis)
    if m.kind == Match.NO_MATCH:
        allowed = set(rules()["not_applicable_requires_confidence"])
        if rec.low_tokens:
            why = reason("no_match_incomplete", model=cfg.model_norm or cfg.family, low=", ".join(rec.low_tokens))
            return done("UNDETERMINED", "model.no_match.incomplete", why, m.kind)
        if set(m.basis) <= allowed and m.basis:
            return done("NOT_APPLICABLE", "model.no_match", m.reason, m.kind, m.basis)
        return done("UNDETERMINED", "model.no_match.low", reason("no_match_low", model=cfg.model_norm), m.kind)
    rule = {
        Match.FAMILY_ONLY: "model.family_only",
        Match.SERIES_OVERLAP: "model.series_overlap",
        Match.SPELLING_VARIANT: "model.spelling_variant",
        Match.UNKNOWN: "model.unknown",
    }[m.kind]
    return done("UNDETERMINED", rule, m.reason, m.kind)


def evaluate_all(cfg: LinkedConfig, records: dict[str, EngineRecord]) -> dict[str, Applicability]:
    return {rid: evaluate(cfg, rec) for rid, rec in records.items()}
