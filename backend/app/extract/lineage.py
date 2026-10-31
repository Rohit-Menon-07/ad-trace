"""Supersession, continuation, applicability change, withdrawal, comment extension and correction rules.

Summary rules (offsets into the Summary):
- supersede.ad (HIGH): every AD number between "supersede/supersedure/superseding/superseded" and the end of
  the clause (", which" / "which" / sentence end). "not to supersede" is skipped (rule supersede.negated).
- supersede.unnumbered (LOW): supersession wording with no AD number ("an existing AD"); no lineage edge.
- continue.actions (HIGH): "continue to require ... AD X". continue.retain (MEDIUM): "retain ... from AD X".
- applicability.reduced / applicability.expanded (HIGH): "reduce(s)/expand(s) the applicability".
  applicability.add / applicability.remove (MEDIUM): "add ... to the ... applicability" / "remove ... from the
  applicability".
- withdraw.notice (HIGH): the record itself withdraws an NPRM ("withdraws/is withdrawing ... NPRM").
- extension.notice (HIGH): the record itself extends/reopens the comment period of the NPRM in its docket.
Comments rules (offsets into the Comments text):
- comments.withdraws (HIGH): "Withdraws FAA AD NPRM <docket>".
- comments.extension (HIGH): "Comment Due Date was extended. The updated Due Date is M/D/YYYY".
- comments.correction (HIGH): "publishing ... as <docket>R<n>" -> correction_of the base docket.
AD numbers tolerate PDF artifacts such as "AD 2024- 05-13" and are normalised to "2024-05-13".
"""

from __future__ import annotations

import re
from datetime import date

from backend.app.extract.types import Extraction, Sent, from_sentence
from backend.app.ingest.clean import parse_mdy

