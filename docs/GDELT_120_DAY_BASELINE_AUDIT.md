# AIBA 120-day GDELT baseline: evidence audit and shadow rollout

## Independently inspected input (November 10, 2026)

- [Historical GDELT backfill Actions run 42743720673](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42743720673)
- Artifact ID **13730990709**, name `gdelt-baseline-2026-07-11-2026-11-07`.
- Manifest reports **120 requested / 120 complete / zero failed** UTC days,
  2026-07-11 through 2026-11-07; 43,756 descriptive replay rows.
- Downloaded archived `daily.jsonl` and audited all 120 records:
  **11,772,072 total GDELT records**, **1,111,048 selected records**
  (**9.44%**) under **EventRootCode 17, 18, 19, 20**.
- **4,850** distinct actor country/country-pair keys across the 120 days;
  **1,636** appeared on exactly one day; **181** appeared on at least
  90 of 120 days.
- The original replay's `robust_z` was null for **22,439 / 43,756**
  case/day rows because historical median absolute deviation was zero.
  Interpretation: zero-inflated or sparse comparison, **not** verified
  absence of conflict or extraordinary predicted risk.
- Selected events/day: median **9,968.5** (range **5,303–13,291**).
  Median weekend selected counts were lower than weekday counts, so
  day-of-week and media-volume confounding warrant further analysis.

These are counts of **news-coded GDELT records**, not independently verified
combat incidents. Media attention, duplicated story roots, named entities,
country-label coding, and active conflicts all affect prevalence.

## Overnight automation audit

- [Successful historical backfill](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42743720673)
- [Successful scheduled operational feed collection](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42774795806)
- [Successful source ingest, checks and Pages deploy](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42801385370)
- [Successful structural-friction job](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42809680492): IODA and AMSA succeeded, NGA returned upstream HTTP 503; health marked partial.
- [Successful map restriction job](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42809623349): source coverage marked partial.
- [Latest successful dashboard build/deploy](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42844424177):
  35/35 GDELT days complete (7/7 recent + 28/28 baseline), 23 unverified
  discovery candidates, Wikimedia 10/15 successful requests.
- Green workflow is not equivalent to complete external-source coverage,
  nor confirmation of the scenario.

## Baseline interpretation

This PR's `scripts/gdelt_shadow_monitor.py` compares one or more **new,
source-compatible 17–20-only daily archives** to the previous **90
calendar days** of event-share observations.

A score is eligible for screening only with:
- At least 28 **immediately preceding valid days**;
- At least 90% coverage of the available pre-day 90-calendar-day window;
- Exact compatibility of the selected event definition and denominator.

For each source-coded case, it computes the prior-day **50th/95th
percentile event share**, the pooled historical event share, and the
number of previously nonzero days. It separates:
- **Established-case deviations** (>=28 days observed, >=50 prior records)
  that exceed 1.5× prior-day 95th-percentile share and 2× pooled share;
- **Sparse/new case leads** (>=10 current records and unusually high relative
  to their limited baseline). These are not assigned a potentially absurd
  ratio to a zero-frequency reference.

Both are **investigative outputs**. These are deliberately uncalibrated
screening heuristics, and both set `executive_eligible:false`.
The script never alters existing AIBA watch severity or executive routing.

Observed example on 2026-11-07 (not an intelligence warning):
`BILAT:RUS:UKR` was 127 records / 1.948% of selected records,
versus 2.141% pooled share over the prior 90 days;
`BILAT:PHL:USA` was 18 / 0.276% versus a prior 0.029% pooled
share. The latter may merit **source-root investigation**, not a military
conclusion or independent causal claim.

## Run the shadow comparison (manual first)

Actions → **GDELT 120-day baseline and forward shadow comparison
(manual)** → Run workflow.

Defaults pin the verified initial artifact run and name. Without
`through`, this computes a clearly marked **historical replay**
for November 7, not today's information.

To ingest subsequent daily archives, enter a `through` day, for
example `2026-11-09`. It downloads **at most 14 daily archives**
beginning November 8 and creates:
- `daily_aggregates.jsonl`: complete valid chronology (source-event
  counts, not bulk raw articles);
- `shadow_comparisons.jsonl`: screens of each newly available day;
- `latest_shadow_comparison.json`: newest evidence and baseline context;
- `manifest.json`: coverage, unavailable days, comparison date, lead
  counts, and `approved_for_production:false`.

Missing upstream archives are recorded as **missing**, never zeros.
If any of the prior 28 calendar dates is unavailable, subsequent
comparisons fail closed rather than interpolating.

The source artifact has GitHub Actions **90-day retention**. The pipeline
will therefore need a durable versioned aggregate store before
February 8, 2027. Current prototype accepts a bounded manual replay;
a scheduled operational pipeline must not depend indefinitely on
an expiring fixed-run artifact.

## Next governance and scientific requirements

1. **Durability:** Provision a GCS bucket (or a carefully controlled
   `aiba-feed-data` aggregate store), versioned `profile`, SHA-256,
   partial-download manifests, and ingestion success/failure receipts.
   Prefer GCS with a least-privilege service account to avoid bulk
   histories in the front-end repository.
2. **Forward collection:** Append verified daily aggregates every day
   rather than repeatedly downloading the same historic 120 days.
   Retries must account for when GDELT's previous UTC day becomes
   available.
3. **Profile mismatch:** Production `aiba_v4.py` uses event roots
   13,16,17–20. Its six-root selected-event denominator is **not**
   comparable to the four-root historical denominator. Compute a
   matched 17–20 live side channel or separately backfill all six.
4. **Event-code and geography QA:** Validate raw CAMEO records, country
   codes including pseudogeographic values (AFR/EUR/etc.), actor pair
   ordering, media duplication and the difference between real-world
   incident incidence and news volume.
5. **Evaluation:** Backtest date-stamped cases across both escalations
   and non-events; establish weekly false-alarm burden, lead time,
   stability, sensitivity, and meaningful comparison to existing
   7/28-day discovery. The first 28 days of this 120-day dataset are
   warmup, leaving 92 eligible comparison days with full coverage.
6. **Materiality:** Separate statistical surprise, consequence,
   independent corroboration, confidence in observation, and
   likelihood of military escalation. No raw code-only increase
   automatically becomes a front-page warning.

Do not mistake the prototype lead count for demonstrated forecast skill.
