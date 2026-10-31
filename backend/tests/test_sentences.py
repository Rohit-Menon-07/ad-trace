import json
from pathlib import Path

import pytest

from backend.app.ingest.sentences import sentence_id, split_sentences

REAL = json.loads((Path(__file__).parent / "fixtures" / "real_summaries.json").read_text(encoding="utf-8"))["cases"]


def texts(summary: str) -> list[str]:
    return [s.text for s in split_sentences(summary)]


def assert_offsets(summary: str) -> None:
    spans = split_sentences(summary)
    for s in spans:
        assert summary[s.start : s.end] == s.text
    assert [s.idx for s in spans] == list(range(1, len(spans) + 1))


# ---- REAL summaries from the workbook (11 cases) ----


@pytest.mark.parametrize("case", REAL, ids=[f"REAL-{c['record_id']}" for c in REAL])
def test_real_summary_splits(case: dict) -> None:
    assert texts(case["summary"]) == case["expected"], case["why"]
    assert_offsets(case["summary"])


# ---- SYNTHETIC cases (invented text, named SYNTHETIC) ----

SYNTHETIC = [
    (
        "SYNTHETIC model designator ends a sentence",
        "This applies to Airbus SAS Model A330-243. This proposed AD would require an inspection.",
        ["This applies to Airbus SAS Model A330-243.", "This proposed AD would require an inspection."],
    ),
    (
        "SYNTHETIC AD number ends a sentence",
        "The FAA proposes to supersede AD 2025-09-07. AD 2025-09-07 requires a test.",
        ["The FAA proposes to supersede AD 2025-09-07.", "AD 2025-09-07 requires a test."],
    ),
    (
        "SYNTHETIC parenthesised acronym then sentence end",
        "Revise the minimum equipment list (MEL). The FAA is proposing this AD.",
        ["Revise the minimum equipment list (MEL).", "The FAA is proposing this AD."],
    ),
    (
        "SYNTHETIC period inside parentheses is not a boundary",
        "Certain parts (e.g. P/N 123. Rev A) are affected. Replace them.",
        ["Certain parts (e.g. P/N 123. Rev A) are affected.", "Replace them."],
    ),
    (
        "SYNTHETIC e.g. and i.e. mid-sentence",
        "Some operators, e.g. Operator A, and some parts, i.e. Pumps, are affected. This is new.",
        ["Some operators, e.g. Operator A, and some parts, i.e. Pumps, are affected.", "This is new."],
    ),
    (
        "SYNTHETIC Inc. as a real sentence end before a strong starter",
        "The design approval is held by Textron Inc. This proposed AD would require a check.",
        ["The design approval is held by Textron Inc.", "This proposed AD would require a check."],
    ),
    (
        "SYNTHETIC Ltd. and Co. mid-sentence before a capitalised name",
        "Made by Example Ltd. Model X and Example Co. Model Y airplanes are affected.",
        ["Made by Example Ltd. Model X and Example Co. Model Y airplanes are affected."],
    ),
    (
        "SYNTHETIC No. followed by a digit",
        "Replace the No. 2 engine bearing. Then test it.",
        ["Replace the No. 2 engine bearing.", "Then test it."],
    ),
    (
        "SYNTHETIC U.S. before a capitalised word",
        "This affects U.S. Registered airplanes only. Comments are due soon.",
        ["This affects U.S. Registered airplanes only.", "Comments are due soon."],
    ),
    (
        "SYNTHETIC unbalanced parenthesis does not swallow later boundaries",
        "A stray ( bracket appears here. This is sentence two. This is three.",
        ["A stray ( bracket appears here.", "This is sentence two.", "This is three."],
    ),
    (
        "SYNTHETIC closing quote after period",
        'Install "INOP" placards." The FAA agrees.',
        ['Install "INOP" placards."', "The FAA agrees."],
    ),
    (
        "SYNTHETIC no terminal punctuation and question mark",
        "Is this affected? The final sentence has no period",
        ["Is this affected?", "The final sentence has no period"],
    ),
    (
        "SYNTHETIC decimals and lowercase continuation",
        "Use 3.5 mm shims. version 2 follows. Done.",
        ["Use 3.5 mm shims. version 2 follows.", "Done."],
    ),
]


@pytest.mark.parametrize(("name", "summary", "expected"), SYNTHETIC, ids=[s[0] for s in SYNTHETIC])
def test_synthetic_splits(name: str, summary: str, expected: list[str]) -> None:
    assert texts(summary) == expected, name
    assert_offsets(summary)


def test_empty_and_none() -> None:
    assert split_sentences(None) == []
    assert split_sentences("") == []


def test_sentence_ids_are_one_based() -> None:
    spans = split_sentences("One. Two.")
    assert [sentence_id("R0001", s.idx) for s in spans] == ["R0001#s1", "R0001#s2"]
