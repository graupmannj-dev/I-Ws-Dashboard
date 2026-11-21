# CAIRN: source geography, missingness and audit of blind spots

## Why this exists

CAIRN has rapidly increased its number of independently issued *public
sources*. That does **not** imply independent mechanisms, global sampling
density, or evidence of military preparations. A globally indexed hazard
catalog may observe only events above a threshold; a national authority's
publisher origin does not establish its observations cover an entire
continent. Not observing an anomaly is *not contradictory evidence* unless
the required location/time/phenomenon is within an established valid
sampling frame.

This upgrade publishes `coverage.json` and a read-only interactive
`coverage.html` with per-source mechanism, declared jurisdiction, publisher
origin, current collector health, bounded sample count, source check clock,
and missingness. The page is linked from Atlas, hypothesis viewer, and
source health. All claim types are explicit in
`dashboard/source_coverage.py`.

## Coverage interpretation

- `issuer_origin` is the institution issuing a source; it does NOT prove
  observations originate inside its home country. **WMO relay = same original
  national authority**, not new confirmation.
- `declared_country_jurisdictions` is a sparse source authority footprint
  for *known national samples only*. This is never called country coverage
  verification. Global feeds such as USGS, NASA EONET and IODA declare
  global-bounded scope with no enumerated country coverage: no false claim
  of 195 independently monitored countries.
- `global_unlocated` (e.g. RIPE's K-root public cohort and Wikipedia
  language editions) expressly has **no identified country-event footprint**.
- `historical national port statistics` (Singapore MPA) are independent
  monthly aggregate physical throughput observations, but *not current
  vessel movement sensors or 10-minute I&W indicators*.
- `current` means latest bounded source health met its freshness rule,
  not that sufficient measurements exist for an operational negative test.
  `current_partial` indicates sampling/coverage limits. Missing source
  health is `not_measured`.
- A current bounded feed returning zero records is explicitly
  `bounded_sample_zero_not_global_all_clear`. Stale source records are
  *not counted* as current evidence, even if a previous latest file exists.
- All modes have `supports_absence_of_threat_inference=false` and
  `has_event_site_coordinates=false` in this jurisdiction ledger,
  independent of separate provider-supplied event point metadata.

## Relationship to hypotheses

The hypothesis workbench may link the *same* family to different hypotheses.
An unobserved expected signpost cannot be used to favor a competing
hypothesis until a reviewer establishes the correct source expectation,
denominator, place, time, latency and availability, and supplies a dated
review. No negative weights are assigned by the coverage ledger.

## Verification

`python -m unittest tests.test_source_coverage -v`

`python -m unittest discover -s tests -v`

`node --check dashboard/coverage.js`

`node scripts/test_coverage_browser.js` after built site is served.

Sources not yet connected or requiring additional permissions are recorded
for follow-up in GitHub issue #89. The ledger is a structured declaration
of *candidate* collection capabilities, not a real-world warning
performance certification.

Next: provider-observed location denominator, local-time seasonal baselines,
network country/asn cohort continuity, maritime event identity de-duplication,
and benchmarked negative-evidence eligibility.
