"""Golden tests for every extraction rule_id.

REAL_* cases use verbatim sentences from the AD NPRM workbook (record id in the test name).
SYNTHETIC_* cases are invented text, used where the dataset has no example (serial ranges/lists, service-info
applicability) or to pin edge cases.
"""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from backend.app.extract import lineage, models, serials
from backend.app.extract.run import coverage_table, extract_db
from backend.app.extract.types import Sent
from backend.app.schemas import CoverageReport


def sent(text: str, sid: str = "R9999#s1", start: int = 0) -> Sent:
    return Sent(sid, text, start)


def values(exs, field=None, key=None):
    return [(e.value[key] if key else e.value) for e in exs if field is None or e.field == field]


def rules(exs) -> set[str]:
    return {e.rule_id for e in exs}


# ------------------------------------------------------------------ normalisation


@pytest.mark.parametrize(
    ("raw", "norm", "fam"),
    [
        ("A330-243", "A330-243", "A330"),
        ("a330–243f", "A330-243F", "A330"),  # en dash, lowercase
        ("AS 365 N2", "AS365N2", "AS365N2"),
        ("A300 B4-603", "A300B4-603", "A300B4"),
        ("737-300 Series", "737-300", "737"),
        ("MBB-BK 117 D-2", "MBB-BK117D-2", "MBB-BK117D"),
        ("DC-9-81", "DC-9-81", "DC-9"),
        ("EMB-545", "EMB-545", "EMB-545"),
        ("A330-200 Freighter", "A330-200 FREIGHTER", "A330"),
        ("AW119 MKII", "AW119MKII", "AW119MKII"),
        ("CFM56-5B1/2P", "CFM56-5B1/2P", "CFM56"),
        ("737 - 800", "737-800", "737"),
    ],
)
def test_norm_model_and_family(raw: str, norm: str, fam: str) -> None:
    assert models.norm_model(raw) == norm
    assert models.family(norm) == fam


# ------------------------------------------------------------------ models (REAL)

REAL_R0001 = (
    "The FAA proposes to adopt a new airworthiness directive (AD) for all Airbus Helicopters Model AS350B3, AS355F, "
    "AS355F1, AS355F2, AS355N, AS355NP, EC130B4, and EC130T2 helicopters."
)
REAL_R0003 = (
    "The FAA proposes to supersede Airworthiness Directive (AD) 2025-09-07, which applies to certain Airbus SAS Model "
    "A330-243, -243F, -841, and -941 airplanes."
)
REAL_R0155 = (
    "The FAA proposes to adopt a new airworthiness directive (AD) for certain The Boeing Company Model 737-600, -700, "
    "-700C, -800, -900, and 900ER series airplanes."
)
REAL_R0189 = (
    "The FAA proposes to adopt a new airworthiness directive (AD) for all Pratt & Whitney Canada Corp. (P&WC) PW210A "
    "and PW210S model turboshaft engines."
)
REAL_R0007 = (
    "The FAA proposes to adopt a new airworthiness directive (AD) for all Airbus SAS Model A318 series airplanes; "
    "Model A319 series airplanes; Model A320 series airplanes; and Model A321 series airplanes."
)
REAL_R0178 = (
    "The FAA is withdrawing a notice of proposed rulemaking (NPRM) that would have applied to certain Gulfstream "
    "Aerospace Corporation (Gulfstream) Models G-IV and GIV-X airplanes."
)


def test_model_column_REAL_R0001() -> None:
    exs = models.models_from_column(
        "R0001", "AS350B3 | AS355F | AS355F1 | AS355F2 | AS355N | AS355NP | EC130B4 | EC130T2"
    )
    assert values(exs, "model", "model")[:3] == ["AS350B3", "AS355F", "AS355F1"]
    assert {e.confidence for e in exs} == {"HIGH"} and rules(exs) == {"model.column"}
    assert all(e.source == "column" and e.span_start is None for e in exs)


def test_model_column_nondesignator_REAL_R0012() -> None:
    exs = models.models_from_column("R0012", "radio (also known as radar) altimeter")
    assert rules(exs) == {"model.column.nondesignator"} and exs[0].confidence == "LOW"
    assert exs[0].value["model"] is None


def test_model_summary_list_and_all_family_REAL_R0001() -> None:
    s = sent(REAL_R0001, "R0001#s1", 0)
    exs = models.models_from_sentence("R0001", s)
    assert values(exs, "model", "model") == [
        "AS350B3", "AS355F", "AS355F1", "AS355F2", "AS355N", "AS355NP", "EC130B4", "EC130T2",
    ]  # fmt: skip
    assert {e.rule_id for e in exs if e.field == "model"} == {"model.summary.list"}
    assert "AS350B3" in values(exs, "applies_all_of_family", "family")
    for e in exs:  # provenance: span points at the token in the Summary
        if e.field == "model":
            assert REAL_R0001[e.span_start : e.span_end] == e.value["raw"]


