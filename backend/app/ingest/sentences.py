"""Sentence splitter for NPRM summaries with exact character offsets.

Contract: for every returned span, summary[start:end] == text (asserted). A boundary is a '.', '?' or '!'
(plus any closing quote) followed by whitespace and an uppercase letter, digit, quote or opening bracket,
outside parentheses/brackets. It is suppressed after protected abbreviations (U.S., No., Inc., S.A., ...)
unless the next word is a strong sentence starter ("This", "The", "We", ...), so "Bombardier, Inc. Model"
stays whole but "... Textron Inc. This proposed AD" splits. AD numbers (2025-09-07) and model designators
(A330-243) contain no '.', so a period after them is an ordinary sentence end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Lower-cased tokens (including their trailing '.') that do not end a sentence by themselves.
ABBREVIATIONS = frozenset(
    {
        "u.s.", "no.", "nos.", "e.g.", "i.e.", "inc.", "ltd.", "co.", "corp.", "s.a.", "s.p.a.", "jr.", "sr.",
        "etc.", "approx.", "fig.", "ref.", "rev.", "vol.", "st.", "mr.", "ms.", "dr.", "b.v.", "n.v.", "a.g.",
        "gmbh.", "p/n.", "s/n.", "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "sept.", "oct.",
        "nov.", "dec.", "u.s.c.", "cf.", "vs.",
    }
)  # fmt: skip

# Words that almost always begin a new sentence in these summaries; they override an abbreviation.
STRONG_STARTERS = frozenset(
    {
        "This", "The", "These", "That", "Those", "We", "Since", "Accordingly", "In", "It", "As", "For", "After",
        "Additionally", "Also", "However", "FAA", "AD", "Comments", "You",
    }
)  # fmt: skip

_TERMINAL = ".?!"
_CLOSERS = "\"')]”’"
_OPENERS = "([{"
_CLOSE_FOR = {")": "(", "]": "[", "}": "{"}
_TOKEN_BEFORE = re.compile(r"(\S+)$")
_NEXT_WORD = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class SentenceSpan:
    idx: int  # 1-based position in the summary
    text: str
    start: int
    end: int  # exclusive


def _is_abbreviation(summary: str, dot: int) -> bool:
    m = _TOKEN_BEFORE.search(summary, 0, dot + 1)
    if not m:
        return False
    token = m.group(1).lstrip("(\"'[").lower()
    if token in ABBREVIATIONS:
        return True
    # Single capital initial such as "J." in "J. Smith" (but not a digit or a model like "A330.").
    return bool(re.fullmatch(r"[a-z]\.", token)) and summary[dot - 1].isupper()


def _boundary_after(summary: str, i: int, depth: int) -> int | None:
    """If summary[i] ends a sentence, return the exclusive end index of that sentence, else None."""
    if summary[i] not in _TERMINAL or depth > 0:
        return None
    end = i + 1
    while end < len(summary) and summary[end] in _CLOSERS and summary[end] not in ")]":
        end += 1
    if end >= len(summary) or not summary[end].isspace():
        return None  # "3.7", "S.p.A.,", end-of-text handled by caller
    j = end
    while j < len(summary) and summary[j].isspace():
        j += 1
    if j >= len(summary):
        return None
    nxt = summary[j]
    if not (nxt.isupper() or nxt.isdigit() or nxt in "\"'“‘" + _OPENERS):
        return None
    if summary[i] == "." and _is_abbreviation(summary, i):
        word = _NEXT_WORD.match(summary, j)
        if not word or word.group(0) not in STRONG_STARTERS:
            return None
    return end


def _bracketed(summary: str) -> list[bool]:
    """True for characters inside a *matched* (), [] or {} pair. Unmatched brackets are ignored so a
    stray '(' cannot suppress every later boundary."""
    inside = [False] * len(summary)
    stack: list[tuple[str, int]] = []
    for i, ch in enumerate(summary):
        if ch in _OPENERS:
            stack.append((ch, i))
        elif ch in _CLOSE_FOR:
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == _CLOSE_FOR[ch]:
                    open_at = stack[k][1]
                    del stack[k:]
                    for j in range(open_at + 1, i):
                        inside[j] = True
                    break
    return inside


def split_sentences(summary: str | None) -> list[SentenceSpan]:
    """Split a cleaned summary into sentences with exact offsets. Empty/None -> []."""
    if not summary:
        return []
    inside = _bracketed(summary)
    spans: list[tuple[int, int]] = []
    start = 0
    for i in range(len(summary)):
        end = _boundary_after(summary, i, 1 if inside[i] else 0)
        if end is not None:
            spans.append((start, end))
            start = end
    spans.append((start, len(summary)))

    out: list[SentenceSpan] = []
    for s, e in spans:
        while s < e and summary[s].isspace():
            s += 1
        while e > s and summary[e - 1].isspace():
            e -= 1
        if s < e:
            out.append(SentenceSpan(idx=len(out) + 1, text=summary[s:e], start=s, end=e))
    for span in out:
        assert summary[span.start : span.end] == span.text, f"offset mismatch at sentence {span.idx}"
    return out


def sentence_id(record_id: str, idx: int) -> str:
    return f"{record_id}#s{idx}"
