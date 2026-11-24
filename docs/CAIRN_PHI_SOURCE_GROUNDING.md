# CAIRN Phi: original-source evidence grounding — stage 1

This is the read-only, **ephemeral** document-to-passage foundation for Milestone 3. It does not authorize the model to sign an ACH direction or establish event occurrence.

## Existing trusted boundary

The extractor `scripts/cairn_phi_source_grounding.py` calls the existing `scripts.cairn_source_inspection.read_original` only for eligible original-source URLs drawn from CAIRN's already identified evidence families. That reader enforces an explicit host allowlist, HTTPS, DNS-public-only checks, redirects disabled, bounded response size, safe content types and minimum document narrative length. Source documents are processed in memory and never committed to Git, copied into Pages, or uploaded as a CI artifact.

Each ephemeral passage retains the original URL, source title, original `evidence_key`, first observation timestamp if known, source publication timestamp if actually available, inspection timestamp, complete-document SHA256, excerpt SHA256, and a reproducible passage ID. The packet distinguishes lexical overlap from verified relevance; neither source text nor two syndicated references proves an event, source independence, actor intent or a decision.

## Hard budgets and injection safeguards

At most four original documents per packet, at most two passages per document, at most 400 characters per passage, at most 1,100 excerpt characters overall. Repeated URLs are not treated as independent corroboration. Obvious text instructions embedded in source passages are discarded, but this pattern filter is **not sufficient** for prompt-injection defense: the local model must still handle *all* source content as untrusted data. Documents that are inaccessible, unsupported, unlicensed for republication or too short fail to an explicit no-passage state rather than fabricating text.

No raw source body and no snippets should be put into GitHub Actions logs or a public sidecar. The model should only return sanitized, source-key-linked paraphrased verification leads.

## Stage 2: model prompt and provenance-validated output (feature-gated)

The follow-on stage-2 branch uses the `CAIRN_PHI_INSPECT_ORIGINALS=1` environment flag to invoke this original-source reader within each **local loopback-only** Phi request. Without that flag the existing title-only model behavior remains unchanged. When passages exist, the model sees bounded, explicitly untrusted excerpts, original evidence keys, and passage IDs, and may return `basis=inspected_passage` with the exact passage ID. The adapter checks the source-key/passage pair and copies the original URL, inspection timestamp and source-body SHA256 from the trusted extraction packet—not from the model. Invented passage IDs are rejected without format retry. The public output never includes source excerpts or complete original article text.

A result based on original document text is labeled `unverified_original_source_lead`; a title-only output remains `unverified_source_title_lead`. Both lack authority to certify incidents or alter ACH judgments. The browser independently checks source-URL membership in the currently published hypothesis evidence, body-hash syntax, passage-ID syntax, freshness and no model-produced ACH direction.

**Cache conservatism:** Original-source pages can change while a headline/source-family packet is unchanged. Until the upstream model preflight independently rechecks the source-body hash, **grounded rows are not reused from the M2 cache**. A fresh grounded output can be displayed if its full provenance passes validation; subsequent publications rerun it instead of silently treating stale source text as current. This trades inference cost for integrity and must be measured. Follow-on optimization may revalidate the whole-document body digest before allowing reuse.

**Source-access limitation:** An actual prior production inspection attempted eight documents but retrieved full narratives for only two. Reuters/other publishers returned 401/403 for many regionally relevant records. Do not attempt credential bypass or infer anything from those missing documents. Expand transparent, primary, geographically diverse accessible providers in subsequent iterations, measure real original-source coverage separately, and preserve title-only status when original text cannot be inspected.

**Release gates still required:** Full CI; pinned live Phi JSON smoke; real-source read-only coverage test with source accessibility reported independently; production result-case audit; never treat a model note as adjudicated real-world outcome. Historical predictive discrimination belongs to M4.

**Stage 1 is a non-inference helper; stage 2 is not activated in production until its own PR is validated and merged.**
