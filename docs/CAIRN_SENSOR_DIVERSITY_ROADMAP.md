# CAIRN — alternative sensor diversification and correlation roadmap

**Researched:** 2026-11-20. Candidate sources are **not automatically deployed**.
Core objective: maximize *independent observation mechanisms* (not headlines)
while retaining unusual single-source indicators, confidence and missingness.

## Source triage (new sources and separate analytical functions)

| Priority | Sensor stream / verified endpoint | Actual observation | What it adds | Principal caveat / first pilot |
|---|---|---|---|---|
| A1 | RIPE Atlas public measurements — https://atlas.ripe.net/docs/apis/rest-api-manual/measurements/ ; RIPE RIS — https://ris-live.ripe.net/ | Probe-level ping/latency/loss/traceroute and BGP route changes | Two network-measurement mechanisms to compare against IODA **event** detections | Probe/cohort changes and routing maintenance; start a *country/ASN aggregated* pilot, not end-user tracking or individual device tracing |
| A1 | U.S. Army Corps of Engineers NTNI — https://ndc.ops.usace.army.mil/ords/ntni/json_data/notices_geoJson | Public inland waterway restrictions and lock/navigation notices | Complementary navigation-bottleneck notices outside NIORD/AMSA | U.S.-only, notices are **institutional reports**, not independent observed vessel flow; count document identity |
| A1 | NASA EONET events — https://eonet.gsfc.nasa.gov/docs/v3 ; USGS GeoJSON — https://earthquake.usgs.gov/earthquakes/feed/v1.0/index.php ; NOAA NWS warnings — https://www.weather.gov/documentation/services-web-alerts | Fire, storms, earthquakes, volcano and weather alert context | **Critical negative controls**, helps separate disaster/meteorology from other explanations for disruptions | Ground-truth *environmental context*, not hostility; maintain geographic and temporal coverage |
| A1 | NOAA PORTS / CO-OPS — https://tidesandcurrents.noaa.gov/web_services_info.html | Water levels, currents, winds and observations near US ports | Independent physical environment check against port restrictions and shipping delays | U.S.-only and station-dependent; does not measure vessel throughput directly |
| A2 | US Energy Information Administration — https://www.eia.gov/opendata/ ; ENTSO-E platform — https://transparency.entsoe.eu/ | Hourly demand, supply, exchanges and planned outages (regions differ) | Electricity/infrastructure mechanism distinct from connectivity data | Seasonal cycles, holidays, weather, country coverage; some access requires registration/token |
| A2 | NASA FIRMS active fire — https://firms.modaps.eosdis.nasa.gov/ | Remote-sensing thermal detections, known hotspot footprints | Physical environmental corroboration and confounder for sudden power/network/transport disruptions | Cloud/sensor overpass, agricultural burning and fire propagation; never infer military activity from fires alone; some API products need free key |
| A2 | CBP Border Wait Times — https://catalog.data.gov/dataset/cbp-border-wait-times | Wait-time measures at U.S. land border crossings | Physical cross-border queues independent of media reports | Selected U.S. crossings; staffing, holidays, trade peaks and source outages confound |
| A2 | GSA/SAM.gov opportunities — https://open.gsa.gov/api/get-opportunities-public-api/ | Public procurement opportunity postings and amendments | Forward institutional demand signals before contract fulfillment | API key/usage requirements, delayed administrative process, many routine purchases; not a real-time event sensor |
| A2 | NOAA SWPC alerts — https://www.swpc.noaa.gov/products/alerts-watches-and-warnings | Geomagnetic/storm alerts and timing | Competing benign explanation for aviation, GNSS, radio and network anomalies | An exogenous *control*, not direct evidence of conflict |
| B1 | Public OpenSky aircraft states — https://openskynetwork.github.io/opensky-api/rest.html | Receiver-observed aircraft positions and fleet-level traffic volumes | Movement/throughput mechanism distinct from NOTAM/FAA *issued notices* | Strong coverage and rate-limit biases; only aggregate corridor counts, avoid individual aircraft tracking |
| B1 | GDELT DOC/Events — https://www.gdeltproject.org/ ; newsroom source archives | Media mentions, tone, article onset | Context, corroboration candidates, event retrospect / first public reporting benchmark | Syndication, publication-time ambiguity and reporting bias; **never dominate primary indicator ranking** |
| B2 | AIS vessel movements, global port calls, war-risk insurance spreads, freight rates | Actual traffic/rerouting; commercial risk pricing | High incremental signal value, complementary to navigation notices | **Not assumed free/live/global**. Validate lawful licensing, coverage, geography, sampling and cost before committing any collector |

