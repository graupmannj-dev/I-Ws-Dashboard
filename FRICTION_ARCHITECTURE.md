# AIBA Structural Friction Collector and Synthesis (Shadow Mode)

## Intended product: a 10–15 minute strategic scan, not a news-feed wall

This increment expands AIBA into a **source-separated evidence and triage system**.
Raw public measurements are retained in the aiba-feed-data evidence branch.
The front-facing Atlas displays short case-specific syntheses, conditions for
reconsidering an assessment, explicitly missing sources and reviewed standing
watch statuses. The underlying source details remain one click away.

**Operational status at PR creation: Not deployed and not source-validated from
GitHub Actions.** PR unit tests use synthetic fixtures. Before relying on
either source, inspect actual provider health and parser conformity in a live
Actions smoke test. No new indicator has been shown to predict conflict.

## Currently implemented

| Family | Endpoint | Cadence | What it actually measures |
| --- | --- | --- | --- |
| IODA (Georgia Tech) | https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events | GH Actions best-effort every 30 minutes | Country-level outage detections in public internet visibility, including BGP-related signals. Not cyber attribution or BGP hijack confirmation. |
| NGA Maritime Safety Information | https://msi.nga.mil/api/publications/broadcast-warn?status=active&output=json | GH Actions best-effort every 30 minutes, if reachable | Official maritime navigation warnings currently reported as active; text may mention military exercises. Not a worldwide, verified blockade database. |
| AMSA NAVAREA X (Australia) | https://www.operations.amsa.gov.au/AMSA.Web.MSIPublication/ | GH Actions best-effort every 30 minutes | Regional officially issued navigational warnings with UTC issue dates; no inferred polygons. Regional, not global coverage. |\n| RIPE RIS Live | https://ris-live.ripe.net/ | Optional standalone, no default network subscription | Bounded public BGP UPDATE aggregates for an **explicit prefix allowlist**. No global firehose, no continuous service deployed. |

Source documentation:
- https://api.ioda.inetintel.cc.gatech.edu/v2/docs
- https://msi.nga.mil/NavWarnings
- https://www.postman.com/api-evangelist/national-geospatial-intelligence-agency-nga/documentation/ak1v6h5/maritime-safety-information-rest-api
- https://ris-live.ripe.net/manual/\n- https://www.amsa.gov.au/safety-navigation/navigation-systems/maritime-safety-information-database

IODA public responses declare Georgia Tech copyright; do not redistribute
entire bulk responses or use unlicensed bulk scraping. This collector retains
a bounded summary of event identities and links to IODA for source review.
It does not scrape local users or track individuals.

NGA API reachability and JSON schema require a live smoke check. Some NGA
routes may be inaccessible or return incompatible content from hosted
runners. The importer intentionally **fails closed** and reports unavailable
instead of substituting a third-party news article or declaring no warnings.
The source's cancellation/expiration semantics are not yet fully validated.
A disappearance from the active list is NOT classified as a cancellation.

## Evidence lineage and collection clocks

Every friction record retains:
- Stable event ID, information root, source family, provider and official URL.
- Source event time (if supplied); source publication time separately, if known.
- First AIBA observation time; current pull observation time.
- Candidate association with an existing watch ID, when the source explicitly
  supports it. National outages are never automatically assigned the cause
  "bilateral military escalation". A text reference is not an incident location.
- Explicit case linkage gaps and no invented latitude/longitude.

The 30-minute collector queries IODA for an overlapping four-hour window,
retrieves bounded active NGA warnings, and parses official AMSA NAVAREA X
radio navigational-warning messages. It records per-source health:
collected, partial, or unavailable. A failed query does not overwrite earlier
successful latest measurements, and zero records are only accepted when the
response has a recognized empty-list schema.

To control repository size, each historical friction snapshot saves **only
newly observed event payloads** and case-source count aggregates; a latest
snapshot contains current records. The persistent 45-day identity index
prevents a reappearance after a temporary absence from being reported as
fresh. Historical triage traces are append-only and do not contain outcome
labels. Source-retention/branch-growth need regular audit.

## Synthesis gates and the noise floor

The deterministic synthesis runs automatically after each collection.
It **does not use an LLM** and does not assign probabilities of war.

- **No baseline:** The first successful pull from each source is treated as
  initial coverage, not a mass alert.
