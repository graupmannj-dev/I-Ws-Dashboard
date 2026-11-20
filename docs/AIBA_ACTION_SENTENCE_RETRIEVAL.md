# AIBA action-language evidence retrieval — shadow-only research lane

## Why this is a distinct component

The first genuine GOV.UK 38-document research corpus produced only four
literal actor/action/object **candidate** extractions and 34 report-level
abstentions using the narrow PR #53 parser. We inspected development-source
language and found passive constructions, composite action phrases and
multiple actions inside one sentence. Worse, the few structured candidates
can assign incorrect actor boundaries. Increasing match thresholds or treating
this output as verified events would worsen AIBA's reliability.

This experiment separates *recalling potentially relevant source text* from
*asserting a structured actor/action/object incident*. It does not change,
replace, or loosen the approved strict extractor or report matcher.

## What this adds

`scripts/aiba_action_sentence_retrieval.py` scans legally ingested source
texts for a bounded vocabulary of action language. It returns each source
sentence verbatim with exact character offsets, original article URL and
the presence of caveat language (negated/denied, hypothetical/planned,
training/testing, attributed/alleged or policy context). It never claims
the act occurred merely because the sentence contains an action verb.

Outputs are always `unreviewed_source_action_language`, with no assumed
actor, no event geolocation, no independent confirmation and no warning
classification. The retrieval includes passive language intentionally but
cannot be treated as verified actor extraction.

Default runs only use `split=development`, keeping the seven initial
held-out GOV.UK reports untouched until independent labels are frozen.
The GitHub Actions test explicitly invokes development-only mode.

## Run

```bash
PYTHONPATH=. python scripts/aiba_action_sentence_retrieval.py \
  --reports private/govuk-eval/reports.jsonl \
  --output private/govuk-eval/development_action_sentences.json
```

The output includes per-sampling-stratum counts and source evidence spans.
Neither candidate count nor source coverage is a measure of precision,
recall, genuine incident detection, or false event-merge probability.
Negative controls can contain event vocabulary in retrospective background.

The new **AIBA development-only source action-sentence coverage audit**
workflow reacquires the 38 GOV.UK sources and records a 30-day diagnostic
artifact. It has no production integration, paid model, deployment or
notification actions.

## How to progress beyond lexical retrieval

1. Use this to identify missed **passages**, not automatically to assert
   more armed incidents. Human coders must label source statements
   independently, including uncertainty and negation.
2. Annotate exact actor/action/object spans only where the text supports
   them; label passive constructions without fabricating an actor.
3. Separately annotate event time, location, action type and source
   lineage; never infer incident location from government offices.
4. Evaluate false-positive retrieval and coverage using the actual
   independently reviewed sample, including nonincident controls.
5. Once a semantic extractor has held-out precision/recall evidence,
   compare it to the strict baseline on identical event pairs.
6. Keep reviewed source claims separate from AIBA operational warnings
   until independently validated cross-source relationships exist.

**An unreviewed candidate sentence is not intelligence corroboration.**
