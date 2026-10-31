"""Human-audited unsupported-claim rate from data/eval/claim_audit.csv (headline answer-quality metric).

Fill the "supported (Y/N)" column by hand (Y or N; blank = not yet judged), then run:

    python scripts/claim_audit_rate.py [path]

Prints, per system (S0 naive RAG vs S2 full), the unsupported-claim rate with n and a 95% Wilson interval.
"""

from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "data" / "eval" / "claim_audit.csv"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, c - h), min(1.0, c + h)


def rates(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    by: dict[str, list[bool]] = defaultdict(list)
    pending: dict[str, int] = defaultdict(int)
    for r in rows:
        v = r.get("supported (Y/N)", "").strip().upper()
        if v in ("Y", "YES"):
            by[r["system"]].append(True)
        elif v in ("N", "NO"):
            by[r["system"]].append(False)
        else:
            pending[r["system"]] += 1
    out = {}
    for sysk in sorted(set(by) | set(pending)):
        judged = by.get(sysk, [])
        unsupported = sum(1 for x in judged if not x)
        out[sysk] = {
            "n_judged": len(judged),
            "pending": pending.get(sysk, 0),
            "unsupported": unsupported,
            "rate": unsupported / len(judged) if judged else None,
            "wilson95": wilson(unsupported, len(judged)),
        }
    return out


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print(f"{path.name}: no claims to audit (no model-written answers in the last eval run).")
        return 1
    res = rates(rows)
    for sysk, r in res.items():
        if not r["n_judged"]:
            print(f"{sysk}: not judged yet ({r['pending']} rows blank)")
            continue
        lo, hi = r["wilson95"]  # type: ignore[misc]
        print(
            f"{sysk}: unsupported {r['unsupported']}/{r['n_judged']} = {r['rate']:.1%} (95% Wilson {lo:.1%}-{hi:.1%}); "
            f"{r['pending']} rows still blank"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
