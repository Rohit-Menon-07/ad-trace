"""Make canonicalisation: normalised-key merging, explicit rules, and hard never-merge guards.

Rules (Prompt 3, DECISIONS.md):
- Raw makes whose normalised keys are equal are merged (lowercase, punctuation -> space, drop STOPWORDS).
- Plain "Airbus" becomes "Airbus SAS" only on rows whose Subject Heading contains "Airbus SAS".
- Airbus Helicopters* and Airbus Canada* never become Airbus SAS; McDonnell Douglas never becomes Boeing.
- Renames and spelling variants of the SAME legal entity are merged via EXPLICIT (reason logged per key).
- make_family groups DISTINCT legal entities of one manufacturer (FAMILY_PREFIXES, e.g. all Airbus,
  Gulfstream, Rolls-Royce, Pratt & Whitney, Bell, Textron Aviation/Cessna); otherwise family = canonical.
- Cells listing several makes ("A | B") are split; each part is canonicalised separately.
Everything else stays separate. Near-miss names are listed in docs/make_audit.md for human review.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

STOPWORDS = frozenset({"the", "inc", "ltd", "limited", "company", "co", "kg", "corporation", "llc"})
MULTI_SEPARATOR = " | "

# Normalised key -> (canonical, reason). Applied before frequency-based naming.
EXPLICIT: dict[str, tuple[str, str]] = {
    "boeing": ("The Boeing Company", 'Instructed merge: "Boeing" and "The Boeing Company" are the same entity.'),
    "airbus helicopters deutschland gmbh ahd": (
        "Airbus Helicopters Deutschland GmbH",
        'Same name plus the parenthetical abbreviation "(AHD)".',
    ),
    "erickson air crane incorporated dba erickson air crane": (
        "Erickson Air-Crane Incorporated",
        'Same company; "DBA Erickson Air-Crane" is a trading-name suffix.',
    ),
    # Data-ambiguity fixes (DECISIONS.md 149): same legal entity, different spelling or a later name.
    "embraer s a": ("Embraer", '"Embraer S.A." is the legal form of "Embraer"; same TC holder.'),
    "cessna aircraft": ("Cessna", '"Cessna Aircraft Company" and "Cessna" are the same TC holder.'),
    "piper": ("Piper Aircraft, Inc.", '"Piper" is the short form of "Piper Aircraft, Inc.".'),
    "bell helicopter textron": ("Bell Textron, Inc.", "Bell Helicopter Textron Inc. was renamed Bell Textron Inc."),
    "bell helicopter textron canada": (
        "Bell Textron Canada Limited",
        "Bell Helicopter Textron Canada Limited was renamed Bell Textron Canada Limited.",
    ),
    "pratt whitney division": ("Pratt & Whitney", '"Pratt & Whitney Division" is the same US TC holder.'),
    "pratt whitney rtx formerly united technologies": (
        "Pratt & Whitney",
        "Same US TC holder; the cell spells out the parent company (RTX, formerly United Technologies).",
    ),
    "general electric ge aerospace": (
        "General Electric Company",
        '"GE Aerospace" is the trading name of General Electric Company.',
    ),
    "eurocopter france": ("Airbus Helicopters", "Eurocopter France was renamed Airbus Helicopters (2014)."),
    "eurocopter deutschland gmbh": (
        "Airbus Helicopters Deutschland GmbH",
        "Eurocopter Deutschland GmbH was renamed Airbus Helicopters Deutschland GmbH (2014).",
    ),
}

# Normalised-key prefix -> family. Distinct legal entities of one manufacturer share a family (not merged):
# the engine treats a same-family make as "same" and lets the model check decide.
FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("airbus", "Airbus"),
    ("eurocopter", "Airbus"),
    ("gulfstream", "Gulfstream"),
    ("rolls royce", "Rolls-Royce"),
    ("pratt whitney", "Pratt & Whitney"),
    ("bell textron", "Bell"),
    ("cessna", "Textron Aviation"),
    ("textron aviation", "Textron Aviation"),
    ("bae systems", "BAE Systems"),
)

AIRBUS_PLAIN_KEY = "airbus"
AIRBUS_SAS = "Airbus SAS"

# (normalised-key prefix, canonical it must never map to)
NEVER_MERGE: tuple[tuple[str, str], ...] = (
    ("airbus helicopters", AIRBUS_SAS),
    ("airbus canada", AIRBUS_SAS),
    ("mcdonnell douglas", "The Boeing Company"),
)

_NON_ALNUM = re.compile(r"[^\w]+|_")


def normalise_key(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw).lower()
    tokens = [t for t in _NON_ALNUM.sub(" ", text).split() if t not in STOPWORDS]
    return " ".join(tokens)


def split_makes(cell: str | None) -> list[str]:
    """'A | B' -> ['A', 'B']; None/empty -> []."""
    if not cell:
        return []
    return [p.strip() for p in cell.split("|") if p.strip()]


def make_family(canonical: str) -> str:
    key = normalise_key(canonical)
    for prefix, family in FAMILY_PREFIXES:
        if key == prefix or key.startswith(prefix + " "):
            return family
    return canonical


@dataclass(frozen=True)
class AliasEntry:
    raw: str
    count: int  # rows whose Make cell contains this raw name
    key: str
    canonical: str
    family: str
    rule: str  # explicit | normalised_key | conditional_subject | unique
    reason: str


def build_alias_map(raw_counts: Counter[str]) -> dict[str, AliasEntry]:
    """Map every distinct raw make name to its canonical name with a reason."""
    by_key: dict[str, list[str]] = {}
    for raw in raw_counts:
        by_key.setdefault(normalise_key(raw), []).append(raw)

    out: dict[str, AliasEntry] = {}
    for key, raws in by_key.items():
        if key in EXPLICIT:
            canonical, reason = EXPLICIT[key]
            rule = "explicit"
        else:
            # Display name = most frequent raw spelling; ties -> longest, then alphabetical.
            canonical = sorted(raws, key=lambda r: (-raw_counts[r], -len(r), r))[0]
            if len(raws) > 1:
                rule = "normalised_key"
                reason = f'Spellings differ only in case/punctuation/legal suffix (key "{key}").'
            else:
                rule, reason = "unique", "Only spelling of this name; kept as is."
        if key == AIRBUS_PLAIN_KEY:
            rule = "conditional_subject"
            reason = (
                'Plain "Airbus" becomes "Airbus SAS" only on rows whose Subject Heading contains "Airbus SAS"; '
                'otherwise it stays "Airbus" (family Airbus).'
            )
        for raw in raws:
            out[raw] = AliasEntry(raw, raw_counts[raw], key, canonical, make_family(canonical), rule, reason)
    check_never_merge(out)
    return out


def check_never_merge(alias: dict[str, AliasEntry]) -> None:
    for entry in alias.values():
        for prefix, forbidden in NEVER_MERGE:
            if entry.key.startswith(prefix) and entry.canonical == forbidden:
                raise ValueError(f"Forbidden merge: {entry.raw!r} -> {forbidden!r}")


def canonicalise(cell: str | None, subject: str | None, alias: dict[str, AliasEntry]) -> list[str]:
    """Canonical makes for one row (deduplicated, original order). Raises on an unmapped raw make."""
    out: list[str] = []
    for raw in split_makes(cell):
        entry = alias.get(raw)
        if entry is None:
            raise KeyError(f"Make {raw!r} missing from alias map")
        canonical = entry.canonical
        if entry.rule == "conditional_subject":
            canonical = AIRBUS_SAS if subject and AIRBUS_SAS in subject else entry.canonical
        if canonical not in out:
            out.append(canonical)
    return out


def candidate_merges(alias: dict[str, AliasEntry]) -> list[tuple[str, str]]:
    """Distinct canonicals sharing their first key token: possible same-entity pairs NOT merged."""
    canon_keys = sorted({(e.canonical, normalise_key(e.canonical)) for e in alias.values()})
    pairs: list[tuple[str, str]] = []
    for i, (a, ka) in enumerate(canon_keys):
        for b, kb in canon_keys[i + 1 :]:
            if ka.split()[:1] == kb.split()[:1] and make_family(a) != make_family(b):
                pairs.append((a, b))
    return pairs
