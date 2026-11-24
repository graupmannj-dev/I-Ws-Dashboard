# Phi structural reliability audit

This is the M1 follow-on to PR #113. GitHub Actions publishes a separate `cairn-semantic-ach-<run_id>` ZIP artifact for each successful publication. Download distinct artifacts and extract each `semantic_ach.json` to a **different filename** (for example `receipts/run-001.json`, `receipts/run-002.json`). Do not overwrite an earlier run.

```bash
python -m scripts.cairn_phi_reliability_audit receipts/*.json --out phi-reliability-audit.json
python -m unittest tests.test_cairn_phi_reliability_audit -v
```

The default release gate requires **at least 50 actual case-runs from at least five distinct publication timestamps** and at least **98% schema-valid results**. This is an observed operational threshold, *not a statistical guarantee*: repeated observations on the same 10 cases are correlated. The audit deduplicates repeated downloads of the same timestamp, excludes model-skipped cases from the denominator, groups failure codes, counts recovered format retries, and fails closed if a published success contains fabricated evidence keys or model-generated ACH directions.

**Interpretation limits:** A structurally valid response is still a provisional machine interpretation based on source titles. This audit does not establish that an event happened, a source is true or independent, an interpretation is substantively correct, or that predictions are calibrated. Separate independently adjudicated source and outcome evaluation is M4. Do not use this percentage as the predictive precision of CAIRN.

**Reproducibility:** Retain input artifact run IDs, model hashes, action job links and audit JSON with each decision. Never log or publish the raw model prompt, source text, or uninterpreted failure output to this public repository.
