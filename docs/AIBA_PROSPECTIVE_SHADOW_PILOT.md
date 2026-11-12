# AIBA prospective shadow pilot — freeze monitoring coverage, not a retrospective story

**Implementation:** Offline, bounded preflight of the *existing* worldwide
behavioral registry and the most recent behavioral fusion record.
The feature **cannot issue an operational warning**, infer hostile intent,
or change Atlas status. It can capture the amount of data and uncertainty
AIBA was actually observing when a future 24-hour review window opened.

## Why this is a new gate

An evidence ledger containing only predictions is not an evaluation
denominator: analysts also need to know where AIBA was watching,
which sources were unavailable, and whether a zero-candidate interval
really meant zero observed anomalies. **Zero candidate warnings is
not evidence that no event occurred or that the world was covered.**

The PR extends the existing SHA-256-chained, local-only
tipper ledger with a separate record kind: **frame**. Frames do NOT
contain a specific geopolitical event prediction and are never
counted in the numerator or denominator of forecast hit rates.
An issued tipper remains a distinct, later event initiated by an
analyst using the PR #44 issuance protocol.

## Inputs and stop conditions

Production-shaped inputs, without introducing new collectors:

- aiba-feed-data/observations/latest/behavioral_registry.json
  (aiba.behavioral-observations.v1)
- aiba-feed-data/observations/latest/behavioral_fusion.json
  (aiba.behavioral-convergence-shadow.v1)

Requirements for an eligible source-coverage frame:

- Both current snapshots were produced within **90 minutes** of the
  actual checker clock; no future records, mismatched registry_asof,
  or old/initial source baseline. This is a bounded design
  threshold, not a proof that every provider actually sampled the
  relevant geography.
- The complete source-health dictionaries must match, with each
  provider's published source_scope, missingness and status
  preserved. Unavailable/partial sources remain explicit and
  cannot be read as quiet observations.
- Candidate counts must be consistent with the actual review list;
  truncated cross-family lists fail. A review group must have
  source-declared geography, multiple source families, providers
  and roots, at least two observation IDs, no future timestamps,
  and **status unreviewed**. This is just a provenance consistency
  check, not proof of source-root causal independence.
- No upstream warning promotion, probability, automatic severity
  change or automatic actor attribution.
- A newly generated prospective start time (2 minutes after local
  capture) and 24-hour horizon. Frames are never backdated and
  are stored as an additional event in the same chain as actual
  separately reviewed tippers.
- Source bytes are SHA-256 hashed before framing. The private
  ledger records hashes and aggregate coverage, not aircraft
  locations or individual source observations.

## Read-only preparation

Use a current local checkout of the *data branch* (not the
historical static data on main). For example, in GitHub Actions
or in an isolated work directory with two repository worktrees:

~~~bash
python scripts/aiba_prospective_shadow.py \
  --registry /private/state/observations/latest/behavioral_registry.json \
  --fusion /private/state/observations/latest/behavioral_fusion.json \
  --receipt /private/aiba-shadow-preflight.json
~~~

The default is **check only**. It does not write a ledger entry.
The resulting receipt reports the source hashes, future frame
window, provider coverage, degraded providers, and review counts
but contains NO specific actors or aircraft coordinates.

### Explicit local freeze (disabled by default)

~~~bash
python scripts/aiba_prospective_shadow.py \
  --registry /private/state/observations/latest/behavioral_registry.json \
  --fusion /private/state/observations/latest/behavioral_fusion.json \
  --mode freeze --ledger /private/aiba-shadow-ledger.jsonl \
  --receipt /private/aiba-shadow-preflight.json

python scripts/aiba_tipper_ledger.py verify \
  --ledger /private/aiba-shadow-ledger.jsonl
~~~

The local ledger must live **outside the public Git checkout**.
Frame entry hashes and original snapshot hashes are available
to anchor in later trusted storage; the local machine clock
and mutable filesystem do not yet prove issuance time.
Do not publish actual tipper predictions or provider-specific
operational details to an open Git repository.

### Manual GitHub Actions readiness check

After PR merge, use **Actions → Manual AIBA prospective shadow source
readiness → Run workflow**. This workflow:

- checks out both the live source code and existing aiba-feed-data
  evidence branch read-only;
- performs exactly the same check as the CLI, including the strict
  90-minute snapshot age limit;