## Next 3 pilots (no purchase or additional VM)

1. **Network pulse pilot (RIPE):** choose a stable set of public aggregation-level
   measurement IDs; ingest 10–30 min numerical intervals with probe denominators,
   country/ASN scope, source timestamp, and a 28-day baseline. Compare to IODA
   events while counting RIPE and IODA dependencies to avoid fake corroboration.
2. **Port and river bottlenecks (USACE):** ingest and version full notice IDs,
   valid-from/to, affected waterway, reason, GeoJSON and amendments. Preserve
   the source's area polygon but do not invent a vessel position or event site.
   Group by waterway + functional restriction *at the topic level*, with
   distinct notice dates nested, as with Danish firing-exercise topics.
3. **Benign cause controls (NASA EONET + USGS/NWS):** link observed extreme
   phenomena to disruptions using explicit causal alternatives and spatial/
   temporal uncertainty; this stream **reduces** false warnings rather than
   increasing counts. Keep hazard sensor updates from being counted multiple
   times as independent causes.

Other high-value pilot: **NOAA PORTS + USACE** for U.S. port context; **EIA +
RIPE** for power/connectivity patterns. Distinct mechanisms offer more value
than additional copycat maritime news articles.

## Correlation engine prerequisites

### Evidence identity and dependence
- Create independent *mechanism families*: issued notices, physical telemetry,
  network vantage-point measurements, market prices, remote sensing,
  institutional procurement, environmental confounds and conventional media.
- Distinguish **direct sensor observations** from several publications copying
  the same primary bulletin. An issuer × mechanism × event identifier should
  not be inflated by multiple URLs, polygons or hourly re-polls.
- Where one primary observation feeds downstream products (e.g. IODA outage
  output incorporating BGP route signals that RIPE also measures), explicitly
  record dependence: two tool feeds do not necessarily mean two independent
  indicators.

### Temporal / spatial matching
- Link *plausible candidates*, not incident identities. Support a window of
  lead/lag and spatial uncertainty: port city vs offshore area vs national
  regulatory scope. Store each raw time type (issued, effective, collector
  first seen, measurement time). Do not claim that two same-day sources
  near one location concern one underlying event.
- Show the actual named **baseline metric** and signed deviation; seasonality,
  denominators, source health and observed coverage must be comparable.
- Flag a single unusually large deviation immediately; corroboration is a
  separate evidence matrix. Cluster score must not average incompatible
  z-scores or convert publication volume to confidence.
- Distinguish **corroborating** streams from **alternative explanations**:
  a port restriction plus vessel diversions plus wave-height/wind extremes
  suggests weather may be explanatory; the same restriction plus stable
  weather and independent shipping-flow decline is different, but still
  cannot identify intent.

### Temporal evaluation
- Record every daily candidate and its score *before* subsequent reporting.
- Compare event-linked alternative indications with the first independently
  sourced substantial public news; track false positives across all covered
  risk-days, not just eventual crises.
- Measure *marginal* lead-time and discrimination per new mechanism. Reject
  an attractive stream if it merely reproduces an existing upstream source
  or imposes unacceptable review burden.
- Audit outages and shifts in data sampling before interpreting changed
  detection rates.

## Practical example of a useful family

**Regional maritime access anomaly (hypothetical):**
- Navigation authority posts a temporary exclusion area at time T.
- Independently measured *aggregate* commercial vessel throughput diverges
  from its own location/weekday baseline at T+4h.
- War-risk market price moves at T+10h.
- Weather and published coastal hazards are normal or explain only part of
  the pattern; news attention changes at T+20h.

The analyst sees all original observations, source health, whether the
sources are genuinely independent, temporal lag, and alternative
explanations. **No claim of military intent** is warranted from those
observations alone, and the record should remain reviewable if nothing
happens.

## Avoid for now

- Individual food deliveries, surveillance of identifiable civilians,
  private account activity or covert human-source inference.
- Unverified rumors, scraped personal social media locations, or a
  real-time actionable list of particular military units/aircraft.
- New paid subscriptions, access-controlled private APIs, unauthorized
  collection or extra cloud infrastructure without user approval.
- Treating source uncertainty as proof of low risk.

## Caveats

All source availability, access agreements, geographic coverage and latency
must be tested in an actual collector before marking a stream operational.
A documented public API is a **candidate**, not evidence that CAIRN presently
ingests its data. Existing GDELT/NIORD/FAA data are complementary but do not
replace telemetry and confounder streams.
