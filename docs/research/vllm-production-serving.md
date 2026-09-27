# vLLM Production Serving (Multi-LoRA, Structured Outputs, GPU Sizing) - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Partially resolved. Features, flags, hardware constraints, security scope and dated prices are verified from official sources. **All throughput and cost-per-ticket figures are ANALYTICAL estimates, not benchmarks** (consistent with L-09). Measuring them is stretch goal G-2.
**Category**: Serving / Infrastructure (production discussion, `docs/serving.md`)
**Linked ADR(s)**: ADR-0014 (Ollama in v1; vLLM as the production path), ADR-0011 (base SLM), ADR-0012 (QLoRA adapters), ADR-0017 (confidence from constrained-token logprobs)
**Spec sections**: §6.2 (confidence via logprobs), §6.6 (constrained decoding), §7.1 (`VLLMProvider` stub), §9.5 (Export/serving), §14.1 (`providers/vllm.py`, `docs/serving.md`), §20 L-09, §21 R-08 (G-2), §23
**Method**: ERPROT §0. vLLM docs (latest, dated September 2026), PyPI, OSV, NVIDIA datasheets, AWS's public price feed, Hugging Face configs. All accessed 2026-09-26.

---

## EXECUTIVE SUMMARY

1. **Current release:** vLLM **0.30.0** (PyPI, 2026-09-22; Apache-2.0; Python 3.10–3.13; **Linux only**; default wheels built with CUDA 12.9). The V1 engine is the only engine ("We have fully deprecated V0"). **Chunked prefill is on by default**, and **logprobs are returned "raw" (before logit processors) by default** through `--logprobs-mode raw_logprobs`. The v0.30.0 source applies the structured-output grammar bitmask *before* computing them, so under constrained decoding they are renormalized over valid tokens.
2. **Multi-LoRA fits Ticketward.** One base model serves the triage adapter now and an optional draft adapter in v1.1. Use `--enable-lora`, `--lora-modules` (`name=path` or JSON with `base_model_name`), `--max-loras` (default 1) and `--max-lora-rank` (default 16; allowed values 1, 8, 16, 32, 64, 128, 256, 320, 512). The request picks an adapter "as if it were any other model via the `model` request parameter". Runtime adapter loading (`VLLM_ALLOW_RUNTIME_LORA_UPDATING=True`) "should not be used in production unless it is an isolated, fully trusted environment", so use static adapters only.
3. **Structured outputs.** Backends are **xgrammar, guidance (llguidance), outlines and lm-format-enforcer**, with `auto` as the default. The server flag is **`--structured-outputs-config.backend`**; the old `guided_decoding_backend` "has been removed as of v0.12.0", and `guided_json` and similar request fields are deprecated. Send `response_format` json_schema or `structured_outputs: {json: …}`. **Security:** 2026 CVEs include ReDoS through `structured_outputs.regex` (fixed in 0.24.0 and 0.26.0), so only server-built JSON schemas may be sent.
4. **Hardware.** Compute capability **≥ 7.5** is required, so T4 is the floor. T4 cannot use bf16 (`--dtype half`), and **FlashAttention/FlashInfer need SM ≥ 8.0**, so T4 falls back to Triton or Flex attention. A10G (SM 8.6) and L4 (SM 8.9) run FA2, and L4 can additionally use FP8.
   - Datasheets: T4 16 GB / 320 GB/s / 65 FP16 TFLOPS; A10 24 GB / 600 GB/s / 125 dense; L4 24 GB / 300 GB/s / 121 dense.
