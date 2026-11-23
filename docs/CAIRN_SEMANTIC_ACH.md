# CAIRN semantic ACH — bounded model interpretation

## Status and trust boundaries

This is a provisional, versioned hypothesis interpretation and evidence-family comparison, **not an autonomous intelligence assessment**. It never writes signed `data/hypothesis_reviews.json` entries, changes reviewed evidence direction, attributes hostile intent, or issues an operational warning. It runs in the trusted GitHub Actions **main** publication collection job only, never in public JavaScript or on untrusted pull requests.

For a live model call, set GitHub Actions secret **OPENAI_API_KEY** and Actions variable **CAIRN_SEMANTIC_MODEL** to a model supporting Chat Completions JSON mode. When either is missing, the site publishes `not_configured` status and no model-origin evidence directions. Secrets must never be stored in the repository or frontend. No external AI service is activated by this pull request itself.

## Processing contract

1. Read the generated `_site/hypotheses.json` and gather each case's primary hypothesis, alternatives, evidence families, source health and HTTPS links.
2. Use CAIRN's existing local hybrid word/character TF-IDF and latent-semantic similarity to prioritize a bounded candidate set (with deterministic lexical fallback). Retrieval similarity is not event identity, confirmation or ACH evidence direction.
3. For up to **three cases per three-hour slot**, send a bounded, redacted source-title/reference packet to the configured model through `https://api.openai.com/v1/chat/completions`. This has API costs if enabled. The prompt directs the model to treat all source text as untrusted evidence, not instructions.
4. Require a JSON object containing explicit hypothesis-by-hypothesis interpretations, observable discriminators and candidate classifications. Only existing evidence IDs are accepted. Unsupported IDs, direction labels, wrong hypothesis indices or malformed results fail the case closed.
5. Publish `_site/semantic_ach.json` and a `semantic_review` field for each case in `_site/hypotheses.json`. An Actions artifact retains the run result for 90 days. Input hashes, model name and prompt version support review; this is not permanent historical retention.
6. Expose a source-linked, clearly provisional comparison below the reviewed ACH matrix. Review-gated balances and approved signed labels remain unchanged.

## Limitations and next validation gates

- Original source titles and mechanism descriptions are not original document text or independently verified incident facts.
- Even the hybrid local semantic shortlist can miss non-obvious evidence; recall and family-level retrieval quality need held-out testing.
- No semantic labels have been calibrated against an independently adjudicated corpus; do not treat them as likelihoods or corroboration.
- Cases not selected in the capped rotation remain `not_selected_in_bounded_run`. The site does **not** retain earlier per-case model results between deployments. A durable, versioned state store and incremental cache are required before this becomes a comprehensive persistent analyst service.
- To promote a model proposal to reviewed evidence, a human must independently inspect the source and explicitly enter a signed reviewer judgment in the separate review contract.

## Offline tests

`python -m unittest tests.test_semantic_ach -v` and existing `python -m unittest discover -s tests -v`.

A live end-to-end test with actual API credentials should only be run after the operator has selected a supported model, budget caps and source-sharing rules.
