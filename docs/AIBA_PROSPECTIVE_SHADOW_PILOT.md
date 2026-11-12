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

- No new schedule or GitHub workflow run in this PR.
- No GCP cost, IAM, secrets or external write integrations.
- No automatic ledger issuance, forecast generation or warning
  change. Manual prospective judgment remains required.
- No claim of trusted timestamps or strong statistical validation
  until the independent anchor, risk sets and adjudication sources
  are operating and assessed.
