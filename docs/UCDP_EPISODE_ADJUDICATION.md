# AIBA escalation episode validation — candidate labels and review queue

**Research status:** preliminary, pre-registered operational construct. No accepted
case–dyad links, no retrospective sensitivity/specificity estimate, and **no
permission to alter production alerts**.

## Why the previous evaluation did not demonstrate early warning

The first pilot classified any future qualifying state-based lethal event
in the nominated country as a positive. It had 225 scored country-days,
but 120 had such a future event; the subset preceded by 14 quiet days had
**zero positives**. The outcome therefore largely rewarded ongoing
violent environments rather than advance notice of new activity.

Our new source is the **frozen UCDP Candidate Events** January–September
2026 release `GEDEvent_v26_01_26_09.csv`, with SHA256 pinned to the
previous validated run:
`134da9b3df08b65266802c4b662e572f396c70c92ab62297319be657540bcede`.
Source: https://ucdp.uu.se/downloads/
Candidate codebook: https://ucdp.uu.se/downloads/candidateged/ucdp-candidate-codebook1.5.pdf

UCDP Candidate is preliminary event coding and is *not* a source of
verified interstate-war onsets. The recent dataset is outcome-complete
only to September 30, 2026. October and November are **unlabeled**.

## Episode construct (fixed before seeing the new episode outputs)

Unit: **UCDP dyad ID × country × date** for coded state-based violence
(`type_of_violence=1`). A dyad may be government vs nonstate insurgents;
an event being state-based does **not** mean interstate war.

Select source events only with `code_status=Clear`,
`date_prec=1`, `event_clarity=1`, `date_start=date_end`,
a nonmissing dyad ID and `best>0`. Use **best-estimate fatalities**,
not high-bound possible deaths. Duplicate IDs with conflicting data
fail closed. All uncertain candidate dates and records with `best=0`
but `high>0` quarantine the corresponding dyad/date interval; missing
dyad assignment quarantines relevant country dates.

Two separate **episode candidate** definitions:

1. **Quiet restart**: first qualifying fatal event in a
   country–dyad after **28 preceding calendar days with no qualifying
   fatal event and no unresolved candidate record**. This is renewed
   activity after a limited quiet interval, **not** an original war onset.
2. **Intensity surge**: a qualifying fatal event on a threshold-crossing
   date when the **current trailing seven calendar days** contain
   **at least 15 best-estimate fatalities**, the *nonoverlapping*
   **prior 28 days** contain **at least 7**, and recent seven-day deaths
   reach **at least 3×** the 7-day expected count derived from the
   preceding 28-day reference. A new surge is suppressed for 14 days
   after a prior candidate surge in the same dyad–country.

The source starts January 1, so no episodes are eligible before
**February 5**, after 35 prior days can be observed. Evaluation is
confined to **July 11–September 30** with verified lagged GDELT
history, absent additional source and adjudication expansion.

These thresholds are **operational hypotheses**, not validated optimal
cutoffs. The results must be reviewed against alternative 14/30/60-day
quiet periods and severity cutoffs in later, separately labeled holdouts.

## The pre-event GDELT review queue

The `ucdp_episode_review_queue.py` process retrieves:
- Verified April 12–July 10 GDELT four-root history from
  [retrospective pilot run 42912512785](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42912512785)
- Verified July 11–November 9 GDELT four-root history from
  [shadow run 42893068477](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42893068477)
- The frozen official UCDP Candidate CSV, which must pass SHA256

It generates each episode **from UCDP alone**, then replays screening
flags dated strictly **1–7 days before** the episode.
Only days with a *complete* 90-day historical reference are admitted.
A GDELT flagged case is queued only where at least one of its GDELT
country codes corresponds to the UCDP episode country. This is just
**geographic overlap**, not verified involvement of GDELT-named
countries in that UCDP opposing actor dyad.

The output artifact has:
- `episodes_unadjudicated.csv`: complete automatically proposed
  episode labels with event IDs, dates, dyads, severity and provenance
- `adjudication_queue_UNREVIEWED.csv`: up to **five pre-event
  geographic-overlap nominations per episode**, with blank human
  adjudication and source fields. The manifest reports any trimming.
- `manifest.json` and `summary.json`: source hashes, exclusions,
  episode-definition thresholds, counts, and coverage.

**All rows begin unreviewed**, and zero actor-resolved matches are
claimed. This batch does not calculate true positives or false
negatives, because these depend on reviewed actor/dyad correspondence
and a preselected negative-case universe.

## Human adjudication standard

For an accepted GDELT country-pair ↔ UCDP actor/dyad association,
independently verify:
- the specific *same* operational confrontation and participants,
  not merely simultaneous violence in the same country;
- identity and role of opposing actors, geography, dates and competing
  explanations; source publication dates must precede the proposed
  warning date when assessing historical information availability;
- two **different named reviewers**, two **independent HTTPS source
  domains**, and written rationale of at least 25 characters.

The helper `scripts/validate_episode_linkage.py` checks consistency,
date ordering and provenance completeness but **does not fact-check the
sources**. Approved reviewer records must undergo case-by-case
substantive audit. The tool does not update live AIBA outputs.

## Run

After merging the PR, open:
[Build UCDP escalation episode adjudication queue (manual)](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/ucdp-episode-adjudication.yml).

Click **Run workflow** on `main`; leave optional `start` and `end`
blank. The workflow reuses the already collected GDELT artifacts
(no Google Cloud credentials needed), downloads the pinned UCDP
Candidate release, and uploads all candidate and review artifacts.
There is no scheduled alert execution.

## Next analytical acceptance gates

1. **Review the whole episode list, including negative/uncertain
   classifications**, and confirm that events represent *onset-like*
   renewed violence or meaningful intensification, rather than
   source revisions or duplicate reports.
2. **Validate actor/dyad links with independent dated sources.** No
   automated country proximity may be counted as a case-level hit.
3. Construct a **fixed, prospective universe of monitored
   dyad-country cases** with complete provider coverage and explicit
   negative days. A dyad must not enter the risk set merely because it
   was later observed to experience violence.
4. Compare both **six-root** 7/28 and 90-day signals on the *same*
   country-pair/actor-verified monitored cases, once April–September
   six-root archive coverage is complete. Use rolling-origin replay,
   lead-time distributions, precision/recall, false alarms per analyst
   day, and clustered uncertainty at the dyad/episode level.
5. Store frozen source versions, adjudicated episodes, exclusions,
   decisions and null results to support future genuine prospective
   predictions. Retrospective flags reconstructed after events are
   not dated warnings that were actually issued.

This is an evidence-grounding research stage. No computed 'confidence'
should be interpreted as a calibrated probability of conflict.
