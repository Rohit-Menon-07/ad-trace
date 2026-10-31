"""Applicability + revision engine tests.

SYNTHETIC_* fixtures are hand-built EngineRecords (always run). REAL_* cases use records from the workbook via
the session `real_db` fixture (skipped without data/raw). The dataset has no serial ranges/lists and no
service-information applicability, so those rules are covered by SYNTHETIC cases only.
"""

from __future__ import annotations

import random
from datetime import date

import pytest

from backend.app.engine.applicability import evaluate, evaluate_all, match_model, rules
from backend.app.engine.data import build_index, load_index
from backend.app.engine.status import latest_in_group, lineage, record_status
from backend.app.engine.types import (
    EngineRecord,
    Evidence,
    LineageRef,
    LinkedConfig,
    ListedModel,
    Match,
    SerialConstraint,
)
from backend.app.extract.models import family

AS_OF = date(2026, 10, 31)
ALLOWED = set(rules()["not_applicable_requires_confidence"])


# ------------------------------------------------------------------ synthetic builders


def ev(rid: str, n: int = 1, conf: str = "MEDIUM") -> Evidence:
    return Evidence(f"E{rid}{n}", f"{rid}#s{n}", conf)  # type: ignore[arg-type]


def lm(model: str, conf: str = "HIGH", series: bool = False, rid: str = "S") -> ListedModel:
    return ListedModel(model, family(model), conf, series, (ev(rid, 1, conf),))  # type: ignore[arg-type]


def rng_c(start: str, end: str, excluded: bool = False) -> SerialConstraint:
    return SerialConstraint(
        "range", start, end, (), excluded, f"serial numbers {start} through {end}", ev("S", 2, "HIGH")
    )


def lst_c(*serials: str, excluded: bool = False) -> SerialConstraint:
    return SerialConstraint("list", None, None, serials, excluded, f"MSN {', '.join(serials)}", ev("S", 3, "HIGH"))


def rec(
    rid: str = "S0001",
    makes: tuple[str, ...] = ("Airbus SAS",),
    models: tuple[ListedModel, ...] = (lm("A330-243"),),
    low: tuple[str, ...] = (),
    all_families: tuple[str, ...] = (),
    certain: bool = False,
    serials: tuple[SerialConstraint, ...] = (),
    svcinfo: bool = False,
    docket: str = "FAA-S-1",
    ad_number: str | None = None,
    published: str | None = "2026-01-01",
    due: str | None = "2026-11-30",
    duplicate: bool = False,
    supersedes: tuple[str, ...] = (),
    withdraws: tuple[str, ...] = (),
) -> EngineRecord:
    from backend.app.ingest.makes import make_family

    return EngineRecord(
        id=rid, docket=docket, makes=makes, make_families=tuple(dict.fromkeys(make_family(m) for m in makes)),
        ad_number=ad_number, citation_publish_date=published, comments_due_effective=due, is_duplicate=duplicate,
        models={m.model: m for m in models}, low_tokens=low,
        all_families={f: (ev(rid, 9),) for f in all_families}, certain=(ev(rid, 4),) if certain else (),
        serials=serials, svcinfo=(ev(rid, 5),) if svcinfo else (),
        supersedes=tuple(LineageRef(a, f"X{rid}", f"{rid}#s1") for a in supersedes), continues=(), corrections=(),
        withdraws=tuple(LineageRef(d, f"W{rid}", f"{rid}#s1") for d in withdraws),
    )  # fmt: skip


def cfg(make: str | None = "Airbus SAS", model: str | None = "A330-243", fam: str | None = None,
        serial: str | None = None) -> LinkedConfig:  # fmt: skip
    return LinkedConfig(make, model, fam or (family(model) if model else None), serial, AS_OF)


# ------------------------------------------------------------------ SYNTHETIC verdict table (rules 1-4)

