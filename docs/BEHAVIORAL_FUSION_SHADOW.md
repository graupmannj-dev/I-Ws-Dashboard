# Source-first behavioral fusion — unreviewed investigation, not predicted conflict

## Mission change

AIBA's primary question is **"What observable preparations may be taking
place before a consequence becomes widely recognized?"** not merely
"Which news-coded confrontation is getting more coverage?"

The behavioral registry (PR #30) is a source-separated ledger. This
PR adds `behavioral_fusion.py` to compare **source-declared geographic
overlaps**, never forcing arbitrary reporting into one of the curated
cases. GDELT and UCDP stay separate: GDELT can provide contextual
history; UCDP can label subsequent outcomes. Neither is a gate to
retain behavioral signals or nominate new areas.

## Fixed mechanical triage rules

1. The latest normalized registry must be within 20 minutes of the
   fusion run. Its **first run is only a baseline**. A failed/stale
   provider is not scored as a quiet observation.
2. Candidate observations must be **first observed by AIBA within the
   previous 72 hours**. For sources with a known publication date,
   that date also must fall within the previous 72 hours. Older
   retrieved notices are background context, not sudden new activity.
3. Keep all source types (including media mentions and markets) in
   the **single-source review queue**. Media and market quotes do
   **not** independently confirm actor behavior.
4. Cross-family candidates require exactly matching explicit
   geographic keys, at least **two different source families** among
   connectivity, maritime notices and protective notices, at least
   two providers, distinct information roots, and at least **one
   observation newly recorded in the current collection**. Different
   countries/regions and unlocated records never auto-merge.
5. Replayed evidence stays in the recent audit trail but does **not**
   repeatedly issue "new" convergence candidates. Multiple maritime
   warnings are one family, not several independent kinds of
   preparation.
6. The geographic cross-family result is explicitly
   `cross_family_cooccurrence_unreviewed`. It **does not** prove
   causal independence, hostile intent, preparations or approaching
   hostilities. The producer writes `approved_warning_count=0`,
   `automated_severity_changes=0` and no forecast probability.

These are triage gates, **not calibrated early-warning thresholds**.
A signal can be valuable even without a matched counterpart; it
remains in single-source review instead of being discarded.

## Persistent evidence

Existing half-hour friction and six-hour operational GitHub workflows
run the normalization step followed by the fusion step, then commit
both sets of source-timed records to the existing `aiba-feed-data`
evidence branch. There are no new external collection APIs.

- `observations/latest/behavioral_registry.json`: current source-ledger,
  including uncovered or failed providers.
- `observations/history/behavioral_registry/*.json`: first-observed
  deltas and observation clocks (initial run is only a baseline).
- `observations/latest/behavioral_fusion.json`: current single-source
  lead queue, geographic co-occurrence review candidates, coverage
  and explicit assessment ceiling.
- `observations/history/behavioral_fusion/*.json`: dated, immutable
  comparison trace for future evaluation.

The approved Pages build publishes a read-only
[`/behavior/`](https://graupmannj-dev.github.io/I-Ws-Dashboard/behavior/)
panel and accompanying JSON snapshot, with **stale source warning**
if the source reconciliation is over six hours old. The Atlas links
to it. This does **not** add unverified map pins or modify existing
standing watch severity.

## Important limits

Current observation streams are **not** sufficient to promise
meaningful worldwide multi-source correlation:

- IODA's country/entity level is geographically broad and
  limited by provider paging/time window; it is not a cyberattack
  attribution system.
- AMSA only covers NAVAREA X; NGA area strings are not precise
  incident locations. Two maritime providers are still a single
  signal family.
- Official advice RSS may lack a machine-verifiable country field;
  country terms in text stay **unlocated** until vetted.
- Commercial headlines do not prove that a carrier/insurer took an
  action. Prediction markets are not material logistics or force
  preparations.
- ADSB.lol aircraft snapshots and worldwide AIS/satellite changes
  are **not** yet persisted in the source-normalized ledger.
- Since these sources may not yet share a verified geographic
  resolution, zero cross-family candidates can be a **coverage
  problem**, not evidence of a quiet world.

The design prefers epistemic caution to invented multisource
convergence. Geolocation/entity resolution and additional genuine
behavioral feeds should be integrated through source-specific
adapters with objective provenance, rather than by fuzzy keyword
matching on headlines.

## Evaluating without hindsight

Save the **as-observed** evidence stream before an eventual outcome,
including absence of coverage. Then define an ex ante risk set,
times, scenario definitions, positive and negative windows,
independent actor-level outcome adjudication, and frozen training/
holdout periods. UCDP alone does not label commercial coercion,
military preparation without conflict, or thwarted escalation.

Do not report precision, recall, advance notice, false-alarm burden
or a model probability until those gates are met. In particular,
using cases selected because they later escalated guarantees
selection bias and cannot establish warning performance.
