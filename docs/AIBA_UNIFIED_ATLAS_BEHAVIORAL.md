# One AIBA Atlas: integrated behavioral discovery

**User interface:** The existing Global AIBA Atlas remains the **single
front-door** at the repository's GitHub Pages site root.
The existing behavioral engine is *not a separate service*: its collectors,
normalization, fusion and source-health snapshots operate in the same repo
and produce evidence in the `aiba-feed-data` branch.

Before this PR, behavioral discovery was available only by following a
sidebar link to `/behavior/`, while curated hotspot/watch state and
the cross-source theater briefing lived in the main globe. Users
could incorrectly think the behavioral engine was another website.

## What this PR changes

- The Atlas right-hand watch panel now offers **All**, **Recent changes**
  and **Behavioral signals** as first-class views; the Views sidebar also
  includes **Explore behavioral signals in Atlas**.
- **Behavioral signals** displays previously collected cross-family
  review candidates, individual source observations (including
  those without verified locations), source dates, and a
  source-health/baseline breakdown. Selecting a candidate opens
  its original evidence and context **over the same globe**.
- The production site build already creates `/behavior/` before
  `dashboard/build_atlas.py`. The Atlas builder now embeds a
  *whitelisted bounded summary* of that same source's
  `/behavior/behavioral_fusion.json` into the existing
  `/atlas.json`. The tab also **checks the existing public
  aiba-feed-data branch every five minutes** for a strictly newer,
  validated behavioral fusion snapshot and uses the published site
  copy as fallback. This is browser-side read-only refresh, not a
  guarantee that providers collect on time. No second backend,
  scheduling job, IAM, new data collector or billed cloud endpoint
  is needed.
- The detailed `/behavior/` page remains available for the
  full source-health table; `/ops/` and `/classic.html` remain
  under the **same website**, linked from Atlas.
- The browser computes source age against **90 minutes** for
  the prospective-readiness cue. Old data remains visible
  **only as historical/unverified context**, not automatically
  relabeled current.

## Necessary intelligence caveats

- A cross-family source co-occurrence is an **investigative lead**,
  NOT a confirmed hostile action, an issued forecast or a validated
  conflict probability. The dashboard refuses to embed payloads
  claiming automatic warning promotion.
- "No new leads" reflects only what was observed in available
  bounded feeds. It **does not** establish normal conditions,
  absence of activity, or complete global coverage.
- A provider-declared country/region/notice area is **not a
  geocoded incident coordinate**. No behavioral pins are added
  unless future work supplies actual verified geometry with
  explicit source provenance and coverage. The existing
  map restriction layers continue separately.
- The *site build* can be newer than source observations.
  The tab shows the source's actual generated timestamp
  and a stale state if older than the freshness gate.
  Github Pages build success is not proof the source is fresh.
- Source independence is **not guaranteed** merely because
  two families/provider domains differ. Common causes,
  syndicated observations and alternatives still need review.
- A tipper ledger and GitHub/Sigstore hash witnesses from
  PR44/47 exist in the repository backend, **not in the
  public static frontend**: public display of real private
  tipper hypotheses or analyst identities is not authorized.
  No live warning creation or adjudication interface is
  added here.

## Verification

Run the same offline verification as the Pages workflow:

~~~bash
python -m unittest tests.test_atlas_behavioral_embed tests.test_atlas
python aiba_v5.py --output-dir _site
python behavioral_render.py --state /tmp/aiba-missing-feeds --site _site
python dashboard/build_atlas.py --site _site
python scripts/check_atlas.py _site
node --check _site/dashboard/atlas.js
~~~

The first command tests shadow input limits, missingness,
unreviewed/promotion gating, URLs, source precision and
integration into `atlas.json`; the remaining commands
exercise the same canonical site-root build order.

## What remains before AIBA is one complete operational workflow

1. The behavioral panel is **integrated visually and structurally**
   into the existing Atlas. Every five minutes the browser attempts
   a read-only check of the existing public evidence branch for a
   **newer** behavioral fusion snapshot. It rejects malformed,
   future-dated, implausibly delayed or promoted warning records
   and retains the static Pages fallback on failure. Browser
   polling does not make the underlying collectors punctual:
   actual provider timestamps and 90-minute staleness warnings
   remain displayed. The refresh exposes no private ledger data.
2. The **private** prospective tipper issuance, independent
   hash witness, first-publication adjudication and evaluation
   remain CLI/Actions workflows. Do **not** render private
   security-sensitive forecasts to the public site.
   A later reviewed public-only scorecard can summarize aggregate
   performance when it exists.
3. Independently verified geospatial behavioral footprints could
   become a separate toggleable map layer. For now do not
   substitute theater centroids or unverified coordinates for
   event locations.
4. Do not infer a scheduler design decision from Nov 9–12
   outage-contaminated collection logs. Record missing periods
   and assess a clean post-incident window first.

The intended operational pattern is **one AIBA Atlas for
watchspot context, sensor investigation, source coverage,
historical references and eventual review-quality warning
scorecards**—with clear boundaries among those evidentiary levels.
