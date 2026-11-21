# CAIRN cross-source physical-event dependency audit

This first cross-publisher adapter compares earthquakes reported by **USGS**
and **Indonesia's BMKG** using original earthquake origin times, epicenter
coordinates, and source magnitude. These may be two measurements of **one
physical earthquake**, not two independently occurring events. A candidate
match requires at most 20 minutes origin-time difference, 150 km epicenter
distance and 0.6 magnitude difference. These are deliberately **review
thresholds**, not a validated seismic association algorithm.

- Only source responses with matching provider health receipts younger than
  12 hours and verified original timestamps are compared. Missing or stale
  data remain `comparison_available=false`.
- One-to-one unambiguous candidate pairs are labeled
  `possible_same_earthquake_unreviewed`; many-to-one links remain
  `ambiguous_pair_candidates`. **Neither is a confirmed match.**
- No deduced world earthquake count is published. Event detection thresholds
  and coverage differ between USGS and BMKG.
- WMO republishing national IMD and SAWS official notices is explicitly a
  *relay*, not a separate observer.
- The source dependency graph never promotes automatically to a warning,
  independently corroborating source count, or support for security
  hypotheses. Missing event matches are not disconfirming evidence.
- Original source event-time precision and URLs are retained; the monitor
  does not infer military activity or actor attribution from natural events.

Collector writes `observations/latest/source_dependency_audit.json`
separately from source health, after the provider checks. The public Atlas
publishes `source_dependency_audit.json` and a brief linked summary inside
`coverage.html`.

## Acceptance tests
`python -m unittest tests.test_source_dependency -v`
`python -m unittest discover -s tests -v`
`node --check dashboard/coverage.js`

Next expansion: apply the same issuer/relay/observation-root logic to country
weather notices, real-time utility records and network measurements without
assuming repeated reporting indicates independent confirmation.
