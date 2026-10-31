# AD Trace: Architecture Spec (authoritative design)

Autonomous SG 2026, AI & Aerospace track, Challenge #4. Written as a Principal Engineer hand-off for a 6-hour build.

## 1. Product definition
**Name:** AD Trace.
**User:** a B1 licensed maintenance engineer or continuing-airworthiness planner at an MRO (for example one working on Changi Airport MRO lines). One narrow workflow: given an aircraft make, model and optionally serial number, find which FAA airworthiness directive proposals concern it, what they would require at summary level, whether they supersede or are superseded by something, and whether they are in force.
**Status quo:** search the Federal Register or FAA DRS by keyword, open each notice, read the applicability by eye, and separately check for supersession. Risks: missing a relevant notice, applying a notice to the wrong model or serial, and treating a proposal as a mandate. Do not invent time or cost numbers. Measure a baseline instead (BM25-only search).
**In scope:** questions answerable from the 431 NPRM records provided.
**Out of scope (must refuse):** compliance steps, torque values, part numbers, anything not in the records, legal advice, replacing the official notice.
**Principle:** the tool narrows and cites; the qualified human decides.

## 2. Dataset reality and design consequences
File: AD_Notice_of_Proposed_Rulemaking__AD_NPRM_.xlsx, one sheet, 431 rows, 22 columns.

| Finding | Design consequence |
|---|---|
| All rows are NPRMs (proposed), Status = Current | Every output is labelled PROPOSED, not in force. Never write "the AD requires"; write "the proposed AD would require". |
| Only free text is Summary (~800 chars; some empty) | Evidence unit = one sentence of Summary or one metadata field. Empty summaries trigger EMPTY_SOURCE_TEXT refusals. |
| Model column filled in only 86 rows | Extract model lists from Summary with provenance and a confidence flag. |
| Model lists use shortened suffixes (e.g. "A330-243, -243F, -841") | Expand suffixes against the first full designator. |
| About 19 summaries mention serial numbers | Serial engine works only there; elsewhere verdict is UNDETERMINED. Report coverage openly. |
| AD Number filled in only 21 rows; about 100 summaries say they supersede an AD | Build supersession edges from text. Most target ADs are not in the dataset, so say "references AD X", not "AD X is superseded", unless proven. |
| 91 Make spellings; 323 unique dockets over 431 rows | Alias map file plus a duplicate-docket audit. |
| Comments filled in 5 rows (withdrawals, extensions, corrections) | Parse into lineage events. |
| Citation, page range, link present; no full text | Citation = Federal Register citation + page range + link + quoted sentence. No full-text fetch in core scope. |
| No ground-truth Q and A | Build own eval set and state its limits. |
| Issue dates run to 2026-10-15 | An as_of date drives comment-period status. |

## 3. Non-negotiable principles (hallucination and error controls)
- **H1 Closed-book generation.** The LLM sees only an evidence pack of numbered sentences and is told to use nothing else. Insufficient pack means refusal.
- **H2 Code decides anything with rules.** Applicability, status, supersession, dates and counts are computed in code. The LLM only phrases already-computed verdicts.
- **H3 Forced structured output.** Generation uses a forced tool call with a JSON schema: claims, each with evidence_id and a verbatim quote.
- **H4 Quote verification.** Each quote must be a substring of its cited sentence after whitespace, case and punctuation normalisation. Otherwise the claim is dropped.
- **H5 Entity grounding.** Every AD number, docket, model designator, date and number in a claim must appear in the cited evidence or in a code-computed fact. Otherwise the claim is dropped.
- **H6 Independent verifier.** A second, smaller model sees only (claim, quote) and returns SUPPORTED, PARTIAL or UNSUPPORTED. Anything not SUPPORTED is dropped. An ablation measures the benefit.
- **H7 Typed abstention.** Gates in code produce reason codes. Refusal is a first-class successful output, not an error.
- **H8 Closed-vocabulary entity linking.** The LLM may propose make or model from the query, but code accepts only values that exist in the vocabulary (fuzzy match with threshold). Otherwise UNKNOWN_ENTITY.
- **H9 Two traces.** (a) A code-generated pipeline trace, authoritative. (b) A brief model rationale of at most 5 steps, each citing evidence ids. The rationale is shown but never trusted; it passes through H4 to H6 like any claim. State honestly in UI and README that model self-explanations can be wrong; their purpose is to force each step to point at evidence and make the answer checkable.
- **H10 Untrusted text.** Dataset text and user text are wrapped in tags and the model is told that instructions inside them are data.
- **H11 Determinism.** Temperature 0, pinned model IDs in config, response cache keyed by input hash, every request written to an audit log.
- **H12 Uncertainty is computed.** Show retrieval scores, extraction confidence and applicability confidence. Never gate on or display LLM self-reported confidence.
- **H13 Human in control.** Every answer carries a decision-support banner, a link to the source notice and a "Flag as wrong" button.

