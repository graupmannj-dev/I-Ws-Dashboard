# CAIRN prospective early-warning performance: frozen evidence contract

This is a **separate offline evaluator**. It does not treat source counts,
GDELT first reports, a live registry snapshot, or a retrospectively coded
event as a forecast that existed before the event.

## Input, reproducibility and privacy

The evaluator accepts two explicitly supplied JSON files with versioned
schemas:

- `cairn.prospective-risk-set.v1`: A predeclared risk window ID and
  UTC start/end, an independently adjudicated `event`, `no_event`, or
  `pending` outcome, a dated reference, audited outcome coverage,
  and an event onset and first public-report time where applicable.
- `cairn.prospective-forecasts.v1`: Exactly one frozen alert decision per
  risk window, UTC issuance **no later than window start**, and immutable
  model version. Optional baseline and augmented probabilities must be
  submitted as a **pair, both logged before outcomes**.

Missing windows, repeated IDs, future or post-window forecasts, absent
outcome-coverage audits, pending outcomes, or incomplete pre-registration
**disqualify performance claims**. No quiet periods are synthesized by a
lack of collector observations. Event onset is distinct from first
public reporting.

All data are passed explicitly to the CLI. Private case records must
remain **outside the public source tree**. The scheduled GitHub workflow
does not access or upload private forecasts or outcome files. Its output
is only a no-sensitive-data `readiness.json` with all skill metrics
`null`, until an authorized review workflow is created.

## Metrics computed only with an adequate frozen evaluation risk set

Minimum 20 fully adjudicated windows, including at least five event and
five no-event windows. Then:

- True/false positive and negative alert **windows**
- Precision and recall (risk-set dependent)
- False alerts per 100 adjudicated risk windows
- Median verified pre-event warning lead hours
- Median pre-publication lead hours, only when a first-publication
  reference is available and the alert predates it
- Baseline and augmented Brier losses and their paired improvement,
  **only if both prospective probabilities are present for every case**.

All metrics remain explicitly **private** and are not automatically
published or certified as causal improvement. The paired ablation is
descriptive on a matched risk set. Confidence intervals, multi-site
clustering, contamination checks, timestamp provenance and external
replication are required before declaring incremental forecasting skill.

## Run

```bash
python -m unittest tests.test_prospective_evaluation -v
python cairn_prospective_evaluation.py --readiness-only
python cairn_prospective_evaluation.py \
  --risk-set /private/riskset.json \
  --forecasts /private/forecasts.json \
  --output /private/evaluation-report.json
```

The GitHub Actions `CAIRN prospective warning evaluation readiness`
workflow runs on main changes, manual dispatch and Mondays. It checks
the validator against synthetic frozen datasets and uploads only the
public-safe readiness artifact.

**Current correct result:** `no_connected_signed_prospective_outcomes`.
CAIRN cannot yet report a real false-alarm rate, lead time, or forecasting
advantage. There is no basis to invent those measurements.

The next substantive step after collecting enough prospective records
is an access-controlled, independently adjudicated evaluation with
registered exposure denominators, explicit site/time coverage, and
paired baseline-vs-added-sensor predictions.