SYNTHETIC = [
    # id, config, record, verdict, rule
    ("SYN01 no make no model", cfg(None, None), rec(), "NOT_CHECKED", "not_checked"),
    ("SYN02 different make", cfg("The Boeing Company", "737-8"), rec(), "NOT_APPLICABLE", "make.different"),
    ("SYN03 record make missing", cfg(), rec(makes=()), "UNDETERMINED", "make.missing"),
    ("SYN04 make only", cfg("Airbus SAS", None), rec(), "UNDETERMINED", "make.only"),
    ("SYN05 same family other make, model differs", cfg("Airbus SAS", "AS350B3"),
     rec(makes=("Airbus Helicopters",), models=(lm("EC130B4"),)), "NOT_APPLICABLE", "model.no_match"),
    ("SYN06 related make spelling", cfg("Embraer", "EMB-545"), rec(makes=("Embraer SA",), models=(lm("EMB-545"),)),
     "APPLICABLE", "serial.none"),
    ("SYN07 model only, exact", cfg(None, "A330-243"), rec(), "APPLICABLE", "serial.none"),
    ("SYN08 exact, no serial, certain", cfg(), rec(certain=True), "APPLICABLE", "serial.none.certain"),
    ("SYN09 family-only query", cfg(model=None, fam="A330"), rec(models=(lm("A330-243"), lm("A330-941"))),
     "UNDETERMINED", "model.family_only"),
    ("SYN10 family query, whole type listed", cfg(model=None, fam="A330"), rec(models=(lm("A330"),)),
     "APPLICABLE", "serial.none"),
    ("SYN11 variant query, whole type listed", cfg(), rec(models=(lm("A330"), lm("A340"))), "APPLICABLE", "serial.none"),
    ("SYN12 all-family honoured (whole type listed)", cfg(None, "A318-111"),
     rec(models=(lm("A318", "MEDIUM", series=True),), all_families=("A318",)), "APPLICABLE", "serial.none"),
    ("SYN13 no match, HIGH list", cfg(model="A330-202"), rec(models=(lm("A330-243"),)), "NOT_APPLICABLE",
     "model.no_match"),
    ("SYN14 no match, MEDIUM list", cfg(model="A330-202"), rec(models=(lm("A330-243", "MEDIUM"),)), "NOT_APPLICABLE",
     "model.no_match"),
    ("SYN15 no match, list has LOW tokens", cfg("The Boeing Company", "737-900ER"),
     rec(makes=("The Boeing Company",), models=(lm("737-600", "MEDIUM"),), low=("900ER",)), "UNDETERMINED",
     "model.no_match.incomplete"),
    ("SYN16 only LOW tokens", cfg(), rec(models=(), low=("radio altimeter",)), "UNDETERMINED", "model.unknown"),
    ("SYN17 no model list", cfg(), rec(models=()), "UNDETERMINED", "model.unknown"),
    ("SYN18 series overlap A330-200 vs A330-243", cfg(), rec(models=(lm("A330-200", "MEDIUM"),)), "UNDETERMINED",
     "model.series_overlap"),
    ("SYN19 different series digit is a real no-match", cfg("The Boeing Company", "737-800"),
     rec(makes=("The Boeing Company",), models=(lm("737-700", "MEDIUM"),)), "NOT_APPLICABLE", "model.no_match"),
    ("SYN20 series word on token", cfg("The Boeing Company", "737-900ER"),
     rec(makes=("The Boeing Company",), models=(lm("737-900", "MEDIUM", series=True),)), "UNDETERMINED",
     "model.series_overlap"),
    ("SYN21 spelling variant SA-365N/SA365N", cfg("Airbus Helicopters", "SA365N"),
     rec(makes=("Airbus Helicopters",), models=(lm("SA-365N"),)), "UNDETERMINED", "model.spelling_variant"),
    ("SYN22 spelling variant GULFSTREAM G150/G150", cfg("Gulfstream Aerospace LP", "G150"),
     rec(makes=("Gulfstream Aerospace LP",), models=(lm("GULFSTREAM G150", "MEDIUM"),)), "UNDETERMINED",
     "model.spelling_variant"),
    ("SYN23 serial in range", cfg(serial="S-1200"), rec(serials=(rng_c("S-1000", "S-1500"),)), "APPLICABLE",
     "serial.in"),
    ("SYN24 serial out of range", cfg(serial="S-1600"), rec(serials=(rng_c("S-1000", "S-1500"),)), "NOT_APPLICABLE",
     "serial.out"),
    ("SYN25 serial in list", cfg(serial="45"), rec(serials=(lst_c("0012", "0045"),)), "APPLICABLE", "serial.in"),
    ("SYN26 serial not in list", cfg(serial="0099"), rec(serials=(lst_c("0012", "0045"),)), "NOT_APPLICABLE",
     "serial.out"),
    ("SYN27 serial excluded", cfg(serial="0045"), rec(serials=(lst_c("0045", excluded=True),)), "NOT_APPLICABLE",
     "serial.excluded"),
    ("SYN28 exclusion only, not excluded", cfg(serial="0046"), rec(serials=(lst_c("0045", excluded=True),)),
     "APPLICABLE", "serial.unlimited"),
    ("SYN29 range and exclusion inside it", cfg(serial="1250"),
     rec(serials=(rng_c("1000", "1500"), lst_c("1250", excluded=True))), "NOT_APPLICABLE", "serial.excluded"),
    ("SYN30 prefix mismatch", cfg(serial="T-1200"), rec(serials=(rng_c("S-1000", "S-1500"),)), "UNDETERMINED",
     "serial.incomparable"),
    ("SYN31 serial + service info", cfg(serial="1234"), rec(svcinfo=True), "UNDETERMINED", "serial.svcinfo"),
    ("SYN32 serial + certain, no constraint", cfg(serial="1234"), rec(certain=True), "UNDETERMINED", "serial.certain"),
    ("SYN33 serial, no constraint, no qualifier", cfg(serial="1234"), rec(), "APPLICABLE", "serial.unlimited"),
    ("SYN34 service info without serial", cfg(), rec(svcinfo=True), "APPLICABLE", "serial.none"),
]  # fmt: skip


