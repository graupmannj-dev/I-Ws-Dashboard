# AIBA: private source-text intake and claim graph — operational boundary

This milestone follows PRs #52–#55 and closes three engineering gaps:
(1) source text remains missing in the observed 72-hour AIBA feed;
(2) synthetic claims alone cannot validate event identity;
(3) copied press releases and shared headlines are not independent corroboration.

**No automatic warning change, merge, source-content publication or server/cloud
deployment.** The current public registry still has title-level observations.
This PR supplies a local/offline body-ingestion route and a candidate graph
for future separately reviewed real-text intake. It is not active on the live
AIBA collectors.

## Single-command private evaluation workspace

Once permission-approved original source bodies or excerpts are present in
`private/approved_input.jsonl`, the integrated claim lab can run intake,
literal claim extraction, report-pair candidate nomination and two independent
prediction-blind annotation packets in one local command:

```sh
PYTHONPATH=. python scripts/aiba_claim_lab.py \\
  --input private/approved_input.jsonl \\
  --workspace private/claim_lab_run
```

This creates `reports.jsonl`, `lineage_splits.json`,
`candidate_claims.json`, `candidate_relationships.json`,
`reviewer_A.jsonl`, `reviewer_B.jsonl` and `receipt.json`
in the private workspace. The manifest is reused on subsequent runs so
the same story lineage cannot switch evaluation partitions. Corpus
content stays local and the command prints only aggregate counts.

**Important:** The current AIBA live history does not yet supply article
body text; this command is not deployed or invoked by existing collectors.
It will not produce actual field-validation metrics without a permitted
source corpus and independently adjudicated ground truth.

## 1. Provider-neutral article text intake

`scripts/aiba_source_text_intake.py` requires an operator-controlled JSONL
with source-specific HTTPS article URL, original body or bounded source excerpt,
story-lineage ID, UTC retrieval date, content type, provenance, exact permission
basis and a specific rights explanation. A generic accessibility claim does not
qualify as permission to copy.

```sh
PYTHONPATH=. python scripts/aiba_source_text_intake.py \
  --input private/approved_input.jsonl \
  --private-output private/reports.jsonl \
  --manifest private/lineage_splits.json \
  --receipt private/intake_receipt.json
```

The importer refuses malformed URLs, missing source content, duplicate source
documents, unsupported rights, invalid typed sites, oversized bodies and
lineage split conflicts. Stable assignment keeps a single source-story lineage
in one development or held-out partition. **Hash partitioning does not create
an independent randomized sample:** retain the manifest and perform manual
source/period stratification in a real evaluation.

The importer stores only local/private artifacts, with source text SHA-256
hashes. Never commit licensed full-text corpora to the public GitHub repository
or to Pages; do not assume `rights_basis=public_domain` proves ownership.

## 2. DVIDS first-eligible provider adapter

DVIDS' documented `/search` and `/asset` API endpoints expose news metadata
and asset `description`. Source location is where the media was created, **not**
necessarily the site of an alleged security incident.

DVIDS reports that federal agency media are generally public domain unless
otherwise marked. Asset-specific review remains mandatory (including credited
third-party material). Register for an API key via
https://api.dvidshub.net/docs and read
https://api.dvidshub.net/docs/copyright before populating the approval list.

1. Create local `private/approved_dvids_ids.json` containing explicit reviewed
   `news:1234567` identifiers (not a blanket list of all DVIDS assets).
2. Set `DVIDS_API_KEY` in the local environment, **never in GitHub source or
   logs**. This is opt-in only; no collector or GitHub CI job uses credentials.
3. Fetch a maximum of 25 reviewed full `news` asset records per invocation:

```sh
PYTHONPATH=. python scripts/aiba_dvids_fetch.py \
  --approved-ids private/approved_dvids_ids.json \
  --private-export private/dvids_export.json
```

4. Feed the result through the asset adapter with an ISO UTC retrieval time:

```sh
PYTHONPATH=. python scripts/aiba_dvids_asset_adapter.py \
  --asset-export private/dvids_export.json \
  --approved-ids private/approved_dvids_ids.json \
  --retrieved-at 2026-11-13T19:30:00Z \
  --private-output private/reports.jsonl \
  --manifest private/lineage_splits.json \
  --receipt private/dvids_receipt.json
```

This adapter demands news assets with complete descriptions and matching DVIDS
article-specific URLs, rejecting unsupported categories, incorrect URL IDs,
unapproved rights and missing bodies. DVIDS descriptions can contain press
material, background, opinion or non-incidents; they are **source assertions**
rather than confirmed events. Same-source reposts and reproductions require
manual shared-lineage reconciliation. Full-text availability and licensing
have not yet been tested with a user's DVIDS key.

## 3. Claim-aware report relationship nominations

```sh
PYTHONPATH=. python scripts/aiba_extracted_claim_graph.py \
  --reports private/reports.jsonl \
  --output private/claim_candidates.json
```

The tool obtains literal source evidence spans from the existing claim
extractor and proposes review relationships only when controlled actions
match and actor/object token overlap is sufficient. It disqualifies
same-event nominations when two explicit source-declared incident times
differ by more than 72 hours or two valid explicitly reported incident
sites are more than 150 km apart. Neither number is a calibrated event
identity threshold.

Same `story_lineage_id` implies possible copying, **not independent evidence**.
The location of the publisher or source asset never becomes the incident
site. Identical words from two distinct reports still may describe
two separate events, so every output remains unreviewed. Claim pair
matching is deterministic, English-only and conservative; it can miss
paraphrases, passive language, negated accounts and multilingual evidence.
It has no automatic event merge, warning update or alert.

## 4. What remains before operational adoption

- Create a **real** multi-source, multilingual corpus under provider terms
  with body-availability denominators and signed provenance.
- Blind double-code actor, action, object, source-asserted time/site,
  reporting lineage, uncertain allegations and incident identity;
  adjudicate disagreements.
- Hold out entire story lineages and source/time strata; report claim span
  precision/recall and pair false-merge rates with appropriate intervals.
- Review failures and correct parser, source alignment and copy detection.
- Only then consider a separate opt-in Atlas preview for reviewed candidate
  evidence, with explicit unverified labels and no automatic escalation.

The synthetic 100% scores from PR #54 must **never** be reused as evidence
of performance on full original source reports.
