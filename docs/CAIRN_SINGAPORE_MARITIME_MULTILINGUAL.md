# CAIRN: Singapore port throughput and wider language sampling

## Independent physical-mechanism addition: Singapore MPA

**Publisher:** Maritime and Port Authority of Singapore (MPA),
https://data.gov.sg/datasets/d_8f264219109e61fffa87ac64dd5a9a65/view

**Fetch:** Singapore government's free public CKAN API
`/api/action/datastore_search`, dataset
`d_8f264219109e61fffa87ac64dd5a9a65`, one bounded 80-row query sorted by
`month desc`.

**Observed quantity:** official monthly arrivals of vessels exceeding
75 gross tons *by type*, not positions, live ship tracks, AIS traffic,
tonnage carried or current port closures. Source counts represent the
same national port reporting mechanism, not multiple independent
maritime sensors. **Latest monthly figures may be preliminary and
are published with a lag**; the source is useful for retrospective
baseline comparison, trend context and detecting large reporting shifts
when enough comparable observations exist, not same-day warnings.

Data checks: exact resource ID, required CKAN success, 80-row cap,
enumerated types, ISO YYYY-MM period, nonnegative bounded integer count,
month date not in future and current latest period no more than three
calendar months old. Old 1995 first-page result, corrupt duplicates and
schema mismatches fail closed instead of publishing false normal levels.

Historical performance must not be calculated merely from a single recent
month or incomparable vessel classes. `baseline_status=not_calibrated`
until a dedicated seasonally comparable per-type retrospective history
passes validation.

Source attribution: **© / Data: Maritime and Port Authority of Singapore
(MPA), via Singapore government data.gov.sg**, used under the Singapore
Open Data Licence: https://data.gov.sg/open-data-licence .

## Multilingual attention: not a geographic sensor

Extend public Wikimedia edit-count samples to 14 language editions:

en, fr, es, **ar, ru, zh, hi, id, ja, pt, tr, sw, ko, fa**.

Each edition is sampled independently with a hard 500-change / three-hour
cap and stored as aggregated main-namespace edit counts and up to eight
public article titles; no editor identifiers or IPs. Editions are
`14` query windows, not 14 geographically identified countries or
independent physical evidence. The `wiki_edits` mode remains
context-only and does not directly weight a hypothesis.

CI tests and the source health dashboard record partial coverage and
source timestamps. Failed language editions do not block successful
editions, but source health discloses their missingness.
