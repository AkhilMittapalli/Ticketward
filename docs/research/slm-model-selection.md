# SLM Model Selection - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: September 26, 2026
**Last Updated**: September 26, 2026
**Status**: Partially resolved
**Status Note**: Landscape, licenses and chat templates are resolved from primary sources. The zero-shot bake-off (Q4) and dev-laptop CPU tokens/s (Q5) stay Open until P2 runs them. The final choice (Q6) depends on both.
**Category**: ML / Base-model selection
**Linked ADR(s)**: ADR-0011 (base SLM choice), ADR-0012 (training stack), ADR-0014 (serving)
**Spec sections**: §9.4 (prompt formats), §9.5 (model selection + bake-off), §9.6 (registry naming, model card), §9.8 M-01/M-03c/M-08, §21 R-06/R-10/R-14, §22, §23

---

## EXECUTIVE SUMMARY

- The spec's candidate list (§9.5: "Qwen2.5-1.5B/3B-Instruct or the latest Qwen3 small instruct", Llama-3.2-3B, Phi mini) is out of date. As of 2026-09-26 the newest small models are **Qwen3.5-0.8B/2B/4B** (released 2026-03-02, Apache-2.0, hybrid Gated DeltaNet + attention, vision-language checkpoints) and **Gemma 4 E2B/E4B** (released 2026-04-02, now **Apache-2.0**). No newer small Llama or Phi has been found: Llama 3.2 1B/3B (2024) and Phi-4-mini-instruct (Feb 2025) are still the current small models in those families.
- **Qwen2.5-3B-Instruct is under the non-commercial Qwen Research License** and should be dropped. The Llama 3.2 license requires a "Llama" prefix on the name of any fine-tuned model that is distributed. That conflicts with the registry naming `tw-triage-<base>-<method>` (§9.6).
- The chat templates differ in ways that matter for train/serve parity:
  - Qwen3.5 inserts an empty `<think>\n\n</think>\n\n` block when thinking is off.
  - Llama 3.2 inserts today's date into the system header.
  - Gemma 4 uses new `<|turn>` tokens.
  - Phi-4-mini is not among the families TRL auto-patches for assistant-only loss.
- **Recommendation (provisional, pending P2 measurements):** run a 5-model zero-shot bake-off: Qwen3.5-2B, Qwen3-1.7B, Qwen3-4B-Instruct-2507, Llama-3.2-3B-Instruct and Phi-4-mini-instruct, plus optional Gemma-4-E2B-it and Qwen3.5-0.8B. Then run a short 1-epoch fine-tune probe on the top 2. The default candidate is **Qwen3.5-2B**. The pre-agreed fallback is **Qwen3-1.7B**: a pure transformer with the lowest tooling risk on T4 and CPU, used if the Qwen3.5 training smoke test or CPU latency fails.
- The CPU latency target (M-08: triage P50 ≤ 5 s on 8 vCPU) is at risk for every 2–4B candidate. It must be measured in P2 before the base model is locked (see Open Risks).

---

## SPEC IMPACT (owner action required; spec not edited)

