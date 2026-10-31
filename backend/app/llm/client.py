"""Anthropic SDK wrapper: structured output via one tool call, validated with Pydantic, cached, cost-logged.

- Model IDs come only from config.yaml (`models.*`). Per-model options in `llm.model_options`:
  forced tool_choice where the model allows it, otherwise tool_choice auto + strict schema + an instruction
  (Claude Sonnet 5.5 rejects forced tool_choice with a 400). No temperature is sent (rejected by these models).
- Timeout 20 s, SDK retries (max 2, exponential backoff). Tool input failing validation -> one retry, then LLMError.
- Disk cache keyed by sha256(model + system + messages + tool schema): identical requests are deterministic.
- Every call (live or cached) is appended to logs/llm_calls.jsonl with tokens and estimated cost. The API key
  is never logged or printed.
- LLM_MODE=fake: answers come from backend.app.llm.fake (registered by tests), so the suite runs offline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from backend.app.config import ROOT, load_config, repo_path

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Any failure to obtain a valid structured answer. Callers map this to reason code LLM_ERROR."""


@dataclass
class LLMResult:
    output: BaseModel
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cached: bool
    latency_ms: float
    request_id: str | None


def load_env_files() -> None:
    """Load KEY=VALUE lines from ./.env and ./data/.env into os.environ (existing values win). Never logged."""
    for path in (ROOT / ".env", ROOT / "data" / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_DROP_KEYS = {"title", "default", "maxItems", "minItems", "maxLength", "minLength"}


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema -> strict tool schema: $refs inlined, every object closed and fully required."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            # Length/count limits are enforced by Pydantic after the call, not by the strict tool schema.
            out = {k: walk(v) for k, v in node.items() if k not in _DROP_KEYS}
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(raw)


def _cache_key(model: str, system: str, messages: list[dict[str, Any]], tool: dict[str, Any]) -> str:
    blob = json.dumps({"model": model, "system": system, "messages": messages, "tool": tool}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class LLMClient:
    def __init__(self, cache_dir: Path | None = None, call_log: Path | None = None) -> None:
        cfg = load_config()
        self.llm_cfg = cfg["llm"]
        self.models = cfg["models"]
        self.cache_dir = cache_dir or repo_path("response_cache_dir", section="logging")
        self.call_log = call_log or ROOT / self.llm_cfg["call_log"]
        self.fake = os.environ.get("LLM_MODE", "").lower() == "fake"
        self._client: Any = None

    # ------------------------------------------------------------ plumbing

    def _sdk(self) -> Any:
        if self._client is None:
            import anthropic

            load_env_files()
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
                raise LLMError(
                    "No Anthropic credentials: set ANTHROPIC_API_KEY (e.g. in data/.env) or use LLM_MODE=fake"
                )
            if key and (not key.startswith("sk-ant-") or any(ch.isspace() for ch in key)):
                # Checked locally so a placeholder never reaches the API; the value itself is never printed.
                raise LLMError("ANTHROPIC_API_KEY does not look like an Anthropic API key (expected 'sk-ant-...' with "
                               "no spaces). Check data/.env.")  # fmt: skip
            self._client = anthropic.Anthropic(
                timeout=float(self.llm_cfg["timeout_s"]), max_retries=int(self.llm_cfg["max_retries"])
            )
        return self._client

    def _cost(self, model: str, inp: int, out: int) -> float:
        price_in, price_out = self.llm_cfg["pricing_usd_per_mtok"].get(model, [0.0, 0.0])
        return round(inp / 1e6 * price_in + out / 1e6 * price_out, 6)

    def _log_call(self, purpose: str, res: LLMResult, key: str) -> None:
        self.call_log.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(UTC).isoformat(), "purpose": purpose, "model": res.model, "cached": res.cached,
            "fake": self.fake, "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
            "cost_usd": res.cost_usd, "latency_ms": round(res.latency_ms, 1), "request_id": res.request_id,
            "cache_key": key[:16],
        }  # fmt: skip
        with self.call_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    # ------------------------------------------------------------ main entry

    def call_tool(
        self,
        *,
        purpose: str,
        model_key: str,
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        output_model: type[T],
        max_tokens_key: str,
        extra_validator: Callable[[Any], str | None] | None = None,
    ) -> LLMResult:
        """One structured call: the model must answer by calling `tool_name`; the input is validated as output_model."""
        model = self.models[model_key]
        tool = {"name": tool_name, "description": tool_description, "input_schema": strict_schema(output_model)}
        messages = [{"role": "user", "content": user}]
        key = _cache_key(model, system, messages, tool)
        t0 = time.perf_counter()

        if self.fake:
            from backend.app.llm.fake import answer

            out = self._validate(output_model, answer(tool_name, user))
            problem = extra_validator(out) if extra_validator else None
            if problem:
                raise LLMError(f"{purpose}: FAKE output rejected: {problem}")
            res = LLMResult(out, model, 0, 0, 0.0, False, (time.perf_counter() - t0) * 1e3, "fake")
            self._log_call(purpose, res, key)
            return res

        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            out = self._validate(output_model, data["input"])
            res = LLMResult(out, model, data["input_tokens"], data["output_tokens"], 0.0, True,
                            (time.perf_counter() - t0) * 1e3, data.get("request_id"))  # fmt: skip
            self._log_call(purpose, res, key)
            return res

        last_error: Exception | None = None
        tokens_in = tokens_out = 0
        for attempt in range(1 + int(self.llm_cfg["validation_retries"])):
            nudge = (
                "" if attempt == 0 else f"\n\nYour previous answer was invalid ({last_error}). Call {tool_name} again."
            )
            raw, usage_in, usage_out, request_id = self._request(model, system, user + nudge, tool, tool_name,
                                                                 int(self.models[max_tokens_key]))  # fmt: skip
            tokens_in += usage_in
            tokens_out += usage_out
            try:
                out = output_model.model_validate(raw)
            except ValidationError as exc:
                last_error = exc
                log.warning("%s: tool input failed validation (attempt %d)", purpose, attempt + 1)
                continue
            problem = extra_validator(out) if extra_validator else None
            if problem:
                last_error = ValueError(problem)
                log.warning("%s: tool input rejected (attempt %d): %s", purpose, attempt + 1, problem)
                continue
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({"input": raw, "input_tokens": tokens_in, "output_tokens": tokens_out,
                                              "request_id": request_id, "model": model}), encoding="utf-8")  # fmt: skip
            res = LLMResult(out, model, tokens_in, tokens_out, self._cost(model, tokens_in, tokens_out), False,
                            (time.perf_counter() - t0) * 1e3, request_id)  # fmt: skip
            self._log_call(purpose, res, key)
            return res
        raise LLMError(f"{purpose}: invalid tool input after retries: {last_error}")

    def _request(
        self, model: str, system: str, user: str, tool: dict[str, Any], tool_name: str, max_tokens: int
    ) -> tuple[dict[str, Any], int, int, str | None]:
        import anthropic

        opts = self.llm_cfg["model_options"].get(model, {})
        forced = bool(opts.get("forced_tool_choice"))
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system if forced else f"{system}\n\nAnswer only by calling the {tool_name} tool exactly once.",
            "messages": [{"role": "user", "content": user}],
            "tools": [{**tool, "strict": True}],
            "tool_choice": {"type": "tool", "name": tool_name} if forced else {"type": "auto"},
        }
        if opts.get("thinking") in ("disabled", "between_tools"):
            kwargs["thinking"] = {"type": opts["thinking"]}
        if opts.get("effort"):
            kwargs["output_config"] = {"effort": opts["effort"]}
        try:
            resp = self._sdk().messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts, after SDK retries
            raise LLMError(f"Anthropic connection error: {exc}") from exc
        if resp.stop_reason == "refusal":
            raise LLMError("model declined the request (stop_reason=refusal)")
        if resp.stop_reason == "max_tokens":
            raise LLMError(f"output truncated at max_tokens={max_tokens}; raise it in config.yaml")
        block = next((b for b in resp.content if b.type == "tool_use" and b.name == tool_name), None)
        # With tool_choice auto the model may skip the tool: return {} so validation fails and the call retries.
        raw = dict(block.input) if block is not None else {}
        return raw, resp.usage.input_tokens, resp.usage.output_tokens, getattr(resp, "_request_id", None)

    @staticmethod
    def _validate(model: type[T], data: Any) -> T:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise LLMError(f"invalid structured output: {exc}") from exc


_default: LLMClient | None = None


def get_client() -> LLMClient:
    global _default
    if _default is None or _default.fake != (os.environ.get("LLM_MODE", "").lower() == "fake"):
        _default = LLMClient()
    return _default