- **New source lead:** A genuinely new event identity, with an established
  previous source pull, becomes a shadow-mode review candidate.
- **Matched-hour anomaly:** A source-specific case count exceeds a robust
  historical threshold based on at least eight time-neighboring observations
  spanning at least one day. This is a heuristic screening threshold, NOT a
  calibrated significance test or predictive model.
- **Cross-family review:** Newly observed maritime warnings and connectivity
  anomalies associated with the same watch area justify investigating
  common cause and timing. Two feeds do **not** establish independence or
  confirm preparations for conflict.
- **No automatic threat escalation:** All outputs stay in shadow mode.
  Neither Critical nor the curated standing state is changed.
- **No false-alarm statistics without outcomes:** Retain date-stamped
  review traces and later label event/non-event windows before measuring
  sensitivity, precision, lead times, or false-positive burden.

The Atlas shows source coverage and timestamps at the top of the watch panel,
followed by no more than three material review candidates unless the user
opens all theater syntheses. Selecting a hotspot reveals its alternative
explanation, next discriminating evidence, and traceable source clocks.

ChatGPT's separate six-hour collector can use the latest source-linked
brief as analytical input **only after GitHub authorization and successful
handoff**, and should compare it to existing public reporting, previous
assessments and counterevidence. The GitHub deterministic briefing is not
represented as autonomous LLM analysis.

## Periodic versus continuous

**Working in this PR:** GitHub Actions schedule at :13 and :43 each hour,
best-effort, publishes latest friction and triage JSON to the evidence branch.
The static GitHub Pages site is rebuilt on its existing cadence. The browser
additionally attempts to read the latest *public* branch briefing every five
minutes, using the static site copy if the public raw endpoint is unavailable.
This is a near-current view of **last completed samples**, NOT live streaming
from a GitHub Pages browser and NOT a guaranteed five-minute sensor interval.
Time-since-collection and gaps remain prominent.

**Ready for separately hosted use:** ris_stream.py can subscribe to up to
eight specified public, globally routable BGP prefixes. It records aggregates
of announcements, withdrawals and RIPE collectors, with precise connection
coverage windows. It does not subscribe to all global routing traffic.

Example local bounded sample (replace the demonstration public prefix with a
real, analyst-justified monitored prefix before production):

    python -m pip install -r requirements-friction-live.txt
    python ris_stream.py --prefix 8.8.8.0/24 --duration 120 --state /tmp/aiba-ris-test

For an always-on collector on a separately maintained host:

    python ris_stream.py --prefix 8.8.8.0/24 --continuous --state /path/to/state

**This command does not provision a server, sync the local state into
GitHub, provide guaranteed continuous coverage, or authenticate a publisher.**
Those are distinct deployment requirements; GitHub Actions and GitHub Pages
do not provide an always-running streaming service. These commands should
not be used to infer cyber hostile intent from normal BGP changes.

## Operations and acceptance

Review the pull request and CI before merging. Main-only schedules do not
run from the PR branch. Source-probe steps are best effort and may fail when
a provider restricts GitHub-hosted runners.

1. Review unit tests for failure semantics, duplicate suppression, initial
   baseline, two-family cooccurrence and UI escaping.
2. After merge, run **Collect AIBA structural friction (shadow mode)** from
   Actions. Inspect source health JSON (especially the NGA API and IODA TLS).
3. Inspect aiba-feed-data/observations/latest/friction.json and
   latest/friction_briefs.json for real source dates, collection clock and
   missingness. Do not confuse initial API coverage with an anomaly.
4. Open the Atlas and verify the Cross-source I&W briefing. Check that a
   newer evidence-branch snapshot overrides the static fallback and that
   a source failure is not rendered as quiet or normal conditions.
5. Measure collection reliability over at least 14 days and label initial
   outcomes before modifying any warning threshold or alert notification.
6. Review branch-history growth, API source terms/quotas, and any repeated
   source failures. A continuously failing NGA endpoint is not "connected."

## Not included yet

Official worldwide NOTAM access may require authorization; existing US FAA
TFR and Danish maritime notice adapters remain unchanged. OONI coverage,
paid/comprehensive commercial movement feeds, Google Trends, FIRMS keys,
physical traffic monitoring, EV charge stations, and chat scraping are not
connected. A high-frequency persistent stream, historical outcome series,
forecast calibration and automated generative summaries are not deployed.
The new code must not claim otherwise.