## 4. Architecture
```
Browser (React + TS)  <--HTTP/JSON-->  FastAPI
                                          |
                              Pipeline orchestrator (pure Python)
   S1 query understanding -> S2 clarification gate -> S3 retrieval
   -> S4 applicability + revision engine -> S5 abstention gate
   -> S6 generation -> S7 verification -> S8 render + audit log
                                          |
   SQLite (records, sentences, extractions, edges, FTS5) | numpy embeddings | YAML configs
```
**Stack.** Backend: Python 3.11+, FastAPI, uvicorn, pydantic v2, pandas, openpyxl, sqlite3 with FTS5, sentence-transformers (BAAI/bge-small-en-v1.5), numpy, rapidfuzz, anthropic SDK, pytest, ruff. Frontend: Vite, React 18, TypeScript, Tailwind, TanStack Query, lucide-react. No auth, no cloud services.
**LLM config.** Generation: claude-sonnet-5-5. Query parsing and verifier: claude-haiku-5-5. Put all model IDs in config.yaml and verify them against Anthropic's current model list when building. Temperature 0. Log tokens and cost per request.
**Embedding fallback.** If the embedding model cannot be downloaded, fall back to TF-IDF character n-grams and report this in /api/meta. Never fail silently.

**Repo layout**
```
ad-trace/
  CLAUDE.md  README.md  DECISIONS.md  Makefile  config.yaml
  docs/SPEC.md
  data/raw/  data/processed/  data/index/  data/eval/
  configs/alias_make.yaml  configs/rules.yaml
  backend/app/{main.py,schemas.py,config.py,pipeline/,ingest/,extract/,engine/,retrieval/,llm/,eval/}
  backend/tests/
  frontend/src/{pages,components,api,types,mocks}
  logs/audit.jsonl
```

