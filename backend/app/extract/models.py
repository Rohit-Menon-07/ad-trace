"""Model designator extraction (rules model.*) plus applicability qualifiers (all.*, qualifier.*).

- model.column (HIGH): Model column split on "|". Tokens without a digit -> model.column.nondesignator (LOW).
- model.summary.list (MEDIUM): "Model(s) <list> <product noun>" in a Summary sentence; list split on commas,
  "and", "or", ";"; parentheticals and the word "series" dropped.
- model.summary.postfix (MEDIUM): "<designators> model <product noun>" (lowercase "model" after the list,
  e.g. "PW210A and PW210S model turboshaft engines"); only tokens that contain a digit.
- model.summary.expanded (MEDIUM): list tokens starting with "-" expanded against the base of the first full
  designator in the same list ("A330-243, -243F" -> A330-243F).
- all.family (MEDIUM): "all ... Model X" sets applies_all_of_family for each family in that list.
- qualifier.certain (MEDIUM): "certain ... Model X" sets qualifier_certain.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from backend.app.extract.types import Extraction, Sent, from_sentence

_DASHES = re.compile(r"[‐‑‒–—―−﹘﹣－]")
_SPACE_DASH = re.compile(r"\s*-\s*")
# Join "AS 365 N2" / "A300 B4" / "AW119 MKII" but not "200 FREIGHTER" or "605R VARIANT F":
# only letter groups of at most 4 characters are glued to an adjacent number.
_LETTER_DIGIT = re.compile(r"(?<![A-Z])([A-Z]{1,4})\s+(?=\d)|(?<=\d)\s+(?=[A-Z]{1,4}(?![A-Z]))")
_TRAILING_WORDS = re.compile(r"(?:\s+(?:SERIES|AIRPLANES?|HELICOPTERS?|ENGINES?|PROPELLERS?|GLIDERS?))+$")
_WS = re.compile(r"\s+")

PRODUCT_NOUNS = (
    "airplanes|airplane|helicopters|helicopter|engines|engine|propellers|propeller|gliders|glider|rotorcraft|"
    "aircraft|balloons|airships|airship|auxiliary power units|APUs"
)
_MODEL_PHRASE = re.compile(
    rf"\bModels?\s+(?P<list>.+?)\s+(?:(?:turbofan|turboprop|turboshaft|turbojet|reciprocating)\s+)?"
    rf"(?P<noun>{PRODUCT_NOUNS})\b",
    re.IGNORECASE,
)
# No inner \d: an ambiguous "[...]*\d[...]*" backtracks catastrophically. Digits are checked in code.
_TOKEN = r"[A-Z0-9][A-Za-z0-9/.+-]*"
_POSTFIX = re.compile(
    rf"(?P<list>{_TOKEN}(?:(?:,\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+){_TOKEN})*)\s+models?\s+"
    rf"(?:(?:turbofan|turboprop|turboshaft|turbojet|reciprocating)\s+)?(?P<noun>{PRODUCT_NOUNS})\b"
)
_SEPARATORS = re.compile(r",\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+|;\s*(?:and\s+)?", re.IGNORECASE)
_PAREN = re.compile(r"\([^()]*\)")
_LEADING = re.compile(r"^(?:Models?\s+)", re.IGNORECASE)
_SERIES_TAIL = re.compile(r"\s+series$", re.IGNORECASE)
_SHORT_TOKEN = re.compile(r"^[-‐-―−]\s*\w")
_ALL = re.compile(r"\ball\b", re.IGNORECASE)
_CERTAIN = re.compile(r"\bcertain\b", re.IGNORECASE)
_MAX_LIST = 700


def norm_model(raw: str) -> str:
    """Uppercase, unify dashes, drop spaces around dashes and between letters/digits, drop 'series'."""
    text = unicodedata.normalize("NFKC", raw).upper().strip()
    text = _DASHES.sub("-", text)
    text = _WS.sub(" ", text)
    text = _TRAILING_WORDS.sub("", text)
    text = _SPACE_DASH.sub("-", text)
    prev = None
    while prev != text:
        prev, text = text, _LETTER_DIGIT.sub(lambda m: m.group(1) or "", text)
    return text.strip(" -")


def family(model: str) -> str:
    """Part before the first hyphen; if that part has no digit (DC, BD, EMB, P) include the next segment."""
    parts = model.split("-")
    if len(parts) > 1 and not any(ch.isdigit() for ch in parts[0]):
        return f"{parts[0]}-{parts[1]}"
    return parts[0]


def _expansion_base(designator: str) -> str | None:
    """'A330-243' -> 'A330'; 'DC-9-81' -> 'DC-9'; no hyphen -> None."""
    return designator.rsplit("-", 1)[0] if "-" in designator else None


_ROMAN_DESIGNATOR = re.compile(r"^[A-Z]{1,4}-[A-Z]{1,4}$|^[A-Z]{2,4}-[A-Z]$")  # G-IV, GIV-X, GV-SP


def is_designator(token: str) -> bool:
    """A normalised token is a designator if it contains a digit, or is a short all-caps hyphenated code."""
    if len(token) > 40:
        return False
    return any(ch.isdigit() for ch in token) or bool(_ROMAN_DESIGNATOR.match(token))


def models_from_column(record_id: str, model_raw: str | None) -> list[Extraction]:
    out: list[Extraction] = []
    for raw in (p.strip() for p in (model_raw or "").split("|")):
        if not raw:
            continue
        model = norm_model(raw)
        if is_designator(model):
            value = {"model": model, "family": family(model), "raw": raw}
            out.append(Extraction(record_id, "model", value, "column", None, None, None, "model.column", "HIGH"))
        else:
            value = {"model": None, "raw": raw}
            out.append(
                Extraction(record_id, "model", value, "column", None, None, None, "model.column.nondesignator", "LOW")
            )
    return out


def _segments(text: str, offset: int) -> Iterable[tuple[str, int, int]]:
    """Split a list into (segment, start, end) with offsets relative to the sentence."""
    pos = 0
    for m in _SEPARATORS.finditer(text):
        yield text[pos : m.start()], offset + pos, offset + m.start()
        pos = m.end()
    yield text[pos:], offset + pos, offset + len(text)


def _clean_segment(seg: str) -> str:
    seg = _PAREN.sub(" ", seg)
    seg = _LEADING.sub("", seg.strip())
    seg = _SERIES_TAIL.sub("", seg.strip())
    return seg.strip(" ,;")


def models_from_sentence(record_id: str, sent: Sent) -> list[Extraction]:
    out: list[Extraction] = []
    for m in _MODEL_PHRASE.finditer(sent.text):
        lst = m.group("list")
        if len(lst) > _MAX_LIST:
            continue
        families: list[str] = []
        base: str | None = None
        expanded = False
        for seg, s, e in _segments(lst, m.start("list")):
            cleaned = _clean_segment(seg)
            if not cleaned:
                continue
            # Trim offsets to the visible token inside the segment.
            lead = len(seg) - len(seg.lstrip())
            s, e = s + lead, s + lead + len(seg.strip())
            if _SHORT_TOKEN.match(cleaned):  # "-243F": expand against the list's base designator
                if base is None:
                    continue
                model, rule = f"{base}-{norm_model(cleaned)}", "model.summary.expanded"
            else:
                model, rule = norm_model(cleaned), "model.summary.list"
                if base is None:
                    base = _expansion_base(model)
            if not is_designator(model):
                continue
            confidence = "MEDIUM"
            if rule == "model.summary.list" and base and model[0].isdigit() and "-" not in model and expanded:
                # e.g. "737-600, -700, ... and 900ER": a suffix missing its dash. Never guessed; flagged LOW.
                rule, confidence = "model.summary.orphan_suffix", "LOW"
            expanded = expanded or rule == "model.summary.expanded"
            fam = family(model)
            families.append(fam)
            value = {"model": model, "family": fam, "raw": sent.text[s:e], "product": m.group("noun").lower()}
            out.append(from_sentence(record_id, sent, s, e, "model", value, rule, confidence))
        if not families:
            continue
        # Qualifiers look at the clause before "Model" (from the previous ';' or the sentence start).
        semi = sent.text.rfind(";", 0, m.start())
        clause_start = semi + 1 if semi >= 0 else 0
        prefix = sent.text[clause_start : m.start()]
        if _ALL.search(prefix):
            a = _ALL.search(prefix)
            assert a is not None
            for fam in dict.fromkeys(families):
                out.append(
                    from_sentence(
                        record_id, sent, clause_start + a.start(), m.end(), "applies_all_of_family",
                        {"family": fam, "value": True}, "all.family", "MEDIUM",
                    )
                )  # fmt: skip
        c = _CERTAIN.search(prefix)
        if c:
            out.append(
                from_sentence(
                    record_id, sent, clause_start + c.start(), m.end(), "qualifier_certain", {"value": True},
                    "qualifier.certain", "MEDIUM",
                )
            )  # fmt: skip
    out += _postfix_models(record_id, sent)
    return out


def _postfix_models(record_id: str, sent: Sent) -> list[Extraction]:
    out: list[Extraction] = []
    for m in _POSTFIX.finditer(sent.text):
        for seg, s, e in _segments(m.group("list"), m.start("list")):
            model = norm_model(seg)
            if not model or not any(ch.isdigit() for ch in model):
                continue
            value = {"model": model, "family": family(model), "raw": sent.text[s:e], "product": m.group("noun").lower()}
            out.append(from_sentence(record_id, sent, s, e, "model", value, "model.summary.postfix", "MEDIUM"))
    return out


def dedupe_models(extractions: list[Extraction]) -> list[Extraction]:
    """Keep the first extraction per (field, source, value); later repeats in other sentences are dropped."""
    seen: set[tuple[str, str, str]] = set()
    out: list[Extraction] = []
    for e in extractions:
        key = (e.field, e.source, repr(sorted(e.value.items())) if e.field != "model" else str(e.value.get("model")))
        if e.field == "qualifier_certain":
            key = (e.field, e.source, "")
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