@pytest.mark.parametrize(("name", "c", "r", "verdict", "rule"), SYNTHETIC, ids=[s[0] for s in SYNTHETIC])
def test_synthetic_verdicts(name: str, c: LinkedConfig, r: EngineRecord, verdict: str, rule: str) -> None:
    a = evaluate(c, r)
    assert (a.verdict, a.rule) == (verdict, rule), a.reasons
    assert a.reasons and all(isinstance(x, str) and x for x in a.reasons)
    if verdict == "NOT_APPLICABLE":
        assert a.basis and set(a.basis) <= ALLOWED


def test_reason_texts_from_rules_yaml() -> None:
    assert evaluate(cfg(model=None, fam="A330"), rec(models=(lm("A330-243"), lm("A330-941")))).reasons == (
        "query names a family; the record lists specific variants",
    )
    a = evaluate(cfg(serial="S-1600"), rec(serials=(rng_c("S-1000", "S-1500"),)))
    assert "S-1000 through S-1500" in a.reasons[-1]  # the range is quoted
    assert (
        evaluate(cfg("The Boeing Company", "737-8"), rec())
        .reasons[0]
        .startswith("record concerns a different manufacturer")
    )
    assert evaluate(cfg(serial="1234"), rec(svcinfo=True)).reasons[-1] == (
        "serial applicability is defined in referenced service information that is not in the provided text"
    )


@pytest.mark.parametrize(
    ("c", "r", "kind"),
    [
        (cfg(), rec(), Match.EXACT),
        (cfg(model=None, fam="A330"), rec(models=(lm("A330-243"),)), Match.FAMILY_ONLY),
        (cfg(model="A340-313"), rec(), Match.NO_MATCH),
        (cfg(), rec(models=()), Match.UNKNOWN),
        (cfg(model="A330-202"), rec(models=(lm("A330-243"),), all_families=("A330",)), Match.NO_MATCH),
    ],
    ids=["exact", "family_only", "no_match", "unknown", "all_flag_without_whole_type_is_ignored"],
)
def test_match_model_SYNTHETIC(c: LinkedConfig, r: EngineRecord, kind: Match) -> None:
    assert match_model(c, r).kind == kind