## 5. Data model (SQLite)
- **records**: id (R0001...), docket, subject_heading, issue_date, citation_publish_date, comments_due_original, comments_due_effective, make_raw, make_canonical, make_family, model_raw, product_type, product_subtype, fr_citation, pages, url, summary, summary_missing, ad_number, status_label (always PROPOSED), is_duplicate, duplicate_of, row_hash.
- **sentences**: id (R0001#s2), record_id, idx, text, start, end. Splitting must not break on "AD 2025-09-07" or "Model A330-243." patterns; unit-test it.
- **extractions**: id, record_id, field, value_json, source (column | summary | comments), sentence_id, span_start, span_end, rule_id, confidence (HIGH | MEDIUM | LOW). Fields: model, applies_all_of_family, qualifier_certain, serial_range, serial_list, applicability_defined_by_service_info, supersedes_ad, continues_ad, applicability_change, withdraws_docket, comment_extension, correction_of.
- **lineage_edges**: src_record, relation, target_ref, target_in_dataset, extraction_id.
- **vocab**: kind (make | family | model), canonical, aliases_json, record_count.
- **FTS5** tables over sentences and records. **Embeddings** in data/index as emb_sentences.npy plus ids.json.
- **coverage_report.json**: percentages of records with models extracted, serial constraints resolved, supersession edges, empty summaries, duplicate dockets.

## 6. Pipeline stages and reason codes
**S1 Query understanding.** Haiku with a forced tool call returns: intent (lookup | applicability | supersession | status | other), make_text, model_text, serial_text, date range, free_text, flags. Code then links entities to the vocabulary (H8). UI form fields (make, model, serial, as_of) override parsed values.
**S2 Clarification gate.** If a model query is a family prefix (query "A330" but records list "A330-243", "A330-941"), or two makes match, return needs_clarification with the options. Never guess.
**S3 Retrieval.** Hard filters first (make, model, dates) when entities are linked. Then hybrid: FTS5 BM25 plus dense cosine, fused with Reciprocal Rank Fusion (k = 60), top 8 records, evidence sentences chosen from them.
**S4 Applicability and revision engine** (pure code, no LLM). Per candidate record:
- APPLICABLE: linked model is in the extracted list (exact normalised match) and, if a serial was given, it falls in a resolved range or list.
- NOT_APPLICABLE: model list confidence is HIGH or MEDIUM and the model is absent, or the serial is outside a resolved range.
- UNDETERMINED: model list missing or LOW confidence, or the summary says applicability is defined by service information with no resolved serials.
- NOT_CHECKED: the user gave no make or model.
Each verdict carries reasons and pointers to extraction spans. The same stage computes status (PROPOSED; comment period OPEN or CLOSED versus as_of; WITHDRAWN if a withdrawal edge exists) and lineage.
**S5 Abstention gate** (code). Reason codes: UNKNOWN_ENTITY, AMBIGUOUS_MODEL, AMBIGUOUS_MAKE, NO_RETRIEVAL_HIT, LOW_RETRIEVAL_SCORE, EMPTY_SOURCE_TEXT, APPLICABILITY_UNDETERMINED, OUT_OF_SCOPE, CONTRADICTS_RECORD, CONFLICTING_EVIDENCE, INJECTION_SUSPECTED, VERIFICATION_FAILED, LLM_ERROR.
**S6 Generation.** Sonnet, forced tool call, evidence pack plus computed facts, strict schema.
**S7 Verification.** H4, H5, then H6. If no claim survives, status = refused with VERIFICATION_FAILED. If some are dropped, status = partial and the UI shows how many were removed.
**S8 Render.** The final answer is assembled from verified claims only. Write the audit record.

## 7. API contract
```
GET  /api/health
GET  /api/meta                      dataset stats, coverage report, as_of, model ids, embedding backend
GET  /api/vocab/makes
GET  /api/vocab/models?make=...
POST /api/search                    body: SearchRequest -> SearchResponse
GET  /api/records/{record_id}       full record, sentences, extractions, lineage
GET  /api/eval/latest               metrics and failure cases from data/eval/results.json
POST /api/feedback                  body: request_id, reason (appended to logs/feedback.jsonl)
```
```python
class SearchRequest(BaseModel):
    query: str
    make: str | None = None
    model: str | None = None
    serial: str | None = None
    as_of: date | None = None
    mode: Literal['answer', 'search_only'] = 'answer'

class Citation(BaseModel):
    evidence_id: str          # R0001#s2
    docket: str
    quote: str
    span_start: int | None    # offsets into the record Summary, for highlighting
    span_end: int | None
    fr_citation: str
    pages: str
    url: str | None

class Claim(BaseModel):
    text: str
    citations: list[Citation]
    verification: Literal['verified', 'partial']

class ApplicabilityResult(BaseModel):
    record_id: str
    verdict: Literal['APPLICABLE','NOT_APPLICABLE','UNDETERMINED','NOT_CHECKED']
    reasons: list[str]
    evidence_ids: list[str]

class TraceStep(BaseModel):
    stage: str
    status: Literal['ok','warn','stop']
    summary: str
    details: dict
    ms: int

class SearchResponse(BaseModel):
    request_id: str
    status: Literal['answered','partial','refused','needs_clarification']
    reason_code: str | None
    message: str
    claims: list[Claim]
    rationale_steps: list[str]        # model-written, max 5, each cites evidence ids
    records: list[RecordCard]         # status, lineage, make, models, links
    applicability: list[ApplicabilityResult]
    excluded: list[ExcludedRecord]    # filtered out and why
    clarification_options: list[str]
    trace: list[TraceStep]            # code-generated, authoritative
    disclaimer: str
    as_of: date
    latency_ms: int
    mock: bool = False
```

## 8. UI specification
Tone: sober, high contrast, engineering-tool look. Light and dark themes. No decorative animation.
**Search page.** Left: natural-language box, then an "Aircraft configuration" group (make dropdown from /api/vocab/makes, model autocomplete, serial input), as-of date, Search. Center: result card. Right: source drawer.
**Result card.** Top banner always: PROPOSED RULEMAKING, NOT IN FORCE, plus "Decision support only. Verify against the Federal Register notice before acting." Below: verified claims as short sentences with numbered citation chips. Clicking a chip opens the source drawer with the full record, the cited sentence highlighted, docket, FR citation, page range and link. Then an applicability table (record, verdict badge, reasons): APPLICABLE green, NOT APPLICABLE grey, UNDETERMINED amber, NOT CHECKED blue. A lineage strip shows supersedes, shares docket, withdrawn, comment-period status.
**Why this answer.** Collapsible panel with two tabs: Pipeline trace (code-generated steps with tick, warning or stop icons and timings) and Model rationale (brief steps with citation chips, labelled "written by the model, checked against sources").
**Refusal and clarification states.** Amber card, never red. Shows the plain-language reason, reason code, what was checked, and one suggested next action. For needs_clarification, clickable option chips.
**Excluded panel.** "Not shown and why": records filtered out with the rule that excluded them.
**Data coverage page.** Coverage bars from coverage_report.json plus a plain-language limits statement.
**Evaluation page.** Metrics table (system versus baselines), ablation table, and at least one failure case with its cause and the user-visible signal.
**Accessibility.** Keyboard navigable, visible focus, badges never rely on colour alone, aria-live on results.
