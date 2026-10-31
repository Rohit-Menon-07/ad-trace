"""FAKE LLM for LLM_MODE=fake (tests and offline CLI). Canned, schema-valid tool inputs.

Tests call `register(tool_name, output, when="substring of the user message")`. If nothing matches, a tool may
have a built-in FAKE fallback (parse_query has a crude regex parser so the CLI works offline); otherwise
LLMError. Nothing here is a real model answer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_REGISTRY: dict[str, list[tuple[str | None, Any]]] = {}  # output: dict, or callable(user_message) -> dict
_FALLBACKS: dict[str, Callable[[str], dict[str, Any]]] = {}


def register(tool_name: str, output: Any, when: str | None = None) -> None:
    """Most recent registration wins; `when=None` matches any message. `output` may be a callable taking the
    user message (used by the FAKE verifier, which must answer per item)."""
    _REGISTRY.setdefault(tool_name, []).insert(0, (when, output))


def clear() -> None:
    _REGISTRY.clear()


def answer(tool_name: str, user_message: str) -> dict[str, Any]:
    from backend.app.llm.client import LLMError

    for when, output in _REGISTRY.get(tool_name, []):
        if when is None or when in user_message:
            return output(user_message) if callable(output) else output
    if tool_name in _FALLBACKS:
        return _FALLBACKS[tool_name](user_message)
    raise LLMError(f"FAKE LLM: no canned output registered for tool {tool_name!r}")


def _fake_parse_query(user_message: str) -> dict[str, Any]:
    """Crude FAKE parser: copies the first designator-like token and AD number. Offline use only."""
    m = re.search(r"<user_query>(.*)</user_query>", user_message, re.S)
    text = (m.group(1) if m else user_message).strip()
    model = re.search(r"\b[A-Z]{1,4}-?\d{2,4}(?:-[0-9A-Z]+)*\b", text)
    ad = re.search(r"\b(?:AD\s+)?(\d{4}-\d{2}-\d{2})\b", text)
    return {
        "intent": "lookup", "make_text": None, "model_text": model.group(0) if model else None,
        "serial_text": None, "ad_number_text": ad.group(1) if ad else None, "date_from": None, "date_to": None,
        "asks_out_of_scope": False, "out_of_scope_kind": "none", "asserted_premises": [],
        "injection_suspected": False, "free_text": text,
    }  # fmt: skip


_FALLBACKS["parse_query"] = _fake_parse_query
