# AIBA behavioral observation registry — source-first, worldwide-capable

## Purpose

Treat **observable action / sensor readings** as primary intelligence
leads, and press/news-coded GDELT as background discovery and contextual
history. The system must NOT wait for GDELT news coverage or require
membership in a preselected watchlist before retaining an observation.

This is the **foundation**, not a calibrated early warning detector.
It does not claim complete global coverage, hostile intent, actionable
military movement, a severity score, or predictive reliability.

## Implemented v1 data contract

`behavioral_registry.py` normalizes EXISTING feed records onto a
single versioned observation ledger:

- `id` / `raw_source_id`: provider-qualified stable identities,
  with 45-day seen-index retention and no duplicate “new” notices.
- `source_family`, `provider`, `evidence_class`, `information_root`:
  distinct providers are not automatically independent causes.
- `event_at`: source-described event onset (may be null).
- `source_published_at`: original source publication clock (may be null).
- `observed_at`: time the AIBA source collector obtained the record.
- `first_observed_at`: first recorded observation by AIBA or the
  upstream feed index; no backdating of published availability.
- `geography`: an explicit country code or maritime source area,
  or `unlocated`, with no fake map coordinates. Unrecognized country
  codes are retained rather than rejected using a 15-country pilot list.
- `case_hint`: optional reference to an existing monitored scenario,
  NEVER a requirement and NEVER unverified dyad attribution.
- `claim_level`: strictly bounded by the source type; a commercial
  article is NOT a verified independent shipping/insurance decision.
- `alert_eligible=false` on every record and source registry.

Collection health is tracked **by provider**, with status,
sample/cap limits, latest actual check, last usable snapshot time,
freshness and missingness. An unavailable provider is **not** zero
incidents; a partial first page is **not** full worldwide coverage.

### Source types currently wired in

| Input | What v1 captures | Important limitation |
|---|---|---|
| Georgia Tech IODA | Public network outage detections, explicit country/region/network entity | First 100 source events in a recent bounded query, not global routing history; no cyber attribution |
| NGA | Public navigational warning identities and text areas | Feed availability is variable; notices do not establish attacks |
| AMSA | NAVAREA X official warnings | This region is NOT the world and provides no validated point geolocation |
| US State / UK FCDO | Source-published protective advisories | Feed does not give verified operational incident location in current schema |
| Trade press / syndication | Articles mentioning commercial rerouting/risk | Media mentions, NOT independent company actions |
| Exact-ID prediction-market watchlist | Contract observations with exact question IDs | Market quotes are not attack probabilities or independent preparation indicators |

ADSB.lol aircraft, AIS route deviations, satellite detections, official
worldwide NOTAMs, insurer rate changes and logistics measurements are
**NOT** yet connected to the persistent normalized evidence ledger.
Their absence MUST NOT be interpreted as quiet or normal behavior.

## Evidence branch outputs

Collection workflows reconcile the registry after their existing
collector jobs and before committing the `aiba-feed-data` branch:

- `observations/latest/behavioral_registry.json`: current normalized
  bounded observations, source health and missingness.
- `observations/history/behavioral_registry/<UTC>-<run>.json`:
  immutable event delta with **newly observed** records and coverage.
- `observations/index/behavioral_seen.json`: stable first-seen
  identities, retained for 45 days.

The first successful registry snapshot is **a baseline**, not an alert.
A source can be healthy while reporting zero records; this distinction
is preserved. Stale or failed feeds do not create signals.

Run locally against synthetic samples: `python -m unittest tests.test_behavioral_registry -v`.
To backfill current source observations manually, run either of the
existing operational or friction collector workflows; there is **no**
new high-frequency crawler or external API quota demand from this PR.

## Nonnegotiable analytical limits

- Do not infer geographic location from arbitrary news text or silently
  associate any country with a UCDP dyad.
- Do not treat two articles as independent confirming behavior.
- Do not read a market repricing as an attack probability.
- Do not reclassify curated watch states or executive warning levels.
- Do not let provider failure become a negative observation.
- Keep GDELT/UCDP as separate contextual and *outcome* datasets until
  specific cross-dataset joins and attribution are independently audited.

## Subsequent integration

The follow-on shadow fusion module will compare eligible, explicitly
geolocated observations by **distinct source family, source publication
or first-observed time and information root**. A positive convergence
will only create an unreviewed analyst investigation candidate, never
an automated threat escalation.

Evaluation must use observations saved **before** event dates and an
ex ante monitored universe including negative event windows. Fitted
weights or “forecast skill” are prohibited without that evaluation.
