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