def test_model_summary_expanded_and_certain_REAL_R0003() -> None:
    exs = models.models_from_sentence("R0003", sent(REAL_R0003, "R0003#s1"))
    assert values(exs, "model", "model") == ["A330-243", "A330-243F", "A330-841", "A330-941"]
    assert [e.rule_id for e in exs if e.field == "model"][1:] == ["model.summary.expanded"] * 3
    assert values(exs, "qualifier_certain") == [{"value": True}]
    assert not values(exs, "applies_all_of_family")


def test_model_summary_orphan_suffix_REAL_R0155() -> None:
    exs = models.models_from_sentence("R0155", sent(REAL_R0155))
    got = [(e.value["model"], e.rule_id, e.confidence) for e in exs if e.field == "model"]
    assert got[-1] == ("900ER", "model.summary.orphan_suffix", "LOW")  # source typo: never guessed as 737-900ER
    assert ("737-700C", "model.summary.expanded", "MEDIUM") in got


def test_model_summary_postfix_REAL_R0189() -> None:
    exs = models.models_from_sentence("R0189", sent(REAL_R0189))
    assert [(e.value["model"], e.rule_id) for e in exs if e.field == "model"] == [
        ("PW210A", "model.summary.postfix"),
        ("PW210S", "model.summary.postfix"),
    ]


def test_model_series_list_REAL_R0007() -> None:
    exs = models.models_from_sentence("R0007", sent(REAL_R0007))
    assert values(exs, "model", "model") == ["A318", "A319", "A320", "A321"]


def test_roman_numeral_designators_REAL_R0178() -> None:
    exs = models.models_from_sentence("R0178", sent(REAL_R0178))
    assert values(exs, "model", "model") == ["G-IV", "GIV-X"]
    assert values(exs, "qualifier_certain") == [{"value": True}]


def test_model_SYNTHETIC_spec_example_and_offsets() -> None:
    text = "The FAA proposes an AD for all Model A330-243, -243F, -841, and -941 airplanes."
    exs = models.models_from_sentence("R1", sent(text, "R1#s3", start=100))
    assert values(exs, "model", "model") == ["A330-243", "A330-243F", "A330-841", "A330-941"]
    assert all(e.span_start >= 100 and e.sentence_id == "R1#s3" for e in exs)  # offsets shifted to the Summary
    assert values(exs, "applies_all_of_family", "family") == ["A330"]


def test_model_SYNTHETIC_no_model_phrase() -> None:
    assert (
        models.models_from_sentence("R1", sent("The FAA proposes an AD for the specified Bell model helicopters."))
        == []
    )


# ------------------------------------------------------------------ serials (SYNTHETIC: none in the dataset)


def test_serial_range_SYNTHETIC() -> None:
    exs = serials.serials_from_sentence(
        "R1", sent("This AD applies to serial numbers S-1000 through S-1500 inclusive.")
    )
    assert [e.rule_id for e in exs] == ["serial.range"]
    v = exs[0].value
    assert (v["start"], v["end"], v["numeric"], v["prefix"], v["excluded"]) == ("S-1000", "S-1500", False, "S-", False)


def test_serial_range_numeric_msn_SYNTHETIC() -> None:
    exs = serials.serials_from_sentence(
        "R1", sent("Airplanes, manufacturer serial numbers (MSN) 1000 to 1500, are affected.")
    )
    assert exs[0].value["kind"] == "msn" and exs[0].value["numeric"] is True


def test_serial_list_and_exclusion_SYNTHETIC() -> None:
    exs = serials.serials_from_sentence("R1", sent("All airplanes except MSNs 0012, 0045, and 0101 are affected."))
    assert [e.rule_id for e in exs] == ["serial.list"]
    assert exs[0].value["serials"] == ["0012", "0045", "0101"] and exs[0].value["excluded"] is True


def test_serial_compare_by_prefix_then_number_SYNTHETIC() -> None:
    assert serials.serial_in_range("S-1200", "S-1000", "S-1500") is True
    assert serials.serial_in_range("S-1600", "S-1000", "S-1500") is False
    assert serials.serial_in_range("T-1200", "S-1000", "S-1500") is None  # different prefix: cannot decide


