# AIBA: independent real-report extraction and event-link evaluation

## Scope and status

This implements the **offline evaluation infrastructure**, not an independently
annotated real-world corpus and not operational validation. **No real article
bodies or human judgments have been added to the repository.** The tests use
fictional text solely to verify evaluator behavior. No external article fetch,
scraping, new cloud job, credentials, alert modification or auto-deployment is
authorized by this component.

### Milestone 1 — Source intake and provenance (implemented)

Create a private, permission-appropriate UTF-8 JSONL file of source documents,
one per line, with:

```json
{"id":"r001","source_url":"https://example.org/news/unique-article",
 "source_family":"commercial_media","source_text":"Original source report text here.",
 "story_lineage_id":"original-publication-family-001",
 "rights_basis":"permission_granted",
 "retrieved_at":"2026-11-13T15:00:00Z",
 "first_observed_at":"2026-11-13T15:00:00Z",
 "source_published_at":"2026-11-13T14:00:00Z",
 "title":"Original title","split":"heldout"}
```

Allowed rights flags: `public_domain`,
`licensed_for_internal_evaluation`, `permission_granted`,
`short_permitted_excerpt`. The rights flag is an operator attestation,
**not automatic evidence that a source's license permits copying**; confirm
terms independently and avoid committing licensed full-text articles. Keep
local source text protected and use only source-specific HTTPS URLs.

Missing source body, rights attestation, retrieval timestamp, story-lineage ID,
or split causes rejection. Source families and roles must be explicitly eligible.
Each family of syndicated and directly reprinted publications MUST have the
same lineage identifier. Split leakage across lineage groups fails closed.

### Milestone 2 — Independent blind labeling (packet generation implemented)

```bash
PYTHONPATH=. python scripts/aiba_real_report_eval.py \
  --mode prepare --reports private/reports.jsonl \
  --output private/reviewer_packets
```

This writes independent reviewer A and B packets **without model predictions**.
Two annotators independently inspect the *source text*, not extractor output.
They supply `claims` (empty array for no extractable incident), each containing
`actor_text`, `action` (canonical controlled verb), `object_text`,
`assertion_status`, and exact source-text evidence `{start,end,text}`.
Offsets are Python string character positions, 0-based, end-exclusive.

Annotators should separately label uncertainty, conditional language, negation,
quoted or nested attribution, passive voice, whether a real event is claimed,
source-declared event time/site vs editorial office/notice area, and whether a
source is copying another. These richer categories are future schema extensions;
the current evaluator scores exact actor/action/object/status + evidence span.

Adjudicate disagreements after independent coding. Save the final one-row-per-
report gold file as `private/adjudicated.jsonl`, with
`annotator_id="ADJUDICATED"` and a nonempty `adjudication_id`. Keep original
reviewer A/B labels for audit.

### Milestone 3 — Report pair truth and scoring (implemented)

Create `private/pairs.jsonl`, one report pair per row:

```json
{"a":"r001","b":"r002","label":"different_event","adjudication_id":"pair-001"}
```

Permitted labels: `same_event`, `different_event`, `same_story`,
`same_document`, `uncertain`. Require adjudication and put pairs only
within the same split. A related but different event is a negative for
false same-event nomination. Uncertain truth is excluded, not silently scored
as a negative.

```bash
PYTHONPATH=. python scripts/aiba_real_report_eval.py \
  --mode score --reports private/reports.jsonl \
  --reviewer-a private/reviewer_A.jsonl \
  --reviewer-b private/reviewer_B.jsonl \
  --adjudicated private/adjudicated.jsonl --pairs private/pairs.jsonl \
  --output private/results.json
```

Evaluation refuses a missing reviewer, invalid spans, cross-split pairs,
lineage leakage and incomplete adjudication. Reports overall **and separately
by development/heldout split**: exact claim precision, recall, F1, abstentions,
correct rejection of negative reports; pair same-event precision, recall,
false same-event nominations and acceptable relationship classification.
Disagreement counts and IDs are retained for inspection. Full report contents
are not included in the resulting metrics JSON.

### Remaining work (not claimed complete)

1. Source-permission-aware ingestion of real incident articles with explicit
   body-availability, publication identity, access rights and timestamps.
2. Recruit or coordinate two genuinely independent annotators and adjudication.
3. Sample sources across provider families, event types, negative reports,
   geographic ambiguity, contrary evidence and duplicated/syndicated coverage.
4. Freeze a held-out source-lineage-disjoint corpus before tuning.
5. Publish errors, confidence intervals and detection/false-merge rates by source
   and event type, including missed events due to unavailable body text.
6. Only after robust validation, connect **unreviewed candidate** links to the
   Behavioral panel; never inject them directly into warning severity.

**Never interpret a high synthetic score or a small convenience sample as
validated operational accuracy.** This tool is for evaluation and audit.
