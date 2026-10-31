from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backend.app.config import repo_path
from backend.app.ingest.clean import clean_text, fr_citation, parse_mdy, parse_pages
from backend.app.ingest.db import dump_tables
from backend.app.ingest.duplicates import Row, classify_group
from backend.app.ingest.loader import EXPECTED_COLUMNS, raw_name, row_hash
from backend.app.ingest.makes import (
    AIRBUS_SAS,
    build_alias_map,
    candidate_merges,
    canonicalise,
    check_never_merge,
    make_family,
    normalise_key,
)
from backend.app.ingest.run import ingest

REAL_XLSX = repo_path("raw_xlsx")
needs_real = pytest.mark.skipif(not REAL_XLSX.exists(), reason="raw workbook not present (data/raw is git-ignored)")

# ---- cleaning and dates ----


def test_clean_text_nfkc_whitespace_and_literal_escapes() -> None:
    assert clean_text("  A  B\n\nC \\nD  ") == "A B C D"
    assert clean_text("ﬁle") == "file"  # NFKC ligature
    assert clean_text("   ") is None
    assert clean_text(float("nan")) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10/15/2026", date(2026, 10, 15)),
        ("1/5/2024", date(2024, 1, 5)),
        (" 12/09/2024 ", date(2024, 12, 9)),
        ("2026-10-15", None),
        ("13/01/2026", None),
        ("02/30/2026", None),
        ("10/15/26", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_mdy_strict_never_guesses(raw: str | None, expected: date | None) -> None:
    assert parse_mdy(raw) == expected


def test_pages_and_fr_citation() -> None:
    assert parse_pages("(Pages 66019-66022)") == "66019-66022"
    assert parse_pages("Page 16330") == "16330"
    assert fr_citation("Federal Register, Volume 91 Number 200 (Monday, October 19, 2026)", "66019-66022") == (
        "91 FR 66019"
    )
    assert fr_citation("Federal Register: July 21, 2010", "42340-42342") is None  # no volume: never derived


def test_raw_name_and_row_hash_stable() -> None:
    assert raw_name("Link for Submitting Public Comment") == "raw_link_for_submitting_public_comment"
    assert raw_name("Service/Office") == "raw_service_office"
    raw = {c: None for c in EXPECTED_COLUMNS} | {"Docket Number": "FAA-1"}
    assert row_hash(raw) == row_hash(dict(raw))
    assert row_hash(raw) != row_hash(raw | {"Summary": "x"})


# ---- make alias map ----

NAMES = Counter(
    {
        "The Boeing Company": 75,
        "Boeing": 32,
        "McDonnell Douglas": 15,
        "Airbus SAS": 29,
        "Airbus": 15,
        "Airbus Helicopters": 16,
        "Airbus Canada Limited Partnership": 9,
        "Airbus Helicopters Deutschland GmbH (AHD)": 6,
        "Airbus Helicopters Deutschland GmbH": 3,
        "Bombardier Inc.": 12,
        "Bombardier, Inc.": 3,
        "Leonardo S.p.a.": 3,
        "Leonardo S.p.A.": 2,
        "Embraer": 24,
        "Embraer S.A.": 2,
    }
)


@pytest.fixture(scope="module")
def alias():
    return build_alias_map(NAMES)


def test_normalise_key_drops_stopwords_and_punctuation() -> None:
    assert normalise_key("The Boeing Company") == "boeing"
    assert normalise_key("Bombardier, Inc.") == "bombardier"
    assert normalise_key("Rolls-Royce Deutschland Ltd & Co KG") == "rolls royce deutschland"


def test_boeing_merged_mcdonnell_separate(alias) -> None:
    assert alias["Boeing"].canonical == alias["The Boeing Company"].canonical == "The Boeing Company"
    assert alias["McDonnell Douglas"].canonical == "McDonnell Douglas"
    assert alias["McDonnell Douglas"].family == "McDonnell Douglas"


def test_normalised_spellings_merge_to_most_frequent(alias) -> None:
    assert alias["Bombardier, Inc."].canonical == "Bombardier Inc."
    assert alias["Leonardo S.p.A."].canonical == "Leonardo S.p.a."
    assert alias["Embraer S.A."].canonical == "Embraer"  # explicit rule: legal form of the same TC holder


def test_renamed_entities_merge_and_distinct_entities_share_family() -> None:
    names = Counter({"Eurocopter France": 4, "Airbus Helicopters": 17, "Bell Helicopter Textron": 4,
                     "Bell Textron, Inc.": 1, "Gulfstream Aerospace LP": 8, "Gulfstream Aerospace Corporation": 8,
                     "Scotts-Bell 47 Inc.": 1, "Cessna Aircraft Company": 3, "Textron Aviation Inc.": 3})  # fmt: skip
    a = build_alias_map(names)
    assert a["Eurocopter France"].canonical == "Airbus Helicopters" and a["Eurocopter France"].family == "Airbus"
    assert a["Bell Helicopter Textron"].canonical == "Bell Textron, Inc."
    lp, corp = a["Gulfstream Aerospace LP"], a["Gulfstream Aerospace Corporation"]
    assert lp.canonical != corp.canonical and lp.family == corp.family == "Gulfstream"
    assert a["Scotts-Bell 47 Inc."].family == "Scotts-Bell 47 Inc."  # different company, no shared family
    assert a["Cessna Aircraft Company"].family == a["Textron Aviation Inc."].family == "Textron Aviation"
    assert candidate_merges(a) == []  # same-family pairs are not listed as candidate merges


def test_airbus_conditional_on_subject_heading(alias) -> None:
    assert canonicalise("Airbus", "Airworthiness Directives; Airbus SAS Airplanes", alias) == [AIRBUS_SAS]
    assert canonicalise("Airbus", "Airworthiness Directives; Airbus Airplanes", alias) == ["Airbus"]


def test_airbus_helicopters_and_canada_never_airbus_sas(alias) -> None:
    for raw in ("Airbus Helicopters", "Airbus Canada Limited Partnership", "Airbus Helicopters Deutschland GmbH"):
        assert alias[raw].canonical != AIRBUS_SAS
        assert alias[raw].family == "Airbus"
    assert alias["Airbus Helicopters Deutschland GmbH (AHD)"].canonical == "Airbus Helicopters Deutschland GmbH"


def test_never_merge_guard_raises(alias) -> None:
    bad = dict(alias)
    bad["McDonnell Douglas"] = alias["McDonnell Douglas"].__class__(
        "McDonnell Douglas", 1, "mcdonnell douglas", "The Boeing Company", "The Boeing Company", "x", "x"
    )
    with pytest.raises(ValueError):
        check_never_merge(bad)


def test_multi_make_cell_is_split(alias) -> None:
    assert canonicalise("Boeing | McDonnell Douglas | The Boeing Company", None, alias) == [
        "The Boeing Company",
        "McDonnell Douglas",
    ]
    with pytest.raises(KeyError):
        canonicalise("Unknown Maker", None, alias)


def test_make_family() -> None:
    assert make_family("Airbus Canada Limited Partnership") == "Airbus"
    assert make_family("Embraer") == "Embraer"
    assert make_family("Rolls-Royce plc") == make_family("Rolls-Royce Corporation") == "Rolls-Royce"
    assert make_family("Pratt & Whitney Canada Corp.") == "Pratt & Whitney"


# ---- duplicate-docket classification ----


def _row(rid: str, docket: str = "FAA-1", makes=("A",), model=None, summary="s", issued=date(2020, 1, 1), cmt=None):
    return Row(rid, docket, issued, list(makes), model, cmt, ("make", model, "subj", summary))


def test_exact_duplicate_keeps_earliest() -> None:
    g = classify_group("FAA-1", [_row("R2", issued=date(2021, 1, 1)), _row("R1", issued=date(2011, 1, 1))])
    assert g.cls == "exact_duplicate" and g.duplicate_of == {"R2": "R1"}


def test_multi_product_and_revision_series() -> None:
    assert classify_group("FAA-1", [_row("R1", makes=("A",)), _row("R2", makes=("B",), summary="t")]).cls == (
        "multi_product"
    )
    assert classify_group("FAA-1", [_row("R1", model="X"), _row("R2", model="Y", summary="t")]).cls == "multi_product"
    # One multi-make row repeated across a revision is not multi-product.
    ab = ("A", "B")
    assert classify_group("FAA-1", [_row("R1", makes=ab), _row("R2", makes=ab, summary="t")]).cls == "revision_series"
    assert classify_group("FAA-1", [_row("R1"), _row("R2", model="X", summary="t")]).cls == "revision_series"


def test_correction_by_suffix_or_comment() -> None:
    assert classify_group("FAA-2022-1308R1", [_row("R1", docket="FAA-2022-1308R1")]).cls == "correction"
    assert classify_group("FAA-9", [_row("R1", docket="FAA-9", cmt="OFR correction, unable to publish")]).cls == (
        "correction"
    )


# ---- end-to-end on a SYNTHETIC workbook (runs without the real file) ----


def _synthetic_xlsx(path: Path) -> Path:
    rows = []
    base = {c: "" for c in EXPECTED_COLUMNS} | {"Status": "Current", "Citation": "Federal Register, Volume 91"}
    rows.append(
        base
        | {
            "Docket Number": "FAA-1",
            "Make": "Boeing",
            "Issue Date": "01/02/2026",
            "Page Number": "1",
            "Summary": "The FAA proposes an AD for Model 737-8. This AD would require a test.",
        }
    )
    rows.append(
        base
        | {
            "Docket Number": "FAA-1",
            "Make": "The Boeing Company",
            "Issue Date": "02/30/2026",
            "Page Number": "2",
            "Summary": "The FAA withdraws the NPRM.",
        }
    )
    rows.append(base | {"Docket Number": "FAA-2", "Make": "Airbus", "Subject Heading": "AD; Airbus SAS Airplanes",
                        "Issue Date": "03/04/2026", "Page Number": "3", "Summary": "   "})  # fmt: skip
    pd.DataFrame(rows, columns=list(EXPECTED_COLUMNS)).to_excel(path, index=False)
    return path


def test_synthetic_ingest_end_to_end_and_idempotent(tmp_path: Path) -> None:
    xlsx = _synthetic_xlsx(tmp_path / "synthetic.xlsx")
    db = tmp_path / "out.db"
    res = ingest(xlsx, db, write_docs=False)
    first = dump_tables(db)
    ingest(xlsx, db, write_docs=False)
    assert dump_tables(db) == first

    recs = {r["id"]: r for r in res.load.records}
    assert list(recs) == ["R0001", "R0002", "R0003"]
    assert recs["R0001"]["make_canonical"] == recs["R0002"]["make_canonical"] == "The Boeing Company"
    assert recs["R0003"]["make_canonical"] == AIRBUS_SAS and recs["R0003"]["make_family"] == "Airbus"
    assert recs["R0002"]["issue_date"] is None  # 02/30 is unparseable -> null, logged
    assert [(i.record_id, i.raw) for i in res.load.date_issues] == [("R0002", "02/30/2026")]
    assert recs["R0003"]["summary_missing"] is True and recs["R0003"]["summary"] is None
    assert all(r["status_label"] == "PROPOSED" for r in recs.values())
    assert recs["R0001"]["raw_make"] == "Boeing"  # raw kept untouched
    assert [s["id"] for s in res.sentences] == ["R0001#s1", "R0001#s2", "R0002#s1"]


# ---- the real workbook (skipped when data/raw is absent) ----


@needs_real
def test_real_workbook_ingest(tmp_path: Path) -> None:
    db = tmp_path / "real.db"
    res = ingest(REAL_XLSX, db, write_docs=False)
    recs = res.load.records
    assert len(recs) == 431
    assert len({r["docket"] for r in recs}) == 323
    assert len(res.cell_counts) == 91
    by_id = {r["id"]: r for r in recs}
    for s in res.sentences:
        assert by_id[s["record_id"]]["summary"][s["start"] : s["end"]] == s["text"]
    assert all(r["status_label"] == "PROPOSED" for r in recs)
    assert not res.load.date_issues
    first = dump_tables(db)
    ingest(REAL_XLSX, db, write_docs=False)
    assert dump_tables(db) == first
