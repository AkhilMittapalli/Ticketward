# GGUF Export, Quantization & Ollama Serving - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: September 26, 2026
**Last Updated**: September 27, 2026
**Status**: Partially resolved
**Status Note**: The toolchain, commands, Ollama runtime behaviour and HF conventions are resolved from docs and source code. Still pending at P3: an end-to-end conversion of our merged text-only checkpoint, the quantization-drift measurement, and the template-parity tests.
**Category**: ML serving / Export & packaging
**Linked ADR(s)**: ADR-0014 (Ollama serving; vLLM production path), ADR-0011 (base model), ADR-0012 (training stack), ADR-0013 (registry)
**Spec sections**: §7.1 (Ollama CPU), §9.5 "Export/serving", §9.6 (registry, HF Hub, model card), §9.8 M-08, §15 (health checks), §16 P3, §21 R-06/R-12/R-14, §23

---

## EXECUTIVE SUMMARY

**Ollama's backend changed in 2026.**

- **v0.30.0 (2026-05-13):** Ollama runs GGUF models by wrapping llama.cpp's `llama-server` as a subprocess. v0.34.4 pins llama.cpp **b11081**.
- **v0.34.1 (2026-09-14):**
  - **`ADAPTER` (LoRA) support was removed.** The source now has `errAdaptersUnsupported = "LoRA adapters are no longer supported"`.
  - "GGUF model creation now requires using llama.cpp tooling for safetensor conversion and quantization." The import docs confirm: "Ollama does not quantize GGUF models during import."
  - The spec's merge → convert → quantize plan is therefore the **only** path.

**Export steps for our model.**

1. Train the LoRA adapter.
2. Merge it on CPU in fp32 with PEFT `merge_and_unload()`. For Qwen3.5 load `Qwen3_5ForCausalLM`, the text-only class.
3. Save bf16 safetensors plus the tokenizer.
4. Convert with `convert_hf_to_gguf.py --outtype bf16`, pinned to **the llama.cpp build Ollama ships**. Qwen3.5, Gemma 4, Phi-3/4 and Llama architectures are all registered.
5. Build an `llama-imatrix` from **train-split** prompts.
6. Quantize with `llama-quantize` to Q4_K_M, Q5_K_M, Q6_K and Q8_0.
7. Pick the smallest quant that passes the drift gate on val.

**Serving gotchas.**

- **Context size:** Ollama defaults to a **4k context below 24 GiB VRAM** (CPU counts as 0). Our budget is 6,000 ticket tokens + ~350 system + ≤ 512 output, so `num_ctx 8192` must be set.
- **Silent truncation:** prompts longer than `num_ctx` are cut in the middle with only a server-log warning. Request `truncate: false` to fail loudly.
- **Template parity:** the most robust choice is to send the **exact training-rendered prompt** with `raw: true`. The Modelfile `TEMPLATE` is then only for interactive use, and parity is guaranteed by CI tests. Ollama has a debug flag `_debug_render_only` and returns `prompt_eval_count`, which make those tests easy.

**HF Hub publishing.** Publish three repos: the adapter (`library_name: peft`, `base_model_relation: adapter`), the merged model (`finetune`), and the GGUF (`quantized`).

- Files follow the GGUF naming convention `<BaseName>-<SizeLabel>-<FineTune>-<Version>-<Encoding>.gguf`.
- Adding `template` (Go) and `params` (JSON) files lets `ollama run hf.co/<user>/<repo>:Q4_K_M` work directly.
- The app itself should fetch **by revision SHA and verify sha256**, not use `ollama pull hf.co/...`.

---

## SPEC IMPACT (owner action required; spec not edited)

