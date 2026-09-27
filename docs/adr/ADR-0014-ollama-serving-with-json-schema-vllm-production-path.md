---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §8; spec §6, §6.2, §6.6, §9.4, §9.5, §9.10, §15, §20 L-09, §21 R-05/R-06; research constrained-decoding, gguf-export-and-ollama, vllm-production-serving
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0014: Ollama serving with JSON-schema format; vLLM as the production path

> **Amended in spec v1.1 (2026-09-27; change record A-19, A-04; ERPROT export/decoding impact items).**
> * Ollama ≥ v0.34.1 removed runtime LoRA (`ADAPTER`) and create-time quantization. **Merging and llama.cpp
>   quantization are therefore mandatory** (ADR-0012 export). Pinned: Ollama 0.34.x (0.34.4 ships llama.cpp b11081;
>   verify).
> * **Raw prompts** (`raw: true`) rendered from `prompt_format.json`, with byte-for-byte parity tests. A derived
>   **decoding schema** (refs inlined, every field required, key order = training order) is sent as `format`.
> * `num_ctx 8192` (Ollama defaults to 4k on CPU), `num_predict 512`, `temperature 0`, `seed 42`, `repeat_penalty 1.0`,
>   `truncate: false`, `OLLAMA_NUM_PARALLEL=2`, keep-alive 30 m.
> * **Drift gate:**
>   * BF16 GGUF vs HF merged model ≥ 98% field agreement;
>   * a quant loses ≤ 2.0 macro-F1 and ≤ 1 point recall per critical class;
>   * calibrator re-fitted per quant;
>   * the smallest passing quant is chosen (Q4_K_M + imatrix expected).
> * **vLLM production recipe:**
>   * 0.30.x pinned (many 2026 CVEs);
>   * `--structured-outputs-config.backend` (xgrammar) + `response_format` (the old guided-decoding fields were
>     removed in 0.12.0);
>   * `--logprobs-mode raw_logprobs` (post-bitmask; verify);
>   * compute capability ≥ 7.5, Linux only; on T4 fp16 with fallback attention;
>   * behind a proxy allowing only `POST /v1/chat/completions` and `GET /health`;
>   * ~10k tickets/day break-even (analytical).
> * Logprobs exist in Ollama (since v0.12.11), so the v1.0 open question (R-05) is downgraded (ADR-0017).

## Context and Problem Statement

The brief says "Ollama for MVP; vLLM for a production-serving discussion" (brief §8). The fine-tuned SLM is merged,
converted to GGUF and quantized (ADR-0012), then served on the CPU-only demo box (8 vCPU / 16 GB).

Triage must be schema-valid. The chain is: constrained decoding, strict Pydantic validation, deterministic repair,
one model retry, then fail-closed rules fallback (§6.6). M-04 targets ≥ 99.5% validity, with ≥ 98% on first pass.
Triage has a 15 s timeout (P7 `model_unavailable` on failure). Confidence uses path probabilities from logprobs
(ADR-0017), and readiness checks that Ollama's `/api/tags` includes the active model.

Which inference server should serve the SLM in v1, and what is the documented production path?

## Decision Drivers

* CPU-friendly GGUF serving with JSON-Schema constrained decoding (BR-027, M-04).
* Train/serve parity: what is measured is what is served (the same GGUF, quant, prompt rendering and Ollama
  version).
* Access to token logprobs for confidence.
* Security: internal-only, patched, integrity-checked model files.
* A credible, pinned production path on GPU (L-09).

## Considered Options

1. Ollama (pinned 0.34.x) with raw prompts + decoding schema for v1; vLLM documented as the production path (chosen)
2. llama.cpp server (`llama-server`)
3. Hugging Face TGI
4. vLLM now

## Decision Outcome

Chosen option: "pinned Ollama with raw prompts and the decoding schema; vLLM as the production path", because Ollama
is the simplest way to serve a GGUF on CPU in Compose. It exposes structured outputs and logprobs, and with raw
prompts plus parity tests its behaviour is pinned to what training produced.

Rules:

* **Modelfile** (`infra/ollama/Modelfile.<tag>`, generated from `prompt_format.json`):
  * `FROM ./<file>.gguf` (never a library tag);
  * `REQUIRES <ollama version>`;
  * `TEMPLATE` for interactive use only;
  * the parameters listed above, plus the family's stop token.

  Compose pins the `ollama/ollama` image to the same version.
* **Integrity:** GGUFs are downloaded by HF `revision=<sha>`, and their sha256 is verified against
  `model_versions.gguf_sha256` before `ollama create`. A mismatch blocks activation and readiness
  (`model.integrity_check_failed`).
* **Isolation:** Ollama's API is unauthenticated and includes model-management endpoints. It sits on the internal
  network only, and its port is never published (ADR-0026).
