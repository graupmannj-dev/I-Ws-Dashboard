# Executive recent-changes publication gate (proposed)

The **Recent Changes** panel is an analyst product, not a raw event queue.

A source event is eligible for front-page publication only when an assessment includes:
1. The case-specific question and what materially changed since the prior review.
2. **So what:** plausible operational or strategic consequence, and the causal link to the indicator.
3. Evidence FOR and AGAINST, with source dates and distinct underlying information roots.
4. A credible alternative cause, confidence in the observation versus escalation, and the most discriminating next signpost.
5. Original source links and coverage limitations.

If these cannot be completed, retain the observation in the investigative queue, not Recent Changes.
Corroboration is NOT mandatory for an assessment; its absence is an uncertainty that must be analyzed.
Repeated identical or unchanged observations do not constitute recent changes.
A novel observation without an articulated consequence is not automatically a material change.
No automatic change to standing watch severity; no generated or inferred outcome labels.

## Historical baseline acceptance
- Preserve exact source event and collection timestamps and distinguish backfill from forward-time observation.
- Require coverage-aware matched baselines; missing days are not zero activity.
- Historical anomaly replay is descriptive, not evidence of predictive skill.
- Validate with independently adjudicated outcome and non-event windows before changing thresholds.
- No bulk raw article or provider data published to public Git branches.

## Executable early-indicator rule

The deterministic structural-friction synthesizer now distinguishes
`triage` (why a source is retained for investigation) from
`executive_eligible` (why a case deserves front-page attention).

Executive visibility is granted for:
- A source-specific count above the *existing* 14-day matched-hour robust
  screening threshold, explicitly showing current count, median, sample count,
  and threshold;
- Two date-stamped distinct source families within six hours, while clearly
  noting that underlying causes can be shared; or
- One source root with a fresh, approved, case-specific materiality assessment
  in `data/executive_signal_reviews.json`. The reviewer must explain
  qualitative/quantitative baseline context, possible operational consequence,
  contradictory evidence, next observation, original source URL and exact root.

No new source automatically qualifies merely because it was first seen.
An exceptional **uncorroborated** event can still qualify on documented
materiality, and its uncertainty must be visible. The analyst review is an
authorization record, not independent source confirmation.

The dashboard's default Cross-source I&W and Recent Changes sections show
only executive-eligible friction signals. The expanded investigatory view
retains unpromoted sources and their collection gaps. All standing theater
severity labels remain unchanged. Older evidence JSON without explicit
`executive_eligible: true` fails closed, rather than promoting the old
novelty-based candidates.

The 14-day baseline is only provisional until historical backfills and
forward-time outcome assessments are complete. Quantitative deviations
are not predictive probability or proven operational intent.
