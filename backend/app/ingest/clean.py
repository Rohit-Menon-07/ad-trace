"""Text and date cleaning primitives. Pure functions; no guessing."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

_WS = re.compile(r"\s+")
# The export contains literal two-character backslash-n sequences inside 17 summaries.
_LITERAL_ESCAPES = re.compile(r"\\[nrt]")
_MDY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def clean_text(value: object) -> str | None:
    """NFKC-normalise, turn literal backslash escapes (\\n, \\r, \\t) into spaces, collapse whitespace, trim.

    Empty -> None.
    """
    if value is None or (isinstance(value, float) and value != value):  # NaN from pandas
        return None
    text = _LITERAL_ESCAPES.sub(" ", unicodedata.normalize("NFKC", str(value)))
    text = _WS.sub(" ", text).strip()
    return text or None


def parse_mdy(value: str | None) -> date | None:
    """Parse a strict MM/DD/YYYY (1- or 2-digit month/day) date. Anything else -> None, never guessed."""
    if not value:
        return None
    m = _MDY.fullmatch(value.strip())
    if not m:
        return None
    month, day, year = (int(g) for g in m.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


_PAGES = re.compile(r"(\d+)(?:\s*-\s*(\d+))?")
_FR_VOLUME = re.compile(r"Volume\s+(\d+)", re.IGNORECASE)


def parse_pages(value: str | None) -> str | None:
    """'(Pages 66019-66022)' -> '66019-66022'; 'Page 16330' -> '16330'. Unparseable -> None."""
    if not value:
        return None
    m = _PAGES.search(value)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)


def fr_citation(citation: str | None, pages: str | None) -> str | None:
    """'Federal Register, Volume 91 ...' + '66019-66022' -> '91 FR 66019'. Needs both parts, else None."""
    if not citation or not pages:
        return None
    m = _FR_VOLUME.search(citation)
    return f"{m.group(1)} FR {pages.split('-')[0]}" if m else None