* **Post-decode validation stays authoritative:** grammar decoding may not enforce every schema keyword (for example
  string length bounds), so Pydantic strict validation gates every output. `done_reason == "length"` means invalid,
  and goes to repair L2.
* **Nightly checks (§9.10):**
  * a grammar-derivation test against `llama-server` at Ollama's pinned llama.cpp build (every enum literal and the
    `rationale` bound present);
  * Ollama parity tests;
  * `truncate: false` erroring on a 10k-token prompt.
* **vLLM path** (`docs/serving.md`): the recipe in the note above, static multi-LoRA (`--enable-lora`, runtime
  adapter loading off), prefix caching set explicitly, and a serving-drift check (≤ 2 points vs the GGUF) gating any
  switch. Capacity and cost are analytical (about 2,900 / 3,900 / 5,600 tickets/hour on T4 / L4 / A10G for a
  1.5B-class model).

**Verify at build:** the Ollama version and its llama.cpp tag; the `_debug_render_only` debug field used by the
parity test (skipped if it disappears); the vLLM version and its logprobs-mode semantics.

### Consequences

* Good, because a reviewer runs `docker compose up -d --build` and gets a working local model, with the stub LLM
  provider for CI and Playwright.
* Good, because raw prompts plus parity tests close the "wrong Modelfile template" failure mode that silently costs
  accuracy.
* Good, because the drift gate protects critical-class recall per quant, not just macro-F1.
* Bad, because CPU inference takes seconds per ticket (L-09, R-15). Mitigations: the smallest passing quant, the 2B
  default, the async UX over SSE, and cached demo results.
* Bad, because the unauthenticated Ollama API makes the network boundary the control. The digest checks detect a
  model swap.
* Neutral, because the vLLM path is analytical unless stretch goal G-2 runs. The dev laptop (Windows) needs WSL or a
  container for vLLM.

### Confirmation

* M-04: validity ≥ 99.5%, first pass ≥ 98% (constrained), from `make eval-slm` against Ollama. `T-SCHEMA-gate`.
* The drift gate (quant vs BF16, per critical class), recorded in the eval report and model card.
* Parity tests in CI and nightly: backend rendering equals the HF golden renderings; `prompt_eval_count` equals the
  HF token count; 50 golden val tickets give identical JSON between HF-bf16 and the deployed GGUF (≥ 98%).
* `/api/v1/health/ready` checks that the active model is loaded. `T-SEC-MODEL-sha-mismatch` shows a tampered GGUF is
  refused.
* `eval-nightly.yml`: the deployed GGUF on `hard_dev` plus a 200-ticket val sample (never the sealed splits). It
  fails on a drop of > 2 points against the production baseline, and also runs the grammar-derivation test.
* compose-smoke: the Ollama service publishes no ports (proposed assertion).

## Pros and Cons of the Options

### Ollama (pinned, raw prompts, decoding schema)

* Good, because model management is simple, it is efficient on CPU, and it offers structured outputs, logprobs and
  brief alignment.
* Bad, because its API is unauthenticated, it recently removed features (ADAPTER), and concurrency tuning is limited.

### llama.cpp server

* Good, because it uses the same engine, and exposes GBNF, token probabilities and fine control. It remains the
  adapter of choice for raw grammars and for the nightly grammar test.
* Bad, because we would own its image and model management.

### Hugging Face TGI

* Good, because it is a production GPU server.
* Bad, because it is GPU-oriented and a poor fit for CPU GGUF. Its current maintenance status would need checking.

### vLLM now

* Good, because it has the best throughput, structured outputs, multi-LoRA and logprobs.
* Bad, because it needs a GPU host (T4 is the floor), which the demo budget cannot justify. It also has a heavy 2026
  advisory stream, so it stays the pinned production path.

## More Information

* Spec (private): §6 (decoding schema), §6.2 (logprobs), §6.6 (validity gate), §7.7, §9.4 (parity), §9.5
  (export/serving, Modelfile, drift gate, vLLM recipe), §9.10, §15, §20 L-09, §21 R-05, R-06. Change record A-19,
  A-04.
* Brief (private): §8. BR-032, BR-036.
* Research: [constrained-decoding](../research/constrained-decoding.md),
  [gguf-export-and-ollama](../research/gguf-export-and-ollama.md),
  [vllm-production-serving](../research/vllm-production-serving.md),
  [confidence-calibration](../research/confidence-calibration.md).
* Related ADRs: ADR-0011, ADR-0012, ADR-0015, ADR-0017, ADR-0036 (egress proxy for model fetch).
* Revisit when: GPU serving is funded (move to vLLM), or Ollama changes its structured-output or logprob behaviour.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (mandatory merge + quantization, raw
  prompts and parity, drift gate, vLLM recipe).
