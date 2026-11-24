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

- **M1 production:** PR #113 runtime [45408587481](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/45408587481) had 9/10 provisional model successes, two successful bounded format retries and one `invalid_note_count` in `iran_gulf`. Model step ~18.5 minutes. PRs #113, #115 and #116 merged with full CI. The >=98% five-run structural gate remains unverified.
- **M2 stage 1:** PR #117 merged as `7395aa97ea401bdb581be7d33186470f5792a167`, implementing exact-input hash/TTL cache and safe sidecar assembly. Full CI passed.
- **M2 stage 2 work branch:** `feat/cairn-phi-m2-postdeploy-sidecar`. A separate `cairn-phi-results` branch exists. Source `hypotheses.json` now includes `semantic_input_sha256` and `phi_async_enabled`. Pages `collect` no longer runs Phi. New serialized `phi-postdeploy` job reads the exact same-run Pages artifact, applies the M2 stage-1 cache, runs only changed cases with pinned local Phi, and writes the provisional sidecar to its isolated branch. The browser requests the sidecar and checks matching hash, timestamp, schema, model, source keys, no signed reviews. Tests cover publisher integrity, browser expiry/invalid links and workflow job isolation. **This cutover is still under development and unverified against the real GitHub pipeline.**
- **Next action:** Open/validate this M2 stage-2 PR, inspect full CI and Playwright output; fix failures; merge only when green. Inspect postmerge Pages deploy, postdeploy job and isolated branch. Confirm the dashboard source publication no longer waits on Phi and actual model results render only for matching packets. If model job fails, preserve source publishing and explicitly report the failure. Do not claim M2 done until verified.
- **M3–M5:** Not started. Next stage after M2 is bounded, attributable original-source text evidence, then historical benchmarking and analyst workbench.
- **Cross-session issue:** [#114](https://github.com/graupmannj-dev/I-Ws-Dashboard/issues/114).

