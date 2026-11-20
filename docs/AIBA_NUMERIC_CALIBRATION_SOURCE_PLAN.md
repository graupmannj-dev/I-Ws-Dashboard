# AIBA numerical-source calibration roadmap (2026-11-19)

The ±5σ gauge describes **a specific source-measured numeric quantity**. It is
not a risk score or a proxy for military intent. Evidence independence and
statistical abnormality are separate axes.

## Now implemented: FAA NAS matched-clock daily baseline

- Original source: FAA National Airspace System airport-event status endpoint,
  https://nasstatus.faa.gov/api/airport-events
- An existing official collector operates approximately every 10 minutes when
  GitHub scheduling permits, storing source-health and a bounded sample.
- The calibration adapter preserves each *successful* FAA observation as a
  minimal immutable clocked numeric record, with its original collection clock,
  count of airport records displaying a NAS event, and source-scope definition.
- For a current sample, compare one successfully observed same-UTC-clock-time
  sample from each of the preceding 28 calendar days (±45 minutes).
- Require an exact match of the sampled airport-ID set, validated by its
  SHA-256 roster digest; equal sample sizes alone are not comparable.
- Require >=14 actual reference days, nonzero sample SD, valid source schema,
  current matching health, and matching authoritative source endpoint.
- Never convert a failed or omitted sample into zero. A baseline absence
  displays "not calibrated" without a gauge marker.
- If |z|>=2 or a non-routine NAS state is explicitly reported, preserve an
  investigatory FAA operational family on the durable archive. A pattern
  observed repeatedly is still **one issuer**, not multiple confirmations.
- The measurement is the number of *records returned from the monitored
  FAA source* reporting airport effects, NOT a flight-cancellation percentage,
  a constant sample of all US airports, a world aviation denominator, or
  evidence of a coordinated/hostile disruption.
- This is a descriptive anomaly score, not calibrated warning accuracy or
  an estimate of the probability of conflict.

## Follow-on source adapters, validated for feasibility, not enabled here

### IODA (Georgia Tech / CAIDA)
https://api.ioda.inetintel.cc.gatech.edu/v2/docs

Already in AIBA: country/network outage *event* reports. Next adapter must
retrieve the underlying comparable raw signal series (BGP / darknet / GTR)
from the documented API and validate each signal's reference period, coverage,
method, source geography, and confidence separately. A list of detected
outages or an opaque provider "score" is **not** a z-score.

### RIPE Atlas
https://atlas.ripe.net/docs/apis/rest-api-manual/introduction/
https://atlas.ripe.net/docs/apis/streaming-api/

Public measurement results support time-series ping loss, latency and
traceroute changes. Select stable public measurement IDs and stable probe
cohorts; account for probe turnover, endpoint changes, geographic coverage,
API pagination and streaming gaps. A once-off event scrape is not a baseline.
No private probe addresses or personal information should enter public
persistent evidence.

### Cloudflare Radar
https://developers.cloudflare.com/api/resources/radar/

Potentially suitable for national Internet volume and outage time-series;
documented API requires access controls. Verify API access, allowed usage,
numerical normalization, response cadence, geographic definitions and
reference sample stability before live integration. Do not hard-code secrets
or equate the platform's proprietary anomaly confidence to σ.

### FAA ATCSCC controlling advisories
https://www.fly.faa.gov/fly/flyfaa/plaintext.html

This official program status is complementary corroboration to the airport
effects API, not an independent issuer. Preserve the official directive
identifier, actual affected set and collection time. Issue #60 is the
controlling-advisory/latency follow-up.

### Aviation/maritime traffic
https://opensky-network.github.io/opensky-api/rest.html
https://coast.noaa.gov/accessais/

OpenSky offers observed aircraft state vectors subject to quotas,
geographic surveillance biases and different historical access paths.
NOAA AccessAIS is historical *US coastal* vessel movement, not an
exhaustive worldwide real-time service. Both require stable traffic
exposure denominators and day-of-week/seasonality reference windows.
The user's optional adsb.lol backend deployment remains unverified.

## Not allowed

- Treating source absence as zero when coverage failed, or a timestamp
  replay as a new independent day.
- Pooling incompatible source-family units into a synthetic family-level σ.
- Treating repeated media syndication as independent source families.
- Converting an operational disruption into hostile attribution.
- Showing zero anomaly when calibration is actually unavailable.

## Evaluation

Retain every source's reference measurements, uptime/availability,
comparison clock, sample size and calibration status. Subsequently audit
false anomaly rates against coverage-matched negative periods and compare
prospective timestamped warnings with independently adjudicated events.
