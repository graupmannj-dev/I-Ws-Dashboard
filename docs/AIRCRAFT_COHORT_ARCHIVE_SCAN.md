# Bounded offline historical aircraft cohort archive scan

**Status:** manually invoked experimental offline extractor, synthetic tests
only. Not live, scheduled, hosted, deployed, published, or an Atlas input.

This is the **resource-measurement and selected-source extraction** step
following [the corridor comparator](AIRCRAFT_ROUTE_RETROSPECTIVE.md).
It measures how many **local TAR bytes** must be read to select a
predeclared set of aircraft identities from an archive day. It cannot
independently establish complete ADS-B receiver coverage, valid flight
legs, or comparable route/direction groups.

## Source and constraints

ADSB.lol publishes daily TAR archives split into .tar.aa, .tar.ab, and
sometimes later parts. These are ordered portions of one archive,
not separate populations. Do not combine production, staging and
MLAT-only data as if observations were independent. Upstream:
https://github.com/adsblol/globe_history_2026 and
https://www.adsb.lol/docs/open-data/historical .

Several GiB of TAR data per production day are common, making a
28-day scan potentially expensive in processing, transfer, or storage.
An archive prefix is not a representative sample or a historical
reference. This script **downloads nothing** and does not prove
end-to-end zero cost.

## Local use

Freeze the existing corridor cohort manifest before evaluating a held-out
date. The scanner selects at most 100 unique ICAO identities across
at most 20 predeclared route groups. It does not infer a route from
flight geometry or assert that one aircraft takes the same route daily.
Acquire local archive parts independently only if you have verified
their availability, source, license and acquisition cost.

For an intentionally incomplete 64 MiB / 60-second smoke check:

~~~bash
python scripts/aircraft_cohort_archive_scan.py \
  --cohort /tmp/aiba-cohort.json \
  --date 2026-11-10 \
  --part /local/archive/v2026.11.10-planes-readsb-prod-0.tar.aa \
  --part /local/archive/v2026.11.10-planes-readsb-prod-0.tar.ab \
  --max-bytes 67108864 --max-seconds 60 \
  --report /tmp/aiba-cohort-scan-receipt.json
~~~

For a *manual* full-source scan of already available local parts, the
explicit hard bounds are 8 GiB scanned, 10 minutes, 800,000 TAR members,
100 selected aircraft, 2 MiB per selected decoded JSON and 24 MiB
total selected data. These are resource **caps**, not expected usage or
permission to download the archive or use billable hosting.

Optionally add:

~~~bash
--candidates-output /tmp/aiba-selected-source-traces.json
~~~

This writes raw selected trace geometry to a **local path outside the Git
checkout**. Never commit or publish it. Candidate traces are not directly
accepted as flight legs by the comparator; they must be split and reviewed
for continuity, callsign, source coverage and route assignment.
On incomplete/failed scans, the candidate file is atomically replaced by
an empty failure record to prevent reuse of stale apparent successes.

## Report interpretation

The aggregate report schema is aiba.aircraft-cohort-archive-scan.v1.

| Status | Meaning |
| --- | --- |
| archive_scanned_review_required | All supplied parts scanned through two zero TAR end blocks with no nonzero tail; **not** verified receiver coverage |
| incomplete_archive | Byte/time/member/output budget exhausted, truncated input, bad TAR header or missing terminator |
| unavailable | Bad local input, selected trace failure, duplicate selected identity, or unsupported TAR features |

The receipt includes source day and instance, input part count and
aggregate local file size, scanned bytes and SHA-256, elapsed time,
Python peak RSS, number of scanned members, matched selected traces,
expanded selected bytes, and failure reason where applicable.
It includes **no aircraft identity, callsign or coordinate**.
It measures *local reads*, not network download bytes or pricing.

If requested, the separate local candidate file has schema
aiba.aircraft-cohort-review-input.v1, status review_required only on
complete TAR input, and detector_input_ready=false always. Its
flight_leg_review and receiver_coverage fields require human review.

This pilot recognizes ordinary TAR members and gzip-compressed selected
JSON. Extended PAX/GNU TAR headers cause an explicit unsupported
result, rather than a false complete scan. It never follows archive
links, extracts member paths, or materializes nonselected geometry.

## Before any daily workflow

1. **Completed**: [full-day 2026-11-10 source benchmark](AIRCRAFT_ONE_DAY_BENCHMARK.md)
   verified both archive SHA-256 hashes and scanned 3.689 GB / 75,360
   trace members in approximately 23.2 seconds. This was a synthetic
   negative-control selection, **not** a valid route history.
2. Test whether archive indexing or a cheaper selected-identity source
   exists. A split TAR does not itself permit random individual-aircraft
   retrieval. Do not treat source absence as zero flights.
3. Build human-reviewed leg and route/direction assignments for the
   corridor comparator. A full TAR scan alone is not full receiver coverage.
4. Review source ODbL terms, privacy, retention, quotas, and *measured*
   job costs before requesting a scheduled daily run. Six-hour freshness
   requires a different source.

No cloud resources, IAM, daily schedule, public geometry, or
deployment are added.

Run synthetic regressions locally:

~~~bash
python -m unittest \
  tests.test_aircraft_archive_probe \
  tests.test_aircraft_route_history \
  tests.test_aircraft_cohort_archive_scan -v
~~~
