# Aircraft data tiering after completed, reviewed normal flights

**Status:** offline, copy-only retention experiment. No ADS-B collection,
scheduled jobs, source deletion, production storage mutation, publication,
alerts or IAM/cloud changes. This is NOT a license to discard aircraft
evidence automatically, and is not an AIBA sensor or a tipper engine.

## Operational goal

The high-resolution aircraft sensor should evaluate the flight as it
develops and preserve evidence for all unexplained detours, coverage
gaps, alerts and cross-source activity. After an aircraft lands, only a
fully reviewed, covered, historically unsurprising flight can be
considered for storage in a lower-resolution tier.

This is separate from **real-time sensor sampling**. Do not reduce
new observations to 10-minute spacing before the early warning analysis:
doing so could erase short maneuver sequences, approach/holding
patterns, or evidence supporting an actual pre-news tipper.

## Explicit three-tier retention concept

| Tier | Contents | Current state |
| --- | --- | --- |
| Active flight / unresolved | Full source resolution and complete original trace evidence; never reduce prior to analysis | No production changes |
| Landed with suspicious, unknown or incomplete classification | Preserve original data and metadata for further review and reproducible adjudication | Excluded from low-resolution experiment |
| Landed AND complete normal adjudication | Eligible for a separately stored, loss-bounded compressed copy, with original SHA-256 and reviewer provenance | **Offline experiment implemented**; source still retained |

Normality is **NOT** established solely by flying near some FAA
published airway: flights can legitimately fly direct or along another
airway, while an abnormal flight can remain near published routes.
This pilot's deliberately conservative gate requires **all**:

- Landing verified with a ground observation and timestamp; flight
  closed, and analyst review after the flight.
- Source coverage complete; prior screening finished.
- A valid historical comparison explicitly marked within_reference,
  AND FAA airway check marked network_proximity_only.
- An explicit named reviewer marking normal_reviewed with a written
  reason and positive retention approval.
- Zero unresolved indicators and zero active/open AIBA tippers.

No automatic system presently produces this complete, validated gate.
It must be supplied by trusted operator adjudication. In particular,
existing historical comparison prototypes are **not calibrated**, so
the gate is a test of future retention policy, not production
authorization. Airport landing observations may not by themselves
establish the identity/closure of the actual flight. A separate
landing-validation integration is needed.

## Bounded, curvature-sensitive simplification

The experimental implementation
scripts/aircraft_postlanding_retention.py uses **time anchors every
at most 600 seconds**, always preserves the first/last point,
then retains extra points wherever linear time-based interpolation
would exceed either:

- 2 km horizontal deviation at any original observation, or
- 500 feet of altitude error at any original observation.

Preservation is based on error against *all* original recorded
positions—not visual smoothness inferred from a few points.
Longitude interpolation handles the antimeridian. It explicitly
refuses invalid positions, gaps over 10 minutes, nonmonotonic time,
implausible jumps, unidentified fields/flags, and missing landing or
review evidence. No hidden source metadata is discarded.

A 10-minute **maximum** interval is not guaranteed to mean one
point every 10 minutes: a bend, climb or deviation keeps additional
points. The geometric error limits are engineering hypotheses and
have NOT been shown to preserve every important short-duration
flight maneuver. There is no claim that downsampling a path with
2 km reconstruction error has acceptable intelligence loss in all
contexts.

Example eligible **synthetic** input:

~~~json
{
  "schema": "aiba.aircraft-retention-candidate.v1",
  "source": "ADSB.lol",
  "flight_id": "synthetic-1",
  "points": [
    {"t": 1794312000, "lat": 38.0, "lon": -100.0, "altitude_ft": 32000}
  ],
  "gate": {
    "landed_verified": true,
    "leg_closed": true,
    "source_coverage": "complete",
    "screening_complete": true,
    "historical_status": "within_reference",
    "airway_status": "network_proximity_only",
    "analyst_review": "normal_reviewed",
    "retention_approved": true,
    "unresolved_indicators": 0,
    "open_tippers": 0,
    "reviewer_id": "reviewer-1",
    "review_note": "Verified normal after reviewing all source observations",
    "landing_ground_observed_at": 1794314000,
    "flight_closed_asof": 1794314010,
    "reviewed_asof": 1794314050
  }
}
~~~

The one-point example above intentionally fails: **six or more**
valid time-ordered positions and at least fifteen minutes of flight
history are required. This prevents a minimal skeleton from being
mistaken for successful evidence.

## Run locally

Dry run, aggregate statistics only, **no compacted geometry output**:

~~~bash
python scripts/aircraft_postlanding_retention.py \
  --input /tmp/verified-closed-flight.json \
  --receipt /tmp/flight-retention-receipt.json
~~~

Explicit opt-in to write a *private* compact gzip copy:

~~~bash
python scripts/aircraft_postlanding_retention.py \
  --input /tmp/verified-closed-flight.json \
  --receipt /tmp/flight-retention-receipt.json \
  --copy /tmp/flight-compact-private.json.gz
~~~

The compact archive contains identifiable flight metadata and
trajectory; keep it off the public repository. The script requires
the compressed copy path to be outside the Git checkout and refuses
to overwrite an existing file. The receipt contains aggregate
position counts, upper bounds on geometric reconstruction error,
the SHA-256 of source input and optional compressed-copy digest.
It **does not include** flight ID or coordinates. This is for
provenance and independent audits.

The program **never deletes, rewrites or archives-over the raw
input**, and no production data retention schedule is created.
Even an ineligible flight produces an explicit failure receipt
rather than a normal/zero-event claim.

## Acceptance gates before any raw-source deletion

1. Compare an actual, end-to-end recorded sample of real landed
   flights and flagged flights on a fixed, held-out period.
   Repeat *every* anomaly and pre-event tipper detector on full
   versus compacted tracks. Document missed meaningful events,
   changed scores, false positives, analyst time and outcomes.
2. Do not preselect only retrospectively obvious normal examples.
   Measure the false-negative rate for hidden significant
   maneuvers and uncertainty due to receiver gaps, offshore
   coverage, clutter and routing dynamics.
3. Confirm legal, source-license, privacy and evidence-retention
   obligations, including requirements to preserve original
   imagery/track evidence for warning provenance.
4. Implement a genuinely trusted landing/closure/normality state
   machine with source provenance, plus a quarantine and appeal/
   rehydration path for any subsequently significant case.
5. Only after an explicit retention-policy review should original
   raw bytes ever be purged; no such process is in this PR.
   Preserve source and analytical hashes so past tipper issuance
   times and outcome judgments cannot be rewritten.

## Big-picture alignment

The objective is not accumulating aircraft telemetry. The
[AIBA global warning evidence loop](AIBA_TIPPER_EVIDENCE_LOOP.md)
is still: independent OSINT friction signals → specific, frozen,
pre-media tippers → comparison to first GDELT/public reporting
→ independently adjudicated outcomes/UCDP where relevant →
versioned held-out calibration for fewer false alarms.

Cheap FAA proximity and audited postflight downsampling are
operational cost optimizations **only**. They cannot be used
to suppress multi-source tippers or destroy source evidence
before subsequent outcome adjudication.
