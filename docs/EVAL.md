# AD Trace evaluation (test split)

_Generated 2026-10-31T07:14:32.550384+00:00 by `make eval-test`. Frozen 2026-10-31T07:14:21.679434+00:00; cases sha256 `50ccd6b403ec9e22`; thresholds {'min_top_cosine': 0.62, 'min_top_bm25_norm': 0.9}._

## Setup

- **Test cases: n = 44** {'lookup': 7, 'model_applicability': 7, 'serial_unresolved': 2, 'supersession': 6, 'status': 3, 'unknown_entity': 3, 'ambiguous_family': 3, 'out_of_scope': 3, 'false_premise': 3, 'injection': 2, 'off_topic': 3, 'empty_summary': 2}; provenance {'auto': 44}.
- **Manual cases: 24 drafted cases are AWAITING HUMAN REVIEW** (data/eval/manual_review.md) and are NOT included. Every number below comes from AUTO cases only.
- **Circularity caveat:** auto cases are generated from structured fields (Model column, raw summary text, raw dates). They test the pipeline, not extraction quality. Model-applicability auto cases are partly circular: the engine reads the same Model column. Treat high scores on them as plumbing checks, not accuracy evidence.
- **LLM availability:** no valid ANTHROPIC_API_KEY: generation, verifier, parser and judge fall back or are skipped. Projected cost $0.00.
- Systems: **B1** B1 BM25 + extractive (keyword search, no LLM, no engine); **B2** B2 dense + extractive (no LLM, no engine); **B3** B3 hybrid + extractive (no LLM, no engine); **S0** S0 hybrid + generation, no verification, no engine (naive RAG); **S1** S1 = S0 + quote and grounding checks; **S2** S2 full system: engine, gates, clarification, generation, all verification layers.
- Thresholds tuned on the dev split only: {'min_top_cosine': 0.62, 'min_top_bm25_norm': 0.9} (see DECISIONS.md).
- Brackets are bootstrap 95% CIs (1000 resamples). n is shown next to every metric.

## Retrieval (answerable cases with expected records)

| System | Recall@5 | MRR | n |
|---|---|---|---|
| B1 | 100.0% [100-100%] | 92.8% [81-100%] | 18 |
| B2 | 61.1% [39-83%] | 47.3% [28-67%] | 18 |
| B3 | 77.8% [56-94%] | 77.8% [56-94%] | 18 |
| S2 | 72.2% [50-89%] | 73.8% [52-90%] | 18 |

S2 retrieves with engine-consistent hard filters (make/model), so its numbers are not a pure ranking comparison.

## Applicability engine (direct evaluation, independent of retrieval)

Accuracy 100.0% [100-100%], n = 7.

| Expected \ Got | APPLICABLE | NOT_APPLICABLE | UNDETERMINED | NOT_CHECKED |
|---|---|---|---|---|
| APPLICABLE | 4 | 0 | 0 | 0 |
| NOT_APPLICABLE | 0 | 3 | 0 | 0 |

Per class: {"APPLICABLE": {"acc": 1.0, "n": 4}, "NOT_APPLICABLE": {"acc": 1.0, "n": 3}}
UNDETERMINED by engine rule: none. Coverage matters more than accuracy here: UNDETERMINED is a visible, safe outcome.

## Refusal behaviour (should refuse/clarify vs did)

| System | Precision | Recall | F1 | Reason-code acc. | False refusals | n |
|---|---|---|---|---|---|---|
| B1 | 100.0% | 15.8% | 27.3% [0-50%] | 0.0% (n=3) | 0/16 | 35 |
| B2 | n/a | 0.0% | n/a [0-0%] | n/a (n=0) | 0/16 | 35 |
| B3 | n/a | 0.0% | n/a [0-0%] | n/a (n=0) | 0/16 | 35 |
| S0 | n/a | 0.0% | n/a [0-0%] | n/a (n=0) | 0/16 | 35 |
| S1 | n/a | 0.0% | n/a [0-0%] | n/a (n=0) | 0/16 | 35 |
| S2 | 94.7% | 94.7% | 94.7% [86-100%] | 100.0% (n=18) | 1/16 | 35 |

