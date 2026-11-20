# CAIRN source expansion — public procurement and encyclopedia attention

Added two source-separated **experimental contextual** collectors to the existing
`collect-cairn-alternative-sensors.yml` three-hour workflow.

## Source contracts

- `uk_tenders`: UK Find a Tender service's official OCDS
  `/api/1.0/ocdsReleasePackages` public release endpoint. Query is bounded to
  a rolling two-day *update* window and 100 entries. Each release uses its
  OCDS release ID + OCID as its root and original release timestamp. This is
  a **partial publication sample**, NOT proof of purchasing, urgency, physical
  stockpiling, delivery or a defense-sector signal. Live accessibility and
  provider schema stability must be validated through collection health.
- `wiki_edits`: Wikimedia's public `action=query&list=recentchanges` API
  for `en`, `fr` and `es` Wikipedia main-namespace pages, a rolling
  three-hour interval capped at 500 changes per edition. Collector publishes
  only an aggregate change count, distinct-article count and a bounded list of
  most-edited **public page titles**; never editors, IPs, comments or revision
  contents. No national event attribution or predictor validity is implied.

Both streams write their own current source-health receipts even when providers
fail, and never convert nonresponse to zero activity. Existing source records
are retained only as history; failed readings do not enter the current
behavioral registry. Sampling caps and first-provider baselines are explicit.

## Validation and interpretation

`python -m unittest tests.test_alternative_sensor_pipeline -v` checks
schema validation, independent failure handling, source identity, clocks,
first baseline behavior and omission of editor identifiers. GitHub's publishing
workflow is approval gated; merging source code does not guarantee a successful
collector or update the public Atlas until publication passes.

The model does not assign warning weights to publication or edit counts without
matched history and explicit hypotheses. If a provider returns 403, schema
errors or an empty partial result, examine `observations/health/` before
attributing meaning to the absence.

Sources:
- https://www.find-tender.service.gov.uk/apidocumentation/1.0/GET-ocdsReleasePackages
- https://www.mediawiki.org/wiki/API:RecentChanges
