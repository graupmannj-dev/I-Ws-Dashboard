# CAIRN: Public alternative sensor ingestion — initial automated wave

Seven independently managed provider integrations were added to the existing
public evidence branch. Their *information origins* may overlap, so seven
feeds are **not seven independently corroborating observations**.

| Collector | Automated URL/source scope | Raw observation | Analytical treatment |
|---|---|---|---|
| USGS earthquakes | `earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson`; worldwide M4.5+ rolling week | Source event IDs, magnitude and source times | Environmental explanation, **not** conflict warning |
| NASA EONET | `eonet.gsfc.nasa.gov/api/v3/events?status=all&days=7&limit=100` | Curated natural event IDs, categories and latest source-geometries' date | Environmental explanation, potential upstream duplicates |
| NOAA SWPC | `services.swpc.noaa.gov/products/alerts.json` | Recent issued solar/geomagnetic bulletins; 96h filter | Confounding explanation for radio/GNSS/network changes |
| NWS | `api.weather.gov/alerts/active?limit=100` | U.S. weather watches and warning **issuance**; not proof of damage | Weather contextual explanation; capped first page |
| USACE | `ndc.ops.usace.army.mil/ords/ntni/json_data/notices_geoJson/DDMMYYYY` | Public U.S. inland navigation notices, original stable notice IDs | Issued infrastructure/navigation constraints, *not* actual vessel traffic |
| NOAA CO-OPS | `api.tidesandcurrents.noaa.gov/api/prod/datagetter`, fixed public stations (SF, Norfolk, Galveston, Seattle) | Observed station winds (m/s), actual source observation times | Physical conditions; not throughput, no calculated z-score |
| RIPE Atlas | public built-in measurement 1001, ping toward K-root | Aggregate sampled-public-probe response-time median and denominator; only one worldwide reference target | Physical network measurement, **not** country attribution or network-outage adjudication |

## Integration

- `alternative_sensor_pipeline.py` makes bounded, no-token HTTPS API
  requests. Every provider has independent health, freshness, errors,
  sample cap, evidence type and last successful snapshot.
- `behavioral_registry.py` accepts these seven providers by explicit
  schemas. Each provider's first successful collection establishes a
  **baseline**; no historical notices or natural disasters are promoted
  to newly discovered threat indicators. Failed or stale providers remain
  unknown rather than normal/zero.
- `family_archive.py` receives original normalized roots, preserving
  provenance and historical chronology. Shared USACE query URLs cannot
  silently collapse distinct original notice identities.
- Source health displays all seven streams, expected scope, role, last
  checks and missingness; environmental sources are ranked as explanatory
  context, not first-priority threat leads.
- RIPE probe IDs/IPs and individual device readings are **not** saved;
  published data only contain a bounded cohort aggregate.
- Raw observed metrics (`observed_measurement`) are **not** z-scores and
  never pass CAIRN's qualified-baseline anomaly contract until real
  comparable history is established.

## Acceptance and operational caution

- Check `health/<mode>.json` on `aiba-feed-data` after production job.
  Status `unavailable` does **not** imply a provider returned zero.
- On partial sources, only the explicitly sampled subset is represented.
  NWS is U.S.-only; USACE is U.S.-only; NOAA stations are a four-station
  sample; RIPE is one K-root ping measurement and is **not** a country
  outage/latency surveillance system.
- NASA EONET curates upstream reports. It may depend on USGS/NWS/etc.
  even when presented in a separate collector. Count at the
  **primary observation mechanism** level for corroboration.
- USACE ORDS fields and RIPE response envelopes are best-effort
  adapters: if live schemas are not safely recognized, the collector
  records unavailable health and retains its last valid snapshot.
- GitHub Actions hourly scheduling is best effort. HTTP providers can
  rate-limit, change APIs or fail; those conditions do not hold back
  other successfully sampled sources.
- No new keys, paid data, cloud instances, personal location tracking,
  military-unit tracking, automated military assessments, inferred
  hostile incident coordinates or automatic threat promotions.
- Follow-on: actual baseline calibration, geospatial/temporal candidate
  linking, cross-source *dependence* graph, and much broader regional
  network and port coverage only after independent denominators are
  validated.

## Not connected by this PR

ENTSO-E/ENTSOG credentials, EIA API key-dependent products,
NASA FIRMS key/coverage, transborder traffic, procurement API, global
AIS or individual aircraft tracking. These are separate pilots, **not
operational sources** simply because publicly documented APIs exist.