S2 false refusals (answerable cases refused): [{'id': 'A-STAT-05', 'category': 'status', 'status': 'needs_clarification', 'reason': 'AMBIGUOUS_MODEL'}].

## Answer quality and ablation (S0 to S2)

- **S0: NOT MEASURED: no answer was written by the model (generation fell back to extractive or was off).** Answer modes: {'extractive_fallback': 44}.
- **S1: NOT MEASURED: no answer was written by the model (generation fell back to extractive or was off).** Answer modes: {'extractive_fallback': 44}.
- **S2: NOT MEASURED: no answer was written by the model (generation fell back to extractive or was off).** Answer modes: {'extractive_fallback': 25, 'null': 19}.

- **Unsupported-claim rate (headline, human audit): AWAITING HUMAN REVIEW.** data/eval/claim_audit.csv has 0 rows (20 from S0 and 20 from S2 when available); compute with `python scripts/claim_audit_rate.py`.
- LLM judge (a model; it can be wrong): {"run": false, "note": "LLM judge NOT RUN: no valid API key."}.

## Latency and cost

| System | p50 retrieval | p95 retrieval | p50 end-to-end | p95 end-to-end | cost/query | n |
|---|---|---|---|---|---|---|
| B1 | 5.1 ms | 7.6 ms | 7.0 ms | 10.0 ms | $0.0000 | 44 |
| B2 | 8.6 ms | 10.7 ms | 11.0 ms | 13.0 ms | $0.0000 | 44 |
| B3 | 15.2 ms | 18.3 ms | 18.0 ms | 21.0 ms | $0.0000 | 44 |
| S0 | 15.4 ms | 18.8 ms | 19.0 ms | 22.0 ms | $0.0000 | 44 |
| S1 | 14.9 ms | 19.0 ms | 18.5 ms | 22.9 ms | $0.0000 | 44 |
| S2 | 13.7 ms | 17.7 ms | 17.0 ms | 23.9 ms | $0.0000 | 44 |

End-to-end is low because no LLM call succeeded in this run; it is not representative of a run with a working key.

## Failure analysis (S2, worst per category)

VISIBLE = the user sees a warning (refusal card, UNDETERMINED badge, partial). **SILENT = no warning: the dangerous kind; we report it.**

### A-SER-03 (serial_unresolved): missed_refusal (SILENT)
- Query: Do the proposed ADs apply to our A330-341 serial 1234?
- Expected: {"status": "refused", "reason_code": "APPLICABILITY_UNDETERMINED"}
- Observed: answered ; top retrieved ['R0061', 'R0046', 'R0037']
- Probable cause: no gate fired; expected APPLICABILITY_UNDETERMINED
- Fix: add or widen the gate for this pattern

### A-SUP-01 (supersession): record_missed (SILENT)
- Query: Which proposal would supersede AD 2026-09-02?
- Expected: {"status": "answered", "expected_record_ids": ["R0002"], "required_fact_substrings": ["would supersede AD 2026-09-02"]}
- Observed: answered ; top retrieved ['R0051', 'R0005', 'R0149']
- Probable cause: expected record not in the top 8 retrieved
- Fix: retrieval (query wording, model linking, ranking tiers)

### A-SUP-06 (supersession): record_missed (SILENT)
- Query: Which proposal would supersede AD 2015-07-03?
- Expected: {"status": "answered", "expected_record_ids": ["R0027"], "required_fact_substrings": ["would supersede AD 2015-07-03"]}
- Observed: answered ; top retrieved ['R0213', 'R0230', 'R0051']
- Probable cause: expected record not in the top 8 retrieved
- Fix: retrieval (query wording, model linking, ranking tiers)

