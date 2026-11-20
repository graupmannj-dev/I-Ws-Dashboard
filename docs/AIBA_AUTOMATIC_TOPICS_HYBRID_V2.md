# AIBA autonomous analytical-family matching — issue #75, v2

## Purpose and hierarchy

Source fragments → original documents/notices → **unreviewed analytical theme**
→ candidate actual incident (separate resolver) → independently corroborated event
(separate review). A topic is a reading group. Group membership does not imply
one physical occurrence or an independently verified claim.

## Implementation

- Local, no-download, deterministic title embeddings: word and bigram TF-IDF
  combined with character 3–4-grams, plus randomized low-rank latent semantic
  analysis (24 dimensions, fixed seed). Uses existing pinned NumPy/SciPy.
- Hybrid nearest-neighbor candidate discovery across historical topic seeds and
  source titles. Prior assignments are retained unchanged. Unassigned source
  observations never disappear from the evidence interface.
- Hard barriers *before* accepting similarity: incompatible explicit geographic
  subjects, incompatible source domains, conflicting recognized functional
  activity roles, or only generic source-template language. Publisher labels
  alone are never evidence of independence.
- General linguistic normalization for paraphrases (ship/vessel, cargo/freight,
  interdiction/blockade, communications/network, etc.), not topic-specific
  rules for Denmark, Iran, or other watch areas.
- Persist per-original-document match explanations, source-independent topical
  IDs, first-observed chronology, historical document totals and model schema
  with the existing evidence archive. The public projection remains bounded.
- The expanded evidence workspace shows *why* each source document attached,
  including shared terms and a text-similarity score clearly labeled as **not
  the probability of one actual event**.

## Safety and QA gates

- Negatives: same country with incompatible activity (Iran agreement vs
  blockade), disjoint country-code network measurements, generic travel
  advisory forms, unrelated FAA template restrictions and unrelated domain
  stories.
- Positives: paraphrased cargo interdiction reporting, cross-source
  commercial/prediction-market discussion of the same maritime topic, repeated
  dated references with a stable long-lived family ID.
- Measure positive-pair recall and false-join rate on a fixed adversarial
  fixture set; do not treat fixture scores as field-validated precision.
- Audit real current observations read-only through GitHub Actions, plus
  standard unit, production-site and Playwright browser tests.
- No automatic threat warning or event confirmation, no inferred incident
  coordinates, no cloud machine, token or paid model. Collection gaps remain
  unknown, not zeros.

## Explicit limitations

This is **corpus-local latent semantic representation**, not a pretrained
multilingual sentence transformer. It can recover lexical paraphrases and
context shared in an English-language source corpus but may miss genuinely
different-language reporting, indirect causal links, and similar topics with
few shared content terms. Latent representation is retrained per collection
batch, so only new matches use it; immutable previously accepted assignments
do not silently drift.

Future improvement: benchmark small multilingual open-weight embeddings with
a fixed holdout from independent source providers before choosing a deployable
model. Measure false merges, missed semantic links, collection runtime,
resource footprint and changes in family identities across versions. Keep
unreviewed links reversible and source provenance permanent.
