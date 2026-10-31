"""S1 query understanding: Haiku parses the question into fields via the forced tool `parse_query`.

The model only copies strings; code links them to the vocabulary (linker.py) and decides (gates.py).

CLI: python -m backend.app.pipeline.query "question" [--make ...] [--model ...] [--serial ...] [--as-of ...]
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.config import repo_path
from backend.app.llm.client import LLMClient, LLMError, LLMResult, get_client

PROMPT_PATH = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "parse_query.md"


class Premise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    make_text: str | None
    model_text: str | None
    ad_number_text: str | None
    claim_text: str


class ParsedQuery(BaseModel):
    """Tool input of parse_query. All fields required; null when the user did not state them."""

    model_config = ConfigDict(extra="forbid")
    intent: Literal["lookup", "applicability", "supersession", "status", "other"]
    make_text: str | None
    model_text: str | None
    serial_text: str | None
    ad_number_text: str | None
    date_from: str | None = Field(description="YYYY-MM-DD if the user gave a start date")
    date_to: str | None = Field(description="YYYY-MM-DD if the user gave an end date")
    asks_out_of_scope: bool
    out_of_scope_kind: Literal["compliance_steps", "numeric_spec", "parts", "legal", "other_data", "none"]
    asserted_premises: list[Premise]
    injection_suspected: bool
    free_text: str | None


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def wrap(query: str) -> str:
    """User text is data (H10): wrapped in tags; closing tags inside it are neutralised."""
    safe = query.replace("</user_query>", "</ user_query>").replace("<user_query>", "< user_query>")
    return f"<user_query>{safe}</user_query>"


def parse_query(query: str, client: LLMClient | None = None) -> LLMResult:
    return (client or get_client()).call_tool(
        purpose="parse_query",
        model_key="query_parser",
        system=system_prompt(),
        user=wrap(query),
        tool_name="parse_query",
        tool_description="Record the structured fields of the engineer's question. Never answer it.",
        output_model=ParsedQuery,
        max_tokens_key="max_tokens_parser",
    )


_RB_MODEL = re.compile(r"\b[A-Z]{1,4}-?\d{2,4}(?:-[0-9A-Z]+)*\b")
_RB_AD = re.compile(r"\b(?:AD\s+)?(\d{2,4}-\d{2}-\d{2,3})\b")
_RB_SERIAL = re.compile(r"\b(?:MSN|S/N|serial(?:\s+number)?)\s*:?\s*([A-Z]{0,3}-?\d{2,6})\b", re.IGNORECASE)


def rule_based_parse(query: str) -> ParsedQuery:
    """Degraded S1 when the parser LLM is unavailable: copies designator-like tokens, AD numbers and serials only.
    Linking (H8) still validates everything; out-of-scope / injection / premise checks have their own code rules."""
    from backend.app.pipeline.checks import heuristic_premises

    model = _RB_MODEL.search(query)
    ad = _RB_AD.search(query)
    serial = _RB_SERIAL.search(query)
    return ParsedQuery(
        intent="applicability" if serial else "lookup",
        make_text=None,
        model_text=model.group(0) if model else None,
        serial_text=serial.group(1) if serial else None,
        ad_number_text=ad.group(1) if ad else None,
        date_from=None,
        date_to=None,
        asks_out_of_scope=False,
        out_of_scope_kind="none",
        asserted_premises=heuristic_premises(query),
        injection_suspected=False,
        free_text=query,
    )


def main(argv: list[str] | None = None) -> None:
    from backend.app.pipeline.gates import run_pre_retrieval_gates
    from backend.app.pipeline.linker import Linker, UIFields, link_query

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query")
    p.add_argument("--make")
    p.add_argument("--model")
    p.add_argument("--serial")
    p.add_argument("--as-of")
    p.add_argument("--db", type=Path, default=repo_path("sqlite_path"))
    args = p.parse_args(argv)
    try:
        res = parse_query(args.query)
    except LLMError as exc:
        print(
            json.dumps({"stop": True, "status": "refused", "reason_code": "LLM_ERROR", "message": str(exc)}, indent=2)
        )
        raise SystemExit(2) from exc
    parsed: ParsedQuery = res.output  # type: ignore[assignment]
    print(f"parser: {res.model}  cached={res.cached}  tokens in/out {res.input_tokens}/{res.output_tokens}  "
          f"cost ${res.cost_usd:.6f}  {res.latency_ms:.0f} ms")  # fmt: skip
    print(json.dumps(parsed.model_dump(), indent=2))
    linker = Linker.from_db(args.db)
    ui = UIFields(args.make, args.model, args.serial, date.fromisoformat(args.as_of) if args.as_of else None)
    linked = link_query(parsed, ui, linker)
    print("\nlinker:")
    print(json.dumps(linked.summary(), indent=2))
    decision = run_pre_retrieval_gates(args.query, parsed, linked, linker)
    print("\ngate:", json.dumps(decision.as_dict(), indent=2))


if __name__ == "__main__":
    main()
