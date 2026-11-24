# CAIRN Phi: asynchronous sidecar architecture (M2)

The source data and GitHub Pages publication must not depend on Phi CPU inference. This document records the staged plan and the exact-input cache contract.

## Stage 1: versioned incremental engine

`scripts/cairn_phi_incremental.py` is a **pure local data-processing utility**. It does not contact any model endpoint, write to GitHub or alter reviewed ACH.

```bash
python -m scripts.cairn_phi_incremental prepare \
  --source _site/hypotheses.json \
  --prior phi-state/phi/latest.json \
  --work /tmp/cairn-phi-delta

# Only if the prepare output says "changed": N>0:
bash scripts/run_cairn_phi.sh --site /tmp/cairn-phi-delta --max-cases 10

python -m scripts.cairn_phi_incremental assemble \
  --source _site/hypotheses.json \
  --prior phi-state/phi/latest.json \
  --work /tmp/cairn-phi-delta \
  --output phi-state/phi/latest.json
```

The prepare step checks exact SHA256 of `semantic_ach.evidence_packet(case)`, the original model identifier, strict analyst-approval boundary, complete original source references and a 24-hour default TTL. Only exact-match, non-stale, fully validated provisional rows are reused. Changed cases are placed in a separate temporary `hypotheses.json` for local Phi; the trusted publication never changes. Failed model results remain explicit failures, not last-known-good results falsely dated as current. The assemble phase rejects evidence packets that change between prepare and publish.

A valid row remains an **unverified model interpretation**, not independently confirmed source truth or ACH direction.

## Stage 2 (not yet deployed): independent publication and browser checks

1. Remove synchronous Phi execution from the `collect` job. Source Page deployment succeeds and becomes available first.
2. Add a post-`deploy` job for the pinned local model, storing validated `cairn.phi-sidecar.v1` results on a dedicated `cairn-phi-results` branch. Limit branch writes and serialize them; never write the collector's `aiba-feed-data` branch.
3. Embed the packet hash into the source-built `hypotheses.json`. Browser accepts a sidecar row only when its case ID, input SHA256, model/schema identity, source provenance and bounded model timestamp agree with the currently viewed source packet. Treat unavailable, expired or mismatched rows as pending/stale, not negative evidence.
4. Extend tests with a real Pages preview browser case, a stale-cache test, a corrupt-sidecar test, and proof source publication completes before inference.

**Do not enable Stage 2 until tested end-to-end.** If downloading the deployed source document races GitHub Pages propagation, abort sidecar publication instead of analyzing stale data.

## Acceptance

- Pages source publication does not wait for the optional model run.
- Unchanged, valid, fresh packets do not trigger model download or inference.
- Changed, stale, corrupted or model-failed packets never inherit an apparently fresh result.
- No model-signed ACH evidence, warnings, fabricated source links or private prompt logs can reach the public sidecar.
- GitHub Actions and browser tests prove the above; track timings rather than assuming cost or latency improvements.
