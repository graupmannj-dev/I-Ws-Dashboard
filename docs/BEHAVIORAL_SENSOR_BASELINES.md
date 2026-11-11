# Behavioral OSINT provider baselines — what we can and cannot compare

## Purpose

Normalize and retain the evidence first, then characterize what is
**ordinary for each actually monitored provider** before claiming
anomalies or anticipatory indicators. An action can be unusual in one
source without proving any threat; two source anomalies can arise from
one common trigger. GDELT remains contextual and UCDP validates
historical outcomes separately.

## Measured unit of analysis

This initial baseline is deliberately **per provider, per UTC-day
latest accepted source snapshot**. It is not:

- an observed 24-hour world event count;
- country, dyad or precise route activity;
- a historical AIS or ADS-B aircraft sample;
- an unbiased estimate of globally missing incidents;
- a calibrated anomaly threshold, hostile-preparation probability or
  demonstrated warning lead time.

Normalized `behavioral_registry.py` now records a frozen
`snapshot_counts_by_mode` and `first_seen_counts_by_mode` into each
run's immutable source ledger, alongside source health and actual
per-provider `checked_at` clocks. That is the denominator: an
unavailable provider has count `null`, NEVER 0.

`behavioral_baselines.py` reads up to the previous 28 UTC dates:

1. Excludes historical records from before source-specific counters
   existed. They cannot be treated as a day of zero activity.
2. Requires the provider to have actually been checked on the
   evaluation date. Repeated AIBA fusion runs displaying the same
   older provider snapshot are not independent samples.
3. Uses at most **one source snapshot per provider per date**, chosen
   by the actual provider observation clock.
4. Excludes days with known provider outages; keeps partial versus
   complete sources in separate comparison populations.
5. Records **source days seen**, **source days missing**, first
   provider baseline exclusions, and the latest source-visible
   record count.
6. Requires **14 comparable observed provider days** and at
   least 13 valid post-baseline daily first-seen measures before
   reporting descriptive medians/MAD.
7. Outputs `status=descriptive_reference_only` at best. No
   automatic behavioral score, probability, significance threshold,
   Alert or Critical promotion follows.

The 14-day minimum is an **engineering adequacy threshold for
showing a descriptive reference**, not a validated 14-day
conflict-prediction benchmark. The daily distribution is not yet
weekday/season-adjusted, and repeated source snapshots can be
serially correlated.

## Source scope and selection

Current source families include IODA connectivity (first page),
NGA and AMSA maritime notices, US/UK protective advisories,
trade-press headlines, selected market contracts, and after
the previous PR, FAA TFR and Danish Niord notices.

The last two are:
- **FAA TFR:** only US airspace restrictions in the collector's
  selected feed, subject to unsupported geometry and incomplete
  upstream schema;
- **Danish Niord:** Baltic/North Sea regional maritime notices,
  not global vessel route measurements.

These sources often report partial results because unsupported
notices are excluded for structural validity. A partial snapshot
must NEVER be treated as complete world coverage.

## Files and site

- `observations/history/behavioral_registry/<asof>-<run>.json`:
  original per-provider status and measurable source counts.
- `observations/latest/behavioral_baselines.json`: rolling
  28-day descriptive reference and coverage gaps.
- `observations/history/behavioral_baselines/<asof>-<run>.json`:
  append-only baseline audit receipts.
- Published `/behavior/` page: separate table displaying
  provider history readiness and median snapshot counts (only once
  adequate history accumulates). Publication still warns if the
  fusion source is stale.

No additional external provider queries or VM/cloud configuration
is required. All three existing scheduled source-collection
workflows compute the baseline after their normal registry/fusion
audit and commit to the same evidence branch.

## Next engineering acceptance gates

Before treating any behavioral departure as a **preparation
anomaly**, we need:

1. A reviewed **stable geographic or route observation frame**
   established before outcomes (not a footprint invented from
   the notice we later want to predict).
2. Source-specific **exposure** (sampled routes, receivers,
   ships/aircraft seen, scheduled outages, pagination and
   source uptime) that makes source absences interpretable.
3. Observation-specific **timing**: earliest public availability,
   true actor action versus source announcement, and AIBA first
   observation. A scheduled exercise is not equivalent to an
   unscheduled deployment.
4. Independent **causal roots**, negative evidence and competing
   benign explanations.
5. Frozen, prospective **events and non-events** across a
   representative observation universe; UCDP-only violent-event
   labels are insufficient for coercion, deployments or crises
   avoided through deterrence.

We should only introduce scoring weights after those foundations
produce enough evaluation evidence to measure false alarms and
useful advance notice.

## One-time deployment check

After merging the official-restriction adapter PR and this baseline
PR, run existing **Collect AIBA near-current map restrictions**
once. Inspect `observations/latest/behavioral_baselines.json`.
The expected first result for the new sources is
`insufficient_comparable_source_days`, not an anomaly
or a warning. Their medians become available only after comparable
observations accumulate, if the provider data quality permits.