# ------------------------------------------------------------------ safety invariant (property-style)


def _random_record(rnd: random.Random, i: int) -> EngineRecord:
    """Random records where every model/serial extraction is LOW or missing."""
    pool = ["A330-243", "A330-941", "737-800", "AS350B3", "EMB-545", "A330-200"]
    return rec(
        rid=f"P{i:04d}",
        makes=rnd.choice([("Airbus SAS",), ("Airbus Helicopters",), ("Embraer S.A.",), ()]),
        models=(),
        low=tuple(rnd.sample(pool, rnd.randint(0, 3))),
        certain=rnd.random() < 0.5,
        svcinfo=rnd.random() < 0.3,
    )


def test_safety_invariant_never_not_applicable_from_low_or_missing_SYNTHETIC() -> None:
    rnd = random.Random(20261031)
    configs = [cfg(m, mod, serial=s) for m in ("Airbus SAS", "Embraer", None) for mod in ("A330-243", "EMB-545", None)
               for s in (None, "1234")]  # fmt: skip
    for i in range(400):
        r = _random_record(rnd, i)
        for c in configs:
            a = evaluate(c, r)
            if a.verdict == "NOT_APPLICABLE":
                # only the make check (Make column, HIGH) may exclude a record whose extractions are LOW/missing
                assert a.rule == "make.different" and a.basis == ("HIGH",), (r, c, a)


def test_every_not_applicable_has_high_or_medium_basis_SYNTHETIC() -> None:
    for name, c, r, *_ in SYNTHETIC:
        a = evaluate(c, r)
        if a.verdict == "NOT_APPLICABLE":
            assert a.basis and set(a.basis) <= ALLOWED, name


# ------------------------------------------------------------------ status and lineage (SYNTHETIC)


@pytest.mark.parametrize(
    ("due", "as_of", "period"),
    [("2026-10-31", date(2026, 10, 31), "OPEN"), ("2026-10-31", date(2026, 11, 1), "CLOSED"), (None, AS_OF, "UNKNOWN")],
    ids=["due_today_open", "day_after_closed", "no_date_unknown"],
)
def test_comment_period_SYNTHETIC(due: str | None, as_of: date, period: str) -> None:
    r = rec(due=due)
    idx = build_index({r.id: r})
    st = record_status(r, idx, as_of)
    assert (st.status_label, st.comment_period, st.comments_due_effective) == ("PROPOSED", period, due)


def test_withdrawn_and_lineage_SYNTHETIC() -> None:
    nprm = rec("S1", docket="FAA-D", ad_number="2026-01-01", published="2025-01-01")
    snprm = rec("S2", docket="FAA-D", published="2025-06-01")
    notice = rec("S3", docket="FAA-D", published="2025-09-01", withdraws=("FAA-D",))
    dup = rec("S4", docket="FAA-D", published="2025-12-01", duplicate=True)
    successor = rec("S5", docket="FAA-E", supersedes=("2026-01-01", "1999-01-01"))
    idx = build_index({r.id: r for r in (nprm, snprm, notice, dup, successor)})
    st = record_status(nprm, idx, AS_OF)
    assert st.withdrawn and [w.value for w in st.withdrawn_by] == ["S3"] and st.withdrawn_by[0].extraction_id == "WS3"
    assert not record_status(successor, idx, AS_OF).withdrawn
    ln = lineage(nprm, idx)
    assert [r.value for r in ln.superseded_by_proposal] == ["S5"] and ln.superseded_by_proposal[0].extraction_id
    assert ln.same_docket_group == ("S1", "S2", "S3", "S4")
    assert latest_in_group(nprm, idx) == ("S3",)  # the duplicate S4 is newer but never "latest"
    assert not ln.is_latest_in_docket_group and lineage(notice, idx).is_latest_in_docket_group
    assert not lineage(dup, idx).is_latest_in_docket_group
    sup = lineage(successor, idx).supersedes_ad
    assert [(r.value, r.target_in_dataset, r.target_record_ids) for r in sup] == [
        ("2026-01-01", True, ("S1",)),
        ("1999-01-01", False, ()),  # not in the dataset: nothing inferred
    ]


