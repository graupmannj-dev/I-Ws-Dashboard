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
| M2: Incremental inference | NOT STARTED | Move expensive optional Phi inference off the source-publication critical path. Hash evidence packets; reuse only exact-match validated results with explicit generated time and freshness. Changes, errors and staleness fail safely; measured no-regression source publication latency. |
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

- **M1 PR #113:** merged as `8531522471fcccd9f2e9c958731f5545bd44bd74`, live smoke and full CI passed; production [run 45408587481](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/45408587481) collected and deployed successfully.
- **Observed M1 outcome:** **9/10** structurally valid provisional outputs; `horn_ethiopia_eritrea` and `taiwan` recovered on the one-time format retry, while `iran_gulf` failed `invalid_note_count` despite retry. Output contained zero approved ACH directions.
- **M1 PR #115:** structural reliability audit merged as `2ec2b1b0182abda729b32dde50a796511e935bc5`; full CI passed. Acceptance requires 5 distinct runs and 50 actual case-runs; **not yet achieved**.
- **Current engineering branch:** `fix/cairn-phi-m1-note-bounds`. Hard-bound source notes in the runtime JSON schema (6 normally, 3 on format retry), retain fail-closed validation, add live smoke tests.
- **Next action:** Test and merge the note-bound PR only if GitHub's pinned live Phi smoke and full CI succeed. Then inspect a new production `cairn-semantic-ach` artifact for `iran_gulf` and measure model runtime. Do not claim M1's 98% threshold from one improved production cycle. M2 decoupling will be necessary if CPU runtime remains close to the 19-minute hard limit.
- **Cross-session tracker:** [issue #114](https://github.com/graupmannj-dev/I-Ws-Dashboard/issues/114).