def test_serial_never_invented_REAL_R0002() -> None:
    text = (
        "AD 2026-09-02 requires repetitive angled ultrasonic scan inspections, and for certain serial numbers, removal "
        "from service and replacement of the HPT 1st-stage air seal."
    )
    assert serials.serials_from_sentence("R0002", sent(text)) == []


def test_svcinfo_defined_SYNTHETIC() -> None:
    exs = serials.svcinfo_from_sentence("R1", sent("The affected airplanes are identified in the service information."))
    assert [e.rule_id for e in exs] == ["svcinfo.defined"]


@pytest.mark.parametrize(
    "text",
    [
        # REAL R0163: about the unsafe condition, not applicability
        "Since the NPRM was issued, the FAA issued AD 2023-17-11, which addresses the unsafe condition identified in "
        "the NPRM.",
        # REAL R0158: actions specified in an EASA AD, not applicability
        "This NPRM proposed to require replacement of all affected parts, as specified in a European Union Aviation "
        "Safety Agency (EASA) AD.",
    ],
    ids=["REAL_R0163_negative", "REAL_R0158_negative"],
)
def test_svcinfo_not_triggered_REAL(text: str) -> None:
    assert serials.svcinfo_from_sentence("R", sent(text)) == []


# ------------------------------------------------------------------ supersession and lineage (REAL)

REAL_R0011 = (
    "The FAA is revising a notice of proposed rulemaking (NPRM) to supersede Airworthiness Directive (AD) 2014-16-22 "
    "and AD 2017-25-13, which apply to certain Airbus SAS Model A330-200, A330-200 Freighter, A330-300, A340-200, "
    "A340-300, A340-500, and A340-600 series airplanes; and AD 2024-25-11, which applies to certain Airbus SAS Model "
    "A330-200, A330-200 Freighter, A330-300, A330-800 and A330-900 series airplanes."
)


def test_supersede_ad_multiple_clauses_REAL_R0011() -> None:
    exs = lineage.supersession_from_sentence("R0011", sent(REAL_R0011))
    assert values(exs, "supersedes_ad", "ad_number") == ["2014-16-22", "2017-25-13", "2024-25-11"]
    assert rules(exs) == {"supersede.ad"} and {e.confidence for e in exs} == {"HIGH"}
    for e in exs:
        assert REAL_R0011[e.span_start : e.span_end] == e.value["ad_number"]


def test_supersede_ad_REAL_R0003() -> None:
    exs = lineage.supersession_from_sentence("R0003", sent(REAL_R0003))
    assert values(exs, "supersedes_ad", "ad_number") == ["2025-09-07"]


def test_supersede_pdf_space_artifact_and_revision_REAL_R0194() -> None:
    text = (
        "The FAA is withdrawing a notice of proposed rulemaking (NPRM) and a supplemental NPRM (SNPRM) that proposed to "
        "supersede airworthiness directive (AD) 72-14-08 R1 for Cessna Aircraft Company (now Textron Aviation Inc.) "
        "Models 310, 320, 401, 402, 411, and 421 airplanes."
    )
    assert values(lineage.supersession_from_sentence("R0194", sent(text)), key="ad_number") == ["72-14-08 R1"]
    assert lineage.norm_ad("2024- 05-13") == "2024-05-13"  # REAL artifact in R0017


def test_supersede_unnumbered_REAL_R0240() -> None:
    text = (
        "We propose to supersede an existing airworthiness directive (AD) for Agusta Model AB139 and AW139 helicopters."
    )
    exs = lineage.supersession_from_sentence("R0240", sent(text))
    assert rules(exs) == {"supersede.unnumbered"} and exs[0].value["ad_number"] is None and exs[0].confidence == "LOW"


def test_supersede_negated_REAL_R0268() -> None:
    text = (
        "Since we issued that NPRM, we decided not to supersede AD 2009-17-05, but instead to issue a new NPRM for "
        "those additional 360 parts."
    )
    exs = lineage.supersession_from_sentence("R0268", sent(text))
    assert rules(exs) == {"supersede.negated"} and exs[0].value["ad_number"] is None


def test_continue_actions_REAL_R0003() -> None:
    text = "This proposed AD would continue to require the actions specified in AD 2025-09-07 and would require modifying the airplane."
    exs = lineage.continuation_from_sentence("R0003", sent(text))
    assert [(e.rule_id, e.value["ad_number"]) for e in exs] == [("continue.actions", "2025-09-07")]


