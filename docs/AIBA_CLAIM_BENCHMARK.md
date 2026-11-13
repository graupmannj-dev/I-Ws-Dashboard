# AIBA claim extraction — reproducible synthetic diagnostic benchmark

This PR introduces a **synthetic, developer-authored, non-blinded** benchmark,
not real-world performance validation. It runs on GitHub Actions and locally.
The suite includes 20 source-claim inputs and 8 report-pair scenarios.

## Run

```sh
PYTHONPATH=. python scripts/aiba_claim_benchmark.py --output /tmp/aiba-claim-results.json
PYTHONPATH=. python -m unittest tests.test_aiba_claim_benchmark
```

The resulting JSON includes each expected vs predicted claim, exact
actor/action/object/assertion-status agreement, literal evidence-span integrity,
true positives, false positives, false negatives, specificity of negative
examples, abstention and report-pair relation classifications. Pairwise metrics
include **false same-event nominations for known different events**.

The runner does not hide poor quality or reclassify candidate matches as
confirmed incidents. Optional `--fail-on-false-merge` is a strict diagnostic
for known-negative pairs. The CI currently checks fixture integrity and runs
a metrics report; it does **not** enforce an unsupported precision threshold.

## Test design

Positive cases include reported strikes, interception, detention, port
closure and seizure. Adversarial examples include a source denial, quotation,
hedged claims, passive voice, proposed/predicted operations, pronouns,
compound clauses and unrelated commercial notices. Relationship cases include
the same apparent incident reported from New York and Kyiv, incompatible
source-declared event sites, unrelated nearby incidents, an exact article
syndication and a repeated original document.

**The current literal parser is expected to make mistakes**. For example,
the benchmark deliberately includes hedging and attribution structures that
can incorrectly contaminate actor boundaries. A numeric score from these
tests is diagnostic only; it does not estimate real-world sensitivity,
precision, or source-independent evidence.

## Next evaluation gate

Acquire permissibly accessible original report body text with URL, acquisition
timestamp, license/permission, provenance and article-specific identity.
Have at least two independent annotators label source assertions and disputed
claims without seeing model predictions. Adjudicate disagreements and split
train/tuning and held-out evaluation at **source-story lineage** level to
prevent syndicated articles leaking across splits. Include actual no-event
base rates and difficult same-area/different-event negatives.

Report claim-level precision/recall, span accuracy, source-by-source
abstention, correct treatment of uncertainty and negation, event pair
precision/recall, **false-merge rates**, and uncertainty intervals. No
unreviewed candidates may feed automatic alert levels. No automatic production
monitoring, article scraping, UI change, cloud resources or paid models are
introduced by this benchmark.
