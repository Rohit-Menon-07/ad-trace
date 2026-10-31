## Analyst notes

### v2 run: the test split is NOT clean any more (read this first)

v1 (frozen 2026-10-31T07:14) was run once on the test split and its failures were read. The v2 fixes below were motivated by those test failures, so **v2 test numbers are contaminated: they are an optimistic re-test, not an unbiased held-out estimate.** No threshold was tuned on test (dev tuning re-ran and kept 0.62 / 0.90), but which bugs got fixed was chosen by looking at test failures. A clean estimate needs new held-out cases (e.g. the 24 manual cases once a human confirms them, since none of them were used to choose fixes).

What changed between v1 and v2, and why:
- **Label fixes (my construction errors, not system changes).** A-STAT cases now use the most specific listed model (v1 used "206L", a family, so the system correctly asked for clarification). A-SER cases are now selected by a rule over the raw text (every listing record says "certain", none says "all" or mentions serials), replacing my hand-picked A330-341, which records R0046/R0061 apply to.
- **Exact-identifier tier in retrieval (system fix for the two SILENT v1 failures A-SUP-01/06).** A record containing an AD number or docket typed in the query now ranks first within its model tier (BM25 and hybrid modes only; the dense-only baseline is unchanged). The test split was not used to tune it; it is a rule, with regression tests on the two failing queries.
- **Make-name ambiguity in the spreadsheet.** Renames and spelling variants of one legal entity are merged (e.g. "Embraer S.A." -> "Embraer", "Eurocopter France" -> "Airbus Helicopters", "Bell Helicopter Textron" -> "Bell Textron, Inc."); distinct legal entities of one manufacturer share a make family (Gulfstream, Rolls-Royce, Pratt & Whitney, Bell, Textron Aviation/Cessna). Reasons per name in docs/make_audit.md.
- **Out-of-scope gate.** "Which proposed AD addresses loss of torque on ...?" is a lookup and is no longer refused (manual case M-01 would have been a false refusal); "What torque value / which P/N should I order" is still refused.
- **Verifier grounding.** Spelled-out numbers ("three inspections") are now grounded like digits; "the existing AD requires ..." is treated like "AD 2024-05-13 requires ..." (a description of the superseded final AD, not a mandate claim).

### v2 result in one line

S2 on the 44 auto test cases: 0 failures flagged; refusal F1 1.0 and status accuracy 1.0 (n = 35), Recall@5 83.3% (n = 18, v1 72.2%). Contaminated as explained above.

**The three remaining S2 Recall@5 misses are label limits, not clear errors, and I did not relabel them after seeing test.** A-LOOK-01 (402C) and A-EMPTY-01/03 (EMB-120) expect only the records whose sparse Model column lists the aircraft. S2 ranks first other records that also concern it by Subject Heading (e.g. R0397 "Cessna Aircraft Company Models 402C and 414A", R0351/R0431 "EMBRAER Model EMB-120"), and the expected record comes in at rank 6 or 7, inside the top 8 shown to the user. Recall@5 counts these as misses. A fair label would list every record whose heading or summary names the model, and that needs a human.

**Unconfirmed manual cases (17 on the test split, reported separately in EVAL.md):** two SILENT failures are worth the user's attention. M-09: the engine says APPLICABLE for a 206L-4 when the summary limits the proposal to helicopters with a given STC (the engine has no STC rule). M-17: "737-900ER" is not matched to the record that lists the 737-900 series (shown as UNDETERMINED, which is visible), and the record also fell out of the top 8.

### Still true from v1

**Too good to be true:**
- **B1 BM25 Recall@5 is high** because auto lookup and supersession queries contain the exact model or AD token, which is where keyword search is strongest. This is a property of auto-generated queries, not evidence that keyword search is enough. Manual paraphrase cases (pending review) are designed to test this.
- **Engine accuracy** on auto cases: expected verdicts come from the same Model column the engine reads (circular), and n is tiny. The known engine weaknesses (STC-conditional applicability in R0044, the "900ER" typo in R0155) are in the manual cases, which are pending human review.
- **Dev tuning F1 = 1.0** on 22 dev cases, with 24 of 54 threshold settings tied. The dev split cannot separate them; the previous placeholders (0.62 / 0.90) were kept by the tie-break rule.

**Not measured (no valid API key in data/.env):**
- Every S0/S1/S2 answer was extractive, so S0, S1 and S2 differ here only by engine and gates.
- Answer-quality layer rates, the human-audited unsupported-claim rate and the LLM judge are NOT MEASURED. claim_audit.csv has no rows.
- Latency and $0 cost exclude LLM calls.
