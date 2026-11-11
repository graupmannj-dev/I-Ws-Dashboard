# AIBA behavioral sensor expansion — FAA airspace / Niord maritime

## Why

The global behavioral fusion foundation already collects IODA,
US/UK protective notices, AMSA/NGA maritime feeds and context headlines.
Separately, the Atlas's existing `collect-live-restrictions.yml`
captures real **FAA Temporary Flight Restriction** and **Danish
Maritime Authority (Niord)** notices with source-provided area geometry.

The two systems were not connected. This PR adds a **source-specific
adapter** that reuses the *already-downloaded* official restriction
records. It does not send any additional provider request or claim
global NOTAM/AIS coverage.

## What changes

- `behavioral_restrictions.py`: validates official identity, HTTPS
  provenance, announced validity period, authority-defined polygon,
  circle or point, and semantic version hash. Returns source notice
  identities and source-footprint keys **without inventing incident
  geolocation, force location or causal affiliation**.
- `behavioral_registry.py`: new independent `live_airspace` and
  `live_maritime` adapters with their own short **two-hour freshness
  ceilings**, direct source-health propagation, and per-provider
  first-successful-collection baselines. All existing behavior streams
  continue under their current contracts.
- `behavioral_fusion.py`: considers `airspace_restriction` as a
  distinct official source family; maritime remains **one family**
  whether NGA, AMSA, or Niord produced the notice. Only exact
  provider-declared geographic footprints can coincide automatically.
  News citations, contracts and repeated versions of the same official
  notice do not become independent preparations.
- `behavioral_render.py`: adds both authority feeds, collection
  scope and failures to the existing read-only `/behavior/` page.
- `.github/workflows/collect-live-restrictions.yml`: reuses the
  existing ~15-minute scheduled official source collection, then
  normalizes, fuses and audits its output before the evidence-branch
  commit. Errors in the behavioral adapter are reported **after**
  the original source-health/error receipt is committed.

## Crucial distinctions

### Publication / first seen / effective date

The FAA date strings can be timezone-naive, so **do not** recast those
as known UTC source-published dates. Niord's time-zoned `date`
is an upstream *updated-at* field, not a guaranteed first-publication
timestamp. Each source remains usable in the registry only with its
actual AIBA collection timestamp; unknown source publication stays
null rather than being invented.

`valid_from` and `valid_until` are announced **effective times**.
An airspace/maritime restriction whose validity starts tomorrow is
**not** an event that occurred today, even if it is a legitimate
official preparatory signpost. For this reason each record carries
`scheduled_valid_from`, `scheduled_valid_until`,
`restriction_status` and `event_at=null`.

### Geography and dependence

A source polygon is a **notice footprint**, not an incident coordinate,
a troop location or a maritime route diversion. The registry stores
its content hash and geometry type, not an invented centroid.
A source point is labeled explicitly as a *notice position* and must
not be drawn as an incident point.

The geographic key `source-footprint:<hash>` can match only an exact
authority-declared shape. Broad IODA country outages do not match
maritime polygons by fuzzy text; they remain separate observations.
Only a documented, reviewed spatial join can compare dissimilar
geographic resolutions in a later PR.

The notice's underlying information root remains the **same** as its
title, boundary or validity window changes. New versions are retained
as separate dated revisions but **not counted as independent sources**.

### First provider baseline

The existing live restrictions have been available for days. Adding
them to the new registry must **not** manufacture a sudden surge of
new FAA or Niord notices. Each provider's first successful integration
is an initial baseline, even if the registry itself already exists,
and that status survives provider outages. Only a subsequent valid
new identity/version can become a provisional investigation lead.
If a source-updated clock is available and older than 72 hours, a
notice retrieved for the first time is *not* a new early-warning lead.

## What this does NOT do

- Does not expand FAA TFR coverage beyond the United States.
- Does not expand Danish Niord beyond its source geographic footprint.
- Does not prove a firing exercise, restriction or airspace closure is
  a hostile preparation or emerging crisis.
- Does not collect global AIS vessel routes or military aircraft tracks.
- Does not issue threat scores, promotions or watch status changes.
- Does not turn an unavailable provider or unsupported geometry into
  'nothing happened'.
- Does not yet derive source-specific normal-season / activity
  baselines or measure forecasting skill.

Once reviewed and merged, run the already existing
[Collect AIBA near-current map restrictions](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/collect-live-restrictions.yml)
workflow once, then inspect the evidence branch:
`observations/latest/behavioral_registry.json`,
`observations/latest/behavioral_fusion.json`, and
`observations/health/live_layers.json`.

The first collection for each newly attached source is a **baseline**.
No new FAA/Niord warning should be asserted from that run.
