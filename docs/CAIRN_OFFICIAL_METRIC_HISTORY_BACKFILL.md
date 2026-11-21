# CAIRN public physical-metric historical backfill

## Objective

Warm up source-specific comparisons without treating a few recent
snapshots as a calibrated trend. This does **not** create a conflict
prediction model or a new independently observed military indicator.

### Brazilian ONS

Queries the **official ONS verified load endpoint** for **nine one-day
windows one week apart** before the latest verified day (two days behind
the collector clock), for each of four areas (`SECO`, `N`, `NE`, `S`).
Maximum **36 one-day official requests** per refresh, with 48 normal
half-hour observations per day.

- Requires at least 40 source-timestamped, non-duplicate half-hour
  measurements for a calendar day. Incomplete periods are rejected,
  not padded with zeros.
- Uses `din_referenciautc` (ONS official UTC source field), exact
  region identity and `val_cargaglobal` in MWmed, never scrape time.
- Retains original source query URL and stable period identity.
- No individual facility, classified asset, or utility customer is monitored.

This narrow design supplies **eight or nine prior matching weekdays** at
half-hour resolution, sufficient for the **descriptive** matched-cohort
gate when the recent region is also observed and source health remains
valid. It does not establish weather, holiday or seasonal
exchangeability; those confounders remain for formal testing.

### Singapore MPA

One official `data.gov.sg` CKAN dataset request with `limit=500`,
sorted latest month descending, bounded to the public MPA vessel
arrivals >75 gross tons dataset. Each row is keyed by **calendar
month and vessel type**; source counts must be valid nonnegative
integers. A multi-year sample is required; monthly data are
historical, never a same-day port disruption measurement.

The model requires **at least 3 distinct prior years** of the same
vessel class and calendar month before showing a descriptive
baseline deviation.

### Storage, limitations and operations

Historical source rows are stored in
`observations/metric_history/official_metric_backfill.json`
with versioned schema `cairn.metric-historical-backfill.v1`.
This is **not** the current source snapshot or a false first-seen alert.
Latest current collection remains separate.

Successful initial collection is refreshed no sooner than 21 days;
partial provider failures retry no sooner than one day. No network
requests are made during a successful refresh hold.
Existing source-period values remain immutable; source revisions that
conflict with prior measured values must be reviewed, not silently
rewritten.

Backfill is integrated into the 3-hour CAIRN collector **after durable
family archive update and before matched cohort calibration**.
A missing endpoint does not erase raw healthy sources; provider
failures remain surfaced. The collector requests no credentials
and incurs no infrastructure provisioning.

**Attribution:** ONS Brazil (https://dados.ons.org.br/dataset/carga-energia-verificada),
Maritime & Port Authority of Singapore via
https://data.gov.sg/datasets/d_8f264219109e61fffa87ac64dd5a9a65/view .

**Rate limits:** Singapore documents free unauthenticated
`datastore_search` with rate limits
(https://guide.data.gov.sg/developer-guide/api-overview/api-rate-limits).
The collector does one Singapore request every eligible refresh.
Brazil uses 36 short historical requests at most once every 21 days on
complete success.

## Validation

`python -m unittest tests.test_metric_history_backfill -v`

`python -m unittest discover -s tests -v`

Live source probe must validate the official endpoint's actual response
for a historical interval and the Singapore `limit=500` sample.
Production backfill is **not** established by a passing fixture;
the persisted evidence-branch receipt must be verified after
the collection workflow runs.

This retains no automated hypothesis support/contradiction or
validated warning-performance claims.
