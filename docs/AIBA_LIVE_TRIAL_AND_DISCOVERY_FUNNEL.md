# AIBA real prospective gate and the empty-source-panel diagnosis

## Actual prospective source-readiness experiment

At **2026-11-13 13:55:19Z**, a read-only GitHub Actions runner
checked the current actual aiba-feed-data registry/fusion through
the merged private-pilot capture script in its **check-only** mode.
Result: **preflight_only_not_frozen**, no error.

[Original Actions run](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/43437892581).
[Permanent aggregate evidence](evidence/aiba-real-readiness-source-funnel-2026-11-13.json).

**A successful preflight is NOT a real time-witnessed private frame.**
No private ledger/archive was created, no forecast issued, no
source-coverage gap labeled negative and no event adjudicated.
Next: the analyst must select a durable user-controlled private
Linux/WSL storage location, obtain fresh actual public snapshots,
explicitly freeze an immutable local frame and immediately witness
the resulting private ledger head through GitHub Sigstore.
See [the local capture runbook](AIBA_PRIVATE_PILOT_CAPTURE.md).
Never publish original private forecasts in PR artifacts.

## Actual observed source pipeline (Nov 13, 12:28:06Z)

| Stage | Result |
| --- | ---: |
| Normalized source records | 377 |
| Distinct historical observations in 72h fusion window | 171 |
| Newly observed identity in the latest collection | 0 |
| Latest records without a comparable geography key | 335 |
| Latest records with a source geography key | 42 |
| Latest geography keys shared across review-capable families | 0 |
| New single-source nominations | 0 |
| Exact-geography cross-family review groups | 0 |
| Approved forecasts/automatic severity promotions | 0 |

The separately collected decision briefs have **10 standing
curated cases with zero new accepted case-specific evidence**.
The friction briefing likewise retains ten standing cases
with no executive-eligible change. The Atlas Recent changes
tab currently draws from those reviewed changes, not from
the complete source registry.

**Assessment:** ingestion and registry normalization are working.
The empty views arise largely from (a) an extremely strict
new-this-run identity gate, (b) source geography that cannot
meet the cross-family exact-key join and (c) the front end
showing only nominated/curated cases rather than monitored
observations. This does NOT establish that AIBA missed an
actual hostile preparation or event.

## What this PR changes safely

- Reports source-flow counts: latest registry size, new
  identities, unique observations from the prior 72 hours,
  records without geography, and exact-geography
  cross-family intersections
- Adds a **source-family-balanced 24-record sample** of
  already-normalized observations from the past 72 hours
  (maximum eight observations per source family)
- Displays these in the main Atlas Behavioral signals tab
  as clearly labeled **OBSERVED, NOT WARNINGS** source
  evidence, even if there are zero newly nominated leads
- Explains a blank Recent changes tab and gives a direct
  navigation link to source observations without calling
  ordinary source activity a reviewed development
- Uses existing public evidence-branch read-only refresh
  and the static Pages fallback with explicit source age
- Does NOT adjust existing warning thresholds, infer
  geographic incident points, fabricate actor attribution,
  use market/media coverage as independent corroboration,
  issue forecasts or update standing watch severity

## Root-cause follow-up

The main blocking issues are **cross-provider geographic
compatibility** and **identity-only novelty**.

A network provider country code and an exact marine polygon
do not share an identical source geography key, even when
they might describe events occurring in the same broad area.
Most official notices and media records are entirely
unlocated. A later reviewed PR should build a provenance-
preserving hierarchy of geography using source-defined
geometry and verified boundaries, reporting uncertainty.
It must not geocode prose with invented coordinates.

The registry presently treats a previously encountered
source ID as existing; a substantive amendment to that
notice may not be treated as a new signal. Future source
version comparison should detect verified amendments,
cancellations, exclusion period changes and geometry
updates without repeatedly flagging old notices or
routine fetches.

Performance assessment still needs pre-registered risk
sets, independently witnessed specific forecasts, original
first-publication timing, complete outcome ascertainment
and explicit monitoring gaps. This PR does not provide
validated predictive accuracy.
