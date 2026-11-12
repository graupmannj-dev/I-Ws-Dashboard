# AIBA source-cadence audit and prospective coverage reliability

**Purpose:** verify whether each existing source collector actually starts at
a usable cadence. Operational AIBA needs continuous enough fresh inputs before
a model can evaluate *pre-media* warning performance. A missing run is NOT a
no-event observation; a successful run does not establish source coverage.

## Documented collector schedules and limits

| GitHub Actions workflow | Intended schedule (UTC) | Diagnostic threshold |
| --- | --- | --- |
| Collect AIBA near-current map restrictions | minutes 07,22,37,52 (every 15 min) | >30 min between observed workflow start times |
| Collect AIBA structural friction | minutes 13,43 (every 30 min) | >60 min |
| Collect AIBA operational feeds | core 00:17/06:17/12:17/18:17 (6h), plus commercial and weekly audit | >12 h between all operational job starts, **optimistic** |

GitHub Actions schedule delivery is best-effort. Workflow starts shown by the
GitHub API do not prove whether a scheduled slot was emitted and dropped,
delayed on GitHub, cancelled by capacity, or skipped by an executor. They do
prove that the *observed source freshness* cannot be assumed. Separate
provider collection times, availability and error states remain distinct.

The current workflows share the concurrency group
aiba-operational-snapshots, with cancellation disabled. This serializes
writes to aiba-feed-data and avoids push collisions but can add queuing.
We should not remove that constraint without designing safe concurrent
append semantics. Regular GitHub cron delivery needs independent evaluation
before a new control plane is selected.

## November 8–12 initial audit

Public GitHub Actions workflow-run metadata for the existing repository
was inspected with GitHub's API. Across the last four days (sample of
inspected workflow records):

- Structural friction: maximum observed start gap **644 minutes** (~10.7h).
- Live restrictions: maximum gap **635 minutes** (~10.6h).
- Mixed-mode operational: maximum gap **697 minutes** (~11.6h).

These are *observed run-start gaps*, **not inferred real event
misses**, and no source completeness is proven by an eventual successful run.
The core 6-hour collector may have worse true gaps than the mixed-mode
operational figure because commercial/audit jobs also start the same workflow.

The previously tested shadow readiness check correctly refused stale
registry/fusion data stamped 2026-11-12T19:56:26Z. An incomplete workflow
cadence is a priority engineering blocker for a 24-hour prospective test.

## Offline audit script

~~~bash
python scripts/aiba_collection_cadence_audit.py \
  --runs /tmp/aiba-actions-runs.json \
  --registry /tmp/observations/latest/behavioral_registry.json \
  --fusion /tmp/observations/latest/behavioral_fusion.json \
  --output /tmp/aiba-cadence-audit.json
~~~

The runs JSON comes from GitHub GET
/repos/graupmannj-dev/I-Ws-Dashboard/actions/runs with enough pages
to cover the evaluation window. The audit explicitly reports if the
retrieved page range does **not** include the start of the window.
It does not assert that a GitHub Actions run carries an actual source
observation. It identifies (a) latest observed start,
(b) gaps between runs, (c) success/failure/pending statuses,
(d) current registry/fusion freshness and mismatch, and
(e) providers unavailable, partial or bounded.

The default lookback is 72 hours. Failure to read inputs or
validate matching fusion and source-health schemas fails closed.
The returned JSON is a source-readiness assessment and contains
**no threat locations, event hypotheses, raw aircraft tracks or
claims of real warning success**. A cautionary/green result still
records source continuity NOT proven and negative events NOT inferred.

The repository can provide a manual read-only GitHub Actions check
using the same script; no new automatic schedule, external billing
or production source changes are introduced.

## Recommended repair sequence

1. **Near term:** use existing workflow_dispatch collectors for
   source refreshes when human review requires them; keep
   provider missingness explicit. This is not a continuous
   monitoring solution.
2. **Instrument:** measure a full rolling 72 hours of provider-level
   collected_at, scheduled occurrence versus actual workflow starts,
   runner execution/queuing, failure, observation freshness, push
   completion, and source availability. Preserve lag/outage
   intervals as unknown for scoring, never fill forward with
   old values or treat old notices as new actions.
3. **Reliability design:** move the schedule trigger to a dependable
   orchestrator if measured gaps persist. A small authorized
   external cron/GCP scheduler triggering GitHub collection
   workflows could isolate scheduling from extraction, but
   requires explicit review of authentication, IAM, cost,
   GitHub API rate limits, secrets and concurrency behavior.
   **This PR does not create that scheduler.**
4. **Prospective pilot gate:** only timestamp genuinely
   contemporaneous snapshots and explicit analyst-reviewed
   falsifiable forecasts. Preserve no-warning periods without
   calling them verified negatives. Independent timestamps and
   outcome evidence remain separate acceptance gates.

The AIBA strategic value proposition is warning lead time before
public awareness **at an acceptable false-alarm and missed-case
rate**. A collection cadence audit is not itself an intelligence
prediction or a change to existing Atlas watch ratings.
