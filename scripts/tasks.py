"""Cross-platform task runner behind the Makefile (GNU make is not available on every dev box).

    python scripts/tasks.py {setup,dev,test,lint,types,ingest,eval}

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
    "eval": lambda: not_built("eval"),
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        sys.exit(f"usage: python scripts/tasks.py {{{','.join(TASKS)}}}")
    TASKS[sys.argv[1]]()
