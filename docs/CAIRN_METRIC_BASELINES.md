# CAIRN matched physical-metric baseline — readiness, not conflict forecasting

## Sources, identity and denominators
- **Brazil ONS** — verified regional half-hour average load, `MWmed`, keyed by the authority's source UTC event time and area `SECO`, `N`, `NE` or `S`. Comparisons require **matching weekday and UTC half-hour**, at least 8 distinct historical comparable periods within 180 days.
- **Singapore MPA** — official vessel arrivals >75 GT by type and **calendar month**, keyed by the exact month/type. Comparisons require the matching month and vessel type in at least **three distinct previous years**. The latest reported month is not live port traffic.

Both sources are read from **immutable, source-root-sharded history** on the evidence branch, not from overwritten latest snapshots or truncated public caches. A repeated poll of one published period is not additional evidence. Conflicting values for the same source-period identity cause a fatal integrity error rather than a silent average.

## Interpretation and restrictions

The report `observations/latest/metric_cohort_baselines.json` has schema
`cairn.metric-cohort-baselines.v1`. Data are published for inspection in
`metric_baselines.json` on GitHub Pages and as a small readout on
`coverage.html`.

- `insufficient_or_incomplete_baseline` means inadequate comparable prior readings, stale provider health, or delayed source reporting. **Do not show an anomaly gauge.**
- `descriptive_matched_cohort` means the contract has sufficient historical observations *for a descriptive comparison only*, not verified security-anomaly detection.
- Numerical robust deviation uses `(current - historical median)/(1.4826 * MAD)` only if comparable coverage and MAD > 0. Zero MAD produces **null**, never infinity.
- Source-dependent observations, simultaneous shared explanations and missing measurement periods remain epistemically distinct.
- No automatic warning, supporting or contradicting hypothesis weight, attacker attribution, country coverage certification, or predictive claim is approved.

## Data limitations to address

A key practical constraint: the original ONS ingest stores the latest historical half-hour observation for each grid region on each polling day. Therefore a full matched weekday/half-hour baseline will **not** be ready instantly and requires many actual sampling days unless a separately verified historical backfill is added. The current Singapore sample contains a bounded recent-month window and will generally require historical pagination before a same-month multi-year baseline becomes available.

**Do not substitute a 10-month simple average for seasonal monthly baselines, and do not claim that a single ONS reading proves a blackout.**

## Tests and deployment
- `python -m unittest tests.test_metric_cohort_baselines -v`
- `python -m unittest discover -s tests -v`
- `node --check dashboard/coverage.js`
- Collector publishes the report only **after** the family archive succeeds. Calibration failure does not suppress already collected source receipts, but it surfaces a failed workflow after the partial push.
- Dashboard build publishes a `metric_history_not_yet_collected` placeholder when its evidence branch has not produced the report yet.
