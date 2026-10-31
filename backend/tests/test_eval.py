"""Eval harness unit tests: metrics, splits, freeze discipline, cost guard, audit-rate script."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

from backend.app.eval import cases as cmod
from backend.app.eval import harness as h


def C(cid: str, cat: str = "lookup", status: str | None = "answered", records=None, reason=None) -> dict:
    return {"id": cid, "category": cat, "expected": {"status": status, "reason_code": reason,
            "expected_record_ids": records or [], "expected_verdicts": {}, "required_fact_substrings": []}}  # fmt: skip


def Out(retrieved=None, status="answered", reason=None) -> dict:
    return {"retrieved": retrieved or [], "status": status, "reason_code": reason, "claims": []}


def test_recall_and_mrr() -> None:
    c = C("x", records=["R1", "R2"])
    assert h.recall_at(c, Out(["R9", "R1", "R3"])) == 0.5
    assert h.rr(c, Out(["R9", "R1"])) == 0.5 and h.rr(c, Out(["R9"])) == 0.0
    big = C("y", records=[f"R{i}" for i in range(8)])
    assert h.recall_at(big, Out([f"R{i}" for i in range(5)])) == 1.0  # denominator capped at k


def test_refusal_metrics_and_false_refusals() -> None:
    cases = [C("a", status="refused", reason="OUT_OF_SCOPE"), C("b", status="answered"), C("c", status="refused",
             reason="UNKNOWN_ENTITY"), C("d", status=None)]  # fmt: skip
    outs = [Out(status="refused", reason="OUT_OF_SCOPE"), Out(status="refused", reason="LOW_RETRIEVAL_SCORE"),
            Out(status="answered"), Out(status="refused")]  # fmt: skip
    m = h.refusal_metrics(cases, outs)
    assert (m["tp"], m["fp"], m["fn"], m["n"]) == (1, 1, 1, 3)  # case d (status None) not scored
    assert m["reason_code_accuracy"] == 1.0 and [f["id"] for f in m["false_refusals"]] == ["b"]


def test_boot_ci_and_small_n() -> None:
    assert h.boot_ci([1.0]) == (None, None)
    lo, hi = h.boot_ci([1.0, 0.0] * 20)
    assert lo < 0.5 < hi


def test_answer_quality_not_measured_without_llm() -> None:
    aq = h.answer_quality([{"answer_mode": "extractive_fallback", "s7": {"claims_in": 3}}])
    assert aq["measured"] is False and "NOT MEASURED" in aq["note"]


def test_splits_are_stratified_and_seeded() -> None:
    cs = [{"id": f"{cat}-{i}", "category": cat} for cat in ("a", "b") for i in range(10)]
    cmod.assign_splits(cs)
    first = [c["split"] for c in cs]
    cmod.assign_splits(cs)
    assert [c["split"] for c in cs] == first
    for cat in ("a", "b"):
        assert sum(c["split"] == "dev" for c in cs if c["category"] == cat) == 3


def test_manual_decisions_parsing(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text("## M-01 (dev)\n- Decision: CONFIRMED\n## M-02 (test)\n- Decision: PENDING\n", encoding="utf-8")
    assert cmod.manual_decisions(p) == {"M-01": "CONFIRMED", "M-02": "PENDING"}


def test_eval_test_refuses_after_cases_change(tmp_path: Path, monkeypatch) -> None:
    cases = tmp_path / "cases.jsonl"
    cases.write_text('{"id": "x"}\n', encoding="utf-8")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"cases_sha256": "0" * 64, "manual_decisions_sha256": h.decisions_hash(),
                                  "config_sha256": h.config_hash(), "thresholds": {}}), encoding="utf-8")  # fmt: skip
    monkeypatch.setattr(h, "CASES_PATH", cases)
    monkeypatch.setattr(h, "FREEZE_PATH", freeze)
    with pytest.raises(SystemExit, match="changed after freezing"):
        h.run_test()


def test_cost_guard(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert h.projected_cost(60, available=False) == 0.0
    assert h.projected_cost(60, available=True) > 0.5
    assert h.projected_cost(100000, available=True) > 8  # would abort under the default EVAL_MAX_USD


def test_claim_audit_rate_script(tmp_path: Path, capsys) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import claim_audit_rate

    p = tmp_path / "a.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["system", "claim", "supported (Y/N)"])
        w.writeheader()
        w.writerows([{"system": "S0", "claim": "a", "supported (Y/N)": "N"}, {"system": "S0", "claim": "b",
                     "supported (Y/N)": "Y"}, {"system": "S2", "claim": "c", "supported (Y/N)": ""}])  # fmt: skip
    r = claim_audit_rate.rates(list(csv.DictReader(p.open(encoding="utf-8"))))
    assert r["S0"]["rate"] == 0.5 and r["S0"]["n_judged"] == 2 and r["S2"]["pending"] == 1


def test_built_cases_meet_minimums() -> None:
    if not cmod.CASES_PATH.exists():
        pytest.skip("cases not built")
    rows = [json.loads(x) for x in cmod.CASES_PATH.read_text(encoding="utf-8").splitlines()]
    counts = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    assert len(rows) >= 60 and counts["manual"] >= 20
    assert all(counts[k] >= n for k, n in {"lookup": 10, "model_applicability": 10, "supersession": 8, "status": 5,
               "unknown_entity": 5, "ambiguous_family": 5, "out_of_scope": 5, "false_premise": 4, "empty_summary": 3,
               "injection": 3}.items())  # fmt: skip
    manifest = json.loads(cmod.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["cases_sha256"] == cmod.sha256(cmod.CASES_PATH)