5. **Capacity (analytical).** Workload: Qwen2.5-1.5B fp16, one triage plus one draft per ticket, about 3,150 prefill tokens (after prefix caching) plus 500 decode tokens. Estimated derated capacity: **~2,900 (T4), ~3,900 (L4), ~5,600 (A10G) tickets/hour per GPU.** Qwen3-1.7B (4× the KV cache per token) and 3B-class models reach roughly half of that.
6. **Cost.** AWS us-east-1 on-demand, from AWS's public price feed dated 2026-09-25: g4dn.xlarge (T4) $0.526/h, g6.xlarge (L4) $0.8048/h, g5.xlarge (A10G) $1.006/h.
   - At full utilization that is about **$0.18–0.20 per 1,000 tickets**.
   - An *always-on* GPU at **1,000 tickets/day costs $0.013–0.024 per ticket**. That is worse than M-09's CPU target of < $0.002 and similar to a Sonnet 5 complex draft ($0.013).
   - The break-even point is around **10k tickets/day** ($0.0013–0.0024), unless the GPU can scale to zero.
   - This supports ADR-0014: the demo stays on CPU/Ollama, and vLLM is the documented production path.
7. **Security.** `--api-key` protects only `/v1`, `/v2`, `/inference` and `/cohere`. `/invocations`, `/score`, `/rerank`, `/pause`, `/update_weights` and others stay unauthenticated. Keep vLLM on the internal network behind a proxy that forwards only `/v1/chat/completions` and `/health`.

---

## QUESTIONS

| # | Question (spec §23 + implementer needs) | Answered in |
|---|---|---|
| Q1 | How does multi-LoRA serving work? | F3, D1–D2 |
| Q2 | Which guided/structured decoding backends exist, and how are requests shaped? | F4, D3 |
| Q3 | How do continuous batching and scheduler/memory knobs work? | F2, D2 |
| Q4 | What throughput can a 1.5–3B model reach on L4, A10 and T4? | F5, F6, D6 (analytical) |
| Q5 | How much GPU is needed, and what does it cost per N tickets/day (dated prices)? | F7, D6 |
| Q6 | How are the provider, logprobs for confidence, QLoRA compatibility, security and version pinning handled? | F1, F2, D3–D5, D7 |

---

## FINDINGS

All links below were accessed 2026-09-26.

### F1. Version, platform and vulnerability history

