# LoRA/QLoRA Training on T4 (Kaggle / Colab) - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: September 26, 2026
**Last Updated**: September 27, 2026
**Status**: Partially resolved
**Status Note**: Platform stack, precision rules, TRL API, Unsloth decision and checkpoint/resume are resolved from primary sources and code. Still pending: the 20-step T4 smoke test per finalist (memory, kernels, fp16), and Kaggle quota/session numbers, whose primary docs are JS-rendered and unreadable.
**Category**: ML / Training infrastructure
**Linked ADR(s)**: ADR-0012 (HF Transformers + PEFT + TRL + bitsandbytes), ADR-0002 (Python pin), ADR-0003 (uv, separate ml lock), ADR-0013 (MLflow)
**Spec sections**: §9.4 (loss on completion only), §9.5 (QLoRA table, hardware plan), §9.6 (tracking/registry), §14.2 (Python), §21 R-03/R-12/R-14, §23

---

## EXECUTIVE SUMMARY

**Platform stack today (primary sources)**

- **Colab GPU runtime:** Ubuntu 24.04, **Python 3.13**, **torch 2.11.0+cu130**, transformers 5.17.0, peft 0.21.0.
- **Kaggle GPU image:** built on the 2026-07-16 Colab image, so torch 2.11 and **Python 3.12**. Kaggle dropped P100 on 2026-09-05; the GPU you select is **T4 ×2**.
- **bitsandbytes 0.50.2** supports Turing (sm_75) and CUDA 13 wheels.
- **Latest TRL is 1.14.0 (2026-09-25).**

**Precision on T4**

- The T4 has **no bf16 hardware**. Yet `torch.cuda.is_bf16_supported()` defaults to `including_emulation=True`, and **TRL's `SFTConfig.bf16` defaults to True unless `fp16` is set**.
- You must set `fp16=True, bf16=False`.
- Measured on a Colab T4, emulated bf16 is ~2× slower than fp16.

**TRL API (current)**

- `DataCollatorForCompletionOnlyLM` is gone (removed in TRL 0.20.0).
- Use a **prompt-completion dataset**: completion-only loss is the default. Or pass **pre-tokenized `input_ids` + `labels`**.
- `assistant_only_loss=True` works only with `{% generation %}` templates. TRL auto-patches these for Qwen/Llama/Gemma/Phi-3, but **not Phi-4-mini**.
- `max_length` defaults to **1024**; set it explicitly.

**QLoRA traps on T4**

- TRL 0.26 → 1.14 casts trainable adapter weights of *quantized* models to **bf16**. On T4 that must be undone: re-cast to fp32 after trainer init.
- Unsloth explicitly advises **against QLoRA for Qwen3.5**.
- **Recommendation:** use plain LoRA on an fp16 base for 0.8B–2B models. They fit easily (about 6 GB estimated for Qwen3.5-2B). Keep QLoRA (NF4, double quant) as an option for 3–4B bases.

**Unsloth: no, for the primary pipeline.** The current wheel pins `transformers<=5.5.0` and `trl<=0.24.0`, which conflicts with the TRL 1.x features we rely on. It can be an optional, separately locked speed experiment.

**Checkpoint/resume**

- Push every ~25 optimizer steps to a private HF repo with `hub_strategy="checkpoint"` (the `last-checkpoint/` folder).
- Resume with `trainer.train(resume_from_checkpoint=...)`.
- Run the Kaggle "Save & Run All" background job, which is capped at 12 h per session.
- The whole 3-epoch run is only ~338 optimizer steps, so the spec's "every 200 steps" cadence is far too coarse.

---

## SPEC IMPACT (owner action required; spec not edited)

