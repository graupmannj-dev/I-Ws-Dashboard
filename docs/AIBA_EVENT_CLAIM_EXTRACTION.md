# AIBA experimental event-claim extraction (shadow v1)

## What this milestone does

AIBA now has a self-contained, deterministic **candidate-claim** extractor in
`behavioral_claim_extraction.py`. Its input is a source-associated report body,
not an RSS headline, a publisher address, a news URL alone, or an official
restriction notice. It extracts bounded, literal English clauses with actor,
action, and object **as written by the source**, preserving exact character
offsets and a source URL. A source assertion is not an observed event.

No auto-fetching of paywalled or third-party article content, outside model
service, geocoding, new schedule, or production pipeline modification is made.
The current behavioral registry largely contains titles and source links, so
most current records should **abstain** with `source_body_unavailable`. This
is an intentional safety constraint and a measurable ingestion gap, not an
extraction-system failure.

## Contract

Input requires `id`, HTTPS `source_url`, eligible `source_family` or
`source_kind`, and a supplied `source_text` (up to 12,000 characters).
Optional source-provided `event_at` and typed `reported_event_location`
may be carried through **unreviewed**. Source publication time, reporting
origin, coarse geography, region label, or restrictions polygon are **never
promoted** to time/location of an incident.

Output preserves `observation_id`, `source_url`, each candidate's
`actor_text`, controlled `action`, `object_text`, `assertion_status`,
`evidence_span {start,end,text}`, optional unreviewed event site and time,
and a stable `claim_id`. Negated or quoted statements are conservatively
excluded. Uncertainty terms receive `attributed_or_uncertain`. This
deliberately does **not** resolve passive voice, pronouns, nested attribution,
document duplication, multilingual reports, causal attribution or syndicated
origins. Complex sentences can be incorrectly parsed; humans must review
claims against the linked original source.

All claims are `candidate_claims_unreviewed`.
`independent_corroboration_established=false`,
`warning_level_change=false`, `automatic_alerts_created=0`.

## Validation gate before integration

1. Capture legally accessible, actual article-body text with article-specific
   provenance, source timestamp, body acquisition status, and exact offsets.
2. Construct a blinded, human-annotated evaluation corpus containing positive
   claims, no-event articles, hedging, negation, passive clauses, geographic
   ambiguity, syndicated stories and contradictory accounts.
3. Report actor/action/object span precision and recall, abstention coverage,
   event-site/time correctness, false-match and false-merge rates **by source**.
4. Only then connect candidate claims to the report relationship lane; retain
   source lineage and separate possible same event from possible same article.
5. Keep alert/escalation classification and corroboration gates independent of
   unreviewed extracted claims.

Run local checks with:
`python -m unittest tests.test_behavioral_claim_extraction`

This PR delivers the extraction component and unit contract only, not a
validated event resolution system or operational deployment.
