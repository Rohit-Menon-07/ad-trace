"""Prompt 8 live check: three queries through retrieval + engine + Sonnet generation.

Prints, per query, the exact evidence pack, the raw submit_answer tool output, and tokens/cost.
Needs a real ANTHROPIC_API_KEY (e.g. in data/.env); without one each query shows the extractive fallback.

    python scripts/live_generate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.pipeline.generate import main  # noqa: E402

QUERIES = [
    ["Which proposed ADs concern the radio management panels on our A330-243?", "--make", "Airbus SAS",
     "--model", "A330-243", "--as-of", "2026-10-31"],
    ["What would the proposal for the PW4090 engines require?", "--model", "PW4090", "--as-of", "2026-10-31"],
    ["Is there a proposal about oxygen generators, and is its comment period still open?", "--as-of", "2026-10-31"],
]  # fmt: skip

if __name__ == "__main__":
    for i, argv in enumerate(QUERIES, 1):
        print(f"\n{'#' * 40} QUERY {i} {'#' * 40}")
        main(argv)