| ID | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | ADR-0014 alternatives; runbooks | Ollama v0.34.1 removed LoRA adapters and create-time GGUF quantization. Bisected in source: absent in v0.34.0, present in v0.34.1. | State that merging and llama.cpp quantization are mandatory. The runtime-adapter option only exists with llama-server directly or with vLLM. |
| SI-2 | §9.5 "Ollama `Modelfile` with template and `PARAMETER temperature 0`" | Default context is 4k on CPU ([context-length docs](https://docs.ollama.com/context-length)). There is no stop token unless set. Library bases inherit renderer, parser and penalties. | The Modelfile must set `num_ctx 8192`, `num_predict 512`, `stop "<|im_end|>"` (per family), `temperature 0`, and `seed`. Build `FROM ./<file>.gguf`, never from a library tag. |
| SI-3 | §9.4 / §9.5 template | Chat-path rendering depends on Ollama's template selection (Go TEMPLATE vs llama-server Jinja, template autodetection, per-arch renderers). | The OllamaProvider sends **raw** prompts rendered from an exported `prompt_format.json`, and CI proves parity with the HF template. |
| SI-4 | §9.6 `model_versions` (HF revision, GGUF sha256, eval_run_id) | Converter and runtime compatibility follows Ollama's pinned llama.cpp (`LLAMA_CPP_VERSION`: b11081 in v0.34.4, b10864 in v0.34.1, b9452 in v0.30.0). | Also record `llama_cpp_build`, `quant_type`, `imatrix_sha256`, `chat_template_sha256`, `ollama_version`, `calibrator_version`. |
| SI-5 | §9.5 "quantization-drift check (Q4 vs fp16 on val) ≤ 2 points macro-F1" | The spec gates only on macro-F1. | Keep it. Add per-critical-class recall drop ≤ 1 pt, JSON validity unchanged, and a calibrator re-fit per quant. Use the BF16 GGUF as the "fp16" reference, and check it against HF outputs. The imatrix comes from the train split only (leakage). |
| SI-6 | §9.6 "HF Hub publishes the adapter (safetensors) + GGUF + model card" | Correct lineage needs `base_model` chains, and there are GGUF naming conventions. Llama requires a name prefix (see `slm-model-selection.md`). | Three repos (adapter, merged, GGUF) with the metadata below. |
| SI-7 | §18 quick start "pull the GGUF from the HF Hub" | `ollama run hf.co/...` resolves the repo's current revision. | README may use it for convenience. Compose and eval must download by `revision=<sha>` and verify sha256 before `ollama create`. |

---

## QUESTIONS (from SPEC §23)

1. What are the merge + convert steps for the chosen architecture?
2. Which quantization, and how much drift does it cause?
3. Is the Modelfile template correct?
4. What are the HF Hub GGUF publishing conventions?
5. (Added) What Ollama runtime facts affect correctness: version, context, truncation, template selection?

---

## FINDINGS

### Q1. Merge + convert

**PEFT merge** ([PEFT LoRA guide](https://huggingface.co/docs/peft/main/en/developer_guides/lora), accessed 2026-09-26):

- `model = PeftModel.from_pretrained(base, adapter); model = model.merge_and_unload()`.
- "It is important to assign the returned model… `merge_and_unload()` is not an in-place operation."
- For bitsandbytes-quantized bases, Transformers offers `model.dequantize()`, which "may result in some quality loss" ([Transformers bitsandbytes docs](https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes)).

**Text-only Qwen3.5.** "Use `Qwen3_5ForCausalLM` for text-only generation with `Qwen3_5TextConfig`" ([Transformers Qwen3.5 docs, v5.17.0](https://huggingface.co/docs/transformers/model_doc/qwen3_5)).

**llama.cpp converter** (`convert_hf_to_gguf.py` on master, with registrations in the new `conversion/` package; accessed 2026-09-26):

- Options include `--outtype {f32,f16,bf16,q8_0,tq1_0,tq2_0,auto}` (default `auto`), `--outfile`, `--model-name`, `--metadata`, `--split-max-size`, `--remote`, `--dry-run`, `--vocab-only` and `--mmproj`.
- `conversion/qwen.py` registers `Qwen3_5ForConditionalGeneration` and `Qwen3_5ForCausalLM` (plus MoE variants) and `Qwen3ForCausalLM`.
- `conversion/gemma.py` registers `Gemma4ForConditionalGeneration` and `Gemma4ForCausalLM`.
- `conversion/phi.py` registers `Phi3ForCausalLM`; Phi-4-mini's config uses `Phi3ForCausalLM`.
- `conversion/llama.py` registers the Llama family.

**Quantize README** ([tools/quantize/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md)):

- Two phases: "Convert the original model to GGUF format" and "Quantize the converted GGUF file".
- "`--outtype auto` (or omitting `--outtype` entirely) also works well" for 16-bit sources.
- "the Python requirements install transformers 4, but more and more models (like Gemma 4) require transformers 5. You can safely `pip install -U transformers`." Qwen3.5 also needs Transformers v5, per Unsloth's guide.
- Multimodal encoders go into a separate `mmproj` GGUF via `--mmproj`. "llama.cpp will convert the LLM portion of the source model, which is enough for conversational applications."

**Ollama import** ([import docs](https://docs.ollama.com/import), accessed 2026-09-26):

- `FROM /path/to/file.gguf`, then `ollama create my-model`.
- "Ollama does not quantize GGUF models during import. Prepare and quantize them first with a GGUF tool such as llama.cpp's `llama-quantize`."
- Split GGUFs use `FROM ./model-*.gguf`.

### Q2. Quantization choice and drift

Size and speed, for Llama-3.1-8B from the quantize README:

| Quant | bits/weight | text-generation t/s |
|---|---|---|
| Q4_K_M | 4.8944 | 71.93 |
| Q5_K_M | 5.7036 | 67.23 |
| Q6_K | 6.5633 | 58.67 |
| Q8_0 | 8.5008 | 50.93 |

The README excerpt does not state the benchmark hardware; treat the speed column as relative only.

Quality, for LLaMA 3 8B vs FP16 from [tools/perplexity/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/perplexity/README.md):

| Quant | KLD (no imatrix) | KLD (WikiText imatrix) | "same top p" |
|---|---|---|---|
| Q4_K_M | 0.031273 | 0.028152 | 91.901% |
| Q6_K | — | — | 96.031% |
| Q8_0 | — | — | 97.674% |

- The perplexity tool supports `--kl-divergence-base <logits file>` then `--kl-divergence` against a quantized model.
- These are **8B wikitext** figures. Small (1–4B) models and our constrained labels may behave differently. **UNVERIFIED** for our models, so measure.

**imatrix** ([tools/imatrix/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/imatrix/README.md)):

- `llama-imatrix -m model.gguf -f calibration.txt [-o imatrix.gguf] [--parse-special] [--chunks N]`. GGUF is the default output format.
- `--parse-special` "enables parsing of special tokens (e.g., `<|im_start|>`…)".
- Then `llama-quantize --imatrix imatrix.gguf in.gguf out.gguf q4_k_m`.

**Runtime size cap on the laptop.** Library Q4_K_M sizes range from 1.4 GB (`qwen3:1.7b`) to 7.2 GB (`gemma4:e2b`); see `slm-model-selection.md`.

### Q3. Modelfile and template correctness

**Modelfile reference** ([docs](https://docs.ollama.com/modelfile), accessed 2026-09-26):

- Instructions: `FROM`, `PARAMETER`, `TEMPLATE`, `SYSTEM`, `LICENSE`, `MESSAGE`, `REQUIRES` ("minimum version of Ollama required"). **`ADAPTER` is no longer documented.** The parser still accepts `renderer`, `parser` and `draft` keywords (`parser/parser.go`), but `server/create.go` rejects adapters (v0.34.1+).
- Parameters: `num_ctx` ("Default: 2048" in the table), `repeat_last_n`, `repeat_penalty` (default 1.0, disabled), `temperature` (0.8), `seed`, `stop`, `num_predict` (-1), `draft_num_predict`, `top_k` (40), `top_p` (0.9), `min_p` (0.0).
- The **context-length page** supersedes the table's 2048: "Ollama defaults to the following context lengths based on VRAM: < 24 GiB VRAM: 4k context …" ([docs](https://docs.ollama.com/context-length)). The change arrived in v0.15.5 (2026-02-03, release notes).
- The template is Go `text/template` with `.System`, `.Prompt`, `.Response`, `.Messages` and `.Tools` ([template docs](https://docs.ollama.com/template)). "By default, models imported into Ollama have a default template of `{{ .Prompt }}`."

**How Ollama picks a prompt renderer** (v0.34.4 source):

- `usesOllamaRenderedChat(m)` is true if the model has a Renderer or Parser, uses Harmony, or `shouldUseGoTemplate(m)`. In that case Ollama renders in Go, starts llama-server with `--no-jinja --chat-template chatml`, and calls `/completion`. Otherwise it uses "llama-server's chat_template handling through /v1/chat/completions" (`llm/llama_server.go` header; `server/routes.go`).
- Go templates can be **autodetected** at create time: `template.Named()` picks the built-in template with Levenshtein distance < 100 to the GGUF's `tokenizer.chat_template` (`template/template.go`).
- A GGUF chat template can be preferred over a Go template when it has more capabilities (`PreferChatTemplate`, `server/images.go`).
- Renderers and parsers are auto-assigned only for GGUF archs `gemma4` (plus stop `<turn|>`), `laguna` and `nemotron_h*` (`server/create.go`).

**Raw mode.** `/api/generate` with `raw: true` sends the prompt verbatim. The rules: "raw mode does not support template, system, or context", and the format "applies from its first token" (`server/routes.go`).

**BOS.** llama-server inserts BOS for string prompts if `tokenizer.ggml.add_bos_token` is true ([server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)). Ollama notes "llama.cpp forces add_bos on for Gemma4". Qwen: `add_bos_token: false`. Llama 3.2's HF template emits `bos_token` itself, which creates a double-BOS risk in raw mode.

**Debug and verification hooks** (v0.34.4 `api/types.go`):

- `_debug_render_only` "returns the rendered template instead of calling the model", in response field `_debug_info.rendered_template`.
- `prompt_eval_count` is the "Number of input tokens in the prompt". `prompt_eval_duration` is "Time spent evaluating uncached prompt tokens" ([API docs](https://docs.ollama.com/api/generate)).

**Truncation** (`llm/llama_server.go`):

- If the prompt is at least `num_ctx` tokens and context shift is on, Ollama keeps the first `num_keep` tokens, discards the middle, and logs `"truncating input prompt"`. With context shift off it returns HTTP 400.
- The generate handler sets `Truncate: req.Truncate == nil || *req.Truncate` and `Shift: req.Shift == nil || *req.Shift` (`server/routes.go` v0.34.4). Both default to on.

**Parallelism** ([FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)):

- "`OLLAMA_NUM_PARALLEL` … default 1. Required RAM will scale by `OLLAMA_NUM_PARALLEL` * `OLLAMA_CONTEXT_LENGTH`."
- The llama-server launch uses `-c num_ctx*numParallel -np numParallel`.
- `num_gpu 0` maps to `-ngl 0` and `num_thread` to `-t` (source).

### Q4. HF Hub GGUF publishing conventions

**Ollama integration** ([hub/ollama](https://huggingface.co/docs/hub/ollama), accessed 2026-09-26):

- Use `ollama run hf.co/{username}/{repository}:{quantization}`. "By default, the `Q4_K_M` quantization scheme is used, when it's present inside the model repo."
- The template is "selected automatically from a list of commonly used templates… based on the built-in `tokenizer.chat_template` metadata". Alternatively "create a new file called `template` in the repository. The template must be a Go template, not a Jinja template."
- An optional `system` file and a `params` file (JSON) are supported.
- Private repos work via the Ollama SSH key added to HF.

**Model-card metadata** ([hub/model-cards](https://huggingface.co/docs/hub/model-cards)):

- `base_model`: "The Hub will infer the type of relationship from the current model to the base model (`"adapter", "merge", "quantized", "finetune"`) but you can also set it explicitly… `base_model_relation: quantized`."
- A custom license uses `license: other` + `license_name` + `license_link`.
- `library_name` must be explicit "for model repos created after August 2024".

**GGUF naming convention** ([ggml docs/gguf.md](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md)):

- Pattern: `[<Sidecar>]<BaseName><SizeLabel><FineTune><Version><Encoding><Type><Shard>.gguf`.
- "At a minimum all model files should have at least BaseName, SizeLabel, Version". A validation regex is provided. `mmproj-` is the sidecar prefix for vision projectors.
- The fields can be driven from GGUF metadata (`general.basename`, `general.size_label`, `general.finetune`, `general.version`), i.e. converter `--model-name` / `--metadata`.

**Other notes.** The Hub has a GGUF metadata and tensor viewer. `ggml-org/gguf-my-repo` "syncs from llama.cpp `main` every 6 hours". That makes it convenient but **unpinned**, so do not use it for release artifacts ([hub/gguf](https://huggingface.co/docs/hub/gguf), quantize README).

### Q5. Version facts

**Ollama releases** ([releases](https://github.com/ollama/ollama/releases), accessed 2026-09-26):

- Latest stable **v0.34.4 (2026-09-23)**; pre-release v0.40.0 (2026-09-25).
- v0.30.0 (2026-05-13): llama.cpp backend.
- v0.34.1: adapters removed; GGUF creation via llama.cpp tooling.
- v0.17.5 (2026-03-02): Qwen3.5 support and "Fixed issue where Ollama would not be able to run models imported from Qwen3.5 GGUF files".
- v0.12.11: logprobs, and Vulkan (opt-in `OLLAMA_VULKAN=1`).
- v0.14.0: `REQUIRES`.

**`LLAMA_CPP_VERSION`** per tag: v0.34.4 = `b11081`, v0.34.1 = `b10864`, v0.30.0 = `b9452` (raw file at each tag).

---

## DECISION / RECOMMENDATION

### 1. Pipeline (`ml/src/tw_ml/export/`; run on Kaggle right after training, CPU is fine)

```text
adapter (HF private) ─merge(fp32, CPU)→ merged bf16 safetensors + tokenizer + prompt_format.json
  ─convert_hf_to_gguf (llama.cpp @ Ollama's LLAMA_CPP_VERSION)→ *-BF16.gguf
  ─llama-imatrix (train-split text)→ imatrix.gguf
  ─llama-quantize→ Q4_K_M(imatrix), Q5_K_M, Q6_K, Q8_0
  ─drift eval on val via Ollama CPU→ choose smallest passing quant
  ─Modelfile + ollama create→ parity tests → HF publish (3 repos) → model_versions row
```

### 2. Merge (`export/merge.py`)

```python
import json
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, Qwen3_5ForCausalLM

TEXT_ONLY_ARCHS = {"Qwen3_5ForCausalLM", "Qwen3ForCausalLM", "LlamaForCausalLM", "Phi3ForCausalLM", "Gemma4ForCausalLM"}

Cls = Qwen3_5ForCausalLM if arch == "qwen3_5" else AutoModelForCausalLM
base = Cls.from_pretrained(BASE, revision=BASE_REV, dtype=torch.float32, device_map="cpu")  # fp32 merge
merged = PeftModel.from_pretrained(base, ADAPTER_REPO, revision=ADAPTER_REV).merge_and_unload()
merged = merged.to(torch.bfloat16)                          # checkpoints ship in bf16
merged.save_pretrained(OUT_DIR, safe_serialization=True, max_shard_size="2GB")
tok = AutoTokenizer.from_pretrained(BASE, revision=BASE_REV); tok.save_pretrained(OUT_DIR)
with open(f"{OUT_DIR}/config.json", encoding="utf-8") as f:
    arch_saved = json.load(f)["architectures"][0]
assert arch_saved in TEXT_ONLY_ARCHS, arch_saved             # text-only class -> text-only GGUF
```

- **RAM (estimate):** fp32 weights take ~4 bytes/param, i.e. ~7.5 GB for 2B and ~16 GB for 4B. For 4B-class models, merge in bf16 or on a high-RAM box.
- **If the adapter was trained with QLoRA:** merge into (a) the original bf16 weights and (b) `dequantize()`d NF4 weights. Keep whichever has the smaller val disagreement with the 4-bit+adapter model. Recommendation only; **UNVERIFIED** which wins.
- **Parity gate:** HF merged-bf16 greedy outputs vs the adapter model on 50 val tickets must be ≥ 99% identical. Otherwise stop.

### 3. Convert + quantize (Linux shell on Kaggle; pin the tag)

```bash
LLAMA_TAG=b11081                    # = LLAMA_CPP_VERSION of the Ollama version we deploy (v0.34.4)
git clone --depth 1 --branch "$LLAMA_TAG" https://github.com/ggml-org/llama.cpp && cd llama.cpp
python -m pip install -r requirements.txt && python -m pip install "transformers==5.17.0"
cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j --target llama-quantize llama-imatrix llama-perplexity llama-bench llama-server
NAME=tw-triage-qwen35-2B-lora-v0.1.0            # ggml naming: BaseName-SizeLabel-FineTune-Version
python convert_hf_to_gguf.py ../merged --outtype bf16 --outfile ../gguf/$NAME-BF16.gguf --model-name tw-triage-qwen35
python -m tw_ml.export.calib_text --split train --n 400 --out ../gguf/calib.txt     # rendered prompts + gold JSON, TRAIN ONLY
./build/bin/llama-imatrix -m ../gguf/$NAME-BF16.gguf -f ../gguf/calib.txt --parse-special --chunks 200 -o ../gguf/imatrix.gguf
for Q in Q4_K_M Q5_K_M Q6_K; do ./build/bin/llama-quantize --imatrix ../gguf/imatrix.gguf ../gguf/$NAME-BF16.gguf ../gguf/$NAME-$Q.gguf $Q; done
./build/bin/llama-quantize ../gguf/$NAME-BF16.gguf ../gguf/$NAME-Q8_0.gguf Q8_0
sha256sum ../gguf/*.gguf > ../gguf/SHA256SUMS
```

- Text-only conversion omits `--mmproj`. Using `Qwen3_5ForCausalLM` should yield text weights only. Verify with the Hub GGUF viewer or `gguf-dump` that no `v.*`/`mm.*` tensors are present.
- On Windows (the dev laptop), use the prebuilt release binaries for the same tag for `llama-bench`. The Python converter runs anywhere.

### 4. Drift gate (val n = 450, Ollama CPU, raw prompts, decoding schema, T = 0)

| Artifact | Required |
|---|---|
| BF16 GGUF (reference) | ≥ 98% field-level agreement with HF merged-bf16 on 100 val tickets (catches conversion bugs) |
| Candidate quant | macro-F1 drop ≤ 2.0 pts vs BF16 (spec); **each critical-class recall drop ≤ 1 pt**; JSON validity unchanged; ECE re-computed after re-fitting the calibrator on this quant |
| Choice | The smallest quant passing everything. Expected Q4_K_M+imatrix (hypothesis); fallback Q5_K_M → Q6_K |

Optional diagnostic: `llama-perplexity --kl-divergence-base bf16.kld -f val_completions.txt` with the BF16 model, then `-m <quant> --kl-divergence-base bf16.kld --kl-divergence`. Report KLD and "same top p" in the model card.

### 5. Modelfile (`infra/ollama/Modelfile.tw-triage-qwen35-2b`)

For interactive use and the `/api/chat` path. The app uses raw mode.

```text
FROM ./tw-triage-qwen35-2B-lora-v0.1.0-Q4_K_M.gguf
REQUIRES 0.34.4
TEMPLATE """{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
<think>

</think>

{{ .Response }}"""
PARAMETER temperature 0
PARAMETER seed 42
PARAMETER num_ctx 8192
PARAMETER num_predict 512
PARAMETER repeat_penalty 1.0
PARAMETER stop "<|im_end|>"
LICENSE """Apache License 2.0. Fine-tuned from Qwen/Qwen3.5-2B (Apache-2.0). See NOTICE."""
```

- `ollama create tw-triage-qwen35-2b-lora:0.1.0 -f infra/ollama/Modelfile.tw-triage-qwen35-2b`, then `ollama ps` to confirm CONTEXT shows 8192 and PROCESSOR shows CPU.
- This `TEMPLATE` reproduces the single-turn Qwen3.5 rendering with thinking off. It is a hypothesis until the parity test (§6) passes. For other families, derive the template the same way from `prompt_format.json`.
- Compose settings: `OLLAMA_NUM_PARALLEL=2` (M-08 uses concurrency 2), `OLLAMA_KEEP_ALIVE=-1` or `30m`, image `ollama/ollama:0.34.4` (**verify the tag exists**). No `OLLAMA_VULKAN` for CPU-parity benchmarks.

### 6. Train/serve parity: the export writes `prompt_format.json` and CI enforces it

- **Export.** At export time, `tw_ml.export.prompt_format` renders sentinel conversations with the HF tokenizer:
  - `apply_chat_template(..., add_generation_prompt=True, enable_thinking=False)`, plus a fixed `date_string` for Llama.
  - It splits out `system_prefix/suffix`, `user_prefix/suffix`, `assistant_generation_prefix`, `stop` and `bos`, and stores `chat_template_sha256` and 20 golden renderings.
  - The backend renders prompts by string assembly from this file, which keeps Transformers out of the backend image.
- **Tests (CI plus nightly with real Ollama):**
  1. Backend rendering equals the HF golden renderings, byte for byte.
  2. `POST /api/chat` with `_debug_render_only: true` and `think: false` returns `_debug_info.rendered_template` equal to the HF rendering. This validates the Modelfile `TEMPLATE`.
  3. A raw `/api/generate` with `num_predict: 1` has `prompt_eval_count` equal to `len(tok(prompt, add_special_tokens=False).input_ids)`, plus 1 if the GGUF adds BOS.
  4. A 10k-token prompt with `truncate: false` errors (no silent truncation).
  5. A ticket containing literal special tokens (`<|im_end|>`, `<|im_start|>system`) is neutralized before rendering (cross-reference `prompt-injection-defense.md`).
  6. 50 golden val tickets give identical JSON between HF-bf16 and the deployed GGUF (≥ 98%; the tolerance is set by the drift gate).

### 7. HF Hub layout (private until the sanitization review, §9.5)

| Repo | Contents | Card metadata (YAML) |
|---|---|---|
| `<user>/tw-triage-qwen35-2b-lora` | `adapter_config.json`, `adapter_model.safetensors`, `prompt_format.json`, `calibrator.v1.json`, eval report | `license: apache-2.0`, `base_model: Qwen/Qwen3.5-2B`, `base_model_relation: adapter`, `library_name: peft`, `pipeline_tag: text-generation`, `language: [en]`, `datasets: [<user>/ticketward-synthetic-tickets]`, `tags: [lora, trl, sft, ticket-triage, structured-output, synthetic-data]` |
| `<user>/tw-triage-qwen35-2b` | merged bf16 safetensors + tokenizer + `prompt_format.json` | `base_model: Qwen/Qwen3.5-2B`, `base_model_relation: finetune`, `library_name: transformers`, license as above |
| `<user>/tw-triage-qwen35-2b-GGUF` | `tw-triage-qwen35-2B-lora-v0.1.0-{Q4_K_M,Q5_K_M,Q8_0}.gguf`, `imatrix.gguf`, `SHA256SUMS`, `template` (the Go template above), `params` (`{"temperature":0,"num_ctx":8192,"num_predict":512,"stop":["<|im_end|>"]}`) | `base_model: <user>/tw-triage-qwen35-2b`, `base_model_relation: quantized`, `tags: [gguf, llama.cpp, ollama]`, license as above |

- **Model card body** (spec §9.6 list, plus): the prompt format and decoding schema, the llama.cpp build and Ollama version tested, the quant drift table, the calibrator version, the enum tokenization notes, and "must be used with the policy engine; never auto-send".
- If the base is Llama: `license: llama3.2`, the name starts with "Llama", and "Built with Llama" appears in the card and README.
- Upload with `huggingface_hub` (`create_repo(..., private=True, exist_ok=True)`, `upload_folder(...)`) or `hf upload`. Record the returned commit SHA in `model_versions`.
- **App fetch:** `hf_hub_download(repo_id, filename, revision=<sha>)`, then verify sha256 against `model_versions.gguf_sha256`, then `ollama create` from a Modelfile with `FROM <path>`. Readiness check: Ollama `/api/tags` lists the active tag. Optionally compare its reported digest with the recorded sha256 (**verify** that Ollama's blob digest equals the file sha256).

---

## IMPLEMENTATION CHECKLIST

- [ ] `tw_ml.export.merge`, `.gguf` (convert/imatrix/quantize wrappers with the pinned tag), `.prompt_format`, `.calib_text` (train only), `.hub` (three repos, cards from `ml/model_cards/tw-triage.md.j2`).
- [ ] `infra/ollama/Modelfile.*` generated from `prompt_format.json` and committed. Compose pins `ollama/ollama:<version>` to match `REQUIRES`.
- [ ] The drift-gate report goes to `evals/reports/<date>/quant_drift.md` and to the model card.
- [ ] Parity tests 1–6 in CI (1, 5) and nightly with real Ollama (2, 3, 4, 6).
- [ ] Extend `model_versions` with `llama_cpp_build`, `quant_type`, `imatrix_sha256`, `chat_template_sha256`, `ollama_version`, `calibrator_version` (SI-4).
- [ ] Runbook `model-rollback.md`: previous GGUF by SHA, then `ollama create`, then activate.

---

## OPEN RISKS / TO VERIFY AT BUILD TIME

1. End-to-end conversion of a *merged* `Qwen3_5ForCausalLM` checkpoint at b11081, and that its tensors load in Ollama v0.34.4. Source-level evidence only. **UNVERIFIED**.
2. Drift for small hybrid models at Q4_K_M. **UNVERIFIED**; the gate decides.
3. Whether the Modelfile `TEMPLATE` above equals the HF rendering, including whitespace. Parity test 2.
4. Whether the `_debug_render_only` flag is stable. It is an underscore-prefixed debug field and may change; keep the test tolerant (skip if absent).
5. `truncate: false` end-to-end behaviour. **UNVERIFIED**; parity test 4.
6. The Ollama Docker image tag format and CPU-only operation in the compose container, and whether blob digest = file sha256. **UNVERIFIED**.
7. Ollama's 2026 cadence: v0.40.0 is in pre-release, and backends and features were removed in v0.34.1. Pin the version, and re-read the release notes before any upgrade (R-14).

---

## LINKED ADR

- **ADR-0014: Serving.** Record the llama-server backend, the removed adapters/quantize, raw-prompt parity, Modelfile requirements, pinned versions, and the HF fetch-by-SHA flow.
- ADR-0013 (registry fields, SI-4) and ADR-0011 (base model, naming) are also affected.

---

## SOURCES (all accessed 2026-09-26)

1. Ollama releases (v0.12.11, v0.14.0, v0.15.5, v0.17.5, v0.30.0, v0.34.1, v0.34.4, v0.40.0-pre): https://github.com/ollama/ollama/releases
2. Ollama docs, Importing a Model: https://docs.ollama.com/import
3. Ollama docs, Modelfile Reference: https://docs.ollama.com/modelfile
4. Ollama docs, Context length: https://docs.ollama.com/context-length
5. Ollama docs, Template: https://docs.ollama.com/template
6. Ollama docs, API generate (timing fields, raw): https://docs.ollama.com/api/generate
7. Ollama docs, FAQ (`OLLAMA_NUM_PARALLEL`, keep-alive, context): https://github.com/ollama/ollama/blob/main/docs/faq.mdx
8. Ollama source: `server/create.go` (v0.34.1/v0.34.4), `parser/parser.go`, `server/routes.go`, `server/images.go`, `template/template.go`, `llm/llama_server.go`, `api/types.go`, `LLAMA_CPP_VERSION`, `llama/README.md`: https://github.com/ollama/ollama
9. llama.cpp `convert_hf_to_gguf.py` and `conversion/{qwen,gemma,phi,llama}.py`: https://github.com/ggml-org/llama.cpp
10. llama.cpp quantize README: https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md
11. llama.cpp imatrix README: https://github.com/ggml-org/llama.cpp/blob/master/tools/imatrix/README.md
12. llama.cpp perplexity README (KLD, same-top-p tables): https://github.com/ggml-org/llama.cpp/blob/master/tools/perplexity/README.md
13. llama.cpp server README (BOS insertion, flags): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
14. ggml, GGUF spec and naming convention: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
15. Hugging Face Hub docs, Use Ollama with any GGUF model: https://huggingface.co/docs/hub/ollama
16. Hugging Face Hub docs, GGUF: https://huggingface.co/docs/hub/gguf
17. Hugging Face Hub docs, Model Cards (base_model, base_model_relation, license, library_name): https://huggingface.co/docs/hub/model-cards
18. Hugging Face PEFT, LoRA guide (merge_and_unload): https://huggingface.co/docs/peft/main/en/developer_guides/lora
19. Hugging Face Transformers, bitsandbytes (dequantize): https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes
20. Hugging Face Transformers, Qwen3.5 (`Qwen3_5ForCausalLM` text-only): https://huggingface.co/docs/transformers/model_doc/qwen3_5
21. Unsloth, Qwen3.5 fine-tune guide (Transformers v5 requirement; GGUF export options): https://unsloth.ai/docs/models/qwen3.5/fine-tune
