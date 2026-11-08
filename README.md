# AIBA 5.0 — Global Intelligence Early Warning

A global, open-source OSINT dashboard for investigative leads. It is not an
official intelligence assessment, a calibrated conflict probability, or a
validated attack-prediction model.

Repository: https://github.com/graupmannj-dev/I-Ws-Dashboard

## Review and deployment

The application is proposed in a pull request. Do not merge or publish until
approved. The default branch initially contains only a review placeholder.

After approval:

1. Merge the reviewed PR.
2. Select **Settings → Pages → Build and deployment → Source → GitHub Actions**.
   The connected GitHub integration could not change this setting (HTTP 403).
3. Set repository Actions variable `AIBA_PUBLISH_APPROVED` to `true` only when
   publication is approved. Leaving it unset prevents all deployments.
4. Run **Validate and publish AIBA** on `main`. Inspect the tests, collection,
   and deployment jobs. The workflow runs daily at **14:35 UTC** thereafter.

Expected URL after a successful approved deployment:
https://graupmannj-dev.github.io/I-Ws-Dashboard/ (not yet published).
PRs run tests and an offline build without deployment permissions. Collection
runs only on `main`; deployment requires successful collection and the approval
variable. No auto-merge is configured. GitHub Pages environment reviewers and
branch protection can provide additional account-level controls.

## Optional ADSB.lol regional aircraft overlay

AIBA's persistent `/api/layers` backend now supports the public ADSB.lol
geographic API through an explicitly enabled, bounded, source-attributed
adapter. It requires a chosen center and radius (1–250 nautical miles), uses
at most one query every five minutes, and never writes aircraft positions
into the public historical Git branch.

The Atlas left toolbar offers military/civilian/unknown affiliation, broad
airframe type categories (combat-type, transport, tanker, passenger-type,
cargo-type, scientific and others), and a selectable maximum-marker count.
Military affiliation requires a database flag; civilian requires positive
operator metadata; missing evidence stays **Unknown**. These labels are
provisional airframe/metadata categories, **not flight mission assessments**.
The layer is off by default and appears only when a live backend is configured.

ADSB.lol data is ODbL 1.0 and production users are asked to contact the
provider. Review that license and obtain provider approval before publishing
or scaling automated collection.

See [ADSB_LOL_DEPLOYMENT.md](ADSB_LOL_DEPLOYMENT.md) for Google Cloud settings.

## Near-current sourced closure maps and optional always-on backend

AIBA Atlas now supports 40× globe zoom and automatic **Focus on sourced area**
for official FAA/Danish airspace and maritime restriction geometry. A separate
scheduled GitHub workflow publishes bounded source-dated current restriction
polygons every ~15 minutes, with explicit unavailable/partial source states.
The Atlas checks the public evidence branch every minute and falls back to
its dated static snapshot; GitHub cron delivery and raw-file caching remain
best effort, **not true live streaming**.

A Dockerfile packages the existing optional live AIS/OpenSky API service for
a separately provisioned always-on host. No external host, API subscriptions
or streaming credentials are deployed by this repository change.

See [LIVE_MAP_ARCHITECTURE.md](LIVE_MAP_ARCHITECTURE.md) for verification steps.

## Ephemeral structural friction: new source-separated triage

AIBA includes a **shadow-mode** collector for public NGA navigational-warning
notices and Georgia Tech IODA internet outage detections. New source events are
stored as compact append-only historical deltas; source-specific failures and
observation clocks are visible rather than quietly labeled normal. A bounded,
optional RIPE RIS Live sampler is provided for a separately hosted streaming
service; GitHub Pages is not a persistent WebSocket backend.

The Atlas's **Cross-source I&W** section provides brief theater-specific
comparison, contradictory hypotheses, and next signposts, with source links
on selection. It attempts a read-only five-minute refresh from the public
evidence branch, with the static Pages snapshot retained as a fallback. This
is **not** a five-minute global collection guarantee, a calibrated warning
score, or a verified live intelligence product.

See [FRICTION_ARCHITECTURE.md](FRICTION_ARCHITECTURE.md) for operational
instructions, source limitations and pre-merge acceptance gates.

## Atlas operational history and analyst handoff

The Atlas now renders source-dated observations from the existing durable
operational feed branch and displays per-feed health and collection clocks.
Successful GitHub operational or analyst-intake workflows trigger a new
strict-GDELT Pages build; a failed collection never produces a success status.
An unlocated GDELT nomination is a sidebar lead, not a fabricated map point.