def test_continue_retain_REAL_R0167() -> None:
    text = (
        "This proposed AD would retain the requirements from AD 2022-14-14 of repetitively inspecting the wing root ribs "
        "for cracks, looseness, and damage and replacing any root rib with a crack, a loose rib or lift pin bushing, or "
        "any damage; and would add the Model ASW-15B gliders to the applicability."
    )
    exs = lineage.continuation_from_sentence("R0167", sent(text))
    assert [(e.rule_id, e.value["ad_number"]) for e in exs] == [("continue.retain", "2022-14-14")]
    change = lineage.applicability_change_from_sentence("R0167", sent(text))
    assert [(e.rule_id, e.value["change"]) for e in change] == [("applicability.add", "expanded")]


@pytest.mark.parametrize(
    ("rid", "text", "rule", "change"),
    [
        ("R0003", "This proposed AD also reduces the applicability.", "applicability.reduced", "reduced"),
        ("R0050", "This proposed AD would continue to require the actions in AD 2021-17-07 and expand the applicability.",
         "applicability.expanded", "expanded"),
        ("R0130", "This proposed AD would also add Model A319- 173N and Model A321-253NY airplanes to the applicability.",
         "applicability.add", "expanded"),
        ("R0073", "This proposed AD would remove certain engine serial numbers from the applicability of the existing AD.",
         "applicability.remove", "reduced"),
    ],
    ids=["REAL_R0003", "REAL_R0050", "REAL_R0130", "REAL_R0073"],
)  # fmt: skip
def test_applicability_change_REAL(rid: str, text: str, rule: str, change: str) -> None:
    exs = lineage.applicability_change_from_sentence(rid, sent(text))
    assert [(e.rule_id, e.value["change"]) for e in exs] == [(rule, change)]


def test_withdraw_notice_plural_REAL_R0371() -> None:
    text = (
        "This document withdraws two notices of proposed rulemaking (NPRMs) that would have applied to Cessna Aircraft "
        "Company (Cessna) Models 401, 401A, 401B, 402, 402A, 402B, 402C, 411, 411A, and 414A airplanes."
    )
    exs = lineage.withdrawal_from_sentence("R0371", "2002-CE-05-AD, 2002-CE-57-AD", sent(text))
    assert [e.rule_id for e in exs] == ["withdraw.notice"] and exs[0].value["self_notice"] is True


def test_withdraw_notice_not_on_proposal_SYNTHETIC() -> None:
    assert (
        lineage.withdrawal_from_sentence("R1", "D", sent("The FAA proposes to adopt a new AD for X airplanes.")) == []
    )


# ------------------------------------------------------------------ Comments column (REAL, all 5 filled rows)


def test_comments_withdraws_REAL_R0153() -> None:
    exs = lineage.from_comments("R0153", "Withdraws FAA AD NPRM FAA-2024-1884")
    assert [(e.rule_id, e.value["docket"], e.source) for e in exs] == [
        ("comments.withdraws", "FAA-2024-1884", "comments")
    ]


def test_comments_extension_REAL_R0159() -> None:
    text = "On 11/7/2024 the Comment Due Date was extended. The updated Due Date is 12/9/2024."
    exs = lineage.from_comments("R0159", text)
    assert [(e.rule_id, e.value["comments_due"]) for e in exs] == [("comments.extension", "2024-12-09")]
    assert text[exs[0].span_start : exs[0].span_end].endswith("12/9/2024")


@pytest.mark.parametrize(
    ("rid", "text", "base"),
    [
        ("R0166", 'OFR correction, unable to publish NPRM with same docket number. Publishing to DRS as "FAA-2022-1308R1".',
         "FAA-2022-1308"),
        ("R0168", "OFR correction, cannot publish NPRM with duplicate docket number. Publishing in DRS as FAA-2022-1296R1",
         "FAA-2022-1296"),
    ],
    ids=["REAL_R0166", "REAL_R0168"],
)  # fmt: skip
def test_comments_correction_REAL(rid: str, text: str, base: str) -> None:
    exs = lineage.from_comments(rid, text)
    assert [(e.rule_id, e.value["docket"]) for e in exs] == [("comments.correction", base)]


# ------------------------------------------------------------------ the extraction stage on the real DB


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from backend.app.config import repo_path
    from backend.app.ingest.run import ingest

    xlsx = repo_path("raw_xlsx")
    if not xlsx.exists():
        pytest.skip("raw workbook not present (data/raw is git-ignored)")
    db = tmp_path_factory.mktemp("x") / "t.db"
    res = ingest(xlsx, db, write_docs=False)
    return db, res