| ID | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §9.5 "Model selection" candidate list; ADR-0011 | Qwen2.5/Qwen3 are no longer the latest Qwen small models. Qwen3.5-0.8B/2B/4B (2026-03-02) are current; Qwen3.6/3.8 have no model under 5B ([QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8), accessed 2026-09-26). | Replace the candidate list with the shortlist in the Decision section. |
| SI-2 | §9.5 "Qwen2.5-1.5B/3B-Instruct" | Qwen2.5-3B-Instruct is `license: other / qwen-research`, "FOR NON-COMMERCIAL PURPOSES ONLY" ([LICENSE](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE), accessed 2026-09-26). | Remove Qwen2.5-3B. If Qwen2.5 is kept at all, keep only 1.5B (Apache-2.0). |
| SI-3 | §9.6 registry naming `tw-triage-<base>-<method>`; §6.2 example `tw-triage-qwen-1.5b-qlora@1.2.0` | Llama 3.2 License §1.b.i: a distributed model trained from Llama "shall also include 'Llama' at the beginning of any such AI model name" and must "prominently display 'Built with Llama'". | If Llama wins, name it `Llama-tw-triage-3.2-3b-<method>` and add "Built with Llama" to the README and model card. Update the §6.2 example once the base model is chosen. |
| SI-4 | ADR-0011 alternatives ("Gemma small") | Gemma 4 is now Apache-2.0 (not the old Gemma Terms of Use). E2B/E4B are small, but their memory footprint is large (Ollama `gemma4:e2b` Q4_K_M = 7.2 GB) and they have fp16 overflow problems on T4. | List Gemma-4-E2B-it as an optional bake-off entrant with the caveats in the Findings. |
| SI-5 | §9.5 bake-off = zero-shot only | Zero-shot accuracy is a weak proxy for how well a model fine-tunes (recommendation, not a sourced fact). | Add a 1-epoch, 1-seed fine-tune probe for the top 2 zero-shot candidates before ADR-0011 is finalized. |
| SI-6 | §9.8 M-08 (triage P50 ≤ 5 s / P95 ≤ 12 s on 8 vCPU) | Output length (JSON keys decoded token-by-token plus the rationale) and prompt prefill set CPU latency. For hybrid models (Qwen3.5), prefix-cache reuse through Ollama is uncertain (Finding F5). | Measure in P2 (commands below). If it is missed, reduce output length or model size, or explicitly relax M-08 via ADR. |
| SI-7 | §9.4 "Chat template of the chosen base model" | Templates can inject non-constant content (the Llama date) or hidden blocks (the Qwen3.5 empty think block). | Add a rule: a template's rendered output must be deterministic (fixed `date_string`, explicit `enable_thinking=False`), and its sha256 is recorded in `model_versions`. |

---

## QUESTIONS (from SPEC §23)

1. What are the latest small instruct models (1–4B) in the Qwen, Llama, Phi and Gemma families? (verify at training time)
2. What are their licenses, covering commercial use, derivatives and HF publishing obligations?
3. What are their chat templates?
4. What are the zero-shot bake-off results?
5. What CPU Q4 tokens/s does each reach on the dev laptop?
6. Which model is chosen, and why?

---

## FINDINGS

### Q1. Latest small instruct models (as of 2026-09-26)

**Qwen**