### A-STAT-05 (status): false_refusal (VISIBLE)
- Query: Is the comment period still open for the proposed AD on the 206L?
- Expected: {"status": "answered", "expected_record_ids": ["R0044"], "required_fact_substrings": ["comment period CLOSED (closed 2026-10-26)"]}
- Observed: needs_clarification AMBIGUOUS_MODEL; top retrieved []
- Probable cause: gate AMBIGUOUS_MODEL fired on an answerable question
- Fix: narrow that gate (keyword list, thresholds or linking)

All S2 failures: 4 (3 silent). Full list in data/eval/results_detail.json.

## Limitations

- Small n (test n = 44); confidence intervals are wide and most systems cannot be separated statistically where the CIs overlap.
- One dataset: 431 FAA NPRM summaries (proposals, not final ADs), no full notice text.
- Extraction is regex-based; see data/processed/coverage_report.json (e.g. no summary states serial ranges, so serial applicability is never resolved).
- Auto cases are partly circular; manual cases are pending human review.
- Answer-quality and unsupported-claim metrics need a working LLM key and a human audit; until then they are NOT MEASURED.
- No user study and no measured time savings: any impact claim is an estimate, not a measurement.

## Analyst notes (written after the single test run; nothing below changed the run or its numbers)

**Two of the four S2 "failures" are errors in my auto test labels, not system errors.**
- **A-STAT-05:** I built the query from the first token of R0044's Model column, "206L". "206L" is a family with variants (206L-1, -3, -4), so the system correctly asked for clarification (AMBIGUOUS_MODEL). The expected label "answered" is wrong.
- **A-SER-03:** I asserted that every record listing A330-341 says only "certain" airplanes, without checking. R0061 and R0046 list A330-341 with no qualifier, so APPLICABLE is the correct verdict and no APPLICABILITY_UNDETERMINED refusal was due.

The test split is frozen, so the labels were not edited and the run was not repeated. Correcting both labels in a v2 freeze would move S2 to 0 false refusals and 0 missed refusals on this split, but that is not a measured result.

**Two failures are real and SILENT: A-SUP-01 and A-SUP-06 (supersession lookups by AD number).**
- "Which proposal would supersede AD 2026-09-02?": BM25 ranks R0002 first (B1 retrieves it at rank 1). Hybrid RRF drops it out of the top 8 entirely: a record ranked first by one signal only (1/61) loses to records ranked middling by both. The user gets an answer about other proposals, with no warning.
- **Fix (not applied; it would be tuned on dev and re-frozen):** guarantee BM25 rank-1 hits on exact identifier tokens (AD numbers, dockets, designators) a place in the fused list, or add an exact-identifier tier like the model-match tier.

**Too good to be true:**
- **B1 BM25 Recall@5 = 100% (n = 18).** Auto lookup and supersession queries contain the exact model or AD token, which is where keyword search is strongest. This is a property of auto-generated queries, not evidence that keyword search is enough. Manual paraphrase cases (pending review) are designed to test this.
- **Engine accuracy 100% (n = 7).** Expected verdicts come from the same Model column the engine reads (circular), and n is tiny. The known engine weaknesses (STC-conditional applicability in R0044, the "900ER" typo in R0155) are in the manual cases, which are pending.
- **Dev tuning F1 = 1.0** on 22 dev cases, with 24 of 54 threshold settings tied. The dev split cannot separate them; the previous placeholders (0.62 / 0.90) were kept by the tie-break rule.

**Not measured in this run (no valid API key):**
- Every S0/S1/S2 answer was extractive (answer modes: extractive_fallback or none), so S0, S1 and S2 differ here only by engine and gates.
- Answer-quality layer rates, the human-audited unsupported-claim rate and the LLM judge are therefore NOT MEASURED. claim_audit.csv has no rows.
- Latency and $0 cost exclude LLM calls.
