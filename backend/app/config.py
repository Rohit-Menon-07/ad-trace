"""Loads config.yaml (pinned model IDs, thresholds, paths)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_as_of(requested: date | None = None) -> date:
    """Request value wins, then config.yaml `as_of`, then today (DECISIONS.md #13)."""
    if requested is not None:
        return requested
    configured = load_config().get("as_of")
    if configured:
        return date.fromisoformat(str(configured))
    return date.today()


def repo_path(key: str, section: str = "data") -> Path:
    """Absolute path for a config entry such as data.eval_results or logging.feedback_log."""
    return ROOT / load_config()[section][key]
