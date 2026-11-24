# CAIRN: Granite 4.0 Micro vs Phi-4-mini-instruct — read-only benchmark

**Isolation:** Experimental pull-request-only GitHub Actions. No new workflow is merged, scheduled, or added to production. No OpenAI API, model provider hosted endpoint, CI secrets, alert changes, ACH signed evidence modifications, or repository writes. Runs on a free standard public-repo CPU runner with 4 CPU / 16GB RAM. Every model receives the same deterministic real-source probes and local JSON-output task.

## Models

- IBM Granite 4.0 Micro Q4_K_M — IBM-owned GGUF repository `ibm-granite/granite-4.0-micro-GGUF`.
- Microsoft Phi-4-mini-instruct Q4_K_M — independent GGUF quantization `bartowski/microsoft_Phi-4-mini-instruct-GGUF`, originating from Microsoft's open-weight base model.

Both model downloads are read-only. The runner prints the Hugging Face snapshot revision, local SHA-256 of the downloaded file, and the llama.cpp commit. Using a third-party Phi quantization is a separate supply-chain consideration; independently validate/reproduce the quantization before production.

## Dataset and scoring

1. Checkout CAIRN's actual retained `aiba-feed-data/observations/latest/family_archive.json` as a read-only second working tree. Refuse to run if the real evidence is absent.
2. Select up to 8 diverse, distinct information-root source records across modes, deterministic based on source title and root hash; preserve IDs, titles, mode, ingestion timestamp, and source root hash. Repeated root content does not count as independent observations.
3. Generate one three-hypothesis ACH problem per real source. Add three **controlled** epistemic probes built on those same real source titles, including the difference between absent evidence and evidence of absence.
4. Use a single prompt, deterministic temperature zero, the same Q4_K_M quantization tier and the same CPU/thread/context settings for both models.
5. Score JSON parse, strict schema adherence, evidence-key fidelity, explicit uncertainty, and diagnostic caution. Record elapsed response time, token usage and llama-server peak RSS.
6. Retain individual outputs as a non-production GitHub Actions artifact for inspection.

**Interpretation boundary:** The source title is a source assertion, not a source document or independently verified military incident. The project does **not** possess adjudicated event-level truth for these source samples. Therefore, the benchmark measures adherence to source-honest analytical rules and comparative model behavior; it cannot measure real-world predictive accuracy, whether a hostile event happened, or whether a model's ACH likelihood assignments are correct. Diagnosticity checks are deliberately conservative and imperfect; raw rationales must be examined before choosing a model.

**Model failure is a result, not a pass.** Each sample records model timeouts, invalid JSON or rationale failures. A missing model artifact invalidates that model's comparison. No fabricated results or synthetic replacement evidence are permitted.

## Cost and reproducibility

GitHub's standard public-repository Ubuntu-hosted runners are free; no paid API is called. Infrastructure and model file hashes are recorded in the job logs. Runtime model downloads can fail due to Hugging Face/network restrictions and must be reported as failures, not interpreted as analytical weaknesses.

**No code or model is authorized for production use on the basis of this benchmark.**
