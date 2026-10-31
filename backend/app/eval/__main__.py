"""python -m backend.app.eval {build|dev|freeze|test|report}"""

from __future__ import annotations

import json
import logging
import os
import sys


def main() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    logging.disable(logging.WARNING)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        from backend.app.eval.cases import build

        m = build()
        print(
            json.dumps(
                {
                    "counts": m["counts"],
                    "dev": len(m["dev"]),
                    "test": len(m["test"]),
                    "cases_sha256": m["cases_sha256"],
                },
                indent=2,
            )
        )
    elif cmd == "dev":
        from backend.app.eval.harness import run_dev

        r = run_dev()
        print(
            f"dev cases: {r['n_dev_cases']}; chosen thresholds {r['chosen']} (dev refusal F1 {r['chosen_f1']:.3f}; "
            f"{r['tied_settings']} tied settings; previous {r['previous']})"
        )
    elif cmd == "freeze":
        from backend.app.eval.harness import freeze

        print(json.dumps(freeze(), indent=2))
    elif cmd == "test":
        from backend.app.eval.harness import run_test

        d = run_test()
        for k, m in d["systems"].items():
            r = m["refusal"]
            print(
                f"{k}: R@5 {m['recall_at_5']} (n={m['n_retrieval_cases']}) MRR {m['mrr']} | status acc "
                f"{m['status_accuracy']} (n={m['n_status_cases']}) | refusal F1 {r['f1']} (n={r['n']}) false refusals "
                f"{len(r['false_refusals'])}/{r['false_refusal_n']} | "
                f"facts {m['fact_hit_rate']} (n={m['n_fact_cases']}) | "
                f"p95 retr {m['latency']['p95_retrieval_ms']} e2e {m['latency']['p95_e2e_ms']}"
            )
        e = d["engine"]
        print(f"engine accuracy {e['accuracy']} (n={e['n']}) per class {e['per_class']}")
        print(f"worst5: {d['worst5']}")
    elif cmd == "report":
        from backend.app.eval.harness import regenerate_report

        regenerate_report()
        print("docs/EVAL.md regenerated from data/eval/results_detail.json (no re-run)")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
