# AIBA analyst synthesis protocol — case-first I&W, not a report digest

## Purpose and operating posture

The product is an analyst-readable **10–15 minute global warning brief**,
not a dashboard of all observations or a source of guaranteed early warnings.
Data collection is large and source-dated. Assessment publication is
selective. Every automated source or LLM-generated statement remains OSINT
until source provenance and alternative explanations are checked.

This is a reasoning protocol for authorized ChatGPT scheduled AIBA collectors
and for human reviewers. It is **not** a claim that GitHub Actions execute an
LLM or that the optional RIS collector runs continuously.

## Inputs to compare at each run

When available and current, inspect the evidence branch:

- observations/latest/friction_briefs.json — new IODA/AMSA/NGA structural
  friction observations, source families, baselines, review candidates,
  novel-vs-replayed identities and missing source coverage.
- observations/latest/decision_briefs.json — existing case-specific
  conventional official/commercial observations, their event dates and
  exact contract definitions. Not an independent military intelligence report.
- observations/latest/fusion.json — provisional overlaps and source gaps.
- observations/latest/friction_validation.json — descriptive outcomes only;
  absent valid labels means no skill estimate.
- observations/latest/ris_sampling.json — OPTIONAL scoped historical BGP
  measurements. Never treat a sample as complete continuous coverage.
- data/decision_registry.json and data/verified_hotspots.json on main —
  case questions, horizons, reviewed standing status, alternatives and next
  evidence that would change the assessment.

Read the source clocks. Refuse to use a stale observation as new and
do not treat a failed collection as a negative observation. If the new
files are absent, not yet merged, inaccessible, or syntactically invalid,
use the existing conservative method and state the coverage gap.

## First stage: mechanical triage, always transparent

1. **Relevance:** Does the observation answer a specific case question?
   A domestic incident is not automatically evidence of an interstate war.
2. **Temporal novelty:** Was the source event published/observed after the
   preceding assessment? Distinguish event date, source publication, AIBA
   collection, and analyst assessment.
3. **Information root:** Reduce syndicated press copies and duplicated
   agency notices to one underlying claim, not independent confirmations.
4. **Anomaly relative to regime:** Does a behavior depart from the
   comparable 7-/30-day source and local baseline, season/day/hour effects
   and current conflict level? When no baseline exists, state so.
5. **Proximity:** Do distinct sensors record changes within a defensible
   time window, or merely on the same day in the same region?
6. **Causal structure:** Are sensors detecting one shared underlying public
   announcement, weather disruption, safety drill or communications outage?
7. **Contradiction:** Which high-quality evidence would falsify the concern?
   An official cancellation, network restoration, routine scheduled closure
   or measured return to baseline can reduce alert salience.
8. **Counterfactual:** Would a different underlying cause produce the same
   observations? If yes, describe the distinction, not a confident escalation.
9. **Source coverage:** Explicitly list failed/late providers and what was
   not measured. No claim that absence equals calm.
10. **Outcome link:** Forecast only a defined observable outcome and horizon;
    without labeled forward-time evaluation, do not quote attack
    probabilities or assert predictive skill.

## Second stage: compact hotspot synthesis

For at most three to five **materially changed** hotspots in the executive
brief (keep unchanged watches summarized separately), use this structure:

- **Watch / standing state:** Existing reviewed state; no automated
  reclassification from a data anomaly.
- **Net assessment:** One or two sentences on what the combined evidence
  supports, relative to the prior scan.
- **Why it changed:** Most discriminating new evidence and its actual dates;
  avoid a blow-by-blow news chronology.
- **Convergence versus contradictions:** Confirmed independent costly
  behavior, shared-source dependencies, evidence against the hypothesis,
  and whether traditional/nontraditional streams genuinely disagree.
- **Confidence:** Distinguish confidence that an event happened from
  confidence that it predicts further escalation. These are not equal.
- **Next signpost:** Exact observable indicator, ideally with time horizon,
  that would most alter the judgment.
- **Verification:** One to three original source links for decisive claims,
  plus explicit unknowns.

"Interesting" is not synonymous with "strategically significant." Routine
daily notices, repeated missile tests, single IODA anomalies and one-off
market prices are collected but normally excluded from alerts.

An unlocated discovery remains **provisional** until supported by actual
geospatial coordinates; do not repurpose an adjacent conflict's map anchor.

## Notification / publication policy

The default for ordinary variation is **no notification**. If the existing
Six-Hour/Commercial/Discovery tasks discover a major novel verified event,
well-supported anticipatory costly behavior, a substantive contradiction,
a materially altered scenario, or an important de-escalation, they may
notify with a compact case synthesis.

Evidence branch publication is different from user notification. When the
approved GitHub comment gateway is available to the scheduled task, it may
store a strict AIBA-OSINT-V1 record on Issue #9, subject to existing source
link/schema authorization. This is a source-linked **unreviewed analyst
hypothesis**, not independent military confirmation. An empty completed
batch records coverage without sending a false alert. No user-facing
notification or "dashboard updated" claim without verified delivery.

Never copy classified/private data or credentials into public GitHub.
Do not claim that independent source families prove common military intent.
Do not promote severity on the basis of co-occurrence alone.

## Honest performance review

Each week, compare saved pre-event shadow triage against independently
adjudicated outcome/non-event windows. Labeled outcomes may support
descriptive lead-time counts. Until a representative sampling frame and
exhaustive outcome labels exist, the system has no defensible sensitivity,
precision, false-alarm rate or calibrated forecast probability.

This protocol is a scientific quality-control standard, not a replacement
for deliberate analyst judgment.
