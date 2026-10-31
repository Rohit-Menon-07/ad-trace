"""Cross-platform task runner behind the Makefile (GNU make is not available on every dev box).

    python scripts/tasks.py {setup,dev,test,lint,types,ingest,eval,screens}

`make <target>` calls exactly this, so running the script directly is equivalent.
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
PY = sys.executable
NPM = shutil.which("npm") or "npm"


def run(*cmd: str, cwd: Path = ROOT) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def setup() -> None:
    run(PY, "-m", "pip", "install", "-r", "backend/requirements.txt")
    run(NPM, "install", cwd=FRONTEND)


def stop_tree(p: subprocess.Popen[bytes]) -> None:
    """Stop a process and its children (npm.cmd -> node on Windows would otherwise be orphaned)."""
    if p.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()


def dev() -> None:
    """Backend (uvicorn --reload on :8000) and frontend (Vite on :5173) together; Ctrl-C stops both."""
    procs = [
        subprocess.Popen(
            [PY, "-m", "uvicorn", "backend.app.main:app", "--reload", "--reload-dir", "backend", "--port", "8000"],
            cwd=ROOT,
        ),
        subprocess.Popen([NPM, "run", "dev"], cwd=FRONTEND),
    ]
    try:
        while all(p.poll() is None for p in procs):
            try:
                procs[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            stop_tree(p)
    sys.exit(max(p.returncode or 0 for p in procs))


def types() -> None:
    run(PY, "-m", "backend.app.export_types")


def test() -> None:
    run(PY, "-m", "pytest", "-q")
    run(NPM, "run", "typecheck", cwd=FRONTEND)


def lint() -> None:
    run(PY, "-m", "ruff", "check", "backend", "scripts")
    run(PY, "-m", "ruff", "format", "--check", "backend", "scripts")
    run(NPM, "run", "lint", cwd=FRONTEND)
    run(NPM, "run", "typecheck", cwd=FRONTEND)


def ingest() -> None:
    run(PY, "-m", "backend.app.ingest.run")


def eval_cmd(sub: str) -> None:
    run(PY, "-m", "backend.app.eval", sub)


def _wait_http(url: str, timeout: float = 180.0) -> None:
    import time
    import urllib.request

    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    sys.exit(f"timed out waiting for {url}")


def screens() -> None:
    """Playwright screenshots of answered / refused / needs_clarification (real pipeline, whatever LLM key is
    configured) and partial (FAKE LLM fixture, shown with a MOCK badge) into docs/screens/."""
    import os

    port, ui = 8010, 4173
    env = {**os.environ, "ADTRACE_API": f"http://127.0.0.1:{port}"}
    run(NPM, "run", "build", cwd=FRONTEND)
    preview = subprocess.Popen(
        [NPM, "run", "preview", "--", "--host", "127.0.0.1", "--port", str(ui), "--strictPort"], cwd=FRONTEND, env=env
    )
    try:
        for fake_llm, states in (
            (False, ["answered", "refused", "needs_clarification", "coverage", "evaluation"]),
            (True, ["partial"]),
        ):
            cmd = [PY, "scripts/screenshot_backend.py", "--port", str(port)] + (["--fake-llm"] if fake_llm else [])
            backend = subprocess.Popen(cmd, cwd=ROOT)
            try:
                _wait_http(f"http://127.0.0.1:{port}/api/health")
                _wait_http(f"http://127.0.0.1:{ui}/")
                run("node", "scripts/screenshots.mjs", f"http://127.0.0.1:{ui}/", *states, cwd=FRONTEND)
            finally:
                stop_tree(backend)
    finally:
        stop_tree(preview)


def not_built(name: str) -> None:
    print(f"`{name}` is not implemented yet (backend pipeline is MOCK in Prompt 2).")
    sys.exit(1)


TASKS = {
    "setup": setup,
    "dev": dev,
    "types": types,
    "test": test,
    "lint": lint,
    "ingest": ingest,
    "eval": lambda: eval_cmd("test"),
    "eval-build": lambda: eval_cmd("build"),
    "eval-dev": lambda: eval_cmd("dev"),
    "eval-freeze": lambda: eval_cmd("freeze"),
    "eval-test": lambda: eval_cmd("test"),
    "screens": screens,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        sys.exit(f"usage: python scripts/tasks.py {{{','.join(TASKS)}}}")
    TASKS[sys.argv[1]]()
