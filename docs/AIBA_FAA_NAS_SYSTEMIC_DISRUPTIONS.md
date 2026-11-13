# AIBA FAA NAS systemic infrastructure disruption sensor

## Why the November 13, 2026 ground stop was missed

FAA ATCSCC advisory 111 described a nationwide U.S. ground stop beginning
about 20:54 UTC. The existing AIBA `live_airspace` collector ingests FAA
**temporary flight restrictions** (TFR geometry), a distinct class of data.
TFRs cannot represent a systemwide air traffic communication failure or
national ground stop. Commercial source snapshots were hours old.

At 21:24:49 UTC the AIBA real-data behavioral registry contained 378
observations but **no national FAA ground-stop entry**. Its aviation TFR source
was last checked at 19:59:30 UTC. Thus this is a missed **disruption detection**
due mainly to coverage and cadence, not evidence of a missed hostile warning.

The event was a nationwide *U.S.* air traffic stop, not a worldwide order.
The FAA and DHS publicly described an ATC communications problem, with no
substantiated hostile or cyber causation. Keep both questions distinct:
(a) detecting an issued operational restriction; (b) predicting the
outage or explaining its cause.

## Verified first-source endpoint

FAA NAS airport events:
https://nasstatus.faa.gov/api/airport-events

This is public, source-origin JSON, exposing per-airport `groundStop`,
`groundDelay`, `departureDelay`, `arrivalDelay` and `airportClosure`
records. A live November 13 sample contained departure reasons such as
`OTHER: NATIONAL STOP`. Some actual national stops are recorded as
**departure delays**, NOT in `groundStop` fields alone.

Other related FAA primary references:
- ATCSCC advisories: https://www.fly.faa.gov/adv/advAdvisoryForm
- Official NAS public UI: https://nasstatus.faa.gov/
- FAA daily air traffic report: https://www.faa.gov/newsroom/faa-daily-air-traffic-report

The first collector implements the structured airport-event endpoint.
The ATCSCC advisory listing would provide earlier **explicit orders**, but
is not yet a validated, machine-readable adapter. Treat that as the next
priority; it may have different access requirements and changing HTML.

## Sensor implementation

`faa_nas_sensor.py`:

- Polls the fixed FAA NAS JSON endpoint, with byte, time, content-type,
  airport-count and schema boundaries.
- Reads NATIONAL STOP or NATIONWIDE STOP language from any relevant airport
  object, including `departureDelay.reason`.
- Separately counts explicit ground-stop objects, airport delays, and
  national-stop reasons; does NOT infer systemwide scope merely from a high
  number of flight delays.
- Requires >=2 distinct airport records with **source-declared national
  stop language** before nominating a cross-airport systemic disruption.
- Treats four or more simultaneous airport ground-stop objects as a weaker
  multi-airport disruption lead, not as proof of nationwide stoppage.
- Reports the source scope: FAA-monitored U.S. airports only.
- Records FAA as ONE source family, so airport records are not counted as
  independent intelligence corroboration.
- Persists `observations/latest/faa_nas.json`,
  `observations/health/faa_nas.json` and **change-only** append-only
  snapshots in `observations/history/faa_nas/` on `aiba-feed-data`.
- On an unavailable provider or malformed source schema, keeps the last
  good sample but writes **unavailable health**. Missingness can never
  be interpreted as a nationwide all-clear.
- Does not assert malicious intent, cyberattack, warning probability,
  military preparations, future events, or alter standing severity.

The workflow runs about every ten minutes in GitHub Actions on a
**best-effort schedule**. GitHub queues can delay runs significantly;
it is NOT a guaranteed ten-minute real-time SLA. The existing shared
snapshot-workflow concurrency guard serializes writes to the data branch.

The Atlas right-hand watch panel has a simple live-reading FAA NAS status
section. It fetches the latest public evidence and source health every
two minutes in the browser. It requires a recent valid source sample to
show any reassuring non-disruption state. A stale or unavailable sample
is surfaced explicitly, never called all-clear.

## Testing

```bash
python -m unittest tests.test_faa_nas_sensor
python faa_nas_sensor.py --state private/faa-nas-probe
```

The second command **does make a live unauthenticated FAA request**.
The scheduled workflow writes the live evidence branch; PR CI uses
temporary state only. No new GCP VM, paid service, IAM change or API
token is involved.

## Generalizable sensor framework recommended

This FAA incident exposes a wider systemic monitoring problem. The
replicable signal is a **control-plane order and its distributed operational
side effects**, not a keyword match for a country or an event title.

| Signal layer | Real provider / example | What to measure | Why it matters |
| --- | --- | --- | --- |
| Control-plane orders | FAA ATCSCC advisories | Nationwide stop, GDP, airspace flow and unusual airport/center equipment notices | Authoritative action before press reporting |
| Operational effects | FAA NAS airport events | Simultaneous ground stops and common reason strings across airports | Distributed effect of shared system problem |
| Behavior | ADS-B.lol / OpenSky where permitted | Departures vs historical hour/day baseline, arrival/landing deviations and geographic breadth | Independent operational effects; does not identify cause |
| Network accessibility | Georgia Tech IODA (already connected) | Country/ASN reachability and routing anomalies | Helps determine whether a disruption extends to public infrastructure |
| Network control plane | RIPE RIS / RIPEstat BGP update data | Routing withdrawals and simultaneous path churn for monitored networks | Possible upstream connectivity stress, not proof of intrusion |
| Commercial infrastructure | Microsoft, Cloudflare, major CDN status feeds | Geographic/service incident notices and incident start times | Reveals shared dependency failures across sectors |
| International aviation | EUROCONTROL / NATS public operational bulletins, subject to terms | Multi-state flow restrictions or disruptions | Extends beyond United States and reduces local-only bias |

Each candidate must have documented access terms, observable update cadence,
source clock, first-observed clock, outage/no-data state, scope limitations,
historical baselines and false-positive audit. Do not conflate events from
different providers merely because they are simultaneous.

**Recommended next:** integrate direct ATCSCC advisory orders, then add a
two-source *disruption impact* assessment combining FAA order and FAA NAS
effects, with ADS-B behavior as independent validation. Keep possible
hostile attribution on a separate, higher evidence standard.

## Backtest limits

The FAA feed's current values establish an observable disruption, not
what could have been known before 20:54 UTC. A legitimate lead-time
backtest requires timestamped archived FAA advisories, independently
time-stamped NAS observations and pre-outage aircraft departure baselines.
Never reconstruct an early warning from current pages and call it
prospective evidence.
