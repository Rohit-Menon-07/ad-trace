"""FAKE LLM outputs for the `partial` screenshot only (scripts/tasks.py screens). NOT model answers.

With no API key the real pipeline never produces `partial` (extractive answers are verbatim), so the screenshot
backend runs with LLM_MODE=fake and these canned outputs: one verbatim-quote claim that passes every layer and one
fabricated claim that the quote check removes. The pipeline marks such responses mock=true, so the UI shows a
MOCK badge on that screenshot.
"""

from __future__ import annotations

import re

from backend.app.llm import fake

PARTIAL_QUERY = "Which proposed ADs concern the radio management panels on our A330-243?"


def _pack_ids(msg: str) -> list[str]:
    return re.findall(r'<e id="([^"]+)"', msg)


def _answer(msg: str) -> dict:
    first = _pack_ids(msg)[0]
    text = re.search(rf'<e id="{re.escape(first)}"[^>]*>(.*?)</e>', msg, re.S).group(1)  # type: ignore[union-attr]
    quote = " ".join(text.split()[:14])
    return {
        "cannot_answer": False,
        "cannot_answer_reason": None,
        "claims": [
            {"text": quote, "evidence_ids": [first], "quote": quote, "fact_ids": ["F1"]},
            {
                "text": "The proposal would require replacing every radio management panel within 30 days.",
                "evidence_ids": [first],
                "quote": "would require replacing every radio management panel within 30 days",
                "fact_ids": [],
            },
        ],  # fmt: skip
        "rationale_steps": [
            f"The notice names the aircraft [{first}].",
            "Applicability was computed by the rules [F1].",
        ],
    }


def _supported(msg: str) -> dict:
    return {
        "results": [{"id": i, "verdict": "SUPPORTED", "issue": None} for i in re.findall(r'<item id="(C\d+)"', msg)]
    }


def register() -> None:
    fake.register("submit_answer", _answer, when="radio management panels")
    fake.register("verify_claims", _supported)
