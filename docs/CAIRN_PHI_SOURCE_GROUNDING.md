# CAIRN Phi: original-source evidence grounding — stage 1

This is the read-only, **ephemeral** document-to-passage foundation for Milestone 3. It does not authorize the model to sign an ACH direction or establish event occurrence.

## Existing trusted boundary

The extractor `scripts/cairn_phi_source_grounding.py` calls the existing `scripts.cairn_source_inspection.read_original` only for eligible original-source URLs drawn from CAIRN's already identified evidence families. That reader enforces an explicit host allowlist, HTTPS, DNS-public-only checks, redirects disabled, bounded response size, safe content types and minimum document narrative length. Source documents are processed in memory and never committed to Git, copied into Pages, or uploaded as a CI artifact.

Each ephemeral passage retains the original URL, source title, original `evidence_key`, first observation timestamp if known, source publication timestamp if actually available, inspection timestamp, complete-document SHA256, excerpt SHA256, and a reproducible passage ID. The packet distinguishes lexical overlap from verified relevance; neither source text nor two syndicated references proves an event, source independence, actor intent or a decision.

## Hard budgets and injection safeguards

At most four original documents per packet, at most two passages per document, at most 400 characters per passage, at most 1,100 excerpt characters overall. Repeated URLs are not treated as independent corroboration. Obvious text instructions embedded in source passages are discarded, but this pattern filter is **not sufficient** for prompt-injection defense: the local model must still handle *all* source content as untrusted data. Documents that are inaccessible, unsupported, unlicensed for republication or too short fail to an explicit no-passage state rather than fabricating text.

No raw source body and no snippets should be put into GitHub Actions logs or a public sidecar. The model should only return sanitized, source-key-linked paraphrased verification leads.

## Stage 2 integration (not implemented here)

1. Enrich the bounded **in-memory** local Phi inference prompt with these passages and explicit `passage_id` citations, preserving strict JSON and the analyst-approval boundary.
2. Reject any model statement claiming text inspection unless the cited passage ID belongs to that exact source and original URL. A title-only fallback must be labeled title-only.
3. Extend the M2 incremental cache contract: **the original source body SHA256 and inspection timing must participate in cache eligibility**. A case-hash match alone is insufficient when the underlying original document has changed.
4. Add controlled tests for statement negation, syndication, foreign-language/encoding failures, fake quotations, date/geography mismatch, and embedded instructions. Include real-source read-only CI probes with source accessibility reported separately from analytical validity.
5. Publish only provenance receipts and bounded model paraphrases. Do not claim calibrated warning accuracy; that requires M4's independent adjudications.

**Stage 1 acceptance:** Unit tests pass and source bodies never leave the bounded local call. No live inference workflow or UI is changed in this PR.
