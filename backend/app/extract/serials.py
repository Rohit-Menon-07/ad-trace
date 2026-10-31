"""Serial-number constraints (rules serial.*) and service-information applicability (svcinfo.*).

Dataset reality (Prompt 4 profiling): no Summary in the workbook states an explicit serial range or list;
summaries only say "certain serial numbers". These rules therefore fire on nothing real today and are
covered by SYNTHETIC tests plus REAL negative tests. They never invent ranges.

- serial.range (HIGH): "<intro> X through|to|thru Y" -> inclusive range.
- serial.list (HIGH): "<intro> X, Y, and Z" -> list.
- Either is marked excluded=True when preceded by "except" / "excluding".
- svcinfo.defined (MEDIUM): products "identified/listed/specified in" service information / a service bulletin,
  only when no serial range or list was parsed for the record.
"""

from __future__ import annotations

import re
from typing import Any

from backend.app.extract.types import Extraction, Sent, from_sentence

_INTRO = (
    r"(?P<kind>manufacturer\s+serial\s+numbers?|serial\s+numbers?|S/Ns?|MSNs?|line\s+numbers?)"
    r"(?:\s*\((?:MSNs?|S/Ns?)\))?\s*"
)
_SERIAL = r"[A-Z]{0,4}-?\d+[A-Z]?"
_RANGE = re.compile(rf"{_INTRO}(?P<a>{_SERIAL})\s+(?:through|thru|to)\s+(?P<b>{_SERIAL})(?:\s+inclusive)?\b")
_LIST = re.compile(rf"{_INTRO}(?P<items>{_SERIAL}(?:\s*,\s*(?:and\s+)?{_SERIAL}|\s+and\s+{_SERIAL})*)\b")
_ITEM = re.compile(_SERIAL)
_EXCLUDE = re.compile(r"\b(?:except|excluding)\b(?:\s+(?:for|those|with|airplanes|having)){0,3}\s*$", re.IGNORECASE)
_PREFIX_NUM = re.compile(r"^(?P<prefix>[A-Z]*-?)(?P<num>\d+)(?P<suffix>[A-Z]?)$")

_SVCINFO = re.compile(
    r"\b(?:airplanes|helicopters|engines|propellers|products|aircraft|rotorcraft|units|serial\s+numbers)\b"
    r"(?:\s+\w+){0,4}?\s+(?:are\s+|is\s+)?(?:as\s+)?(?:identified|listed|specified)\s+in\s+"
    r"(?:the\s+|a\s+|an\s+)?(?:\w+\s+){0,4}?(?:service\s+(?:information|bulletins?|letters?)|SBs?)\b",
    re.IGNORECASE,
)


def _kind(raw: str) -> str:
    low = raw.lower()
    if low.startswith("line"):
        return "line_number"
    if low.startswith(("msn", "manufacturer")):
        return "msn"
    return "serial_number"


def parse_serial(token: str) -> dict[str, Any]:
    """'S-1000' -> prefix 'S-', number 1000. Compare by prefix, then number."""
    m = _PREFIX_NUM.match(token)
    if not m:
        return {"raw": token, "prefix": None, "number": None}
    return {"raw": token, "prefix": m.group("prefix"), "number": int(m.group("num")), "suffix": m.group("suffix")}


def serial_in_range(serial: str, start: str, end: str) -> bool | None:
    """True/False when comparable (same prefix), else None (cannot decide)."""
    s, a, b = parse_serial(serial), parse_serial(start), parse_serial(end)
    if None in (s["number"], a["number"], b["number"]) or not (s["prefix"] == a["prefix"] == b["prefix"]):
        return None
    return a["number"] <= s["number"] <= b["number"]


def _excluded(text: str, start: int) -> bool:
    return bool(_EXCLUDE.search(text[max(0, start - 40) : start]))


def serials_from_sentence(record_id: str, sent: Sent) -> list[Extraction]:
    out: list[Extraction] = []
    used: list[tuple[int, int]] = []
    for m in _RANGE.finditer(sent.text):
        a, b = m.group("a"), m.group("b")
        pa, pb = parse_serial(a), parse_serial(b)
        value = {
            "start": a,
            "end": b,
            "numeric": a.isdigit() and b.isdigit(),
            "prefix": pa["prefix"] if pa["prefix"] == pb["prefix"] else None,
            "kind": _kind(m.group("kind")),
            "excluded": _excluded(sent.text, m.start()),
        }
        out.append(from_sentence(record_id, sent, m.start(), m.end(), "serial_range", value, "serial.range", "HIGH"))
        used.append((m.start(), m.end()))
    for m in _LIST.finditer(sent.text):
        if any(s <= m.start() < e for s, e in used):
            continue
        items = _ITEM.findall(m.group("items"))
        value = {"serials": items, "kind": _kind(m.group("kind")), "excluded": _excluded(sent.text, m.start())}
        out.append(from_sentence(record_id, sent, m.start(), m.end(), "serial_list", value, "serial.list", "HIGH"))
    return out


def svcinfo_from_sentence(record_id: str, sent: Sent) -> list[Extraction]:
    m = _SVCINFO.search(sent.text)
    if not m:
        return []
    value = {"value": True}
    field = "applicability_defined_by_service_info"
    return [from_sentence(record_id, sent, m.start(), m.end(), field, value, "svcinfo.defined", "MEDIUM")]
