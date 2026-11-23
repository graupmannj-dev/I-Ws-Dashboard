# CAIRN Granite vs Phi: harder read-only ACH evaluation

This experiment **does not select or enable production inference**. It extends draft PR #109, remains outside main, has no secrets, and writes results only to 14-day GitHub Actions artifacts.

## Design and provenance
- **Frozen real archive:** `aiba-feed-data` commit `af5c2d1ac9d5d697973459965e3097b473dfd4fb`. Eight genuine CAIRN retained source titles are incorporated as unverified reporting, never claimed as adjudicated military events.
- **16 controlled fictional scenarios** including independent authenticated attack orders, matching exercise evidence, source syndication, coverage gaps, no observations, geophysical explanations, debunked imagery, off-target geography, stale dates, withdrawal, cross-source checks, and source-embedded prompt injection. Stipulations are **not real-world historical labels**.
- **Two hypotheses** evaluated independently in each of 24 cases, with referenceable evidence IDs and information roots. The model must justify evidence directions, cite original packet IDs, distinguish sources vs independent roots, report event and intent verification separately, and specify a useful next discriminator.
- **No label leakage:** The prompt includes general ACH decision rules, not the case's predetermined correct directions or verification labels.
- **Evaluator:** The exact categorical labels are authored before execution. Per-case report contains directions, source IDs, rationales, false-direction counts and deviations from epistemic flags. This is a controlled rubric, not blinded expert judgment or true strategic forecasting accuracy.
- **Model setup:** Granite 4.0 Micro and Phi-4-mini-instruct, Q4_K_M weights from earlier benchmarks. Exact Hugging Face revision and previously measured SHA256 are pinned. The CPU inference runtime is pinned at the previously measured `llama.cpp` commit. Four CPU threads, 4096 context, 650-token maximum, strict JSON-schema output, no external inference calls, and no paid API.
- **Partial information:** Real retained records remain title-level assertions. The hard rubric is a stress test of source fidelity and reasoning, not a substitute for full original-source retrieval and analyst-adjudicated ACH ground truth.

## Scoring

Score per-model: JSON validity, complete schema, evidence-ID validity, independent-root count, event/intent/coverage verification, directional exact match, unsupported directional classifications, and generation wall time / model server high-water RSS. All 24 cases count in the denominator, including timeouts and malformed JSON.

**Safety-critical failures** include fabricated evidence keys, treating syndicated reporting as independent, source text instructing the model, directional evidence without observed content, off-location/stale observations, and absence-of-report evidence against a hypothesis without demonstrated sensor completeness.

## Decision gate

Do not approve automated ACH direction based on high JSON validity alone. A model must demonstrate both low unsupported directional rate and reliable, source-linked positive detection on explicit attack preparation. These small suites cannot establish field accuracy; if both fail, retain extraction-only possibility and require richer independently adjudicated evidence and manual audit before production deployment.
