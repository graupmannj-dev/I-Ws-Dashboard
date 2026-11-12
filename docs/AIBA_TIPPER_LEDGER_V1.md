# AIBA Tipper Ledger v1: issued → public report → adjudication → score

**Status:** offline prototype. No live alerts, GDELT/UCDP API calls, scheduled
jobs, dashboard changes, GCP/IAM modifications or demonstrated predictive
accuracy. Keep real tippers and source references out of the public Git repo.

## Purpose and provenance

A valid tipper records an explicit, falsifiable event hypothesis **at
issuance**, including actors, a proposed action, country/area, likely
consequence, forecast horizon, probability, evidence collected as of issue,
counter-indicators and alternatives. Later news and actual outcomes must
be **appended** as separate records, never silently rewrite the hypothesis.

The local JSONL file has sequential entries, previous SHA-256 entry hash,
current entry hash and a recorded UTC wall-clock time generated during append.
File writes are POSIX advisory-lock protected and fsynced; a malformed or
truncated chain fails closed. Payloads cannot select the issue timestamp.
The local ledger is not cryptographically immutable against a privileged
operator who rewrites and rehashes the entire file, nor is its computer
clock externally trusted. Any future claim of proven pre-news issuance
will require an externally timestamped/write-once chain-head anchor and
clock-synchronization evidence.

## Three payload types

**Issued warning** includes:

- tipper_id (unique), issuer, actors (names), action_key, country (ISO2),
  location_note, consequence, horizon_end (future and no more than 90 days),
  confidence (subjective 0–1, uncalibrated), analyst_action
- counter_indicators, alternatives
- evidence array (1–16), each with family, original_provider, source_id,
  observed_at, available_at, collected_at and quality status

Every source must satisfy observed_at <= available_at <= collected_at
<= issue recorded_at. Repeated original_provider/source_id pairs are
rejected. Relayed secondary copies of one sensor should not be counted
as independent corroboration even when URLs differ.

**Report** includes tipper_id, kind (credible_publication or
gdelt_first_seen), event_time, source_ref, reviewer and
publication_scope_reviewed. GDELT is *ingestion/first seen*, not the
first accessible publication time. A credible article marked reviewed
is still only a manually inspected candidate, not proof that no
earlier article exists. If publication preceded issuance, the scorer
never credits pre-news lead time.

**Adjudicated** includes tipper_id, outcome, case_id, reviewer,
source_ref, adjudication_note, event_time (matched outcome only),
actors_match, action_match, geography_match, verified_through,
coverage_complete and revision_reason. matched_event requires explicit actor/action/area
match. no_event is accepted only if coverage_complete is explicitly true
and the entire original forecast horizon was independently verified.
This flag is an analyst assertion, not independently audited source coverage. censored/inconclusive/not_applicable
cannot count as observed negative outcomes. Later corrections append
a new adjudication with a nonempty substantive revision reason.

All times are strict UTC seconds with a trailing Z. Do not accept
retrospectively invented issue dates as genuinely prospective warnings.

## Local-only CLI

Write each payload as a UTF-8 JSON file outside the repository. A
real issuance horizon must still be in the future at the moment of
issuance.

~~~bash
python scripts/aiba_tipper_ledger.py issue \
  --ledger /tmp/aiba-private-ledger.jsonl --payload /tmp/issue.json

python scripts/aiba_tipper_ledger.py report \
  --ledger /tmp/aiba-private-ledger.jsonl --payload /tmp/report.json

python scripts/aiba_tipper_ledger.py adjudicate \
  --ledger /tmp/aiba-private-ledger.jsonl --payload /tmp/outcome.json

python scripts/aiba_tipper_ledger.py verify \
  --ledger /tmp/aiba-private-ledger.jsonl

python scripts/aiba_tipper_score.py \
  --ledger /tmp/aiba-private-ledger.jsonl \
  --output /tmp/aiba-score-aggregate.json

python -m unittest tests.test_aiba_tipper_ledger -v
~~~

These commands are NOT connected to Atlas production or the current
AIBA watchboard. A local verifier checks consistency and reports
that externally verified immutability is FALSE.

## Scoring contract

The scorer counts per-issue, in-horizon, actor/action/area-matched
events after issue time, and no-event cases only with reviewed complete
window coverage. It reports unadjudicated and censored outcomes separately.
It explicitly reports duplicated cases so two alerts about the same event
do not get treated as independent distinct geopolitical events.

For resolved forecasts it computes the matched fraction, no-event
false-warning fraction, and provisional Brier probability loss.
When a credible first-publication candidate has been manually reviewed,
it reports lead time from issue to that publication, NOT from GDELT
ingestion. GDELT first-seen time is tracked as a separate possible delay.
Unreviewed article timelines provide no pre-news lead credit.

**Not yet estimable:**
- event recall / missed noteworthy events (no independently frozen
  event risk set and verified absence/coverage denominators)
- global precision across genuinely unique events
- false alarms per analyst-day (no standardized watch coverage or
  analyst workload denominator)
- calibrated confidence or defensible pre-media warning performance
  (not enough real prospective cases; local clock not independently
  trusted; first article exhaustiveness not established)

## Subsequent development gates

1. Anchor each issuance's chain head to independent append-only/WORM
   infrastructure and trusted time to prevent silent backdating.
2. Use a frozen global discovery/risk-set mechanism including quiet
   monitored periods, coverage and negative data.
3. Implement first-credible-publication review and separately GDELT
   first-seen joins; never confuse collection latency with news onset.
4. Link independent UCDP actor/dyad/episode labels where appropriate;
   avoid treating missing or out-of-release-window labels as no event.
   Other warnings require other credible adjudication mechanisms.
5. Run actual prospective shadow forecasts alongside current watch
   signals, reviewing counter-indicators and analyst effort, and
   evaluate lead, false warnings and missed cases out of sample.

See AIBA_TIPPER_EVIDENCE_LOOP.md, GDELT_RETROSPECTIVE_VALIDATION.md and
UCDP_EPISODE_ADJUDICATION.md for constraints on retrospective evidence.
