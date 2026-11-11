# Behavioral pre-event validation: ex-ante units, independent outcomes and coverage

## Why this is separate from collecting or reporting leads

The original UCDP country-day pilot rewarded coverage of active fighting,
did not provide reviewed negative windows, and could not validate
advance warning of preparations. This protocol does NOT infer that
an unlabeled country or period is a true negative.

For the new behavioral-first AIBA system, preserve every **as-issued**
source observation and unreviewed fusion candidate *before* knowing
the eventual outcome. Then compare reviewed positive and negative
events with the **entire previously chosen observation universe**.
All outcomes need a defined, observable event and horizon.

## Implemented readiness gate

`behavioral_validation.py` reads frozen
`observations/history/behavioral_fusion/*.json` and a review-controlled
specification at `data/validation/behavioral_outcome_frame.json`.
The current specification contains **no units and no labels**. This
is intentional. It emits:

- `observations/latest/behavioral_validation.json` with
  `status=no_approved_labels_or_frame`;
- no fabricated absence-of-event claims, `null` forecast
  probability, calibrated precision, recall and false-alarm rate;
- valid source-availability metadata and audit scope where
  independent labels are later supplied.

Existing operational and structural-friction workflows update the
readiness receipt after their source-first shadow fusion jobs.
There is **no new external API**, no GDELT/UCDP source restriction,
and no change to production threat colors.

## What a future monitored unit must contain

Each frame unit is entered *before* its observation period starts:

```json
{
  "unit_id": "ILLUSTRATIVE-DO-NOT-MERGE",
  "geo_key": "country:ZZ",
  "registered_at": "2026-11-01T00:00:00Z",
  "window_start": "2026-12-01T00:00:00Z",
  "window_end": "2026-12-08T00:00:00Z",
  "coverage_providers": ["ioda", "official"],
  "geographic_footprint_reviewed": false,
  "coverage_reviewers": [],
  "coverage_evidence_urls": []
}
```

This is a **hypothetical schema illustration**, not a real country
or review declaration. The `geographic_footprint_reviewed` flag must
remain false until **two distinct reviewers and two independent
HTTPS source domains** substantiate that the required providers
actually cover the specified geographic scope and period.

Provider global reach in marketing, a healthy API response, or a
first-page query does **not** independently establish complete coverage
for that unit. Until footprint and source-clock gaps are reviewed,
the unit cannot be used as a scored non-event.

For each unit, an independent source review can later submit a
**positive or negative** outcome label with:
- the identical unit ID;
- `outcome=event` or `outcome=no_event`;
- if event: `event_at` within the registered window;
- `finalized_at` at or after the observation window ends;
- two distinct named reviewers and two independent HTTPS
  outcome-source URLs;
- no post-event source observations counted as earlier warning.

The frame can cover nonkinetic outcomes such as commercial route
changes as well as kinetic ones, but every label must specify a
measurable outcome. UCDP state-based fatalities alone do not resolve
nonkinetic preparations or interstate actor identity.

## What the research receipt may claim

The evaluator matches **only exact source-declared geography** and
the pre-event historical fusion issue clock. It reports:
- descriptive time between recorded review candidates and a later
  reviewed event, **if** the candidate actually preceded it;
- source-review activity during independently adjudicated non-event
  windows, **if** coverage was adequate;
- unadjudicated, missing-footprint and unavailable-source exclusions.

The resulting analysis is `descriptive_curated_only` at most.
It does not produce formal predictive skill, sensitivity/precision
or calibrated probability, because even a hand-reviewed collection
of frames can be unrepresentative, omit unobserved crises, and suffer
from observation/selection bias. We should pre-register the selection
rule and evaluate consecutive country/area-period windows before
attempting more ambitious claims.

## Immediate work after the initial fusion deployment

1. Inspect source health and the physical footprint of each provider;
   **do not** pre-register false worldwide complete country-days.
2. Add vetted, source-specific behavioral sensor adapters for
   persistent global maritime/air routes and official military
   restriction activity, preserving source identity and coverage.
3. Commit a prospective, appropriately scoped monitoring frame
   independent of knowledge of subsequent violence.
4. Review positive **and negative** outcome labels later using UCDP
   and complementary public sources, with actor/dyad adjudication.
5. Only then analyze lead-time distribution, false alarms per
   monitored area-day, case-level misses and held-out performance.

This does not replace `friction_eval.py`; it applies the same
no-future-information discipline to the worldwide-capable behavioral
fusion layer and requires explicit review of country-level
coverage before calling any non-event a negative.