- uploads a short aggregate JSON receipt even on failures; and
- does **not** issue forecasts, freeze a ledger frame, create
  monitoring risk sets, change source evidence or modify any
  production hotspot.

A red readiness run due to stale data is meaningful missingness,
not an absent event or collector "success". This is deliberately
manual (no new polling job or cloud service).

## Concrete non-event handling

A freshly frozen frame records e.g.:

- AIBA observed X new single-source leads and Y cross-family
  co-occurrences (investigatory, not automatically escalated);
- some named feeds returned "current", some "current_partial",
  others "stale_or_unavailable";
- no-event inferred = false, source completeness verified = false,
  approved tippers = 0.

A **future no-event adjudication** still needs a pre-defined
geographic/actor/action risk set plus independent evidence of
complete event ascertainment for the full horizon. A framed
coverage report is not sufficient.

## Trial sample and near-term evidence

The latest behavioral fusion snapshot inspected on November 12,
2026 at 19:56:26 UTC recorded **1 new single-source lead, 0
cross-family review groups, 0 approved warnings**, and mixed
source coverage (including one unavailable maritime provider and
partially sampled air/maritime restrictions). This is a useful
**data-readiness** example, NOT a prospective issued alert or
a retrospective opportunity to claim a true negative.

The checked source files must still be fresh relative to the
actual pilot execution clock. The code will correctly reject
them as stale when they have aged past 90 minutes.

## First real source preflight outcome (November 12, 2026)

The one-off PR45 real-source test read the **actual current
aiba-feed-data branch** using read-only GitHub Actions checkouts.
It used no live new collector, no source writes and no automatic
warning/ledger issuance.

- [Experiment run](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/43321912652)
- [Permanent aggregate receipt and source freshness audit](evidence/aiba-shadow-real-preflight-2026-11-12.json)
- Source branch latest snapshot from 19:56:26 UTC on Nov 12:
  one new unreviewed source-only lead, zero cross-family nominations,
  zero approved warnings, unavailable NGA source and partial
  official air/maritime sampling.
- **Result:** unavailable / source_snapshot_stale_or_future.
  On the runner this source material had aged **more than the
  predeclared 90-minute freshness ceiling**. It was NOT a prospective
  frame, not a negative event, and not a miss.
- No frozen warning or future outcome was registered. A previous
  successful collector run is insufficient evidence of fresh
  current monitoring if the latest snapshots are stale.

The latest evidence-branch commit at the preflight was
18fc0f38bfc0956eba0612beb2b458581eb0539c. Multiple
past scheduled collection jobs succeeded, but their timing was
irregular: the missing newer snapshot must be investigated
before relying on 24-hour prospective coverage. Scheduled GitHub
Actions run time is best-effort and a successful prior job does
not prove punctual ongoing collection.

The test-only workflow used for this one-off live check
was removed from this PR after the aggregate receipt was saved.
No new recurring job was added.

## Evaluation plan

1. In manual, local shadow mode, capture actual snapshots as
   they occur and externally anchor each frame/issued forecast
   hash and timestamp; do not post hoc reissue old frames.
2. Pair those with *deliberately reviewed and specific* forecast
   hypotheses for any independently credible new preparation
   signals. Do not infer actors or hostile intent from a source
   proximity co-occurrence. A warning with a generic country
   name and unbounded "something bad might happen" proposition
   must not pass the issuance process.
3. Preserve quiet coverage intervals and global blind spots.
   Define registered monitored units/actor action outcomes and
   compare matched events **only on units for which event
   ascertainment was verified**.
4. Compare issued forecasts with original publication timestamps,
   not GDELT ingest dates; adjudicate actor-action-location-horizon
   matched events using independent primary sources and, where
   applicable, actor/dyad-specific UCDP episodes.
5. In rolling out-of-sample windows track lead time, verified
   false warnings per analyst-day, source outages, time to review,
   confidence calibration, and missed independently discovered
   events. Never count unobserved outcomes as no-event labels.

## Rollout restrictions

- No new schedule and no automatic forecasting workflow. The manual
  read-only GitHub Actions readiness check can be dispatched after
  this PR is merged; it produces an aggregate receipt and fails red
  when source snapshots are stale. It does not write any ledger entry.
- No GCP cost, IAM, secrets or external write integrations.
- No automatic ledger issuance, forecast generation or warning
  change. Manual prospective judgment remains required.
- No claim of trusted timestamps or strong statistical validation
  until the independent anchor, risk sets and adjudication sources
  are operating and assessed.
