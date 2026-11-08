# ADSB.lol regional aircraft layer and filters — AIBA Atlas

## What is and is not live

The optional persistent Google Cloud (or other HTTPS) backend supports
public ADSB.lol geographic aircraft positions through the existing
`dashboard/collect_layers.py --serve` endpoint. The static GitHub Pages
site does **not** directly call ADSB.lol or store a global aircraft feed.

- **Current regional positions:** at most one geographic API request per
  configured collection cycle, with a hard minimum of 300 seconds.
- **No global collection:** public `/v2/point/{lat}/{lon}/{radius}` only,
  explicitly configured center and radius 1–250 nautical miles.
- **No guarantee of actual coverage:** volunteer ADS-B/MLAT receivers are
  distributed unevenly; missing aircraft are not evidence of no traffic.
- **No operational forecasting:** no automated severity changes or
  strike/mission predictions from transponder positions.
- **No persistent storage:** only in-memory recent positions in the live
  service; the source itself maintains its own history. GitHub Actions and
  Pages do not retain these tracks.

ADSB.lol API and license:
- https://www.adsb.lol/docs/open-data/api
- https://api.adsb.lol/docs
- https://www.adsb.lol/request
- https://opendatacommons.org/licenses/odbl/1-0/

**Provider terms:** ADSB.lol describes its API as free, with *dynamic*
rate limits and prospective API key requirements. It asks public-facing
production users to contact the maintainer, and the public database is
ODbL 1.0. Attribution is displayed on Atlas and in the public data envelope.
ODbL obligations for any derivative or redistributed database should be
reviewed before public production use; attribution is not the only possible
requirement. Request approval for your intended automated cadence and
public reuse before turning it on in production. A free public API is not
permission to hammer it, scrape broadly, or bypass throttles.

## 1. Configure one region, not the world

The backend requires these environment variables:

| Variable | Required | Example | Meaning |
|---|---|---|---|
| `AIBA_AIRCRAFT_PROVIDER` | Yes | `adsb_lol` | Select the ADSB.lol adapter. Unset = no ADSB.lol polling |
| `AIBA_ADSB_LAT` | Yes | `30.4` | WGS84 latitude of region center |
| `AIBA_ADSB_LON` | Yes | `-84.3` | WGS84 longitude of region center |
| `AIBA_ADSB_RADIUS_NM` | Optional | `100` | Radius in nautical miles (1–250), default 100 |
| `AIBA_ADSB_USER_AGENT` | Optional | `AIBA-Research/1.0 (contact: YOU@EXAMPLE.ORG)` | Provider identification |
| `AIBA_ALLOWED_ORIGIN` | Yes for public Atlas | `https://graupmannj-dev.github.io` | Browser origin allowed to read the HTTPS API |

This ADSB.lol region is **independent** of `AIBA_TRACK_BBOX` (used by
OpenSky/AISStream), and the API does not accept an arbitrary global bounding
box. To cover another region in the future, use a second explicitly
approved regional collector, not an automatic world sweep.

## 2. Deploy on the existing Google Cloud VM

In the cloned AIBA repository on your VM, pull approved merged code and
build the image:

```bash
git pull --ff-only origin main
sudo docker build -f deploy/live-backend/Dockerfile -t aiba-map-live .
```

After confirming ADSB.lol production usage and ODbL compliance, run one
narrowly scoped test region (example geographic numbers, not an operational
watchboard decision):

```bash
sudo docker rm -f aiba-map 2>/dev/null || true
sudo docker run -d \
  --name aiba-map \
  --restart unless-stopped \
  -p 127.0.0.1:8765:8765 \
  -e AIBA_AIRCRAFT_PROVIDER=adsb_lol \
  -e AIBA_ADSB_LAT=30.4 \
  -e AIBA_ADSB_LON=-84.3 \
  -e AIBA_ADSB_RADIUS_NM=100 \
  -e AIBA_ALLOWED_ORIGIN=https://graupmannj-dev.github.io \
  aiba-map-live
```

This sends the source poll from the **VM**, not the user's browser, and
keeps port 8765 bound to loopback. Verify locally without exposing credentials:

```bash
curl -fsS http://127.0.0.1:8765/api/layers \
  | python3 -c 'import json,sys; x=json.load(sys.stdin)["layers"]["aircraft"]; print("status:",x["status"]); print("records:",len(x["records"])); print("attribution:",x.get("attribution")); print("message:",x.get("message"))'
sudo docker logs --tail 40 aiba-map
```

Expected behavior: `status` is `snapshot` or `partial` when the
provider returns a valid response; `unavailable` on rejection, 429,
transient network failure, clock mismatch or unsupported schema.
`records: 0` is not proof of no regional flying when coverage is partial.
If ADSB.lol blocks the VM IP/rate, request official provider access rather
than rotating proxies or evading restrictions.

For a publicly reachable Google Cloud deployment, terminate TLS at a
separately configured proxy/Caddy instance, expose only HTTPS port 443,
and keep 8765 bound to localhost. Never place sensitive credentials in
GitHub Pages, front-end JS, public JSON, or the Dockerfile.

## 3. Connect the existing Atlas Pages

Once `https://YOUR_HOST/api/layers` is publicly accessible via HTTPS:

1. Go to GitHub Actions repository variables:
   https://github.com/graupmannj-dev/I-Ws-Dashboard/settings/variables/actions
2. Set `AIBA_LAYER_FEED_URL` to `https://YOUR_HOST/api/layers`.
3. Trigger **Validate and publish AIBA** on `main`; verify Pages deploy
   and JSON publication actually complete.
4. Open Atlas, select **ADS-B aircraft** in the left Layers panel.
   Only an explicitly configured live /api/layers backend exposes this
   opt-in control; the static Pages fallback never pretends to be live ADS-B.
5. Open **Aircraft filters** under the layer controls. Military is selected
   by default; civilian and unknown are initially unchecked. Select
   affiliation groups and expand the platform-type categories as needed.
   The default cap plots at most 150 markers; users may choose 75/150/300/600.
6. Inspect `plotted / matching / valid` counts and source/clock messages
   before interpreting a low density of tracks. Only the plotted markers
   are drawn; underlying matching in-memory observations remain filterable.

## Interpretation: affiliation ≠ mission

Military: only ADSB.lol's documented database flag `dbFlags & 1`
provides a provisional military designation. An absent military flag does
**not** make an aircraft civilian.

Civilian: only a positive civil commercial/research operator descriptor
in the public database creates a provisional civilian association.
Operator names can be missing or wrong; this is not registry validation.

Unknown: no positive evidence for either affiliation. The type code can
suggest a broadly passenger-type or cargo-type platform, but it does not
prove an actual passenger, cargo, scientific, combat, ISR or other mission.

The subcategories describe **platform families**, using a conservative,
small set of exact airframe designators or research/cargo operator terms.
They are not authenticated missions, operational roles, ownership, current
flight purpose, or warning severity. Emitter category A0–D7 is NOT a
military/civilian or mission classifier. Unknown/unclassified is an
intentional outcome, not a software error.

AIBA excludes missing coordinates, positions older than 120 seconds,
invalid identifiers, locations outside the selected region and source
responses over 2,500 aircraft. Freshness uses the provider's own UTC
clock and `seen_pos`. If the provider fails, previously successful
positions are **removed from current display**, not presented as live.

No raw API positions are inserted into the publicly versioned GitHub
`aiba-feed-data` branch by this integration. Sharing snapshots,
retaining tracks or computing an extended database would require its
own explicit licensing, source capacity, retention and privacy review.