- **PyPI:** vllm **0.30.0**, uploaded 2026-09-22, Apache-2.0, `requires_python >=3.10,<3.15` ([PyPI](https://pypi.org/pypi/vllm/json)).
- **Install docs** ([GPU installation](https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html)): "Minimum of 7.5 or higher (e.g., T4, RTX20xx, A100, L4, H100, B200)". Wheels are "built with CUDA 12.9 by default", supported Python is 3.10–3.13, and the OS is Linux only (Windows through WSL).
- **OSV** ([API](https://api.osv.dev/v1/query)): 135 advisories in total, **0 affecting 0.30.0**. Recent examples relevant to us:
  - ReDoS through `structured_outputs.regex` in lm-format-enforcer (CVE-2026-73556, fixed 0.26.0) and in xgrammar/outlines (CVE-2026-55574, fixed 0.24.0).
  - "Cross-User Data Leak Vulnerability" (CVE-2026-73558, fixed 0.27.0).
  - "Completion prompt lists fan out into unbounded engine requests" (CVE-2026-73559, fixed 0.26.0).
  - "Unauthenticated Internal Path and Username Disclosure via Validation Error Messages" (CVE-2026-73555, fixed 0.26.0).
  Conclusion: pin the latest version and track advisories.

### F2. V1 engine semantics ([V1 guide](https://docs.vllm.ai/en/latest/usage/v1_guide.html), [engine args](https://docs.vllm.ai/en/latest/configuration/engine_args.html))

- "We have fully deprecated V0." Removed features: `best_of`, per-request logits processors, GPU↔CPU KV swapping.
- **Chunked prefill** is "enabled by default whenever possible". Continuous batching is intrinsic to the scheduler.
- **Logprobs:** V1 returns logprobs "immediately once computed from the model's raw output", before temperature scaling and other processing. `--logprobs-mode` ∈ {`raw_logprobs` (default), `processed_logprobs`, `raw_logits`, `processed_logits`}. "Raw means the values before applying any logit processors, like bad words." `--max-logprobs` defaults to 20.
- **Grammar masking vs "raw" logprobs, verified in source at tag v0.30.0:** `GPUModelRunner.sample_tokens()` calls `apply_grammar_bitmask(scheduler_output, grammar_output, self.input_batch, logits)` *before* `self._sample(logits, …)`. `Sampler.forward()` then computes `raw_logprobs = self.compute_logprobs(logits)` from those already-masked logits ([gpu_model_runner.py](https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/v1/worker/gpu_model_runner.py), [sampler.py](https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/v1/sample/sampler.py)). So under structured outputs the default logprobs are **renormalized over grammar-valid tokens**: "raw" means before penalties and temperature, not before the grammar mask. `confidence-calibration.md` reaches the same conclusion.
- **Prompt logprobs with prefix caching:** supported, but the engine "recompute[s] the full prefill".
- **Key flags and defaults:**
  - `--dtype` ∈ {auto, bfloat16, float, float16, float32, half}, default `auto`, which follows the model config (bf16 for Qwen).
  - `--gpu-memory-utilization` default **0.92**.
  - `--max-num-seqs` and `--max-num-batched-tokens` defaults are "set for testing convenience" and "should be set in real usage".
  - `--kv-cache-dtype` includes `fp8`.
  - `--trust-remote-code` default False.
  - `--revision` accepts a commit id.
  - **The prefix-caching default could not be confirmed** from the engine-args page (**UNVERIFIED**), so set `--enable-prefix-caching` explicitly and check `vllm serve --help` for the pinned version.

### F3. Multi-LoRA ([LoRA docs](https://docs.vllm.ai/en/latest/features/lora.html), dated 2026-09-16)

- `--enable-lora`
- `--lora-modules name=path`, or JSON `'{"name": "sql-lora", "path": "...", "base_model_name": "..."}'`
- `--max-loras`, `--max-lora-rank`, where the docs advise: "Set it to the maximum rank among all LoRA adapters you plan to use" and "Avoid setting it too high"
- `--max-cpu-loras` (must be ≥ `max_loras`), `--lora-dtype`, `--lora-target-modules`
- Adapter selection: "Requests can specify the LoRA adapter as if it were any other model via the `model` request parameter."
- Dynamic endpoints `POST /v1/load_lora_adapter` and `/v1/unload_lora_adapter` require `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True`, with the warning "should not be used in production unless it is an isolated, fully trusted environment". The [security page](https://docs.vllm.ai/en/stable/usage/security/) adds: "Dynamic LoRA loading is not a secure operation and should not be enabled in deployments exposed to untrusted clients."
- Resolver plugins exist (`lora_filesystem_resolver`, `lora_hf_hub_resolver`). Not needed here.

### F4. Structured outputs ([docs](https://docs.vllm.ai/en/latest/features/structured_outputs.html))

- Backends: xgrammar, guidance (llguidance), outlines and lm-format-enforcer. "The default backend is `auto`, which will try to choose an appropriate backend based on the details of the request."
- Server flag: `--structured-outputs-config.backend`. "The deprecated field `guided_decoding_backend` has been removed as of v0.12.0."
- Requests: OpenAI `response_format` (JSON schema), or `extra_body={"structured_outputs": {"json" | "regex" | "choice" | "grammar" | "structural_tag": ...}}`. Legacy `guided_json` and similar are deprecated. Offline use goes through `StructuredOutputsParams` in `SamplingParams`.
- Reasoning models: `--structured-outputs-config.enable_in_reasoning=True` (for Qwen3-Coder). This is irrelevant for non-thinking triage.

### F5. GPUs ([NVIDIA T4](https://www.nvidia.com/en-us/data-center/tesla-t4/), [A10](https://www.nvidia.com/en-us/data-center/products/a10-gpu/), [L4](https://www.nvidia.com/en-us/data-center/l4/); [attention backends](https://docs.vllm.ai/en/latest/design/attention_backends/))

| GPU | Memory | Bandwidth | FP16 tensor (dense) | TDP | Compute capability → vLLM attention | Notes |
|---|---|---|---|---|---|---|
| T4 | 16 GB GDDR6 | 320+ GB/s | 65 TFLOPS | 70 W | 7.5: FLASH_ATTN needs ≥8.0 and FLASHINFER 8.x–9.x, so TRITON_ATTN or FLEX_ATTENTION ("Any") is used | no bf16, so `--dtype half`; no FP8 |
| A10 (AWS: A10G) | 24 GB GDDR6 | 600 GB/s | 125 TFLOPS (250 with sparsity) | 150 W | 8.6: FA2 | AWS A10G specs may differ from the A10 datasheet (**UNVERIFIED**); A10 used as proxy |
| L4 | 24 GB | 300 GB/s | 121 TFLOPS (242 with sparsity; "one-half lower without sparsity") | 72 W | 8.9: FA2 | FP8 tensor 485 sparse / ~242 dense; `--quantization fp8` possible |

AWS instance-to-GPU mapping (AWS pages): G4dn = T4, G5 = A10G (24 GB), G6 = L4 (24 GB).

### F6. Model shapes for KV-cache sizing (HF `config.json`)

| Model | Params (safetensors) | Layers | KV heads × head_dim | fp16 KV per token | License (HF metadata) |
|---|---|---|---|---|---|
| Qwen/Qwen2.5-1.5B-Instruct | 1.54B | 28 | 2 × 128 | 28 KiB | apache-2.0 |
| Qwen/Qwen2.5-3B-Instruct | 3.09B | 36 | 2 × 128 | 36 KiB | **other: `qwen-research`** |
| Qwen/Qwen3-1.7B | 2.03B | 28 | 8 × 128 | 112 KiB | apache-2.0 |
| Qwen/Qwen3-4B-Instruct-2507 | 4.02B | 36 | 8 × 128 | 144 KiB | apache-2.0 |

(Llama-3.2-3B-Instruct is gated and was not fetched.) At fp16, 32 concurrent sequences × 2,000 resident tokens use 1.84 GB of KV for Qwen2.5-1.5B and 7.34 GB for Qwen3-1.7B. VRAM is not the binding constraint on 16–24 GB cards for these models. Decode bandwidth is.

### F7. Dated on-demand prices (AWS public price feed, us-east-1, Linux; `hawkFilePublicationDate` 2026-09-25)

| Instance | GPU | vCPU / RAM | $/hour |
|---|---|---|---|
| g4dn.xlarge | 1× T4 | 4 / 16 GiB | **0.526** |
| g4dn.2xlarge | 1× T4 | 8 / 32 GiB | 0.752 |
| g6.xlarge | 1× L4 | 4 / 16 GiB | **0.8048** |
| g6.2xlarge | 1× L4 | 8 / 32 GiB | 0.9776 |
| g5.xlarge | 1× A10G | 4 / 16 GiB | **1.006** |
| g5.2xlarge | 1× A10G | 8 / 32 GiB | 1.212 |
| g6e.xlarge | 1× L40S | 4 / 32 GiB | 1.861 |

Source: `https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20East%20(N.%20Virginia)/Linux/index.json`, the JSON behind AWS's on-demand pricing page. GCP GPU pricing could not be read from its static page on 2026-09-26 (**UNVERIFIED**, so it is not listed).

---

## DECISION / RECOMMENDATION

**D1 Production serving design (documented in `docs/serving.md`; not deployed in v1).**
- vLLM 0.30.x, with one base model at a pinned revision and the static LoRA adapters `tw-triage` (plus `tw-draft` in v1.1).
- Structured outputs with server-generated JSON Schemas (the same schemas as Ollama, §6.6) and explicit prefix caching.
- OpenAI-compatible API on an internal network behind the reverse proxy, which allows `/v1/chat/completions` and `/health` only. `--api-key` is set, but it is not the security boundary.
- `VLLMProvider` implements `LLMProvider` over `httpx`.

**D2 Launch command.** Flags verified in the docs, except where marked.

```bash
# L4 / A10G: --dtype auto (bf16 from the Qwen config). T4: --dtype half (no bf16 on SM 7.5).
# --enable-prefix-caching is set explicitly; verify its default for the pinned version with `vllm serve --help`.
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --revision <pinned-commit> \
  --dtype auto \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 32 --max-num-batched-tokens 8192 \
  --enable-prefix-caching \
  --enable-lora --max-loras 2 --max-lora-rank 16 \
  --lora-modules '{"name": "tw-triage", "path": "/models/adapters/tw-triage-1.2.0", "base_model_name": "Qwen/Qwen2.5-1.5B-Instruct"}' \
  --structured-outputs-config.backend xgrammar \
  --api-key "$VLLM_API_KEY" --host 0.0.0.0 --port 8000
```

The bf16 base (the Qwen config's `torch_dtype`) is correct on L4 and A10G. On T4, force `half`. Pinning the backend (`xgrammar`) rather than `auto` keeps results reproducible across requests. Re-check it against any schema feature the backend rejects.

**D3 Provider request shape** (OpenAI-compatible; field names follow the vLLM docs):

```python
# backend/src/ticketward/providers/vllm.py (sketch)
payload = {
    "model": "tw-triage",                                     # LoRA adapter name selects the adapter
    "messages": messages,                                     # system + masked <ticket> (§9.4 triage.v1)
    "temperature": 0,
    "max_tokens": 256,
    "response_format": {"type": "json_schema",
                        "json_schema": {"name": "TriageModelOutput", "schema": TRIAGE_SCHEMA, "strict": True}},
    "logprobs": True, "top_logprobs": 5,                      # for §6.2 confidence (<= --max-logprobs 20)
}
resp = await http.post(f"{base_url}/v1/chat/completions", json=payload,
                       headers={"Authorization": f"Bearer {api_key}"}, timeout=httpx.Timeout(15.0, connect=2.0))
```

Never forward user-supplied `regex` or `grammar` constraints (F1 ReDoS CVEs).

**D4 Confidence (§6.2, ADR-0017).**
- Keep the default `--logprobs-mode raw_logprobs`. Under structured outputs these are computed after the grammar bitmask (F2, verified in source), so the first token of an enum value carries probability mass renormalized over schema-valid continuations. That is the quantity §6.2 wants.
- The mass is still spread over the *first tokens* of the enum values. If two values share a first token (for example `billing_duplicate_charge` and `billing_payment_failure`), sum or condition on the following tokens. `confidence-calibration.md` owns that method.
- Calibrate on val (temperature scaling or isotonic; target ECE ≤ 0.08, M-12).
- Record `--logprobs-mode` and the structured-output backend in `ModelMeta`, because both change the numbers.

**D5 Adapter compatibility (ADR-0012).**
- Adapters are trained with QLoRA on a 4-bit NF4 base (§9.5) but served on the fp16/bf16 base in vLLM, so run a **serving-drift check**: macro-F1 difference ≤ 2 points on val, the same rule as the GGUF check.
- LoRA rank 16 matches the `--max-lora-rank 16` default.
- Confirm the architecture chosen in the bake-off (ADR-0011) is in vLLM's LoRA-supported model list for the pinned version.

**D6 Sizing and cost.** ANALYTICAL; the reproducible script is `ml/src/tw_ml/eval/capacity_model.py`, to be added from this doc's scratch model.

Assumptions:
- Per ticket: triage 1,000 in / 200 out, draft 2,900 in / 300 out, with 750 system-prompt tokens served from the prefix cache. That gives **3,150 prefill + 500 decode tokens**.
- Prefill at 40% of dense FP16 peak.
- Decode is memory-bound: weights plus 32 sequences × 2,000 tokens of KV read per step.
- An overall 0.5 derate for scheduling, attention FLOPs and stragglers.

| Model | GPU (instance) | GPU-ms/ticket (est.) | Derated tickets/h | $ per 1k tickets at full use |
|---|---|---|---|---|
| Qwen2.5-1.5B | T4 (g4dn.xlarge) | ~614 | ~2,930 | $0.180 |
| Qwen2.5-1.5B | A10G (g5.xlarge) | ~323 | ~5,580 | $0.180 |
| Qwen2.5-1.5B | L4 (g6.xlarge) | ~457 | ~3,940 | $0.204 |
| Qwen3-1.7B | T4 / A10G / L4 | ~1,049 / ~553 / ~858 | ~1,720 / ~3,260 / ~2,100 | $0.307 / $0.309 / $0.384 |
| 3B-class (Qwen2.5-3B shape) | T4 / A10G / L4 | ~1,164 / ~611 / ~846 | ~1,550 / ~2,950 / ~2,130 | $0.340 / $0.341 / $0.378 |

Always-on cost per ticket for the 1.5B model, with instances sized for 4× peak-to-average:

| Tickets/day | T4 | A10G | L4 |
|---|---|---|---|
| 1,000 | 1 instance, **$0.0126** | 1, $0.0241 | 1, $0.0193 |
| 10,000 | 1, $0.00126 | 1, $0.00241 | 1, $0.00193 |
| 50,000 | 3, $0.00076 | 2, $0.00097 | 3, $0.00116 |
| 100,000 | 6, $0.00076 | 3, $0.00072 | 5, $0.00097 |

What follows from these tables:
1. VRAM is not the constraint for 1.5–4B models on 16–24 GB cards. Memory bandwidth is, because decode is memory-bound, which is why the A10G (600 GB/s) leads.
2. At low volume the cost is set by idle hours, not by throughput. **Below about 10k tickets/day, CPU serving (M-09 target < $0.002) or scale-to-zero beats an always-on GPU.**
3. For a pilot, a single **T4** gives the lowest hourly cost but needs fp16 and Triton attention. **A10G** gives the best latency and throughput per dollar at scale. **L4** adds FP8, which roughly halves weight bytes and helps bandwidth-bound decode (not modelled here).

**D7 Security hardening.**
- Internal network only. The reverse proxy allows only `POST /v1/chat/completions` and `GET /health`. `--api-key` stays on as defence in depth, since the security page lists unauthenticated `/invocations`, `/score`, `/rerank`, `/pause`, `/resume`, `/abort_requests` and `/update_weights`.
- No runtime LoRA updating. `--trust-remote-code` stays off (the default).
- Bound `--max-model-len` and `--max-num-seqs`. Apply request-size limits upstream (§12.2 DoS).
- Pin vLLM ≥ 0.30.0 and include it in the Trivy/pip-audit scans (R-12).

**D8 Benchmark plan (stretch G-2).**
- Use `vllm bench serve --backend vllm --model <base> --endpoint /v1/chat/completions --dataset-name random --random-input-len 1000 --random-output-len 200 --num-prompts 500 --max-concurrency 32`, plus a replay of 500 masked `test_synth` tickets.
- Report TTFT, TPOT, ITL, requests/s and tokens/s, together with the GPU, driver, CUDA and vLLM versions.
- Commit `evals/reports/<date>/serving_bench.json` and replace the D6 estimates. Only then may L-09 say "benchmarked".

---

## SPEC IMPACT (recorded; the spec was NOT edited)

| # | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §6.6 "vLLM guided decoding", §9.5 serving note | `guided_decoding_backend` was removed in v0.12.0, and `guided_json` is deprecated. | Use `--structured-outputs-config.backend` and `response_format` / `structured_outputs`. |
| SI-2 | §6.2 confidence via logprobs | V1's default `raw_logprobs` are computed *after* the grammar bitmask (source at v0.30.0), so they are renormalized over schema-valid tokens. "Raw" only means before penalties and temperature. | Specify `--logprobs-mode raw_logprobs`, record it and the backend in `ModelMeta`, and handle enum values that share a first token (D4). |
| SI-3 | §9.5 GPU plan / serving | vLLM requires CC ≥ 7.5 and Linux. T4 has no bf16 or FlashAttention. | Note `--dtype half` and the Triton fallback. The dev laptop (Windows) needs WSL or a container for vLLM. |
| SI-4 | §20 L-09 / §9.8 M-09 | At demo volume, an always-on GPU costs more per ticket than the CPU target. | State the ~10k tickets/day break-even (analytical) in `docs/serving.md`. |
| SI-5 | §9.5 candidate list (Qwen2.5-1.5B/3B) | HF metadata lists **Qwen2.5-3B-Instruct as `qwen-research`** (not Apache). Qwen3-1.7B and Qwen3-4B-2507 are Apache-2.0. | Weight this in the bake-off license criterion (15%). Hand it to `slm-model-selection.md`. |
| SI-6 | §12.8/§12.9 (supply chain, containers) | vLLM had many 2026 CVEs, and `--api-key` does not cover all endpoints. | Add the D7 proxy allow-list and version pinning to the serving section. |

---

## IMPLEMENTATION CHECKLIST

- [ ] `providers/vllm.py`: `VLLMProvider` per D3 (httpx, timeouts, error mapping to `model_unavailable`). Contract test against a stubbed OpenAI-compatible server.
- [ ] `docs/serving.md`: D1–D8, with dated prices and the "analytical, not benchmarked" label.
- [ ] Add `ml/src/tw_ml/eval/capacity_model.py` (the D6 model) with its assumptions as constants, so the estimate is reproducible.
- [ ] If G-2 is attempted: run the D8 benchmark on one g4dn/g5/g6 instance, record the results and update L-09.
- [ ] Serving-drift check (D5) as part of the model promotion gate if vLLM becomes the production runtime.

## OPEN RISKS / TO VERIFY

| Item | Status |
|---|---|
| Real throughput and latency vs the analytical estimates (attention cost at ~4k context, Triton attention on T4, scheduler overheads) | **UNVERIFIED**; G-2 benchmark |
| Prefix-caching default in 0.30.x | Verify with `vllm serve --help`; set it explicitly |
| Grammar mask vs logprobs mode | Verified in the v0.30.0 source (F2). Re-check if the pinned version changes. |
| AWS A10G specs vs the A10 datasheet | **UNVERIFIED**; A10 used as proxy |
| GCP, Azure and neo-cloud prices | Not collected (GCP static page unreadable); add when needed, with dates |
| Prices change | Dated 2026-09-25 (AWS feed). Re-pull before any budget decision. |

## LINKED ADR

- **ADR-0014**: unchanged decision (Ollama in v1). Add the vLLM production recipe (D1/D2/D7), the break-even analysis (D6) and the flag changes (SI-1).
- **ADR-0017**: add the logprobs-mode note (D4).
- **ADR-0011**: license finding for Qwen2.5-3B (SI-5).

## SOURCES (all accessed 2026-09-26)

1. vLLM on PyPI (0.30.0): https://pypi.org/pypi/vllm/json
2. GPU installation requirements: https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html
3. V1 guide: https://docs.vllm.ai/en/latest/usage/v1_guide.html ; source at tag v0.30.0: https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/v1/worker/gpu_model_runner.py (`sample_tokens`, `apply_grammar_bitmask`) and https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/v1/sample/sampler.py (`raw_logprobs`)
4. Engine arguments: https://docs.vllm.ai/en/latest/configuration/engine_args.html
5. LoRA: https://docs.vllm.ai/en/latest/features/lora.html
6. Structured outputs: https://docs.vllm.ai/en/latest/features/structured_outputs.html
7. Attention backends: https://docs.vllm.ai/en/latest/design/attention_backends/
8. Security: https://docs.vllm.ai/en/stable/usage/security/
9. Benchmark CLI: https://docs.vllm.ai/en/latest/benchmarking/cli.html
10. OSV vulnerability database (vllm): https://api.osv.dev/v1/query
11. NVIDIA T4 / A10 / L4 product pages: https://www.nvidia.com/en-us/data-center/tesla-t4/ ; https://www.nvidia.com/en-us/data-center/products/a10-gpu/ ; https://www.nvidia.com/en-us/data-center/l4/
12. AWS instance pages: https://aws.amazon.com/ec2/instance-types/g4/ ; https://aws.amazon.com/ec2/instance-types/g5/ ; https://aws.amazon.com/ec2/instance-types/g6/ ; AWS price feed URL in F7
13. Hugging Face configs and metadata: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct ; https://huggingface.co/Qwen/Qwen2.5-3B-Instruct ; https://huggingface.co/Qwen/Qwen3-1.7B ; https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507

---

**Document Version**: 1.0
**Next Update**: After the base-model decision (ADR-0011) or a G-2 benchmark run