The separate ChatGPT scheduled intelligence tasks are **not automatically
connected to the evidence branch**. A validated OSINT report contract and
an authenticated GitHub Actions import workflow have been added, but the
ChatGPT-to-GitHub write/dispatch step still requires connection and approval.
Until a report is actually received, the Atlas will display the ChatGPT
intake as **not connected**. See [ANALYST_HANDOFF.md](ANALYST_HANDOFF.md).

## Run locally

Python 3.11 or 3.12; dependencies are pinned in `requirements.txt`.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python -m unittest discover -s tests -v
# Offline preview: explicitly shows missing GDELT observations
python aiba_v5.py --output-dir _site
# Live refresh: requires all 35 complete UTC daily archives
python aiba_v5.py --download-days 35 --wiki-days 90 --strict-gdelt --output-dir _site
python -m http.server 8000 --directory _site
```

Open http://localhost:8000/. The static page does not fetch new data while open.
`--as-of YYYY-MM-DD` selects the last complete UTC day. Full collection initially
downloads about 220 MB; subsequent daily runs reuse validated ZIPs from cache.

## Evidence and missingness

- **Curated source-linked assessments:** `data/verified_hotspots.json` preserves
  the package's source URLs, observation dates, claim-specific confidence,
  competing explanations, and gaps. The filename reflects the supplied package;
  this integration has not independently reverified those narratives. A source
  link or fetched archive is not independent confirmation of a geopolitical claim.
- **Provisional anomalies:** GDELT news-coded events nominate country pairs and
  domestic activity changes using 7 recent days against 28 baseline days.
  Country coding, duplication, media coverage, and shared sources limit inference.
  Exploratory Beta-Binomial tails and the 5% effective sample factor are heuristics,
  not war probabilities. Multiple screening comparisons are not FDR calibrated.
- **Missing data:** never replaced with zero measurements. No scoring occurs
  without all 35 required valid daily archives and positive selected-event counts.
  Valid GDELT uncoded markers (`--- / --- / --`) are excluded and audited.
  Each archive must be nonempty, have the expected member and row schema, and
  pass ZIP CRC decoding. Malformed days contribute no partial counts.
- **Wikimedia:** optional attention-only feed. Partial/unavailable pages are shown
  in the dashboard's collection-status details and `collection_status.json`.
  Missing Canada control observations produce no paired attention scores.
  Failure of this optional feed does not imply normal attention or market activity.
- **Markets:** `market_attention_2026-10-01_11-04.csv` is a supplied static historical
  series. `preconvergence.py` uses trailing observations, retains missingness,
  and distinguishes a ground-invasion contract from an airstrike forecast.
  No live market ingestion or predictive skill is claimed.

Curated dossier ages are visible; browser time also triggers a stale-build warning
after two days, even when collection failures leave the previous deployment live.
The status JSON and Actions run history expose the last successful collection.
Schedules may be delayed or disabled by GitHub; this is not a guaranteed warning
service. A complete archive means transport/schema completeness, not complete
real-world coverage or verified intelligence.

## Failure handling

The generator stages files separately and replaces the local output only after
successful validation. A strict collection failure exits nonzero before site
output is written. The Pages artifact is uploaded only after strict build and
JavaScript checks pass; deployment depends on that successful job. A failed
required collection therefore retains the last deployed site, which visibly ages.
Optional Wikipedia failure is explicitly labeled and never silently substituted
with old feed results. Cached GDELT files are revalidated and corrupt ZIPs are
redownloaded; publication fails if repair is unsuccessful.

## Package layout and validation

`aiba_v5.py` orchestrates collection/build; `aiba_v4.py` parses GDELT, scores leads,
and renders the dashboard. `collect_wikipedia.py` collects public attention;
`preconvergence.py` analyzes the historical paired panel. `patch_dashboard.py`
and `tests/client.js` are retained legacy development artifacts; neither is used
in the build. The real generated script is checked by `scripts/check_dashboard.py`
and Node. `data/source_status_2026-11-07.json`, `data/observed_divergences.json`,
and the supplied evidence CSVs are historical package records, not runtime health
reports. `output/` contains the package's dated example, not the deployment source.
The workflow always builds `_site/` from source.

See `VALIDATION.md` for live validation evidence and remaining limitations.
The code is MIT licensed; third-party data and source content retain their terms.
