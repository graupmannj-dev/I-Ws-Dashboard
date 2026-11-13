# AIBA real GOV.UK source-text corpus pilot

## What this changes

PR #55 established blinded annotation and held-out evaluation; #56 provided
operator-approved offline intake and a claim graph. This milestone provides a
**credential-free, legitimate real-text acquisition path** using the official
GOV.UK Content API (https://content-api.publishing.service.gov.uk/). It is
bounded to a reviewed list of 38 actual GOV.UK official content pages with
three sampling strata:

- 16 `incident_candidate` articles and statements, including distinct
  Houthi/Red Sea operations and a report concerning attacks in Ukraine;
- 10 `operational_context` releases concerning deployments, exercises,
  Ukraine assistance and defense capabilities;
- 12 `nonincident_control` sources, such as housing, recruitment and
  training reforms.

**Sampling stratum is not event truth.** Even the first category can include
false, negated, hypothetical, or copied allegations. The corpus is heavily
weighted toward the UK government and cannot establish independence or
worldwide representativeness.

## Rights and API provenance

Official API: https://www.gov.uk/api/content/{page_path}

Documentation: https://content-api.publishing.service.gov.uk/

Licence: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

Official documentation says authentication is not required, and rate limiting
is 10 requests/second/client. The code uses a slower default pace, a fixed
allowlist, 15-second request timeout, 550 kB response cap and redirects
disabled. It never scrapes arbitrary news publishers or accesses any paid
source. Each result is checked for exact original `base_path` and
`content_id`, source attribution, copyright-exclusion hints, publication
timestamp and sufficient body text.

The extractor takes official article paragraphs only; it does not include
figures, images, scripts, tables, blockquotes or embedded quotations in
<blockquote> HTML tags. Since authoritativeness and rights cannot be
perfectly inferred by software, the corpus is **provisional licensed
evaluation material** with `rights_verified_by_software=false`.
Always inspect licence exceptions and individual documents before wider
republication. This pilot is deliberately not a general web crawler.

## Run the corpus collection locally (no credentials)

Requires Python 3.11+. From the repository root:

```bash
PYTHONPATH=. python scripts/aiba_govuk_corpus.py \
  --seeds data/govuk_source_seed_manifest.json \
  --private-workspace private/govuk-eval \
  --minimum-success 12
```

The input manifest is the reproducible, reviewed URL inventory. A successful
run creates `reports.jsonl`, `acquisition_audit.json`,
`lineage_splits.json` and `intake_receipt.json` in the private
directory (ignored by Git). The script prints counts only, not article text.

Run the already-merged #56 end-to-end claim lab:

```bash
PYTHONPATH=. python scripts/aiba_claim_lab.py \
  --input private/govuk-eval/reports.jsonl \
  --workspace private/govuk-eval/claim_lab
```

This prepares original-source candidate clauses, possible report links, and
two prediction-blind independent annotation packets and a separate
event-pair review pool that includes both candidate matches and
challenging unlinked comparisons. The pair pool is not a labeled corpus. No independent
annotator decisions have been created by the software. No claim is verified,
and no event is automatically merged or used for warning escalation.

## Download source material without running Python

The GitHub Actions workflow **AIBA GOV.UK real-source corpus pilot
(read-only)** runs this pipeline on the PR and can be manually re-run.
The successful run includes a 30-day GitHub artifact named
`aiba-govuk-official-source-corpus`.

1. Open the linked PR and select **Checks**.
2. Open **AIBA GOV.UK real-source corpus pilot**.
3. Under **Artifacts**, download `aiba-govuk-official-source-corpus`.
4. Unzip it into a private directory on your computer.
5. Review `RIGHTS_AND_LIMITS.txt` and `acquisition_audit.json`.
6. Use `reports.jsonl` for original source excerpts; use
   `claim_lab/reviewer_A.jsonl` and `reviewer_B.jsonl` for actor/action/object
   annotations.
7. For **event identity pair review**, open
   `claim_lab/aiba_blind_pair_labeler.html` in a local web browser.
   Reviewer A loads `blind_pair_reviewer_A.jsonl`, reads both articles
   without looking at model predictions, labels the pair (same event,
   different event, same story, same document or uncertain) and exports
   a decisions file. Reviewer B separately uses the B packet and
   likewise exports decisions. The HTML page performs no API requests
   or uploads; note that opening the original source link in a new tab
   navigates to that external publisher.
8. After both reviewers complete all pairs, run the comparison audit:

```sh
PYTHONPATH=. python scripts/aiba_pair_label_audit.py \\
  --reviewer-a private/claim_lab_run/aiba_pair_reviewer_A_decisions.jsonl \\
  --reviewer-b private/claim_lab_run/aiba_pair_reviewer_B_decisions.jsonl \\
  --adjudication-template private/claim_lab_run/pair_adjudication_queue.jsonl \\
  --audit private/claim_lab_run/pair_review_agreement.json
```

The audit refuses missing decisions or identity mismatches and **never
auto-generates gold labels**. A reviewer/adjudicator must choose a final
label with an adjudication ID, after independent coding. When the
adjudicated file has been completed, use the PR #56 head-to-head
comparator to evaluate the title baseline against claim-based matching
on heldout reports. Never present annotator agreement as model accuracy.

GitHub Actions artifacts expire after 30 days; the sources can be reacquired
from the committed seed manifest. The public repo contains only source
URLs, code and tests; it does not commit copied article text.

## Crucial anti-leakage design

Each original government page retains a distinct `story_lineage_id`.
The reviewed `episode_hint` does **not** assert incident identity; it is
a conservative **split-blocking group**, ensuring that pages concerning
one plausible operation do not appear in both development and heldout.
Exact duplicate text across splits is also rejected. The graph cannot
promote an episode hint into corroboration or automatically merge an event.

## Limitations of the first batch

* One official source family is not multiple independent witnesses.
* Historical public announcements are not a leading indicator of preparation
  before public reporting.
* A claim analyzer trained on GOV.UK releases may perform poorly on field
  reporting, Arabic, Ukrainian, Russian, informal prose or social media.
* Manual episode-group hints are unverified and may need adjudication.
* Parser spans are not human ground truth. Two independent annotators must
  code reports and adjudicate differences before precision or false-merge
  performance can be estimated.
* Excerpting only official narrative paragraphs sacrifices recall in
  exchange for a simpler licensing and provenance boundary.

## Next prerequisites after this batch

1. Review source acceptance rates, actual claim counts, parser abstentions
   and false nominations identified by separate human coding.
2. Freeze an episode-and-story-disjoint held-out corpus and have two
   independent coders label source assertions and same/different events.
3. Run #56 title-only vs claim-aware comparison on identical adjudicated pairs.
4. Expand source families, including the DVIDS asset API once a key and
   asset-specific rights reviews are available. DVIDS official text is
   another government source, not independent confirmation of UK government
   event reports by default.
5. Propose a separate, clearly marked non-alerting dashboard preview only
   after these evaluations.

No collector scheduling, production deployments, alert thresholds, GCP or IAM
changes are included in this PR.
