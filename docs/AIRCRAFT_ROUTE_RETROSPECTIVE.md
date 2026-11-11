# Offline daily aircraft corridor retrospective prototype

**Status:** experimental code and synthetic tests only. **Not scheduled,
published, deployed, fed to Atlas, or calibrated.** This stage consumes
bounded, explicitly curated offline flights (preprocessed single flight legs
or embedded readsb per-aircraft traces). It does not download full daily
ADSB.lol archives. The existing archive prefix probe verifies structure
only and is not a historical reference dataset.

## Fixed cohort and input provenance

Freeze the cohort and its route/direction before evaluating a held-out
date. The route group is explicitly assigned, never inferred from the
evaluation path. Aircraft identity alone cannot establish its route.
The code cannot verify whether the caller assigned each leg to the correct
route group. One input flight must represent **one flight leg**.

Each source-day coverage entry describes **verified collection of that
preselected cohort**, not complete worldwide ADS-B coverage. A complete
label requires independent support from upstream archive retrieval and
selection evidence. Unknown or partial coverage is never upgraded. Never
use an archive-order prefix as a complete source day.

Example synthetic cohort manifest:

~~~json
{
  "schema": "aiba.aircraft-route-cohort.v1",
  "frozen_before": "2026-11-09",
  "cohorts": [{
    "id": "test-eastbound", "label": "Synthetic eastbound route",
    "direction": "east",
    "aircraft_ids": ["abc123", "abc124", "abc125", "abc126"]
  }]
}
~~~

Example synthetic input skeleton (the two points deliberately do **not**
meet coverage criteria; they illustrate the structure only):

~~~json
{
  "schema": "aiba.aircraft-route-flights.v1",
  "source": "ADSB.lol",
  "collection_scope": "preselected_cohort_offline",
  "days": [
    {"date": "2026-11-02", "status": "complete"},
    {"date": "2026-11-04", "status": "complete"},
    {"date": "2026-11-06", "status": "complete"},
    {"date": "2026-11-08", "status": "complete"},
    {"date": "2026-11-10", "status": "complete"}
  ],
  "flights": [{
    "flight_id": "synthetic-one-leg",
    "cohort_id": "test-eastbound", "aircraft_id": "abc123",
    "direction": "east", "day": "2026-11-02",
    "coverage": "complete",
    "points": [
      {"t": 1793620800, "lat": 0.0, "lon": 0.0},
      {"t": 1793620980, "lat": 0.0, "lon": 0.2}
    ]
  }]
}
~~~

Include at least four comparable, usable historical legs on three
distinct days inside the preceding 28 days and a separate held-out leg.
Each leg needs six valid airborne positions spanning at least 15 minutes,
with no gap exceeding 10 minutes. The flag field is optional for compact
positions: bit 0 marks stale data; bit 1 marks a possible new flight leg.
An interior leg marker causes an explicit insufficient coverage result.

Alternatively, substitute a single raw readsb trace envelope for the
points array under the flight's "readsb" key. The envelope must contain
"icao", numeric "timestamp" (Unix seconds), and "trace", containing
the provider row arrays documented in the existing archive probe. Do not
include both representations. A daily aircraft trace that contains more
than one leg must first be split and checked; the comparator will not join
distinct legs. Callsign changes in observed metadata are disqualifying.

Run from the checkout root, using **local inputs only**:

~~~bash
python scripts/aircraft_route_history.py \
  --cohort /tmp/cohort.json \
  --input /tmp/curated-flights.json \
  --date 2026-11-10 \
  --output /tmp/aiba-aircraft-retrospective.json

python -m unittest tests.test_aircraft_route_history tests.test_aircraft_archive_probe -v
~~~

The report remains local. Scored flights retain at most 128 actual
lat/lon geometry points and a 21-point historical centerline plus
half-width, data-quality notes and comparison counts. Do not publish
real traces or derived geometry before reviewing ADSB.lol ODbL terms,
source attribution, reidentification and retention implications.

## Output status and experimental thresholds

| Status | Interpretation |
| --- | --- |
| within_reference | No sustained excess outside a usable historical corridor |
| deviation_candidate | At least three consecutive positions spanning 300 seconds, >=25 km beyond the historical corridor |
| insufficient_history | Fewer than four usable previous legs or three reference days, or high baseline dispersion |
| insufficient_coverage | Incomplete/unknown evaluation day or leg, missing leg, observation gaps, multiple legs, etc. |
| unavailable | Invalid input or failed offline run; replaces prior results instead of showing zero anomalies |

The historical centerline uses 21 equal-distance interpolated positions
from each eligible earlier flight, with median latitude and unwrapped
longitude at each position. The historical half-width is the larger of
10 km and the prior observed 90th-percentile spread plus 10 km.
At more than 80 km historical dispersion, comparisons are withheld.
Actual points are measured against the closest centerline segment,
including across the antimeridian. These are provisional engineering
thresholds and have **no calibrated false-positive rate**. A corridor
is observed earlier behavior, **not** an assigned route, expected
destination, prediction, or evidence of intent. Missing receiver coverage
does not establish a detour. No AIBA severity is changed.

## Testing, hosting and next step

A new PR-only GitHub Actions job runs fully synthetic tests with standard
Python 3.11 and existing archive probe regression tests. It uses read-only
repository permission, a five-minute job timeout, and performs no data
download, artifact publishing or deployment. Standard GitHub-hosted runners
have quota conditions, so this **does not** prove full-scale historical
processing is zero-cost.

Before approving any daily schedule, measure 28-day source coverage and
bounded preselected archive extraction (download bytes, processing time,
CPU, RSS and output size), inspect held-out real examples, and review
source licensing and data retention. A six-hour refresh of a once-daily
archive is not new observation; fresher inputs would need a separate
collection and cost assessment.

Worldwide discovery, full-archive processing, regular jobs, Atlas display
and cloud changes are **not** part of this PR.
