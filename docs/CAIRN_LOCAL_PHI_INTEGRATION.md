# CAIRN: no-paid-API local Phi integration

Phi-4-mini-instruct now runs **on GitHub-hosted Ubuntu CPU runners only**. It is not a hosted Microsoft/OpenAI/Alibaba service. There are no paid LLM API credentials. The weights are downloaded at job execution, **never committed to Git**.

## Pinned supply chain

- Model: `bartowski/microsoft_Phi-4-mini-instruct-GGUF`, file `microsoft_Phi-4-mini-instruct-Q4_K_M.gguf`
- Model Git revision: `7ff82c2aaa4dde30121698a973765f39be5288c0`
- Model SHA256: `01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2`
- llama.cpp revision: `325914defd2c1279a039366d999dff4c19a75b54`
- Runtime: `llama-server` on `127.0.0.1:8080`, 4 CPU threads, 4,096 context, one inference request in flight, no CURL support compiled into llama.cpp.
- `scripts/run_cairn_phi.sh` verifies SHA256 each run, compiles pinned llama.cpp, starts server on loopback only, performs inference, and terminates server. Downloading model binaries is the only model-distributor network interaction; **source texts/hypotheses are not sent to the distributor.**

## Supported CAIRN components

**Publication:** `publish-global-watchboard.yml` first writes a no-inference `semantic_ach.json` fallback as usual, then optionally invokes Phi on up to 10 standing cases. Phi generates hypothesis interpretations and explicitly testable discriminators, plus up to six verified-key *source-title inspection leads* per case. Results appear within the existing `semantic_review` section of `hypotheses.json` and in the **Local Phi · hypothesis interpretation** section of the Hypotheses page. Original-source links reuse known source references. There are no independent review cycles.

**Analyst input:** The owner-approved issue workflow already performs a one-time historical evidence backfill. It optionally starts local Phi in the same issue-intake run to annotate the pending analyst hypothesis and evidence shortlist before creating the reviewable PR. If the inference step is unavailable, the backfill remains, an explicit limitation appears, and the PR can still be reviewed.

**Hard permission boundary:** This model cannot sign, approve, or create ACH evidence directions. The adapter ignores any `evaluations` field a model tries to return; it emits `evaluations: []`, `analyst_approved: false`, and `interpretation_only: true`. Do not assign higher authority to model interpretations. Earlier 24-case testing found the models unreliable at diagnosing actual supporting/contradicting evidence. Evidence keys are checked against the retrieval packet, and HTTPS source hyperlinks are never emitted by the model.

## Failure and cost policy

- In the publish workflow the optional Phi step has `continue-on-error: true` and a 24-minute timeout; the source feed, map, status and Pages publication still proceed if model weights are unavailable, the runner runs out of resources, or the model fails validation.
- The owner-approved analyst-intake workflow has a 22-minute optional step and 30-minute total job limit. It does not fail the PR creation if Phi is unavailable.
- The default no-inference fallback marks the semantic assessment `not_configured`, rather than fabricating a completed assessment. A locally interpreted case has `provisional_complete` with `evaluations: []`.
- No `OPENAI_API_KEY` or `CAIRN_SEMANTIC_MODEL` variable is consumed by either integration workflow.
- Standard public-repository GitHub Actions runners are free under GitHub's current billing policy. They still consume computation, GitHub bandwidth, and execution time; verify eligibility if repository visibility or plan changes.
- The production build will be slower when local Phi succeeds because the model must download, compile and evaluate. The upload/publish job itself is not blocked by inference *failures* but the optional step takes time until success or timeout. Monitor CI durations.

## Validation and next upgrades

`python -m unittest tests.test_cairn_phi_local tests.test_semantic_ach tests.test_analyst_hypothesis_lifecycle -v`

Live-model pull-request smoke checks run the same pinned weights on a synthetic source-linked hypothesis fixture. Production source judgments still require analyst review and source text retrieval. Long term: add reusable pinned binary artifacts and source-body extraction only if reviewed provenance controls are met.
