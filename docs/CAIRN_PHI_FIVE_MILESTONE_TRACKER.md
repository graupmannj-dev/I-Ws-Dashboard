# CAIRN local Phi: five-milestone engineering tracker

This file is the durable restart checkpoint. When work resumes, inspect this file, open PRs and the latest GitHub Actions publication artifacts **before** changing code.

**Scope:** Public-source, provisional hypothesis interpretation only. No automatic ACH direction, signed evidence, source independence, verified event or warning promotion. All inference remains local; public source links are retained but original source text and raw model completions are not publicly published.

## Baseline (24 November 2026)

- Phi-4-mini Q4_K_M integrated and deployed: PRs #110 and #112.
- Production run [45370076686](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/45370076686) reported **7/10** successful provisional interpretations, **3/10** `ValueError` failures.
- Historical cases with failure: `horn_ethiopia_eritrea`, `iran_gulf`, `taiwan`. The old artifact did not expose the underlying validation failure category.
- Existing deployments continued despite failed model cases, and no model-produced ACH direction was approved.

## Roadmap and authoritative gates

| Priority | Status | Deliverables and acceptance |
|---|---|---|
| M1: Reliability | IN PROGRESS | Structured bounded error codes, safe failure summary, at most one format-only retry, invalid-source-ID fail-closed behavior, regression tests. Diagnose persistent failed cases from post-deployment artifacts, and demonstrate >=98% valid outputs on repeated actual production cycles; reliability must be measured, not assumed from a green CI run. |
| M2: Incremental inference | IN PROGRESS | Move expensive optional Phi inference off the source-publication critical path. Hash evidence packets; reuse only exact-match validated results with explicit generated time and freshness. Changes, errors and staleness fail safely; measured no-regression source publication latency. |
| M3: Source-grounded claims | NOT STARTED | Feed bounded, attributable original-text excerpts through the pre-existing allowlisted source inspection; preserve URL, timestamp, place, information root, content excerpt and missingness flags. No claim is verified merely by appearing in retrieved text; test prompt injection and syndication. |
| M4: Historical evaluation | NOT STARTED | Time-fenced ~50–100 packets with predeclared annotations and baseline comparisons, real negatives, known source dependencies, calibrated uncertainty and analyst workload; report denominators and limitations. Do not call synthetic rubrics empirical forecast accuracy. |
| M5: Analyst workbench | NOT STARTED | Hypotheses UI: current changes, source-linked unresolved evidence, alternative explanations, explicit next discriminators, analyst versus model provenance, stale/failed-run indication, browser tests. |

## Workstream discipline

1. One milestone at a time. Each nontrivial release uses a PR, unit/integration test jobs, and an observed post-merge production deployment.
2. Never merge the benchmark-only PR #109 as an implementation shortcut.
3. Preserve the existing signed ACH matrix, warning thresholds, source collector outputs and publication on Phi failure.
4. Every checkpoint update should include PR URL, merged SHA, Actions run URL, measured counts, failure diagnosis, and exact next task.
5. A merged PR is not proof of a fully achieved milestone; use its acceptance criteria to distinguish shipped infrastructure from confirmed performance.

## Current engineering checkpoint

- **M1 deployed result:** [run 45408587481](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/45408587481) produced 9/10 valid provisional outputs, two formatting recoveries and one `invalid_note_count` for `iran_gulf`. Deployment succeeded; no ACH direction was signed.
- **M1 merged changes:** #113 `8531522` (diagnostics and bounded retry), #115 `2ec2b1b` (five-run reliability audit), #116 `cb1df95` (hard JSON note-count schema cap). PR #116 passed full CI and pinned live smoke. Its real-case production result is not yet established.
- **M1 remaining acceptance:** At least 50 actual case-runs and five distinct publication cycles with >=98% structural validity and zero accepted fabricated source IDs; benchmark substantive correctness separately.
- **Active M2 staging branch:** `feat/cairn-phi-m2-incremental-engine`. Implements strict exact-input SHA256 and 24-hour TTL cache selection, generates isolated changed-case batches, and safely assembles a schema-validated Phi sidecar; no production workflow cutover yet.
- **Next action:** Validate and merge the M2 staging PR, then implement postdeploy-only inference, a dedicated public result branch, and browser-side exact-hash/freshness checks in a separate release PR. Never remove the existing Phi user-facing display until the replacement sidecar path has been proven. The website and collectors must publish regardless of Phi availability.
- **Cross-session tracker:** [issue #114](https://github.com/graupmannj-dev/I-Ws-Dashboard/issues/114).