def test_every_extraction_has_provenance(built) -> None:
    db, _ = built
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT e.source, e.sentence_id, e.span_start, e.span_end, e.rule_id, e.confidence, r.summary, s.start, s.end "
        "FROM extractions e JOIN records r ON r.id = e.record_id LEFT JOIN sentences s ON s.id = e.sentence_id"
    ).fetchall()
    assert rows
    for source, sid, a, b, rule, conf, summary, s_start, s_end in rows:
        assert rule and conf in ("HIGH", "MEDIUM", "LOW")
        if source == "summary":
            assert sid and s_start <= a < b <= s_end and summary[a:b]  # span inside its sentence


def test_supersession_targets_never_claimed_in_dataset(built) -> None:
    db, _ = built
    conn = sqlite3.connect(db)
    bad = conn.execute(
        "SELECT COUNT(*) FROM lineage_edges WHERE relation='supersedes' AND target_in_dataset=1 AND target_record_id IS NULL"
    ).fetchone()[0]
    assert bad == 0


def test_comment_extension_REAL_R0159_and_notice_R0157(built) -> None:
    # REAL: the sheet already carries the extended date for R0159, so original == effective here.
    db, _ = built
    conn = sqlite3.connect(db)
    eff = conn.execute("SELECT comments_due_effective FROM records WHERE id='R0159'").fetchone()[0]
    assert eff == "2024-12-09"
    edges = conn.execute(
        "SELECT src_record, target_record_id FROM lineage_edges WHERE relation='comment_extension' ORDER BY src_record"
    ).fetchall()
    assert ("R0157", "R0159") in edges  # R0157 is the extension notice for the R0159 NPRM


def test_comment_extension_updates_effective_due_date_SYNTHETIC(tmp_path: Path) -> None:
    import pandas as pd

    from backend.app.ingest.loader import EXPECTED_COLUMNS
    from backend.app.ingest.run import ingest

    base = {c: "" for c in EXPECTED_COLUMNS} | {"Docket Number": "FAA-1", "Make": "Boeing", "Page Number": "1",
                                               "Issue Date": "09/10/2024", "Comments Due Date": "11/01/2024",
                                               "Summary": "The FAA proposes an AD for Model 737-8 airplanes."}  # fmt: skip
    row = base | {"Comments": "On 11/7/2024 the Comment Due Date was extended. The updated Due Date is 12/9/2024."}
    xlsx = tmp_path / "s.xlsx"
    pd.DataFrame([row], columns=list(EXPECTED_COLUMNS)).to_excel(xlsx, index=False)
    ingest(xlsx, tmp_path / "s.db", write_docs=False)
    conn = sqlite3.connect(tmp_path / "s.db")
    assert conn.execute("SELECT comments_due_original, comments_due_effective FROM records").fetchone() == (
        "2024-11-01",
        "2024-12-09",
    )
    assert conn.execute("SELECT value_json FROM extractions WHERE field='model'").fetchone()[0].find("737-8") > 0


def test_extension_notice_REAL_R0157() -> None:
    text = "This document announces an extension of the comment period for the referenced NPRM, which proposed to supersede Airworthiness Directive (AD) 2020-26-16."
    exs = lineage.extension_notice_from_sentence("R0157", sent(text))
    assert [(e.field, e.rule_id) for e in exs] == [("comment_extension", "extension.notice")]


def test_vocab_models_and_families(built) -> None:
    db, _ = built
    conn = sqlite3.connect(db)
    kinds = dict(conn.execute("SELECT kind, COUNT(*) FROM vocab GROUP BY kind").fetchall())
    assert kinds["make"] > 0 and kinds["model"] > 0 and kinds["family"] > 0
    fam, aliases, n = conn.execute(
        "SELECT family, aliases_json, record_count FROM vocab WHERE kind='model' AND canonical='A330-243'"
    ).fetchone()
    assert fam == "A330" and n > 0 and json.loads(aliases)


def test_coverage_json_matches_printed_table(built, tmp_path: Path) -> None:
    db, res = built
    copy = tmp_path / "copy.db"
    shutil.copy(db, copy)
    out = tmp_path / "coverage.json"
    again = extract_db(copy, write_docs=False, coverage_path=out)
    report = CoverageReport.model_validate_json(out.read_text(encoding="utf-8"))
    assert report == res.extract.report == again.report  # idempotent re-extraction on the same DB
    table = coverage_table(report)
    for m in report.metrics:
        assert f"{m.numerator:5d} / {m.denominator:<5d}" in table
    assert {m.key for m in report.metrics} >= {"models_extracted", "models_high", "serial_resolved", "svcinfo_defined",
                                               "supersession_edge", "empty_summary", "withdrawn"}  # fmt: skip