AD_NUMBER = re.compile(
    r"(?i:\bAD|\bADs|\bairworthiness\s+directives?\s+\(ADs?\))\s+(\d{2,4}\s?-\s?\d{2}\s?-\s?\d{2,3}(?:\s+R\d+)?)"
)
_BARE_AD = re.compile(r"(?<![\d-])(\d{2,4}\s?-\s?\d{2}\s?-\s?\d{2,3}(?:\s+R\d+)?)(?![\d-])")
_SUPERSEDE = re.compile(r"\bsupersed(?:e|es|ed|ing|ure)\b", re.IGNORECASE)
_NEGATED = re.compile(r"\bnot\s+to\s+$", re.IGNORECASE)
_CLAUSE_END = re.compile(r",?\s+which\b|;|\bbecause\b", re.IGNORECASE)
_CONTINUE = re.compile(r"\bcontinue\s+to\s+require\b", re.IGNORECASE)
_RETAIN = re.compile(r"\bretain\w*\b[^.;]{0,120}?\b(?:from|in|of)\s+AD\b", re.IGNORECASE)
_CONT_END = re.compile(r"\s+and\s+(?:would|to|also)\b|;|,\s+(?:would|and)\b", re.IGNORECASE)
_APPL = re.compile(r"\b(?P<verb>reduces?|reducing|expands?|expanding)\s+the\s+applicability\b", re.IGNORECASE)
_APPL_ADD = re.compile(r"\badd\w*\b[^.;]{0,80}?\bto\s+the\s+(?:\w+'?s?\s+)?applicability\b", re.IGNORECASE)
_APPL_REMOVE = re.compile(r"\bremov\w*\b[^.;]{0,80}?\bfrom\s+the\s+applicability\b", re.IGNORECASE)
_WITHDRAW = re.compile(
    r"\b(?:withdraws|withdrawing|is\s+withdrawn|are\s+withdrawn)\b[^.]*?"
    r"\b(?:NPRMs?|SNPRMs?|notices?\s+of\s+proposed\s+rulemaking|proposed\s+rules?|proposed\s+ADs?|proposals?)\b"
    r"|\b(?:NPRM|SNPRM|proposed\s+rule|proposed\s+AD)s?\b[^.]*?\b(?:is|are)\s+withdrawn\b",
    re.IGNORECASE,
)
_C_WITHDRAW = re.compile(r"\bWithdraws\s+FAA\s+AD\s+NPRM\s+(?P<docket>FAA-\d{4}-\d+\w*)", re.IGNORECASE)
_C_EXTENSION = re.compile(
    r"Comment\s+Due\s+Date\s+was\s+extended\.\s+The\s+updated\s+Due\s+Date\s+is\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)
_C_CORRECTION = re.compile(r"\bPublishing\b[^\"]*?\bas\s+\"?(?P<docket>FAA-\d{4}-\d+)(?P<rev>R\d+)\"?", re.IGNORECASE)


def norm_ad(raw: str) -> str:
    """'2024- 05-13' -> '2024-05-13'; '72-14-08 R1' -> '72-14-08 R1' (revision suffix kept, one space)."""
    base, _, rev = raw.partition("R")
    base = re.sub(r"\s+", "", base)
    return f"{base} R{rev.strip()}" if rev else base


def _ad_numbers(text: str) -> list[tuple[str, int, int]]:
    """AD numbers in a clause. After an "AD"/"ADs" keyword, bare numbers in the same list are also taken."""
    found: dict[int, tuple[str, int, int]] = {}
    for m in AD_NUMBER.finditer(text):
        found[m.start(1)] = (norm_ad(m.group(1)), m.start(1), m.end(1))
    if found:
        first = min(found)
        for m in _BARE_AD.finditer(text, first):
            found.setdefault(m.start(1), (norm_ad(m.group(1)), m.start(1), m.end(1)))
    return [found[k] for k in sorted(found)]


def supersession_from_sentence(record_id: str, sent: Sent) -> list[Extraction]:
    out: list[Extraction] = []
    for m in _SUPERSEDE.finditer(sent.text):
        if _NEGATED.search(sent.text[max(0, m.start() - 10) : m.start()]):
            out.append(
                from_sentence(record_id, sent, m.start(), m.end(), "supersedes_ad", {"ad_number": None,
                              "negated": True}, "supersede.negated", "LOW")
            )  # fmt: skip
            continue
        end_m = _CLAUSE_END.search(sent.text, m.end())
        clause_end = end_m.start() if end_m else len(sent.text)
        ads = _ad_numbers(sent.text[m.end() : clause_end])
        if not ads:
            if sent.text[m.end() : clause_end].strip().lower().startswith(("its", "the mandatory")):
                continue  # e.g. "EASA superseded its MCAI": not an AD
            value = {"ad_number": None, "text": sent.text[m.start() : clause_end][:120]}
            out.append(from_sentence(record_id, sent, m.start(), clause_end, "supersedes_ad", value,
                                     "supersede.unnumbered", "LOW"))  # fmt: skip
            continue
        found = [(ad, m.end() + s, m.end() + e) for ad, s, e in ads]
        found += _continued_clauses(sent.text, clause_end)
        for ad, s, e in found:
            out.append(from_sentence(record_id, sent, s, e, "supersedes_ad", {"ad_number": ad}, "supersede.ad", "HIGH"))
    return out


_AND_AD = re.compile(r";\s*and\s+(?=AD\s)", re.IGNORECASE)


def _continued_clauses(text: str, pos: int) -> list[tuple[str, int, int]]:
    """'...supersede AD X, which apply to ...; and AD Y, which applies to ...' -> also AD Y."""
    out: list[tuple[str, int, int]] = []
    while (m := _AND_AD.search(text, pos)) is not None:
        end_m = _CLAUSE_END.search(text, m.end())
        stop = end_m.start() if end_m else len(text)
        out += [(ad, m.end() + s, m.end() + e) for ad, s, e in _ad_numbers(text[m.end() : stop])]
        pos = max(stop, m.end())
    return out


def continuation_from_sentence(record_id: str, sent: Sent) -> list[Extraction]:
    out: list[Extraction] = []
    for rx, rule, conf in ((_CONTINUE, "continue.actions", "HIGH"), (_RETAIN, "continue.retain", "MEDIUM")):
        for m in rx.finditer(sent.text):
            end_m = _CONT_END.search(sent.text, m.end())
            stop = end_m.start() if end_m else len(sent.text)
            if rx is _RETAIN:
                stop = max(stop, m.end() + 20)
            for ad, s, e in _ad_numbers(sent.text[m.start() : stop]):
                s, e = m.start() + s, m.start() + e
                out.append(from_sentence(record_id, sent, s, e, "continues_ad", {"ad_number": ad}, rule, conf))
    return out


def applicability_change_from_sentence(record_id: str, sent: Sent) -> list[Extraction]:
    out: list[Extraction] = []
    for m in _APPL.finditer(sent.text):
        direction = "reduced" if m.group("verb").lower().startswith("reduc") else "expanded"
        out.append(from_sentence(record_id, sent, m.start(), m.end(), "applicability_change", {"change": direction},
                                 f"applicability.{direction}", "HIGH"))  # fmt: skip
    for rx, direction, rule in ((_APPL_ADD, "expanded", "applicability.add"),
                                (_APPL_REMOVE, "reduced", "applicability.remove")):  # fmt: skip
        for m in rx.finditer(sent.text):
            out.append(from_sentence(record_id, sent, m.start(), m.end(), "applicability_change",
                                     {"change": direction}, rule, "MEDIUM"))  # fmt: skip
    return out


def withdrawal_from_sentence(record_id: str, docket: str, sent: Sent) -> list[Extraction]:
    m = _WITHDRAW.search(sent.text)
    if not m:
        return []
    value = {"docket": docket, "self_notice": True}
    return [from_sentence(record_id, sent, m.start(), m.end(), "withdraws_docket", value, "withdraw.notice", "HIGH")]


_EXT_NOTICE = re.compile(
    r"\b(?:extension\s+of|extending|extends|reopening|reopens|reopening\s+of)\s+the\s+comment\s+period\b", re.IGNORECASE
)


def extension_notice_from_sentence(record_id: str, sent: Sent) -> list[Extraction]:
    """The record itself announces a comment-period extension for the NPRM in its docket (no date is parsed)."""
    m = _EXT_NOTICE.search(sent.text)
    if not m:
        return []
    value = {"self_notice": True, "comments_due": None}
    return [from_sentence(record_id, sent, m.start(), m.end(), "comment_extension", value, "extension.notice", "HIGH")]


def from_comments(record_id: str, comments: str | None) -> list[Extraction]:
    if not comments:
        return []
    out: list[Extraction] = []

    def add(field: str, value: dict, m: re.Match[str], rule: str) -> None:
        out.append(Extraction(record_id, field, value, "comments", None, m.start(), m.end(), rule, "HIGH"))

    if m := _C_WITHDRAW.search(comments):
        add("withdraws_docket", {"docket": m.group("docket"), "self_notice": False}, m, "comments.withdraws")
    if m := _C_EXTENSION.search(comments):
        new_due: date | None = parse_mdy(m.group("date"))
        value = {"comments_due": new_due.isoformat() if new_due else None, "raw": m.group("date")}
        add("comment_extension", value, m, "comments.extension")
    if m := _C_CORRECTION.search(comments):
        add("correction_of", {"docket": m.group("docket"), "published_as": m.group("docket") + m.group("rev")}, m,
            "comments.correction")  # fmt: skip
    return out
