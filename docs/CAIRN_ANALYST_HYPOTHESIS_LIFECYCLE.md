# CAIRN analyst hypotheses: activation and routine evaluation

## Lifecycle

Analysts add a hypothesis from a standing case's ACH in `hypotheses.html`. The page opens a public, authenticated GitHub issue with the standing case ID and natural-language statement. The authorized owner labels the issue `cairn-hypothesis-approved`. The owner-gated GitHub Actions intake creates a stable `analyst-...` hypothesis ID in `data/hypothesis_reviews.json`, runs an **initial one-time backfill** against the retained public source archive from `aiba-feed-data`, and opens an explicit reviewable PR. Only once that PR is merged will the analyst hypothesis appear as a native column in the case's ACH.

An analyst hypothesis has the same case, collection, evidence-family, and semantic screening cadence as existing alternatives. The ordinary `Validate and publish AIBA` collection job re-evaluates all standing cases within a 40-case explicit cap. No analyst-specific recurring collection job is added. The original one-time historical backfill is frozen in the approved registry; only new source data and the ordinary case assessment can change subsequent provisional evaluations.

### AI availability

Set **OPENAI_API_KEY** as an Actions secret and **CAIRN_SEMANTIC_MODEL** as an Actions variable before enabling live interpretation. Without both, the initial backfill still indexes bounded, provenance-linked historical candidates but records `interpretation_pending`, **not a completed model analysis**. Subsequent ordinary semantic assessments also remain unconfigured. No signed evidence directions are invented.

### Evidence quality and caution icon

Each analyst entry stores an initial `source_inventory`, stable `evaluated_source_ids`, a bounded set of `source_references`, candidate model judgments when available, and plain-language `limitations`. A partial/missing/failed evaluation displays a small amber caution icon next to the analyst hypothesis in the ACH header. It expands on hover, keyboard focus, and click/touch, without adding a permanent block of methodological text. The case tile offers the same access when an analyst alternative has a limitation.

Sources in a one-time backfill are **historical reference candidates**, not current-verified incidents or independent corroborations. Their provisional model classifications may be displayed with an `≈` prefix in ACH cells, clearly separate from reviewer-signed `+` / `−`. A normal collection can also add new provisional candidate directions. Neither process changes `balance` or creates signed ordinal `reviews`/`ach_reviews`.

### Explicit boundaries

- This iteration supports adding alternative explanations to existing standing cases; it does not create entirely new incident cases.
- The current user-facing ACH layout supports **three alternatives per case**, including any existing dossier alternative. Intake refuses a fourth, rather than silently hiding it.
- Historical retrieval is bounded by CAIRN's retained public archive, distinct-information-root deduplication, case association and a maximum of 24 source candidates. It does not establish complete time, geographic, or sensor coverage.
- The routine semantic runner now evaluates every standing case each existing collection cycle when configured, up to the published 40-case cap. A case beyond the cap remains explicitly not selected. For larger boards we should introduce a batch-completion queue rather than claim complete coverage.
- Intake creation is not a live browser API; GitHub Pages cannot securely persist analyst edits. The GitHub issue → owner approval → one-time backfill → PR merge route is the supported write transaction.
- Production AI remains inactive until the operator separately supplies an authorized credential and model. No live semantic model accuracy has been established by synthetic tests.

## Tests

`python -m unittest tests.test_analyst_hypothesis_lifecycle tests.test_semantic_ach -v`

The full CI suite also exercises the hypothetical analyst ACH column and accessible caution popover in Playwright.
