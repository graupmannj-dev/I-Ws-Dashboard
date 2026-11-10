# AIBA retrospective warning evaluation — v0: provisional country exposure

**Status:** methods pilot, not verified conflict-onset predictions. This does
not feed the dashboard or promote executive warnings.

## 1. Precisely what can be tested with current sources

The verified GDELT historical artifact covers 122 complete days
**2026-07-11 through 2026-11-09**, in a *four-root* source profile
(17–20). The new six-root historical migration is handled separately
in PR #23. The two profiles **must not be pooled**.

**Critical calendar constraint:** the first full 90-day reference from
a July 11 history is not available until **October 9, 2026**. UCDP
Candidate's September release only permits t+7 forecasting windows
through **September 23**, so the two periods have **zero overlap**.
It would be statistically deceptive to call a 28–74-day growing
warm-up window a 90-day baseline.

The evaluation workflow therefore **reprocesses 90 additional original
GDELT daily archives for April 12–July 10, 2026** using the same
four-root parser, validates complete 90/90 source coverage, and
stitches them to the independently verified July–November file.
The combined chronology supports **full lagged 90-day** screens
beginning July 11. A missing April–July source day makes the
workflow fail closed, not score partial 90-day references.

The first independent coded-outcome source is UCDP **Candidate Events**
global quarterly **26.01.26.09**, frozen through **September 30, 2026**:
https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_01_26_09.csv

Authoritative source page:
https://ucdp.uu.se/downloads/
Codebook version 1.5:
https://ucdp.uu.se/downloads/candidateged/ucdp-candidate-codebook1.5.pdf

UCDP's Candidate Events are *provisional reports of organized lethal
violence*; some may be revised or removed. The downloadable release has
not yet covered October or November 2026. A month with no release is
**unlabeled**, not a no-event month.

Only **state-based** candidate events (`type_of_violence=1`) with
`high>0`, exactly dated (`date_prec=1`, `date_start=date_end`),
`event_clarity=1`, and `code_status=Clear` become positives.
Uncertain or temporally imprecise candidate events censor intersecting
future horizons instead of being silently treated as zeros.

The proxy target for each UTC country-day `t` is:

> At least one qualifying UCDP-coded fatal state-based event **in that
> country** from `t+1` through `t+7` inclusive.

The prediction is *not* onset of interstate war, not a dyad/actor match,
not escalation intensity and not country-level policy risk. An
algorithmic GDELT case lead (domestic or bilateral) is projected onto
the mentioned countries merely as a **country-exposure nomination**.
A Russia–Ukraine bilateral mention cannot establish violence between
those states. **Never describe country-exposure evaluation as bilateral
early-warning verification.**

## 2. Pre-registered initial coverage

`data/validation/ucdp_country_crosswalk_pilot.csv` selects a mixed
15-country pilot universe using explicit, reviewable GDELT-code →
UCDP-vocabulary mappings. This is **not** a random global sample.

The parser excludes rather than assigns negative labels to pilot
countries for which the UCDP CSV has **no matching country-name rows**:
absence might mean a spelling mismatch. It reports those names
explicitly for analyst review.

For each eligible country-day (starting **July 11**, after 90 complete
preceding dates), the backtest computes and compares:

- **90-day shadow**: the same four-root lead nominations produced by
  `gdelt_shadow_monitor.analyze_day` with prior 90-calendar-day
  volume-normalized reference, >=28 consecutive preceding dates,
  >=90% coverage of the available preceding window.
- **Simple 7/28 comparator:** case shares in most recent 7 complete
  days relative to the preceding 28, requiring 35/35 valid dates and
  minimum 9 recent case records. Ratio threshold 1.65. **This lacks
  the production beta-binomial tail and has a four-root denominator;
  it is *not* the operational six-root v5 method.**

Both are computed **only from observations no later than t**; outcome
labels use *t+1 through t+7*. The evaluation also reports a restricted
subset with no qualifying or imprecise UCDP event on the preceding 14
calendar days.

Metrics are raw TP/FP/FN/TN, precision, recall, false positive rate,
alerts per 100 country-days and outcome prevalence. Descriptive
statistics alone are not evidence of improved prospective predictive
skill. Overlapping windows make adjacent country-days statistically
dependent, so unadjusted significance tests are prohibited.

## 3. Run with exact pinned inputs

After merging this evaluation PR, run manually:
[Evaluate GDELT shadow leads against UCDP Candidate](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/gdelt-ucdp-retrospective.yml).

It automatically downloads or restores from a versioned Actions cache:
- **90 earlier GDELT daily ZIPs**, April 12–July 10, and requires 90/90
  valid days; a SHA256 of the stitched historical source is retained.
- GitHub Actions source artifact
  `gdelt-shadow-baseline-42893068477` from verified run 42893068477,
  containing the complete 122-day four-root history.
- The precise official UCDP Candidate version
  `GEDEvent_v26_01_26_09.csv`; source SHA256 recorded.

It emits:
- `validation-shadow/report.json`, including source hashes,
  outcome coverage, exclusions, confusion matrices, counts and caveats.
- `validation-shadow/country_day_pilot.csv` for review of every
  source-labelled forecast and its outcome window.
- `ucdp-candidate-source/source.sha256` to detect later version drift.
- `historical-prewindow/{daily.jsonl,manifest.json,source.sha256}` for
  independent review of the extra 90-day original-source collection.

The workflow uses Actions artifacts for a **research pilot only**, not
a durable versioned store. Original raw UCDP CSV is not republished.
No additional cloud permissions or new secrets are needed.

## 4. Evaluation preconditions before we claim forecast skill

1. **Case-level construct validity:** independently adjudicate whether
   any AIBA algorithmic bilateral case actually corresponds to a
   confrontation between the named actors. UCDP country-day lethal
   violence alone cannot do so.
2. **Label completeness:** audit UCDP name mapping, country selection,
   temporal and classification precision, source revisions, and the
   2026 release coverage. No observation after **2026-09-23** is eligible
   for a prospective 7-day event target with this UCDP release.
3. **Past/out-of-sample protocol:** preregister event definitions,
   date ranges, analytic level and threshold *before* observing test
   labels. Build a holdout/rolling-origin period. Reconstructed
   historical alarms are counterfactual backtests, not previously
   recorded forecasts.
4. **Negative cases:** sample complete, unexposed country-days and
   independent high-quality no-event adjudications; do not assume
   missing reports mean no event.
5. **Calibration:** measure burden per analyst-week, event lead time,
   false-alarm costs, base rate, and source availability. Compare
   matched six-root versions of short and long baselines **only after
   PR #23's full historical parity migration**.
6. **Data independence:** UCDP and GDELT both rely partly on open
   reporting. Independent *coding* is not equivalent to fully
   independent underlying evidence.

The pilot is explicitly coded `approved_for_alert_promotion:false`
and cannot change published AIBA risk categories.

## 5. Citation

UCDP Candidate:
Hegre, Håvard, Mihai Croicu, Kristine Eck and Stina Högbladh (2020),
“Introducing the UCDP Candidate Events Dataset,”
*Research & Politics*. https://doi.org/10.1177/2053168020935257.
Dataset version 26.01.26.09, codebook version 1.5, as accessed in
the workflow's source-hash record.