- The Qwen3.5 small series (0.8B, 2B, 4B, 9B) was published 2026-03-02. The QwenLM news feed says: "2026-03-02: Qwen3.5-9B, Qwen3.5-4B, Qwen3.5-2B, and Qwen3.5-0.8B are now available." Later releases are all ≥ 27B: Qwen3.6 (27B, 35B-A3B; April 2026) and Qwen3.8 (27B, 2.4T-A95B; August 2026). Source: [QwenLM/Qwen3.8 README](https://github.com/QwenLM/Qwen3.8), accessed 2026-09-26.
- Qwen3.5-2B model card: "Type: Causal Language Model with Vision Encoder".
  - 24 layers, hidden 2048, FFN 6144.
  - Hidden layout "6 × (3 × (Gated DeltaNet → FFN) → 1 × (Gated Attention → FFN))".
  - Token embedding "248320 (Padded)", LM output tied to the embedding.
  - "Context Length: 262,144 natively".
  - "Qwen3.5-2B operates in non-thinking mode by default".
  - Source: [Qwen/Qwen3.5-2B README](https://huggingface.co/Qwen/Qwen3.5-2B), accessed 2026-09-26.
- Qwen3.5-4B has 32 layers and hidden 2560 in the layout "8 × (3 × (Gated DeltaNet → FFN) → 1 × (Gated Attention → FFN))". It operates in **thinking mode by default**; thinking is disabled with `chat_template_kwargs: {"enable_thinking": False}`. Source: [Qwen/Qwen3.5-4B README](https://huggingface.co/Qwen/Qwen3.5-4B), accessed 2026-09-26.
- Config facts, from each repo's `config.json` (accessed 2026-09-26):
  - Qwen3.5-0.8B: text hidden 1024, 24 layers.
  - Layer mix per model: 18 `linear_attention` + 6 `full_attention` (0.8B, 2B); 24 + 8 (4B).
  - All published in `bfloat16`, `architectures: ["Qwen3_5ForConditionalGeneration"]`.
  - Transformers documents `Qwen3_5ForCausalLM` "for text-only generation" ([Transformers Qwen3.5 docs, v5.17.0](https://huggingface.co/docs/transformers/model_doc/qwen3_5), accessed 2026-09-26).
- Qwen3 (pure transformer, previous generation) is still current for text-only small models:
  - **Qwen3-1.7B**: 1.7B total / 1.4B non-embedding, 28 layers, GQA 16Q/8KV, context 32,768, hybrid thinking ([card](https://huggingface.co/Qwen/Qwen3-1.7B)).
  - **Qwen3-4B-Instruct-2507**: 4.0B / 3.6B non-embedding, 36 layers, 262,144 context. It "supports only non-thinking mode and does not generate `<think></think>` blocks" ([card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)).
  - Both need `transformers>=4.51.0`. HF repo created 2025-04-27 (1.7B) and 2025-08-05 (2507) per the [Hub API](https://huggingface.co/api/models/Qwen/Qwen3-4B-Instruct-2507), accessed 2026-09-26.

**Llama**

- Llama 3.2 1B/3B Instruct are still Meta's smallest text models. The HF page lists "Release Date: September 25, 2024", while the llama-models card says "Model Release Date: Oct 24, 2024", which is the date of the quantized-model update ([MODEL_CARD.md](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md)).
- Llama-3.2-3B-Instruct: 3.21B params, 128k context, knowledge cutoff December 2023. The HF repo is gated (manual approval) ([HF page](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) and Hub API, accessed 2026-09-26).
- Searches found no Llama small model newer than 3.2. The Llama 4 family is large MoE. **UNVERIFIED** that nothing newer exists; re-check at P2.

**Phi**

- **Phi-4-mini-instruct**: 3.8B, "license: mit", vocabulary 200,064, 128K context, released February 2025, `transformers` ≥ 4.49.0 ([card](https://huggingface.co/microsoft/Phi-4-mini-instruct), accessed 2026-09-26).
- The card says flash attention is enabled by default, and that for "V100 or earlier" you set `attn_implementation="eager"`. On T4, use `sdpa` or `eager`.
- No official Phi-5 model card was found. **UNVERIFIED**; re-check at P2.

**Gemma**

- Gemma 4 was released 2026-04-02 in sizes E2B, E4B, 12B, 26B-A4B and 31B ([Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4), [Ollama v0.20.0 release 2026-04-02](https://github.com/ollama/ollama/releases/tag/v0.20.0), accessed 2026-09-26).
  - E2B = "2.3B effective (5.1B with embeddings)", 35 layers, 128K context. E4B = "4.5B effective (8B with embeddings)", 42 layers.
  - "Per-Layer Embeddings (PLE)"; text, image and audio input.
  - The E2B `config.json` shows `vocab_size_per_layer_input: 262144` and `hidden_size_per_layer_input: 256` across 35 layers. That is about 2.35B PLE parameters (arithmetic), which explains the effective vs total gap.

**Candidate summary**

| Model (HF id) | Released | Total params | Arch | Text ctx | Modality | Ollama library Q4_K_M size |
|---|---|---|---|---|---|---|
| Qwen/Qwen3.5-0.8B | 2026-03-02 | 0.8B | hybrid GDN:attn 3:1 | 262k | text+image | plain `qwen3.5:0.8b` 1.0 GB |
| Qwen/Qwen3.5-2B | 2026-03-02 | 2B (text ≈1.88B, arithmetic from config) | hybrid GDN:attn 3:1 | 262k | text+image | `qwen3.5:2b-q4_K_M` 1.9 GB (plain `qwen3.5:2b` = **q8_0** 2.7 GB) |
| Qwen/Qwen3.5-4B | 2026-03-02 | 4B | hybrid GDN:attn 3:1 | 262k | text+image | `qwen3.5:4b` = q4_K_M 3.4 GB |
| Qwen/Qwen3-1.7B | 2025-04 | 1.7B | transformer | 32k | text | `qwen3:1.7b` = q4_K_M 1.4 GB |
| Qwen/Qwen3-4B-Instruct-2507 | 2025-08 | 4.0B | transformer | 262k | text | `qwen3:4b-instruct-2507-q4_K_M` (size not captured) |
| meta-llama/Llama-3.2-1B-Instruct | 2024-09/10 | 1.2B | transformer | 128k | text | `llama3.2:1b` = q4_K_M 808 MB |
| meta-llama/Llama-3.2-3B-Instruct | 2024-09/10 | 3.21B | transformer | 128k | text | `llama3.2:3b` = q4_K_M 2.0 GB |
| microsoft/Phi-4-mini-instruct | 2025-02 | 3.8B | transformer | 128k | text | `phi4-mini` = q4_K_M 2.5 GB |
| google/gemma-4-E2B-it | 2026-04-02 | 5.1B (2.3B effective) | transformer + PLE | 128k | text+image+audio | `gemma4:e2b` = q4_K_M **7.2 GB**; `gemma4:e2b-it-qat` 4.3 GB |

Sizes come from the Ollama library tag pages ([qwen3.5](https://ollama.com/library/qwen3.5/tags), [qwen3](https://ollama.com/library/qwen3/tags), [llama3.2](https://ollama.com/library/llama3.2/tags), [phi4-mini](https://ollama.com/library/phi4-mini/tags), [gemma4](https://ollama.com/library/gemma4/tags), accessed 2026-09-26). Library tags mix quantization levels (`qwen3.5:2b` is q8_0 while `qwen3.5:4b` is q4_K_M), so **library tags must not be used as-is for a fair bake-off**.

### Q2. Licenses

| Model | License (source) | Commercial use | Derivatives / publishing obligations |
|---|---|---|---|
| Qwen3.5-0.8B/2B/4B | `apache-2.0` (model card YAML, Hub API tag `license:apache-2.0`) | Yes | Apache-2.0: keep LICENSE and NOTICE, state changes |
| Qwen3-1.7B, Qwen3-4B-Instruct-2507, Qwen2.5-1.5B-Instruct | `apache-2.0` (model cards) | Yes | As above |
| Qwen2.5-3B-Instruct | `qwen-research` ([LICENSE](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE)) | **No**: "FOR NON-COMMERCIAL PURPOSES ONLY" (§2.a) | Copy of agreement, change notices, attribution, "Built with Qwen" or "Improved using Qwen" (§4.b) |
| Llama 3.2 1B/3B | Llama 3.2 Community License ([LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE)) | Yes, unless > 700M MAU (§2) | §1.b.i: ship a copy of the agreement, "prominently display 'Built with Llama'", and "include 'Llama' at the beginning of any such AI model name". The Acceptable Use Policy is incorporated (§1.b.iv). The EU restriction in the [AUP](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/USE_POLICY.md) applies only "with respect to any multimodal models included in Llama 3.2" (1B/3B are text-only). |
| Phi-4-mini-instruct | `mit` ([card](https://huggingface.co/microsoft/Phi-4-mini-instruct)) | Yes | Keep the MIT notice |
| Gemma 4 E2B/E4B | `apache-2.0`, `license_link` → [Gemma 4 license](https://ai.google.dev/gemma/docs/gemma_4_license) (unmodified Apache 2.0 text, page updated 2026-04-01) | Yes | Apache-2.0. The license page also links a Gemma Prohibited Use Policy and Terms. **UNVERIFIED** whether those bind Gemma 4 weights; read them before publishing if Gemma is chosen. |

All accessed 2026-09-26.

HF publishing, for every candidate: the adapter, merged model and GGUF repos inherit the base license. Set `license:` (or `license: other` + `license_name` + `license_link` for Llama) and `base_model:` in the model card metadata ([HF model cards docs](https://huggingface.co/docs/hub/model-cards)). Details are in `gguf-export-and-ollama.md`.

### Q3. Chat templates (verified renderings and pitfalls)

- **Qwen3.5 (ChatML + think block).** The `Qwen/Qwen3.5-2B` `tokenizer_config.json` chat template ends with a generation prompt of `'<|im_start|>assistant\n'`. That is followed by `'<think>\n'` if `enable_thinking is true`, else `'<think>\n\n</think>\n\n'`. `eos_token` = `<|im_end|>`, `pad_token` = `<|endoftext|>`, `bos_token` = None, `add_bos_token` = False ([tokenizer_config.json](https://huggingface.co/Qwen/Qwen3.5-2B/blob/main/tokenizer_config.json), accessed 2026-09-26). Consequences:
  - With thinking off, the serving prompt must end in `<think>\n\n</think>\n\n`, exactly as in training.
  - For 4B, `enable_thinking=False` must be passed explicitly, because thinking is its default.
- **Qwen3-1.7B.** Same ChatML family with a hybrid think switch. The model card documents `enable_thinking=False` for non-thinking behaviour. **Qwen3-4B-Instruct-2507** has no think tags at all.
- **Llama 3.2.** The format is `<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n…<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n…<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n` ([text_prompt_format.md](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/text_prompt_format.md)). The HF Jinja template (inspected via the ungated mirror [unsloth/Llama-3.2-3B-Instruct tokenizer_config.json](https://huggingface.co/unsloth/Llama-3.2-3B-Instruct/blob/main/tokenizer_config.json), accessed 2026-09-26) starts with `{{- bos_token }}` and sets `date_string = strftime_now("%d %b %Y")` when it is not provided. **The rendered prompt therefore changes daily** unless a fixed `date_string` is passed.
- **Phi-4-mini.** `<|system|>…<|end|><|user|>…<|end|><|assistant|>` ([card](https://huggingface.co/microsoft/Phi-4-mini-instruct)).
- **Gemma 4.** New control tokens `<|turn>` / `<turn|>`, roles `system`/`user`/`model`, e.g. `<|turn>system\n…<turn|>\n<|turn>user\n…<turn|>\n<|turn>model\n`. Thinking is enabled by putting `<|think|>` at the start of the system prompt ([Gemma 4 prompt formatting](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4), accessed 2026-09-26).
  - The model card says E2B/E4B "still generate empty tags" with thinking disabled. **UNVERIFIED** at raw-prompt level; test it.
  - Ollama's source notes that "llama.cpp forces add_bos on for Gemma4 at load time" ([llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go), accessed 2026-09-26).
- **TRL support for assistant-only loss.** TRL auto-swaps a training template with `{% generation %}` markers for these families: Qwen2.5, Qwen3 (incl. Instruct-2507), Qwen3.5 (think/nothink variants), Qwen3.6, Qwen3.8, Llama 3/3.1/3.2, Gemma/Gemma3/Gemma4, Phi-3 and Phi-3.5 ([TRL Chat Templates](https://huggingface.co/docs/trl/main/en/chat_templates), accessed 2026-09-26). **Phi-4-mini is not listed**, so use a prompt-completion dataset for it (see `qlora-training-on-t4.md`).
- **BOS handling in raw prompts.** llama-server inserts BOS for string prompts when the GGUF's `tokenizer.ggml.add_bos_token` is true ([llama-server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)). Templates that emit `bos_token` themselves (Llama) will then produce a double BOS unless it is stripped.

### Q4. Zero-shot bake-off results

**Not run yet (Open, owned by P2).** Model-card benchmark tables are not a substitute. For example, the Qwen3.5-4B card compares it against much larger, mostly reasoning or "Thinking" models (GPT-OSS-120B/20B, Qwen3-Next-80B-A3B-Thinking, Qwen3-30B-A3B-Thinking-2507), and that model runs in thinking mode by default. General benchmarks like these do not predict non-thinking, schema-constrained triage on our taxonomy, so they were not used. The protocol is in the Decision section.

### Q5. CPU Q4 tokens/s on the dev laptop

**Not measured yet (Open).** Facts recorded 2026-09-26 via a local read-only `Get-CimInstance` query:

- CPU: **AMD Ryzen 7 8840HS**, 8 cores / 16 threads.
- **15.3 GB** RAM visible to the OS.
- GPU: AMD Radeon 780M integrated graphics.
- **Ollama is not installed** and `llama-server` is not on PATH.

The M-08 reference box is 8 vCPU / 16 GB, so this laptop is a close proxy.

Serving-structure facts that bear on latency:

- Ollama ≥ 0.30 runs GGUF models through llama.cpp's `llama-server` as a subprocess (see `gguf-export-and-ollama.md`). Ollama always sets `cache_prompt: true` ([llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)). llama-server's `cache_prompt` means "the common prefix does not have to be re-processed" ([server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)).
- For hybrid/recurrent models (Qwen3.5 GDN layers), llama-server relies on context checkpoints: `--ctx-checkpoints` (default 32) and `--checkpoint-min-step` (default 8192 tokens). The Ollama launch code does not pass either flag (source grep, accessed 2026-09-26).
- **UNVERIFIED (verify at build time)** whether the ~350-token system-prompt prefix is reused across requests for Qwen3.5 under Ollama. Check `prompt_eval_duration` on two consecutive requests. Ollama documents it as "Time spent evaluating uncached prompt tokens" ([API docs](https://docs.ollama.com/api/generate)).
- Gemma 4 E2B's Ollama Q4_K_M artifact is 7.2 GB, almost half the laptop's RAM.

### Q6. Which is chosen and why

**Not final (it depends on Q4 and Q5).** The provisional recommendation and decision rule are below. Trainability facts that bias the choice (details in `qlora-training-on-t4.md`):

- Unsloth: "It is not recommended to do QLoRA (4-bit) training on the Qwen3.5 models" ([Unsloth Qwen3.5 fine-tune docs](https://unsloth.ai/docs/models/qwen3.5/fine-tune)).
- The Qwen3.5 Gated DeltaNet path "needs the optional `causal_conv1d` … and `fla` packages for its fast kernels — without them, the model silently falls back to slower and more memory hungry PyTorch ops" ([Transformers Qwen3.5 docs](https://huggingface.co/docs/transformers/model_doc/qwen3_5)).
- Gemma 4's audio attention uses `-1e9`, which "overflows fp16's maximum value" on T4 ([Unsloth Gemma 4 training docs](https://unsloth.ai/docs/models/gemma-4/train)).

All accessed 2026-09-26.

---

## DECISION / RECOMMENDATION

The items below are recommendations, not sourced facts.

### 1. Bake-off shortlist (P2)

| # | Candidate | Why it is in | Main risk |
|---|---|---|---|
| A | `Qwen/Qwen3.5-2B` (non-thinking default) | Newest Qwen small model, Apache-2.0; spec default family | GDN kernels on T4; fp16 behaviour; hybrid-cache CPU latency; 248K vocab |
| B | `Qwen/Qwen3-1.7B` (`enable_thinking=False`) | Pure transformer, mature tooling (TRL template, llama.cpp); smallest "reliable" fallback | Older (2025-04); 32k context (enough for our 8k budget) |
| C | `Qwen/Qwen3-4B-Instruct-2507` | Tests the "≥ 3 F1 points for a bigger model" rule inside the same family; non-thinking only | CPU latency at 4B |
| D | `meta-llama/Llama-3.2-3B-Instruct` | Cross-family comparator named in the spec | License naming and AUP obligations; gated; date in template |
| E | `microsoft/Phi-4-mini-instruct` | Phi-family mini, MIT | 3.8B CPU latency; 200K vocab; no TRL auto-template |
| opt | `google/gemma-4-E2B-it`, `Qwen/Qwen3.5-0.8B` | Newest Google (Apache-2.0) / latency floor | Gemma: 7.2 GB Q4 artifact, fp16 overflow on T4. 0.8B: accuracy |

### 2. Bake-off protocol (identical for every candidate)

1. Pin every HF repo by commit SHA in `ml/configs/bakeoff.yaml`.
2. Convert the official safetensors yourself with llama.cpp at the build Ollama ships (b11081 for Ollama v0.34.4, see `gguf-export-and-ollama.md`) to BF16 GGUF, then `llama-quantize … Q4_K_M` with no imatrix, so that all candidates are treated equally. Do not use library tags or third-party GGUFs: they have mixed quants and supply-chain risk (R-12).
3. Render each prompt with the model's own HF template: `apply_chat_template(..., add_generation_prompt=True, enable_thinking=False)` where applicable, and a fixed `date_string` for Llama. Send it via Ollama `/api/generate` with `raw: true`, `format: <inlined TriageModelOutput schema>`, `options: {temperature: 0, num_ctx: 8192, num_predict: 512, seed: 42}` (see `constrained-decoding.md`).
4. Use the same system prompt `triage.v1` for all models, on val n = 450. Run accuracy on the fastest available hardware (Kaggle T4 with a CUDA llama.cpp/Ollama build is fine). Spot-check 100 tickets on the laptop CPU to confirm the outputs are identical, since backends can differ numerically.
5. Measure CPU speed on the dev laptop, CPU-only:
   ```powershell
   # llama.cpp (pin the same build). -ngl 0 forces CPU; -t 8 = physical cores
   llama-bench -m .\gguf\<model>-Q4_K_M.gguf -p 1024 -n 256 -t 8 -ngl 0 -r 5 -o md
   ```
   Then run a 50-ticket end-to-end latency sample through Ollama with `options: {num_gpu: 0, num_thread: 8}`. Ollama maps `num_gpu 0` to `-ngl 0` and `num_thread` to `-t` ([llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)). Record from the response:
   - `prompt_eval_count`, `prompt_eval_duration`, `eval_count`, `eval_duration` (nanoseconds, [API docs](https://docs.ollama.com/api/generate))
   - decode tokens/s = `eval_count / (eval_duration/1e9)`
   - triage wall time P50/P95
6. Score, with every term normalized to [0, 1]:
   `S = 0.40·macroF1 + 0.25·min_critical_recall + 0.20·min(1, L_target / L_P50) + 0.15·Lic`. Here:
   - `L_target` = 5 s (the M-08 triage P50).
   - `Lic` = 1.0 for Apache-2.0/MIT, 0.5 for Llama 3.2 Community License, 0 (excluded) for non-commercial.
   - A larger model wins only if its macro-F1 gain is ≥ 3 points at acceptable latency (spec §9.5).
7. **Fine-tune probe** (SI-5): run 1 epoch, seed 42, on the top 2 by `S`, then evaluate on val. Choose on the post-probe val macro-F1 and critical recall, with the latency and license terms unchanged. Record everything as an MLflow run and in `evals/reports/<date>/bakeoff.md`.

### 3. Provisional default and fallback

- **Default: Qwen3.5-2B**, if all three hold:
  - (a) the T4 smoke test passes: fp16 forward/backward with no inf/NaN, a plausible step time, and kernels available or an acceptable fallback speed;
  - (b) its CPU triage P50 is within 1.2× the best candidate's;
  - (c) its probe macro-F1 is within 1 point of the best.
- **Fallback: Qwen3-1.7B** if (a) or (b) fails.
- Pick **Qwen3-4B-Instruct-2507** only under the ≥ 3-point rule and only if M-08 still holds.

### 4. Naming

`tw-triage-qwen35-2b-lora@0.1.0`. Use the method name that was actually used (`lora` or `qlora`), see `qlora-training-on-t4.md`. If a Llama base wins, use the `Llama-` prefix (SI-3).

### 5. Template determinism rule

Always pass the template kwargs explicitly (`enable_thinking=False`, and `date_string="26 Sep 2026"` or another fixed string for Llama). Store the sha256 of the chat template string and of one golden rendered prompt in `model_versions` and in the model card.

---

## IMPLEMENTATION CHECKLIST

- [ ] Re-run the Q1 searches at P2 start: new Qwen/Llama/Phi/Gemma small models, and license changes (R-14).
- [ ] Accept the Llama 3.2 license on HF (manual gating) only if Llama stays in the bake-off.
- [ ] Write `ml/configs/bakeoff.yaml` with repo ids and commit SHAs, chat-template kwargs, the quant type, and the llama.cpp build tag.
- [ ] Write `tw_ml/eval/bakeoff.py`: GGUF convert → quantize → Ollama create → val run → metrics → latency sample → score table.
- [ ] Install Ollama on the dev laptop (pinned version, same as compose), then run `llama-bench` and the 50-ticket latency sample with `num_gpu: 0`.
- [ ] Run a T4 smoke test for each finalist (20 steps; see `qlora-training-on-t4.md`).
- [ ] Run the 1-epoch probe for the top 2, then write ADR-0011 with the numbers, license table and template notes.
- [ ] Record the chat-template sha256 and a golden rendered prompt per model.

---

## OPEN RISKS / TO VERIFY AT BUILD TIME

1. **M-08 latency.** Illustrative arithmetic only, not a measurement: if the laptop measures 200 prompt tokens/s and 25 decode tokens/s for a 2B Q4 model, a 900-token prompt plus 180 output tokens takes about 4.5 s + 7.2 s ≈ 11.7 s, which would fail the 5 s P50 target. Measure first. The levers, in order:
   - a shorter `rationale` or fewer optional fields (this is a schema change and needs an ADR);
   - system-prompt prefix caching (pure-transformer models);
   - a smaller model (0.8B/1.7B);
   - a relaxed target via ADR.
2. **Qwen3.5 prefix caching under Ollama** for hybrid layers (Finding Q5). **UNVERIFIED**.
3. **Qwen3.5 GDN kernels on T4.** `fla`/`causal-conv1d` support for sm_75 is **UNVERIFIED**. The fallback is slow and memory hungry per the Transformers docs.
4. **No newer Llama/Phi small model**, and whether the Gemma Prohibited Use Policy applies to Gemma 4. Both **UNVERIFIED**.
5. **Gemma 4 E2B/E4B empty thinking tags** with thinking disabled (model-card statement). Verify at raw-prompt level if Gemma is kept.
6. **Val → test shift.** Selecting on Family-A val can overfit generator style. The Family-B test is the arbiter, and it must never be used for selection.

---

## LINKED ADR

- **ADR-0011: Base SLM choice.** Update it with the bake-off table, the probe results, the licenses table, the chosen default and fallback, and SI-1..SI-4.
- ADR-0012 (training stack) and ADR-0014 (serving) are affected by trainability and serving facts; see the sibling ERPROT docs.

---

## SOURCES (all accessed 2026-09-26)

1. QwenLM, Qwen3.8 repository news (Qwen3.5/3.6/3.8 release list): https://github.com/QwenLM/Qwen3.8
2. Qwen/Qwen3.5-2B model card and files (`config.json`, `tokenizer_config.json`): https://huggingface.co/Qwen/Qwen3.5-2B
3. Qwen/Qwen3.5-4B model card: https://huggingface.co/Qwen/Qwen3.5-4B
4. Qwen/Qwen3.5-0.8B config: https://huggingface.co/Qwen/Qwen3.5-0.8B
5. Qwen/Qwen3-1.7B model card: https://huggingface.co/Qwen/Qwen3-1.7B
6. Qwen/Qwen3-4B-Instruct-2507 model card: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
7. Qwen/Qwen2.5-1.5B-Instruct model card: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct
8. Qwen/Qwen2.5-3B-Instruct LICENSE (Qwen Research License): https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE
9. Meta, Llama 3.2 Community License: https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE
10. Meta, Llama 3.2 Acceptable Use Policy: https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/USE_POLICY.md
11. Meta, Llama 3.2 model card and text prompt format: https://github.com/meta-llama/llama-models/tree/main/models/llama3_2
12. meta-llama/Llama-3.2-3B-Instruct (HF page): https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct
13. Llama 3.2 chat template, ungated mirror: https://huggingface.co/unsloth/Llama-3.2-3B-Instruct/blob/main/tokenizer_config.json
14. microsoft/Phi-4-mini-instruct model card: https://huggingface.co/microsoft/Phi-4-mini-instruct
15. Google, Gemma 4 model card: https://ai.google.dev/gemma/docs/core/model_card_4
16. Google, Gemma 4 license: https://ai.google.dev/gemma/docs/gemma_4_license
17. Google, Gemma 4 prompt formatting: https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4
18. google/gemma-4-E2B-it model card and config: https://huggingface.co/google/gemma-4-E2B-it
19. Hugging Face Hub API (gating, dates, license tags): https://huggingface.co/api/models/{repo_id}
20. Ollama library tag pages: https://ollama.com/library/qwen3.5/tags, https://ollama.com/library/qwen3/tags, https://ollama.com/library/llama3.2/tags, https://ollama.com/library/phi4-mini/tags, https://ollama.com/library/gemma4/tags
21. Ollama releases (v0.17.5 Qwen3.5, v0.20.0 Gemma 4): https://github.com/ollama/ollama/releases
22. Ollama source, `llm/llama_server.go`: https://github.com/ollama/ollama/blob/main/llm/llama_server.go
23. Ollama API reference (response timing fields): https://docs.ollama.com/api/generate
24. llama.cpp server README (cache_prompt, ctx checkpoints, BOS insertion): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
25. llama.cpp llama-bench README: https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md
26. Hugging Face TRL, Chat Templates (bundled training templates): https://huggingface.co/docs/trl/main/en/chat_templates
27. Hugging Face Transformers, Qwen3.5 model docs (v5.17.0): https://huggingface.co/docs/transformers/model_doc/qwen3_5
28. Unsloth, Qwen3.5 fine-tune guide: https://unsloth.ai/docs/models/qwen3.5/fine-tune
29. Unsloth, Gemma 4 training guide: https://unsloth.ai/docs/models/gemma-4/train
30. Hugging Face Hub docs, Model Cards (base_model, license metadata): https://huggingface.co/docs/hub/model-cards
