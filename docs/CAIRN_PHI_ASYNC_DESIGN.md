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

## Stage 2 implementation: independent publication and browser checks

1. Remove synchronous Phi execution from the `collect` job. Source Page deployment succeeds and becomes available first.
2. Add a post-`deploy` job for the pinned local model, storing validated `cairn.phi-sidecar.v1` results on a dedicated `cairn-phi-results` branch. Limit branch writes and serialize them; never write the collector's `aiba-feed-data` branch.
3. Embed the packet hash into the source-built `hypotheses.json`. Browser accepts a sidecar row only when its case ID, input SHA256, model/schema identity, source provenance and bounded model timestamp agree with the currently viewed source packet. Treat unavailable, expired or mismatched rows as pending/stale, not negative evidence.
4. Extend tests with a real Pages preview browser case, a stale-cache test, a corrupt-sidecar test, and proof source publication completes before inference.

**Release requirement:** Do not merge the cutover until the full PR suite, browser-side failure cases and GitHub Actions workflow validation pass. The `phi-postdeploy` job consumes the exact `github-pages` artifact from its own successful deployment (not a mutable Pages URL), so CDN propagation cannot silently swap the evidence snapshot. It runs only after `deploy` succeeds, caches only checked model/runtime files, and commits only `phi/latest.json` to the separate `cairn-phi-results` branch. The browser fetches that raw GitHub file; a missing/expired/unmatched result becomes a conspicuous pending/stale state, never an approved assessment. `phi_async_enabled` enables the overlay only on new source publications.

The source Pages publication still writes a no-inference `semantic_ach.json` fallback, which is deliberately **not** allowed to override a future sidecar result. On failure of the optional local Phi command, the sidecar assembler emits explicit failed results without altering signed ACH evidence or blocking the deployed source page.

**Browser caution:** A source hash is an input identity check, not an authentication signature. Trust in the public sidecar ultimately rests on repository permissions and GitHub-hosted content. The viewer additionally checks freshness, no model ACH evaluations, source URLs and source-key membership, but a model is never permitted to approve source truth.

## Acceptance

- Pages source publication does not wait for the optional model run.
- Unchanged, valid, fresh packets do not trigger model download or inference.
- Changed, stale, corrupted or model-failed packets never inherit an apparently fresh result.
- No model-signed ACH evidence, warnings, fabricated source links or private prompt logs can reach the public sidecar.
- GitHub Actions and browser tests prove the above; track timings rather than assuming cost or latency improvements.
