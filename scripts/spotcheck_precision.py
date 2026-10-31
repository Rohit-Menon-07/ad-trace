"""Precision from the hand-filled extraction spot-check.

Usage: python scripts/spotcheck_precision.py [docs/extraction_spotcheck.csv]

Fill the "correct (Y/N)" column by hand (Y or N; leave blank to skip). Prints overall precision, a breakdown by
field and by confidence, and a 95% Wilson interval, because 25 samples give a wide interval.
"""

from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "docs" / "extraction_spotcheck.csv"
COLUMN = "correct (Y/N)"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def judge(value: str) -> bool | None:
    v = value.strip().upper()
    if v in ("Y", "YES"):
        return True
    if v in ("N", "NO"):
        return False
    return None


def precision(rows: list[dict[str, str]]) -> dict[str, object]:
    judged = [(r, judge(r.get(COLUMN, ""))) for r in rows]
    labelled = [(r, j) for r, j in judged if j is not None]
    k = sum(1 for _, j in labelled if j)
    groups: dict[str, list[bool]] = defaultdict(list)
    for r, j in labelled:
        assert j is not None
        groups[f"field={r['field']}"].append(j)
        groups[f"confidence={r['confidence']}"].append(j)
    return {
        "total": len(rows),
        "labelled": len(labelled),
        "unlabelled": len(rows) - len(labelled),
        "correct": k,
        "precision": k / len(labelled) if labelled else None,
        "wilson95": wilson(k, len(labelled)),
        "groups": {g: (sum(v), len(v)) for g, v in sorted(groups.items())},
    }


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    res = precision(rows)
    print(f"{path.name}: {res['labelled']} of {res['total']} rows labelled ({res['unlabelled']} blank)")
    if not res["labelled"]:
        print("No rows labelled yet: fill the 'correct (Y/N)' column by hand.")
        return 1
    lo, hi = res["wilson95"]  # type: ignore[misc]
    print(f"precision: {res['correct']}/{res['labelled']} = {res['precision']:.1%}  (95% Wilson CI {lo:.1%}-{hi:.1%})")
    for g, (k, n) in res["groups"].items():  # type: ignore[union-attr]
        print(f"  {g:40} {k}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
