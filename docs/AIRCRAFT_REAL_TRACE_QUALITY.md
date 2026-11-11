# Real-source aircraft trace quality audit: first training day

**Scope:** one reproducible historical training day, fixed hash sample,
aggregate-only quality output. This is **not** a vetted recurring-route
cohort, flight-path warning, confirmed receiver coverage, measured
false-positive rate, or live global aircraft feed.

## Rationale and pre-heldout discipline

PR #39 verified that a complete 3.689 GB daily source archive can be
downloaded and parsed on a standard GitHub-hosted runner. That
measurement used a fabricated negative-control ICAO, so it said nothing
about real track continuity.

This pilot selects **real** aircraft source traces for the first time
using a deterministic hash rule, fixed in code *before reading this
pilot's source archive*. It does **not** choose aircraft because an
eventually observed 2026-11-10 trajectory was unusual.

The training source day is 2026-11-07, a prior day relative to the
reserved 2026-11-10 held-out evaluation day. This does **not** make
the 2026 study a prospective forecast issued in real time. It remains
a reconstructed historical experiment.

Selection: SHA-256 of a fixed literal salt plus normalized ICAO
separated by a bar, using the first 64 digest bits, is selected if
the unsigned integer modulo 1024 equals zero. This deterministic
1-in-1024 *identity sampling rule* is independent of aircraft paths,
operator, geographic hotspot, news, conflict outcomes and later
source dates. It is *not* representative across airspace, aircraft
types, flight volume, receiver coverage or geopolitical regions.

The audit checks source traces selected by that rule, but **never
writes identifiers, callsigns, raw paths or coordinates to its output**.
The full archive is processed through a bounded sequential TAR reader;
only a small fixed-hash sample is decompressed and inspected.
Missing or damaged archive input cannot produce success counts.

## Flight-leg usability screening

For each sampled readsb trace, the audit splits at a recorded
leg-start marker, ground observation, stale record, callsign change,
nonmonotonic/large time gap or implausible jump. It does not bridge
missing reception or splice adjacent flights. It counts provisional
segments with at least six observations spanning 15 minutes and
covering at least 5 km. This is only an automated **geometry and
coverage preflight**, not proof that the selected track represents
one operational flight or a stable route. Source-day labels and
timestamps are checked. The audit reports omitted/invalid rows and
fragmentation explicitly.

Receipt categories include: source trace members, selected sampled
traces, decoded traces, oversized/invalid selections, observed rows,
candidate segments, and usable-seeming segments. Those last segments
are **not** valid flight *corridor* references until independently
reviewed for the same origin/destination/direction, call sign,
surveillance continuity and source completeness.

A decoded but empty sample produces an explicit
insufficient_sample status, even if the TAR archive is complete.

## Frozen source assets

The source manifest at
data/validation/aircraft_sample_day_2026_11_07_pin.json locks the
ADSB.lol production release to two parts:

| Asset | Size |
| --- | ---: |
| v2026.11.07-planes-readsb-prod-0.tar.aa | 2,000,000,000 B |
| v2026.11.07-planes-readsb-prod-0.tar.ab | 1,404,765,184 B |

Total **3,404,765,184 bytes**. Each file's published SHA-256 is
pinned and checked again after any download. The runner uses
ephemeral storage and does not publish aircraft data.

Use the Python CLI in metadata mode by default:

~~~bash
python scripts/aircraft_real_source_pilot.py \
  --pin data/validation/aircraft_sample_day_2026_11_07_pin.json \
  --output /tmp/aiba-real-quality.json
~~~

An explicit one-day run requires
--execute --acknowledge YES_SAMPLE_2026_11_07
--work-dir /tmp (or other *ephemeral directory outside Git*).
It will retrieve ~3.40 GB after checking release metadata,
available disk, source size/hashes and transport bounds.
Never invoke it on a billable cloud instance without review.
No scheduled job or automatic daily archives are introduced.

## Decision after the one-day audit

If the hash sample demonstrates repeated complete-enough flight
segments (or their explicit absence), the next isolated study
must **first** specify an operationally meaningful aircraft/route
cohort, selected from training-only observations and frozen before
evaluation days. It then needs multiple independent historical days,
leg-level provenance, equivalent direction and route endpoints,
and verified surveillance availability.

Only a reference with at least four qualified comparable legs
over three earlier complete days can be passed to
scripts/aircraft_route_history.py. A selected aircraft may operate
many routes, and daily readsb files may contain multiple legs.
Neither identity recurrence nor a completed TAR alone meets the
requirements. False-alarm burden must be measured on held-out
real tracks without looking at outcomes while choosing thresholds.

## AIBA mission

This sampled aircraft QA is a single sensor feasibility test inside
the [global tipper → GDELT → UCDP evidence loop](AIBA_TIPPER_EVIDENCE_LOOP.md).
It cannot change hotspot severity or claim pre-news performance.
The system's value should be measured by **convergent independent
signals**, actual immutable pre-headline tippers, eventual
case-accurate and independently adjudicated outcomes, missed events,
source outages, and noise per analyst-day.

Offline tests only:

~~~bash
python -m unittest \
 tests.test_aircraft_real_trace_quality \
 tests.test_aircraft_real_source_pilot -v
~~~
