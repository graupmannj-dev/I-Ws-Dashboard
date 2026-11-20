# CAIRN public alternative-sensor rollout: five first-party sources

These five source adapters extend CAIRN's *independent collection mechanisms*
without credentials or new infrastructure. A documented endpoint is not proof
that a successful measurement has arrived. Each provider writes a separate
`observations/health/<provider>.json` receipt even after an API failure;
only validated successful reads update `latest/<provider>.json`.

## Scheduled collectors

- **USGS** (worldwide natural hazard physical measurement): M4.5+ earthquake
  [past-day GeoJSON](https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson).
  Observations have source IDs, magnitude and origin/published timestamps.
  Contextual environmental explanation, not evidence of military activity.
- **NASA EONET** (cataloged natural events): [v3 events](https://eonet.gsfc.nasa.gov/docs/v3),
  open status, last seven days and 110-item cap. Each event retains
  its original ID and last dated geometry. Latest imagery/provider events
  may be delayed, and location is a hazard record, not an intelligence pin.
- **NWS** (official U.S. marine weather alerts): [active weather API](https://www.weather.gov/documentation/services-web-api),
  area=FL, capped at 110. Source messages are geographic weather
  context; a marine weather alert is not another direct vessel-flow reading.
- **USACE NTNI** (U.S. inland waterway official notices): [active notices
  GeoJSON endpoint](https://ndc.ops.usace.army.mil/ords/ntni/json_data/notices_geoJson),
  with official `DDMMYYYY` start-date path. Validated notice IDs are
  retained as distinct source roots; optional geometry is NOT interpreted as
  an incident location. The upstream schema and availability are independently
  checked; if this service times out or fields cannot be mapped, CAIRN shows
  `unavailable` rather than claiming zero notices.
- **NOAA CO-OPS** (selected physical port environment): [water-level API](https://api.tidesandcurrents.noaa.gov/api/prod/),
  MLLW datum, metric units, stations **9414290 San Francisco**, **8724580
  Key West**, and **8638610 Sewells Point**. One inaccessible station does not
  suppress others. Samples are explicitly not calibrated; do NOT treat water
  level as a threat gauge until same-station/same-datum seasonal baselines
  and source coverage checks are established.

Job: `.github/workflows/collect-cairn-alternative-sensors.yml`,
best-effort every three hours. GitHub schedules can be delayed. Live API
failures are recorded per provider; historical successes are retained on
disk but are not counted as current evidence when new health says failed.
The source status page exposes every mode and its freshness, scope and role.

## Shared evidence model

```text
source JSON + bounded adapter validation
  -> latest/<mode>.json + health/<mode>.json
  -> behavioral_registry.py source-separated records
  -> family_archive.py immutable first-seen source roots
  -> CAIRN analyst family view and Source Collection Health
```

Environmental hazard reports are a **competing benign explanation**, not
additional proof of conflict. They do not pass automatic military-warning
promotion. Their title similarity is insufficient for grouping unrelated
earthquakes or weather alerts as one meaningful incident. Source coordinate
metadata is preserved only as a provider-observed physical location.

NOAA station readings are saved with source metric, unit and datum but
`baseline_status=not_calibrated`; they must **not** be passed as qualified
z-score inputs without ≥14 genuinely comparable historical days, same
station and sensor cohort, consistent unit/datum, positive sample SD, and
adequate current coverage.

## Boundaries / future work

- A maximum of 110 source records per mode per collection. Partial feeds are
  labeled as such; a zero-event valid response is not an outage.
- NOAA is a **three-station U.S. pilot**, not comprehensive global port
  intelligence. USACE/NWS are regional/U.S. only; EONET/USGS are global but
  filtered and bounded. A bad upstream response is never silently accepted.
- Other source candidates requiring additional method design: public RIPE
  Atlas probe cohorts and RIS BGP paths, EIA power data, transit wait times,
  FIRMS thermal detections (account), and AIS (license). A generic network
  measurement ID does not supply meaningful regional coverage by itself.
- Before cross-source association, record measurement dependencies: USGS
  seismic events may also appear in EONET, which is **not independent event
  corroboration**. NWS weather bulletins can explain maritime notices, but
  issuing two notices cannot be treated as independent physical sensors.

## Verification

Unit tests inject authentic-shaped JSON fixtures, including network failure,
schema drift, partial station availability, invalid future timestamps,
geographic uncertainty, uncalibrated numeric values, and registry/archive
integration. A read-only PR live probe reports which APIs are reachable
without asserting unavailable sources are healthy. No paid APIs, private
individual tracking or new cloud services are introduced.
