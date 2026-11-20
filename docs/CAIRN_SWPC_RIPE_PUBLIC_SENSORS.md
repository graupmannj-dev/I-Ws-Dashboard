# CAIRN two additional public sensor mechanisms: NOAA SWPC + RIPE Atlas

This supplements the **five already merged in PR #82** (USGS, NASA EONET,
NWS, USACE and NOAA CO-OPS), rather than replacing their validated adapters.

## NOAA SWPC: environmental explanation
Source: https://services.swpc.noaa.gov/products/alerts.json
- Recent issued solar/geomagnetic bulletins, provider product ID, serial
  number and date as original source identity.
- SWPC's naive UTC issue timestamps are interpreted as UTC only for this
  documented upstream field. Retain issuance provenance.
- *Issued explanatory bulletin*, not direct evidence of network outage
  or hostile action. Multiple bulletins may concern the same solar event.

## RIPE Atlas: physical network telemetry
Source: https://atlas.ripe.net/api/v2/measurements/1001/latest/
- Public built-in ping to **K-root** (measurement 1001). Read a bounded
  public sample, compute the median valid per-probe RTT and disclose
  the valid, failed/invalid and total sampled-probe denominators.
- Retain no individual probe IDs, IP addresses, or personal geography.
- One **global** public probe aggregate; not country-specific outage data.
  The observed probes can change across pulls, so the displayed measurement
  is **not a qualified z-score** or same-cohort deviation.
- This is not independent corroboration of IODA where the underlying
  data/measurement process is shared. Link possible evidence cautiously.

## Operational contract
- The existing three-hour best-effort `collect-cairn-alternative-sensors`
  workflow collects both as additional independent provider modes.
- Existing `aiba-feed-data` source evidence, timestamps, historical
  first-seen baseline, and family archive remain intact.
- When either provider fails, its health file marks unavailable and
  the previous good source snapshot remains untouched. No zero
  event counts are inferred from a missing collection.
- The CAIRN source-status page describes coverage and freshness.
- No new credentials, paid subscription, instance or cloud spending.

## Acceptance
Synthetic parser, source-identity, privacy and error-isolation tests;
read-only live API probe; full CAIRN dashboard/operational regression;
post-merge verification of actual health receipts and registry/archive.