def test_superseded_by_needs_known_ad_number_SYNTHETIC() -> None:
    a = rec("S1", ad_number=None)
    b = rec("S2", supersedes=("2026-01-01",))
    idx = build_index({"S1": a, "S2": b})
    assert lineage(a, idx).superseded_by_proposal == ()


def test_tied_latest_dates_mark_all_SYNTHETIC() -> None:
    a, b = rec("S1", published="2025-01-01"), rec("S2", published="2025-01-01")
    idx = build_index({"S1": a, "S2": b})
    assert latest_in_group(a, idx) == ("S1", "S2")


# ------------------------------------------------------------------ REAL records


@pytest.fixture(scope="module")
def idx(real_db):
    return load_index(real_db)


REAL = [
    ("REAL R0003 A330-243 no serial (certain)", "R0003", cfg(), "APPLICABLE", "serial.none.certain"),
    ("REAL R0003 A330-243 serial 1234 (certain)", "R0003", cfg(serial="1234"), "UNDETERMINED", "serial.certain"),
    ("REAL R0003 family-only A330", "R0003", cfg(model=None, fam="A330"), "UNDETERMINED", "model.family_only"),
    ("REAL R0011 A330-941 from Model column", "R0011", cfg(model="A330-941"), "APPLICABLE", "serial.none.certain"),
    ("REAL R0121 A330-243 vs 'A330-200 series'", "R0121", cfg(), "UNDETERMINED", "model.series_overlap"),
    ("REAL R0057 A330-243 not listed (HIGH)", "R0057", cfg(), "NOT_APPLICABLE", "model.no_match"),
    ("REAL R0089 A330-243 not listed (MEDIUM)", "R0089", cfg(), "NOT_APPLICABLE", "model.no_match"),
    ("REAL R0061 'all' flag not family-wide", "R0061", cfg(model="A330-202"), "NOT_APPLICABLE", "model.no_match"),
    ("REAL R0061 A330-243 no qualifier", "R0061", cfg(), "APPLICABLE", "serial.none"),
    ("REAL R0061 A330-243 serial, no limitation", "R0061", cfg(serial="1234"), "APPLICABLE", "serial.unlimited"),
    ("REAL R0007 A318-111", "R0007", cfg(model="A318-111"), "APPLICABLE", "serial.none"),
    ("REAL R0007 A318 family via 'all ... A318 series'", "R0007", cfg(model=None, fam="A318"), "APPLICABLE",
     "serial.none"),
    ("REAL R0001 Airbus Helicopters AS350B3", "R0001", cfg("Airbus Helicopters", "AS350B3"), "APPLICABLE",
     "serial.none"),
    ("REAL R0001 asked about Boeing", "R0001", cfg("The Boeing Company", "737-8"), "NOT_APPLICABLE", "make.different"),
    ("REAL R0155 737-900ER (orphan 900ER)", "R0155", cfg("The Boeing Company", "737-900ER"), "UNDETERMINED",
     "model.series_overlap"),
    ("REAL R0155 777-200 (list incomplete)", "R0155", cfg("The Boeing Company", "777-200"), "UNDETERMINED",
     "model.no_match.incomplete"),
    ("REAL R0012 radio altimeter: no model list", "R0012", cfg("Airbus Helicopters", "AS350B3"), "UNDETERMINED",
     "model.unknown"),
    ("REAL R0244 record make missing", "R0244", cfg("Hamilton Sundstrand", "14SF-7"), "UNDETERMINED", "make.missing"),
    ("REAL R0017 Embraer S.A. merged into Embraer", "R0017", cfg("Embraer", "EMB-545"), "APPLICABLE",
     "serial.none"),
    ("REAL R0003 no make no model", "R0003", cfg(None, None), "NOT_CHECKED", "not_checked"),
]  # fmt: skip


