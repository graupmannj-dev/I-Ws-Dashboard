# AIBA high-detail globe and two-speed public map collection

## Why the last Atlas zoom level was not enough

The previous Atlas capped its orthographic globe at 5.5×. Its country
outlines are Natural Earth 1:110 million, and the real FAA/Danish restriction
shapes were individually sourced but difficult to find in a full-globe view.
A map can zoom arbitrarily without increasing coastline or provider-source
accuracy. More zoom cannot create a polygon that the provider never supplied.

The globe now supports 0.65–40× and an official-notice **Focus on sourced area**
button. That button centers and scales based ONLY on validated WGS84 points
in the official geometry, including source radius and antimeridian-spanning
boxes. A double-click recenters where clicked; moving around uses normal globe
rotation. Coarse shoreline detail at extreme zoom remains a limitation of
1:110m base geography. The authoritative visual object is the colored sourced
boundary, NOT the coastline backdrop.

## What is actually collected

The existing FAA TFR parser reads the active public TFR listing and linked
notice XML; it supports explicit UTC validity and WGS84 great-circle straight
boundaries. Unsupported arc formats/complex recurring schedules remain omitted
and explicitly counted as partial source coverage. A source that publishes
only text cannot become a polygon on the globe.

The Danish Niord collector requests both niord-nw public navigational
warnings and niord-fe firing exercise notices, using their original
FeatureCollection geometry (when present). Firing exercises are **safety
notices**, not by themselves evidence of combat preparations.

Authoritative source descriptions:
- https://www.faa.gov/uas/getting_started/temporary_flight_restrictions
- https://tfr.faa.gov/tfrapi/exportTfrList?format=json
- https://docs.niord.org/public-api/api.html
- https://docs.niord.org/model/model.html

## Fast path: GitHub-hosted near-live restriction snapshots

A new workflow, **Collect AIBA near-current map restrictions**, samples FAA
and Niord on a best-effort 15-minute cadence (:07, :22, :37, :52 UTC).
This collector does not download GDELT or rebuild Pages; it updates:

- aiba-feed-data/observations/latest/live_layers.json: official supported
  geometry, two source-specific statuses and exact checked times;
- aiba-feed-data/observations/health/live_layers.json: source success/failure,
  counts, skipped notices, last successful collection;
- aiba-feed-data/observations/history/live_layers/<UTC>.json: compact
  identity-change summaries ONLY when there is a material ID/content change;
  no unbounded duplicate full polygons stored each quarter hour.

Both sources have independent failure semantics. A failed FAA pull means
FAA **unavailable**, not no active FAA restrictions. A notice that vanishes
from an active-list query is **not** interpreted as independently confirmed
cancellation. Source event timestamps, validity windows and collector
timestamps are not interchangeable.

The public Atlas polls the branch's latest JSON approximately once per
minute. Its main page continues to be rebuilt on its existing cadence.
The browser accepts only the expected schema, honors the collection clock,
uses static Pages layers.json when the public snapshot is absent or stale,
and explicitly labels static fallback versus periodic current source.
The public branch may be cached by GitHub and GitHub Actions cron is
best effort. Neither the 15-minute scheduler nor one-minute browser polling
creates an actual streaming source.

The static site still supports AIBA_LAYER_FEED_URL to point directly at a
separately deployed /api/layers backend. The browser gives an explicitly
configured live backend priority over branch snapshots.

### Production acceptance checks

1. Review PR tests; verify real FAA/Niord hosted-runner source probe.
2. After merge, use GitHub Actions to manually run **Collect AIBA near-current
   map restrictions**. No additional authentication step is required if the
   existing aiba-feed-data branch write permission remains in place.
3. Verify both source-specific health records and latest JSON actually exist
   on aiba-feed-data. A successful workflow with one source unavailable is
   partial geographic coverage, not a global all-clear.
4. Open Atlas, ensure a near-live snapshot timestamp is shown in the map header.
   In Layers, enable Airspace/Maritime and click an official notice with
   geometry → **Focus on sourced area**. Inspect its boundaries and original
   authority link. Do not interpret schematic country/GCC shapes as
   precise incident polygons.
5. Trigger synthetic source failures in CI only and confirm that live data
   disappears with an unavailable label. Never inject fabricated restrictions
   into the production public evidence branch.
6. Review Actions runtimes, data-branch growth and source terms after a week.
   If FAA requests run too long or source repeatedly throttles, reduce
   cadence and add conditional per-notice cache rather than hammering APIs.

## Slow path: optional persistent stream service

The existing dashboard/collect_layers.py --serve implementation already
supports a local HTTP /api/layers, optional authorized OpenSky regional
aircraft positions, and optional AISStream vessel positions by WebSocket.
The new deploy/live-backend/Dockerfile packages that *existing* service for
deployment to an **independently provisioned, continuously running host**.

Example:
    docker build -f deploy/live-backend/Dockerfile -t aiba-map-live .
    docker run --rm -p 127.0.0.1:8765:8765 -e AIBA_ALLOWED_ORIGIN=https://graupmannj-dev.github.io aiba-map-live

The default starts with official/advisory sources only and no traffic
credentials. To add authorized OpenSky/AISStream subscriptions, provide
OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET, and/or AISSTREAM_API_KEY as
runtime secrets (not browser JS, git commits or public JSON). For sustained
operation use a host with outbound WebSocket support and a managed TLS proxy,
and supply AIBA_LAYER_FEED_URL=https://YOUR-HTTPS-HOST/api/layers as a
GitHub Actions repository variable. Never place an internal host name or
secret in that variable. Do not assume free tiers include 24/7 runtime.

**NOT deployed by this PR:** any always-on external server, AIS or OpenSky
accounts, external TLS URL, global flight tracking, persistent unlimited
telemetry storage or automated AI judgments based on tracked vessels.
The Dockerfile is an option for a user-provisioned service, not a claim that
containers are running. The RIPE RIS Live sampler is a separate scoped
collector and likewise needs authorized persistent hosting for 24/7 capture.

## Scientific / analytic safeguards

The web map shows source-published temporary restriction outlines only
when their effective-time bounds are met. It does not reconstruct historical
restrictions from the separate report-date timeline, infer why airspace was
closed, or upgrade AIBA threat ratings. Real-time events must still be
evaluated against source gaps, normal activity and contradictory signals.