| ID | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §9.5 QLoRA table ("4-bit NF4, double quant, compute dtype fp16"); ADR-0012 | Unsloth advises against QLoRA for Qwen3.5: "not recommended… due to higher than normal quantization differences". 16-bit LoRA fits a T4 for ≤ 2B (estimate ~6 GB). TRL casts QLoRA adapters to bf16 (source), which is unsafe on T4. | Make the quantization row conditional: **LoRA on fp16 base** (default for ≤ 2B), **QLoRA NF4+DQ** (option for 3–4B). Rename E4 to "LoRA/QLoRA SFT". The brief says "LoRA/QLoRA", so this is allowed. |
| SI-2 | §9.4 "TRL SFTTrainer with assistant-only loss / completion-only collator" | `DataCollatorForCompletionOnlyLM` exists in TRL v0.19.0 and is absent from v0.20.0 onward. TRL 1.x has `completion_only_loss` (default on for prompt-completion data) and `assistant_only_loss` (needs `{% generation %}` markers). | Say "prompt-completion dataset (completion-only loss) or pre-tokenized `input_ids`+`labels`". |
| SI-3 | §9.5 "max_seq_len 2,048"; §9.4 | TRL `max_length` default = 1024. Truncation is `keep_start` only, so overlong rows **lose the completion**. `bf16` defaults to True unless `fp16` is set. `learning_rate` default is 2e-5. | Add "set explicitly: `max_length`, `fp16=True`, `bf16=False`, `learning_rate`, `completion_only_loss=True`; drop or trim rows longer than `max_length` before training". |
| SI-4 | §9.5 "eval every 200 steps"; §21 R-03 "checkpoint to HF every 200 steps" | 3,600 × 3 epochs ÷ (4 × 8) ≈ **338 optimizer steps total** (≈ 113/epoch). Every 200 steps means one mid-run eval, and up to ~1.8 epochs lost on a disconnect. | `eval_steps = save_steps = 25` (~0.22 epoch), `save_total_limit=3`, epoch-end generation eval for macro-F1. |
| SI-5 | §14.2 `requires-python = ">=3.12,<3.13"` (backend); `ml/` lock | Colab moved to **Python 3.13** (2026-08-19). Kaggle is still 3.12. | The ml package needs `requires-python = ">=3.12,<3.14"`. Do not lock `torch` in the notebook install; use the platform torch 2.11 and assert it at runtime. |
| SI-6 | §9.5 hardware plan "Kaggle T4×1/×2 (30 h/week)" | Kaggle's image dropped P100 (2026-09-05). "30 h/week" and "T4×2 costs 2× quota" come only from secondary sources; the primary docs are JS-rendered and unreadable (**UNVERIFIED**). | Keep the numbers as "verify on Kaggle quota widget". Prefer 2 seeds in parallel (one per T4) over DDP. |
| SI-7 | §9.5 time estimate ("1.5B ≈ 45–75 min/seed; 3B ≈ 2–3 h") | These are plausible but unmeasured. My FLOP estimate gives ~0.9–1.5 h for 2B-class and ~2.3–3.9 h for 4B-class (3 epochs, one T4), before GDN fallback penalties. | Replace with "measure s/step in the smoke test; budget ≤ 2 h/seed for 2B". |
| SI-8 | ml deps | `huggingface-hub` 2.0.0 shipped 2026-09-24, but `transformers 5.17.0` requires `huggingface-hub<2.0,>=1.5.0` (PyPI metadata). | Pin `huggingface-hub<2` until transformers allows 2.x. |
| SI-9 | §9.5 "target modules: all linear (q,k,v,o,gate,up,down)" | Qwen3.5's Gated DeltaNet layers (18 of 24 in the 2B) use `in_proj_qkv`, `in_proj_z`, `in_proj_b`, `in_proj_a` and `out_proj`, not q/k/v/o (Transformers v5.17.0 source). | Specify the target list per architecture in the config, or use `all-linear`, which excludes `lm_head`. |

---

## QUESTIONS (from SPEC §23)

1. What is the bitsandbytes and CUDA compatibility on Kaggle and Colab today?
2. What are the fp16 vs bf16 constraints on T4?
3. What is the TRL SFTTrainer API for assistant-only loss in the current version?
4. What is the memory budget per model size?
5. Unsloth: yes or no?
6. What is the checkpoint/resume strategy under session limits?
7. (Added) What constraints are specific to Qwen3.5, the default candidate?
8. (Added) What wall-clock time should we expect per seed?

---

## FINDINGS

### Q1. bitsandbytes / CUDA / stack on Kaggle and Colab (as of 2026-09-26)

**Colab GPU runtime**