@pytest.mark.parametrize(("name", "rid", "c", "verdict", "rule"), REAL, ids=[r[0] for r in REAL])
def test_real_verdicts(idx, name: str, rid: str, c: LinkedConfig, verdict: str, rule: str) -> None:
    a = evaluate(c, idx.records[rid])
    assert (a.verdict, a.rule) == (verdict, rule), a.reasons
    if verdict in ("APPLICABLE", "NOT_APPLICABLE") and rule != "make.different":
        assert a.evidence_ids  # every model-based decision points at evidence


def test_real_status(idx) -> None:
    r159 = idx.records["R0159"]
    assert record_status(r159, idx, AS_OF).comment_period == "CLOSED"
    assert record_status(r159, idx, date(2024, 12, 9)).comment_period == "OPEN"  # extended due date, inclusive
    assert record_status(idx.records["R0153"], idx, AS_OF).withdrawn  # Comments: "Withdraws FAA AD NPRM ..."
    for rid in ("R0294", "R0351", "R0403", "R0431"):  # docket 2000-NM-120-AD has a withdrawal notice
        assert record_status(idx.records[rid], idx, AS_OF).withdrawn
    assert not record_status(idx.records["R0003"], idx, AS_OF).withdrawn
    assert all(record_status(r, idx, AS_OF).status_label == "PROPOSED" for r in idx.records.values())


def test_real_lineage(idx) -> None:
    ln = lineage(idx.records["R0011"], idx)
    assert [(r.value, r.target_in_dataset) for r in ln.supersedes_ad] == [
        ("2014-16-22", False), ("2017-25-13", False), ("2024-25-11", False),
    ]  # fmt: skip
    assert all(r.extraction_id for r in ln.supersedes_ad)
    assert ln.same_docket_group == ("R0011", "R0121") and ln.is_latest_in_docket_group
    assert lineage(idx.records["R0159"], idx).latest_in_docket_group == ("R0157",)
    assert not lineage(idx.records["R0195"], idx).is_latest_in_docket_group  # duplicate
    corr = lineage(idx.records["R0166"], idx).corrections
    assert [(c.value, c.target_in_dataset) for c in corr] == [("FAA-2022-1308", False)]
    # No NPRM's AD number is cited by another record, so nothing is "superseded by" in the real data.
    assert all(not lineage(r, idx).superseded_by_proposal for r in idx.records.values())


SWEEP = [
    cfg(None, None),
    cfg("Airbus SAS", None),
    cfg(),
    cfg(serial="1234"),
    cfg(model=None, fam="A330"),
    cfg("The Boeing Company", "737-800", serial="LN-1234"),
    cfg("Embraer", "EMB-545"),
    cfg(None, "PW4090"),
    cfg("Airbus Helicopters", "AS350B3", serial="7000"),
]


def test_sweep_all_records_invariant_and_no_exceptions(idx) -> None:
    for c in SWEEP:
        for a in evaluate_all(c, idx.records).values():
            if a.verdict == "NOT_APPLICABLE":
                assert a.basis and set(a.basis) <= ALLOWED, a
        for r in idx.records.values():
            record_status(r, idx, c.as_of)
            lineage(r, idx)


def test_sweep_degraded_records_never_not_applicable_on_model(idx) -> None:
    """Every real record with its model/serial extractions downgraded to LOW: model/serial NOT_APPLICABLE vanishes."""
    from dataclasses import replace

    for r in idx.records.values():
        degraded = replace(r, models={}, low_tokens=tuple(r.models) + r.low_tokens, serials=(), all_families={})
        for c in SWEEP:
            a = evaluate(c, degraded)
            assert a.verdict != "NOT_APPLICABLE" or a.rule == "make.different", (r.id, c, a)


def test_engine_runtime_under_100ms(idx) -> None:
    from backend.app.engine.explain import bench

    ms = bench(idx, cfg(serial="1234"))
    assert ms < 100, f"{ms:.1f} ms"
