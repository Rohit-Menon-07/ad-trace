"""Backend for the screenshot task: the real app on a given port. With --fake-llm it runs LLM_MODE=fake with the
canned outputs in backend/tests/fixtures/screenshot_fakes.py (responses come back mock=true and show a MOCK badge).

    python scripts/screenshot_backend.py --port 8010 [--fake-llm]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--fake-llm", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    if args.fake_llm:
        os.environ["LLM_MODE"] = "fake"
        from backend.tests.fixtures import screenshot_fakes

        screenshot_fakes.register()
    import uvicorn

    from backend.app.main import app

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