From [googlecolab/backend-info](https://github.com/googlecolab/backend-info) `pip-freeze.gpu.txt` and `os-info-gpu.txt`, latest commits 2026-09-21 ("Update GPU runtime to cuda 13.3.1") and 2026-09-23; accessed 2026-09-26:

- Ubuntu 24.04.4, Python 3.13.15
- torch 2.11.0+cu130, triton 3.6.0
- transformers 5.17.0, peft 0.21.0, accelerate 1.15.0, datasets 4.8.5, tokenizers 0.23.2, huggingface_hub 1.31.0
- bitsandbytes and trl are **not** preinstalled

History from the same commit log:

- torch 2.11 since 2026-05-22
- Python 3.13 since 2026-08-19
- Ubuntu 24.04 since 2026-09-04

**Kaggle GPU image**

From [Kaggle/docker-python](https://github.com/Kaggle/docker-python), accessed 2026-09-26:

- `Dockerfile.tmpl` builds `FROM us-docker.pkg.dev/colab-images/public/runtime:release-colab-external-images_20260716-060051_RC00`.
- Commit #1557 (2026-09-02) bumped that base, bringing "torch 2.10 -> 2.11".
- `ARG PACKAGE_PATH=/usr/local/lib/python3.12/dist-packages` implies Python 3.12. **Verify** with `!python -V`.
- Commit #1560 (2026-09-05), "Drop P100 support", makes "T4x2 … the sole GPU test bed".
- `kaggle_requirements.txt` adds `transformers>=5.0.0` but not trl or bitsandbytes.

**PyTorch and CUDA**

- PyTorch 2.11 CUDA 12.8 and 13.0 builds support "Turing(7.5), Ampere(8.0, 8.6), Hopper(9.0), Blackwell(10.0, 12.0)" on Linux x86 ([pytorch#172663](https://github.com/pytorch/pytorch/issues/172663), accessed 2026-09-26). T4 is sm_75.

**bitsandbytes** ([releases](https://github.com/bitsandbytes-foundation/bitsandbytes/releases), accessed 2026-09-26):

- 0.46.0: its new CUDA Linux aarch64 wheels "Targets are Turing generation and newer: sm75, sm80, sm90, and sm100".
- 0.47.0: "Include NVIDIA Volta support in CUDA 12.8 and 12.9 builds", so x86-64 builds cover Volta and newer, including Turing.
- 0.48.0: CUDA 13.0 support, "limited to Turing generation and newer"; Maxwell removed.
- 0.50.0 (2026-07-25): CUDA 13.2 wheels; new fused 4-bit inference GEMM "across Turing through Bl[ackwell]".
- **Latest 0.50.2 (2026-08-27).**
- The Transformers bitsandbytes page states CUDA 11.8–13.0 support, and lists NF4/FP4 as requiring "Pascal … or newer" ([docs](https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes)).
- Colab's current cu130 torch is therefore covered. **Verify** with `python -m bitsandbytes`.

**Latest PyPI releases** ([pypi.org](https://pypi.org), accessed 2026-09-26):

| Package | Version | Date |
|---|---|---|
| torch | 2.14.0 | 2026-09-02 |
| transformers | 5.17.0 | 2026-09-09 |
| trl | 1.14.0 | 2026-09-25 |
| peft | 0.21.0 | 2026-09-15 |
| accelerate | 1.15.0 | |
| datasets | 5.0.1 | |
| bitsandbytes | 0.50.2 | |
| huggingface-hub | 2.0.0 | 2026-09-24 |
| liger-kernel | 0.8.3 | |
| flash-linear-attention | 0.5.2 | |
| causal-conv1d | 1.7.0 | |
| unsloth | 2026.9.11 | |
| mlflow | 3.16.1 | |

Pin constraints: `transformers 5.17.0` requires `huggingface-hub<2.0,>=1.5.0` and `tokenizers<0.24.0,>=0.23.1`. `trl 1.14.0` requires `transformers>=4.56.2`, `accelerate>=1.4.0`, `datasets>=4.7.0`.

**Session limits**

- Colab (free): "notebooks can run for at most 12 hours"; runtimes time out when idle. Background execution is only "on higher plans" ([Colab FAQ](https://research.google.com/colaboratory/faq.html), accessed 2026-09-26).
- Kaggle: 12 h per GPU session, ~30 h/week GPU quota, and T4×2 billed at 2 quota-hours per hour. These come from secondary sources only ([LuminoAI 2026-03-27](https://www.luminoai.in/blog/kaggle-gave-you-12-hours-your-training-job-needed-more); a Kaggle forum search summary). **UNVERIFIED**: [kaggle.com/docs/notebooks](https://www.kaggle.com/docs/notebooks) is JS-rendered and returned no text.

### Q2. fp16 vs bf16 on T4

**bf16 on a T4 is emulated**

- `torch.cuda.is_bf16_supported(including_emulation=True)` defaults to counting emulation ([PyTorch 2.14 docs](https://docs.pytorch.org/docs/2.14/generated/torch.cuda.is_bf16_supported.html)).
- A Colab T4 with torch 2.11.0+cu128, reported 2026-09-25, measured a median step of fp16 226 ms, fp32 386 ms and bf16 443 ms ([roboflow/rf-detr#1535](https://github.com/roboflow/rf-detr/issues/1535)).
- Accessed 2026-09-26.

**TRL and PEFT defaults**

- `SFTConfig` note: "`bf16`: Defaults to `True` if `fp16` is not set" ([TRL SFT docs](https://huggingface.co/docs/trl/main/en/sft_trainer)). **You must pass `fp16=True, bf16=False`.**
- PEFT upcasts LoRA adapter params to fp32 by default (`autocast_adapter_dtype=True`, per a TRL source comment). That is what fp16 AMP needs: fp32 trainable params with GradScaler.
- **TRL casts QLoRA adapters to bf16.** The TRL source contains `if _is_quantized_model: for param in model.parameters(): if param.requires_grad: param.data = param.data.to(torch.bfloat16)`. It was added between v0.24.0 and v0.26.0 and is still present in **v1.14.0** ([sft_trainer.py v1.14.0](https://github.com/huggingface/trl/blob/v1.14.0/trl/trainer/sft_trainer.py); grep of the tagged sources, accessed 2026-09-26). On T4 that yields bf16 master weights under fp16 AMP. The runtime effect (slowdown or precision loss) is **UNVERIFIED**. The fix is in the Decision section.

**Model dtypes and overflow**

- The Qwen3.5, Qwen3, Gemma 4 and Phi-4-mini checkpoints are published in bf16 (`config.json` `dtype`/`torch_dtype`, fetched 2026-09-26). The Llama 3.2 config was not fetched because the repo is gated. Loading in fp16 changes the dynamic range, from bf16 max ~3.4e38 to fp16 max 65504 (a property of the formats).
- Model-specific overflow evidence:
  - **Gemma 4**: `Gemma4AudioAttention` uses `-1e9`, which "overflows fp16's maximum value (65504)" on T4 ([Unsloth Gemma 4 guide](https://unsloth.ai/docs/models/gemma-4/train)).
  - **Qwen3.5**: no primary source found on fp16 behaviour (**UNVERIFIED**; the smoke test below covers it).

### Q3. TRL SFTTrainer API (TRL 1.14.0; [SFT docs](https://huggingface.co/docs/trl/main/en/sft_trainer), [source](https://github.com/huggingface/trl/blob/v1.14.0/trl/trainer/sft_trainer.py), accessed 2026-09-26)

**Dataset formats**

- Supported: language modeling (`text` / `messages`) or prompt-completion (`prompt` + `completion`), each standard or conversational.
- Conversational data gets the chat template applied automatically.
- A per-example `chat_template_kwargs` column is forwarded to `apply_chat_template` (source: `**example.get("chat_template_kwargs", {})`). Use it for `{"enable_thinking": false}`.

**Loss masking**

- **Completion-only:** "By default, the trainer computes the loss on the completion tokens only" for prompt-completion data (`completion_only_loss=None` → on).
- For conversational prompt-completion, TRL tokenizes `prompt` with `add_generation_prompt=True` and `prompt+completion` without it. On a prefix mismatch it only **logs a warning** ("Mismatch between tokenized prompt and the start of tokenized prompt+completion") and continues.
- **Assistant-only:** "requires the chat template to include `{% generation %}` and `{% endgeneration %}`… For known model families (e.g. Qwen3), TRL automatically patches the template". The list includes Qwen2.5, Qwen3 (and 2507), Qwen3.5 think/nothink, Llama 3.x, Gemma 3/4 and Phi-3/3.5 ([TRL Chat Templates](https://huggingface.co/docs/trl/main/en/chat_templates)). Phi-4-mini is not listed.
- **Pre-tokenized data:** "An optional `labels` column (`-100` on tokens excluded from the loss) is used as is if present".
- `DataCollatorForCompletionOnlyLM`: present in `trl/trainer/utils.py` at v0.19.0 (2025-06-20), **absent** at v0.20.0 (2025-07-29) and in main.

**Key `SFTConfig` fields and defaults**

- `max_length=1024`; `truncation_mode="keep_start"` (the only supported value).
- `packing=False`. Packing is "available only for… setups that use FlashAttention" ([reducing memory](https://huggingface.co/docs/trl/main/en/reducing_memory_usage)). `padding_free` is "only supported with the FlashAttention 2 or 3". FA2 does not run on Turing, so on T4 **no packing and no padding-free**.
- `gradient_checkpointing=True` by default. `learning_rate=2e-5` by default (override). `optim="adamw_torch_fused"`. `report_to="none"`.
- `SFTTrainer(..., quantization_config=BitsAndBytesConfig(...), peft_config=LoraConfig(...))`: `quantization_config` is "Ignored if the model is already instantiated".
- If `model` is a string, "If `dtype` is not specified in `args.model_init_kwargs`, it defaults to `float32`".

**`loss_type` (default `"chunked_nll"`)**

- "the `lm_head` projection is computed on non-ignored tokens only… the cross-entropy is processed in chunks". The docs report "~30 % less peak VRAM, up to ~50 %" (measured on Qwen3-1.7B).
- **Docs vs code disagree.** The reducing-memory page says "Not compatible with `use_liger_kernel=True`, PEFT, or VLM". The v1.14.0 source instead patches the inner model for PEFT and raises only if `lm_head` itself is a PEFT tuner layer.
- PEFT's `all-linear` shorthand excludes the output embedding layer ([tuners_utils.py](https://github.com/huggingface/peft/blob/main/src/peft/tuners/tuners_utils.py)), so LoRA with `target_modules` that exclude `lm_head` should work. **UNVERIFIED at runtime**: the smoke test asserts it. The fallback is `loss_type="nll"` with a smaller batch.

**Other API notes**

- `warmup_steps` accepts a float ratio in [0, 1) ([TrainingArguments docs](https://huggingface.co/docs/transformers/main/en/main_classes/trainer)); `warmup_ratio` is no longer documented.
- `report_to` supports `"mlflow"` and `"codecarbon"` (useful for the model card's CO₂ estimate).

**Qwen3.5 LoRA module names** ([modeling_qwen3_5.py v5.17.0](https://github.com/huggingface/transformers/blob/v5.17.0/src/transformers/models/qwen3_5/modeling_qwen3_5.py), accessed 2026-09-26):

- Attention: `q_proj`, `k_proj`, `v_proj`, `o_proj`
- MLP: `gate_proj`, `up_proj`, `down_proj`
- Gated DeltaNet: `in_proj_qkv`, `in_proj_z`, `in_proj_b`, `in_proj_a`, `out_proj`; `conv1d` is a Conv1d, not a Linear
- The spec's "(q,k,v,o,gate,up,down)" list would **miss the GDN projections in 18 of the 24 layers**.

### Q4. Memory budget per model size (**engineering estimates, not measurements**)

**Assumptions**

- Per-device batch 4, padded sequence 1,024, ~220 completion tokens per example.
- Gradient checkpointing on; LoRA r = 16 on all linear layers.
- fp32 LoRA weights + grads + fp32 AdamW states.
- NF4 + double quant ≈ 0.516 bytes/param for linear weights, with embeddings kept fp16.
- ~0.8 GiB CUDA context.
- Parameter counts come from model cards and configs.

Treat ±30% as the uncertainty. Validate with `torch.cuda.max_memory_allocated()` in the smoke test. The usable T4 budget is ~15 GiB.

| Model | fp16 base weights | NF4 base weights | LoRA + optimizer | Activations | Logits, `chunked_nll` (≤) | Logits, `nll` path (≈) | **Total LoRA-fp16** | **Total QLoRA** |
|---|---|---|---|---|---|---|---|---|
| Qwen3.5-0.8B | 1.4 | 0.7 | 0.10 | 0.5 | 0.8 | 7.6 | **~3.6 GiB** | ~2.9 |
| Qwen3.5-2B | 3.5 | 1.6 | 0.25 | 0.9 | 0.8 | 7.6 | **~6.3 GiB** | ~4.4 |
| Qwen3-1.7B | 3.2 | 1.3 | 0.23 | 1.0 | 0.5 | 4.6 | **~5.7 GiB** | ~3.8 |
| Llama-3.2-3B | 6.0 | 2.1 | 0.43 | 1.5 | 0.4 | 3.9 | **~9.1 GiB** | ~5.2 |
| Phi-4-mini (3.8B) | 7.2 | 2.7 | 0.51 | 1.6 | 0.7 | 6.1 | **~10.7 GiB** | ~6.3 |
| Qwen3-4B-2507 | 7.5 | 2.5 | 0.54 | 1.4 | 0.5 | 4.6 | **~10.7 GiB** | ~5.7 |
| Qwen3.5-4B | 7.8 | 2.9 | 0.56 | 1.3 | 0.8 | 7.6 | **~11.3 GiB** | ~6.4 |

What the estimate shows:

- With the default `chunked_nll`, every candidate fits a T4 with plain LoRA. Qwen3.5-4B and Phi-4-mini are tight.
- **Without chunked loss** (the `nll` path), the full `[batch × seq × vocab]` logits dominate. That is 248K vocab for Qwen3.5 and 200K for Phi. Qwen3.5-2B rises to ~13 GiB and 4B-class models exceed 15 GiB.
- On the `nll` fallback, use per-device batch 1–2 with gradient accumulation 16–32.
- The Unsloth-reported LoRA VRAM for Qwen3.5 is 0.8B: 3 GB, 2B: 5 GB, 4B: 10 GB ([Unsloth](https://unsloth.ai/docs/models/qwen3.5/fine-tune)). That is consistent in magnitude.

### Q5. Unsloth: yes or no?

Facts (accessed 2026-09-26):

- It offers free Colab T4 notebooks for Qwen3.5 0.8B/2B/4B and Gemma 4. It claims "1.5x faster / 60% less" VRAM for Qwen3.5 (4B) ([README](https://github.com/unslothai/unsloth)).
- Core license is Apache-2.0. Unsloth Studio UI components are AGPL-3.0.
- It exports GGUF directly (`save_pretrained_gguf`).
- It advises against QLoRA for Qwen3.5.
- **The current PyPI wheel `unsloth 2026.9.11` pins `transformers<=5.5.0`, `trl<=0.24.0`, `datasets<4.4.0` and `torch<2.13.0`** (PyPI `requires_dist`). That excludes TRL 1.x, the `chunked_nll` default, the Qwen3.5 training templates and current Transformers.

Decision: **No, for the primary pipeline.**

- Keep the reference path on stock Transformers + PEFT + TRL, pinned in `ml/uv.lock`.
- An optional `ml/extras/unsloth` lock may be used for a *speed experiment* reported separately. It is not used for published numbers, because a second stack is a second source of truth.
- Revisit if Unsloth lifts its TRL pin (R-14).

### Q6. Checkpoint/resume under session limits

The relevant `TrainingArguments` options ([docs](https://huggingface.co/docs/transformers/main/en/main_classes/trainer), accessed 2026-09-26):

- **`hub_strategy="checkpoint"`**: "Like `"every_save"` plus push latest checkpoint to `"last-checkpoint"` subfolder for easy resuming". Pushes are async, so they do not block training.
- **`save_only_model`**: "prevents resuming training" (keep it `False`).
- **`save_total_limit`**: keeps "the best checkpoint… plus the most recent ones" when used with `load_best_model_at_end`.
- **`load_best_model_at_end`** requires matching save/eval strategies, and `save_steps` must be "a multiple of `eval_steps`".
- **`enable_jit_checkpoint`**: "Just-In-Time checkpointing on SIGTERM". Whether Kaggle or Colab send SIGTERM with a grace period is **UNVERIFIED**, so do not rely on it.
- `train(resume_from_checkpoint=str|True)` restores the model, optimizer, scheduler and RNG state.

### Q7. Qwen3.5-specific constraints

- Use `Qwen3_5ForCausalLM` "for text-only generation" ([Transformers Qwen3.5 docs](https://huggingface.co/docs/transformers/model_doc/qwen3_5)). It avoids loading the vision tower.
- Unsloth: "Please use `transformers v5` for Qwen3.5. Older versions will not work".
- The fast GDN kernels need `causal_conv1d` and `fla`; "without them, the model silently falls back to slower and more memory hungry PyTorch ops".
- The `fla` install docs list CUDA/ROCm/XPU/NPU/CPU backends but **do not state Turing (sm_75) support** ([fla INSTALL.md](https://github.com/fla-org/flash-linear-attention)). **UNVERIFIED**; the smoke test times both paths.

### Q8. Expected wall-clock (**estimate**)

Assumptions: ~900 tokens/example × 3,600 examples × 3 epochs ≈ 9.7M tokens. Training FLOPs ≈ 6 × N_non-embedding × tokens, with LoRA plus recompute from checkpointing. A T4 has 65 TFLOPS fp16 tensor peak, of which 15–25 TFLOPS effective is assumed.

| Model | Estimated time per seed |
|---|---|
| Qwen3.5-2B / Qwen3-1.7B | **0.9–1.5 h** |
| Llama-3.2-3B | 1.8–3.1 h |
| 4B-class | 2.3–3.9 h |

On top of that:

- a GDN torch-fallback penalty for Qwen3.5 if `fla` is unavailable (**UNVERIFIED**; could be 1.5–2×);
- a dequantization overhead if QLoRA is used (**UNVERIFIED**);
- evaluation time.

---

## DECISION / RECOMMENDATION

### 1. Method per base size

| Base size | Method | Why |
|---|---|---|
| ≤ 2B (Qwen3.5-0.8B/2B, Qwen3-1.7B) | **LoRA, fp16 base, fp16 AMP** | Fits (~4–6 GiB). Avoids NF4 merge mismatch and the TRL bf16 cast. Unsloth advises against QLoRA for Qwen3.5. |
| 3–4B (Llama-3.2-3B, Phi-4-mini, Qwen3-4B-2507, Qwen3.5-4B) | LoRA if the smoke test peaks at < 13 GiB, else **QLoRA NF4 + double quant, compute fp16** | Memory headroom |

### 2. Config (`ml/configs/sft_qwen35_2b.yaml`, loaded by pydantic; `config_sha` logged)

```yaml
base_model: Qwen/Qwen3.5-2B
base_revision: "<pin commit sha>"
model_class: Qwen3_5ForCausalLM        # AutoModelForCausalLM for pure-text bases
method: lora                           # lora | qlora
chat_template_kwargs: {enable_thinking: false}
lora:
  r: 16
  alpha: 32
  dropout: 0.05
  target_modules: [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj,
                   in_proj_qkv, in_proj_z, out_proj]   # never lm_head (chunked_nll)
train:
  max_length: 2048          # rows exceeding it are rejected at dataset build, never truncated
  epochs: 3
  per_device_batch: 4
  grad_accum: 8             # effective 32 -> ~113 steps/epoch, ~338 total
  lr: 2.0e-4
  scheduler: cosine
  warmup: 0.03              # float ratio (TrainingArguments v5)
  optim: adamw_torch        # paged_adamw_8bit when method=qlora
  eval_steps: 25
  save_steps: 25
  save_total_limit: 3
  early_stopping_patience: 4
  seeds: [42, 1337, 2026]
hub:
  checkpoint_repo: "<hf_user>/tw-triage-qwen35-2b-lora-s{seed}-ckpt"
  private: true
```

### 3. Training entry point (sketch for TRL 1.14 / Transformers 5.17 / PEFT 0.21; verify in the smoke test)

```python
# ml/src/tw_ml/train/sft.py (abridged)
import torch
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, EarlyStoppingCallback
from trl import SFTConfig, SFTTrainer

def build(cfg, train_ds, val_ds):
    tok = AutoTokenizer.from_pretrained(cfg.base_model, revision=cfg.base_revision)
    kw = dict(revision=cfg.base_revision, dtype=torch.float16, attn_implementation="sdpa")  # no FA2 on Turing
    if cfg.method == "qlora":
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
    model_cls = resolve_class(cfg.model_class)          # Qwen3_5ForCausalLM | AutoModelForCausalLM
    model = model_cls.from_pretrained(cfg.base_model, **kw)
    if cfg.method == "qlora":
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    args = SFTConfig(
        output_dir=cfg.output_dir, seed=cfg.seed, data_seed=cfg.seed,
        num_train_epochs=cfg.train.epochs, per_device_train_batch_size=cfg.train.per_device_batch,
        gradient_accumulation_steps=cfg.train.grad_accum, per_device_eval_batch_size=8,
        learning_rate=cfg.train.lr, lr_scheduler_type="cosine", warmup_steps=cfg.train.warmup,
        optim="paged_adamw_8bit" if cfg.method == "qlora" else "adamw_torch",
        fp16=True, bf16=False,                           # T4: never bf16
        gradient_checkpointing=True, max_length=cfg.train.max_length,
        packing=False, padding_free=False, completion_only_loss=True, loss_type="chunked_nll",
        eval_strategy="steps", eval_steps=25, save_strategy="steps", save_steps=25,
        save_total_limit=3, save_only_model=False,
        load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
        push_to_hub=True, hub_model_id=cfg.hub.checkpoint_repo.format(seed=cfg.seed),
        hub_strategy="checkpoint", hub_private_repo=True,
        logging_steps=5, report_to=["mlflow", "codecarbon"], run_name=cfg.run_name,
    )
    peft_cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                          task_type="CAUSAL_LM", target_modules=cfg.lora.target_modules)
    trainer = SFTTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
                         processing_class=tok, peft_config=peft_cfg,
                         callbacks=[EarlyStoppingCallback(early_stopping_patience=4)])
    # T4 guard: TRL >=0.26 casts trainable params of quantized models to bf16. Undo it before the
    # optimizer is created (created lazily in train()).
    for p in trainer.model.parameters():
        if p.requires_grad and p.dtype != torch.float32:
            p.data = p.data.float()
    return trainer
```

### 4. Dataset format (recommended)

**Option A: pre-tokenized, the most explicit.** In `tw_ml.train.data`:

```python
prompt_text = tok.apply_chat_template(msgs_system_user, add_generation_prompt=True,
                                      tokenize=False, enable_thinking=False)  # Qwen3.5-2B -> ends with "<think>\n\n</think>\n\n"
p_ids = tok(prompt_text, add_special_tokens=False).input_ids
c_ids = tok(target_json_minified + tok.eos_token, add_special_tokens=False).input_ids  # eos = <|im_end|>
assert len(p_ids) + len(c_ids) <= cfg.train.max_length    # reject; never truncate
row = {"input_ids": p_ids + c_ids, "labels": [-100]*len(p_ids) + c_ids}
```

- This tokenizes the prompt exactly as inference will (see `gguf-export-and-ollama.md`, raw prompts).
- The same `prompt_text` string is what the Ollama provider sends, which gives train/serve parity by construction.
- Choose deliberately whether to include the `\n` after `<|im_end|>`. Stopping happens on `<|im_end|>` at inference, so it is not needed.

**Option B: conversational prompt-completion rows** (`prompt=[system,user]`, `completion=[assistant]`, `chat_template_kwargs={"enable_thinking": false}`). TRL then applies completion-only loss by default. Treat its "Mismatch between tokenized prompt…" warning as a **hard failure** in the pipeline: grep the logs in CI or use Option A.

**Do not** use `assistant_only_loss` for Phi-4-mini, which has no bundled training template.

### 5. Evaluation during training

- `eval_loss` every 25 steps drives early stopping and the best-checkpoint pick.
- A callback runs **generation-based val macro-F1** (greedy, `max_new_tokens=512`, batch 16) at each epoch end, forces a save there, and logs to MLflow.
- The final checkpoint is the best val macro-F1 among the epoch-end checkpoints; ties go to the lower loss. Record the choice.

### 6. Session / resume protocol (Kaggle primary, Colab secondary)

- **Kaggle:** a GPU T4 ×2 notebook with Internet ON. `HF_TOKEN` comes from Kaggle Secrets (`kaggle_secrets.UserSecretsClient().get_secret("HF_TOKEN")`; never print it). Run via **Save & Run All** (background, ≤ 12 h). Run **two seeds concurrently**, one per GPU:
  ```bash
  CUDA_VISIBLE_DEVICES=0 python -m tw_ml.train --config ml/configs/sft_qwen35_2b.yaml --seed 42   > s42.log 2>&1 &
  CUDA_VISIBLE_DEVICES=1 python -m tw_ml.train --config ml/configs/sft_qwen35_2b.yaml --seed 1337 > s1337.log 2>&1 &
  wait
  ```
  This is deterministic per process and needs no DDP. The quota cost of T4×2 is **UNVERIFIED** (secondary sources say 2×).
- **Resume (idempotent start of every run):**
  ```python
  from huggingface_hub import snapshot_download
  try:
      ckpt_root = snapshot_download(repo_id, allow_patterns=["last-checkpoint/*"], token=hf_token)
      trainer.train(resume_from_checkpoint=f"{ckpt_root}/last-checkpoint")
  except Exception:                       # repo or folder absent -> fresh start (log which)
      trainer.train()
  ```
  Keep `ignore_data_skip=False` so data order is restored exactly.
- **Colab (free):** interactive only, with no background execution. It uses the same code path. Expect disconnects, and resume from HF.
- **MLflow:** use a file store under `/kaggle/working/mlruns`. Upload it as an artifact to the HF checkpoint repo (`mlruns/` folder) at the end and on every epoch-end callback. Log `config_sha`, git SHA, data manifest hashes, `torch.__version__`, `transformers`/`trl`/`peft`/`bitsandbytes` versions, `nvidia-smi` GPU name, and seed.

### 7. Environment install in the notebook (thin wrapper)

```bash
python -V  &&  python -c "import torch;print(torch.__version__, torch.cuda.get_device_name(0))"   # expect 2.11.x, Tesla T4
pip install --no-deps -e ./ml          # tw_ml package
pip install -r ml/requirements.lock.txt   # exported from ml/uv.lock WITHOUT torch/triton/nvidia-* (use the platform's)
python -m bitsandbytes                 # CUDA/bnb self-check (only if method=qlora)
```

### 8. Smoke test (per finalist, before any full run): `python -m tw_ml.train.smoke --config ... --steps 20`

It asserts:

1. **fp16 forward/backward** on 8 real training rows with no `inf`/`nan` in loss or grads (logits max-abs is logged).
2. **Trainable param dtypes** are all fp32 after init (catches the TRL bf16 cast).
3. **`loss_type="chunked_nll"`** constructs without error. If it errors, set `nll` and batch 2.
4. **Peak memory** `torch.cuda.max_memory_allocated()` < 13 GiB.
5. **s/step** is recorded, and projected time per seed is ≤ 2 h (2B) or ≤ 4 h (4B).
6. For Qwen3.5, it logs whether the `fla`/`causal_conv1d` fast path was used. Time both with and without the packages installed.
7. **Checkpoint push and resume round-trip**: save at step 10, kill, resume, and require an identical loss at step 11 (±1e-3).

---

## IMPLEMENTATION CHECKLIST

- [ ] `ml/pyproject.toml`: `requires-python = ">=3.12,<3.14"`. Pin trl==1.14.0, transformers==5.17.0, peft==0.21.0, accelerate==1.15.0, `datasets>=4.7.0` (TRL's requirement), bitsandbytes==0.50.2, `huggingface-hub<2`, mlflow and codecarbon. Leave torch unpinned in the notebook export and assert 2.11.x at runtime. These pins are exact as of 2026-09-26; re-verify at P3 (R-14).
- [ ] `tw_ml.train.data`: build Option A rows. Reject rows above `max_length`. Write the manifest hash.
- [ ] `tw_ml.train.sft`: the code above, plus an epoch-end generation-eval callback and the fp32 re-cast guard.
- [ ] `tw_ml.train.smoke`: the 7 assertions. Run on Kaggle T4 for every finalist.
- [ ] Kaggle notebook `ml/notebooks/train_kaggle.ipynb`: a thin wrapper with the install, smoke, two parallel seeds, then a third seed.
- [ ] HF private checkpoint repos per seed. Delete them or make them public only after the sanitization review (§9.5).
- [ ] Record the Kaggle quota and session limits observed in the UI (resolves the Q1 UNVERIFIED items). Update this doc to **Resolved**.

---

## OPEN RISKS / TO VERIFY AT BUILD TIME

1. `fla` / `causal-conv1d` on sm_75, and Qwen3.5 fp16 numerics. **UNVERIFIED**. Fallback: Qwen3-1.7B (see `slm-model-selection.md`).
2. Whether TRL's `chunked_nll` accepts our PEFT and model class. The docs and the code disagree. **UNVERIFIED**.
3. The effect of the TRL bf16 cast under fp16 AMP if QLoRA is used, and whether the fp32 re-cast fully fixes it. **UNVERIFIED**.
4. Kaggle quota, session length, T4×2 billing, `/kaggle/working` size, and SIGTERM grace behaviour. **UNVERIFIED** (secondary sources only).
5. Python 3.13 wheels for bitsandbytes and causal-conv1d on Colab. **UNVERIFIED**; install check in the smoke test.
6. SDPA kernel choice on Turing for head_dim 256 (Qwen3.5 full-attention layers). It may fall back to the math kernel, which is fine at seq ≤ 2k. Memory is covered by the smoke test.
7. Colab free GPU availability is not guaranteed (FAQ). Keep a rented A10/L4 fallback (§9.5). On L4/A10, switch to `bf16=True`, `fp16=False`.

---

## LINKED ADR

- **ADR-0012: Training stack.** Update it with the method-per-size table (SI-1), TRL 1.14 API notes (SI-2, SI-3), the Unsloth decision, and pins.
- ADR-0002 / ADR-0003 are touched by the ml Python range (SI-5).
- ADR-0013 (MLflow) is touched by the file-store-to-HF sync.

---

## SOURCES (all accessed 2026-09-26)

1. Google Colab backend-info (pip-freeze.gpu.txt, os-info-gpu.txt, commit history): https://github.com/googlecolab/backend-info
2. Kaggle docker-python (Dockerfile.tmpl, commits #1557 and #1560, kaggle_requirements.txt): https://github.com/Kaggle/docker-python
3. PyTorch RFC, CUDA support matrix for 2.11: https://github.com/pytorch/pytorch/issues/172663
4. PyTorch, `torch.cuda.is_bf16_supported`: https://docs.pytorch.org/docs/2.14/generated/torch.cuda.is_bf16_supported.html
5. roboflow/rf-detr issue #1535 (T4 bf16 emulation timings): https://github.com/roboflow/rf-detr/issues/1535
6. bitsandbytes releases: https://github.com/bitsandbytes-foundation/bitsandbytes/releases
7. Hugging Face Transformers, bitsandbytes quantization: https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes
8. Hugging Face TRL, SFT Trainer: https://huggingface.co/docs/trl/main/en/sft_trainer
9. Hugging Face TRL, Reducing Memory Usage: https://huggingface.co/docs/trl/main/en/reducing_memory_usage
10. Hugging Face TRL, Chat Templates: https://huggingface.co/docs/trl/main/en/chat_templates
11. TRL source `sft_trainer.py` (v1.14.0, main; tags v0.19.0/v0.20.0/v0.24.0/v0.26.0 for the collator and bf16-cast history): https://github.com/huggingface/trl
12. TRL releases: https://github.com/huggingface/trl/releases
13. Hugging Face Transformers, Trainer / TrainingArguments: https://huggingface.co/docs/transformers/main/en/main_classes/trainer
14. Hugging Face Transformers, Qwen3.5 docs (v5.17.0) and `modeling_qwen3_5.py`: https://huggingface.co/docs/transformers/model_doc/qwen3_5
15. Hugging Face PEFT, LoRA developer guide: https://huggingface.co/docs/peft/main/en/developer_guides/lora
16. PEFT `tuners_utils.py` (all-linear excludes the output layer): https://github.com/huggingface/peft/blob/main/src/peft/tuners/tuners_utils.py
17. flash-linear-attention (INSTALL.md): https://github.com/fla-org/flash-linear-attention
18. Unsloth, Qwen3.5 fine-tune guide: https://unsloth.ai/docs/models/qwen3.5/fine-tune
19. Unsloth, Gemma 4 training guide: https://unsloth.ai/docs/models/gemma-4/train
20. Unsloth README (features, license): https://github.com/unslothai/unsloth
21. PyPI JSON metadata (versions, dates, requires_dist) for torch, transformers, trl, peft, accelerate, datasets, bitsandbytes, huggingface-hub, unsloth: https://pypi.org
22. Google Colab FAQ: https://research.google.com/colaboratory/faq.html
23. Kaggle Notebooks docs (JS-rendered; content not retrievable): https://www.kaggle.com/docs/notebooks
24. LuminoAI, "Kaggle gave you 12 hours…" (secondary; 2026-03-27): https://www.luminoai.in/blog/kaggle-gave-you-12-hours-your-training-job-needed-more
25. Dettmers et al., "QLoRA: Efficient Finetuning of Quantized LLMs" (2023): https://arxiv.org/abs/2305.14314
