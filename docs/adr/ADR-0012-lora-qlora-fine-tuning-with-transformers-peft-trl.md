---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §6, §8, §9; spec §9.4, §9.5, §9.6, §21 R-03/R-21; research qlora-training-on-t4, gguf-export-and-ollama
informed: contributors; model card and resume readers (method-accuracy rule)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0012: LoRA (≤ 2B) or QLoRA (3–4B) SFT with Hugging Face Transformers, PEFT and TRL

> **Amended in spec v1.1 (2026-09-27; change record A-03).** The file was renamed from
> `ADR-0012-qlora-with-transformers-peft-trl.md`, because the decision no longer defaults to QLoRA.
> * **Method by base size:** **LoRA on an fp16 base** for ≤ 2B (the default path: Qwen3.5-2B, Qwen3-1.7B, 0.8B), and
>   **QLoRA** (4-bit NF4 + double quant, fp16 compute) for 3–4B. The brief allows "LoRA/QLoRA".
> * `target_modules="all-linear"` (covers Qwen3.5's Gated DeltaNet projections); `fp16=True, bf16=False` set
>   explicitly; `attn_implementation="sdpa"`.
> * TRL 1.x **prompt-completion data or pre-tokenized labels**. `DataCollatorForCompletionOnlyLM` was removed in
>   TRL 0.20. `max_length` is set explicitly, and over-length rows are rejected.
> * **Eval and checkpoint every 25 steps**, pushed to a private HF repo (`hub_strategy="checkpoint"`), with resume
>   from the Hub. Unsloth is not in the main pipeline. The platform torch is used (ADR-0002).
> * **Every claim names the method actually used** (model card, registry name, README, resume).

## Context and Problem Statement

The brief requires a "LoRA/QLoRA fine-tuned SLM" with "Hugging Face Transformers, PEFT, TRL" producing constrained
JSON labels (brief §6, §8, §9; BR-029, BR-030, BR-037). Training runs on Kaggle **T4 ×2** (two seeds in parallel, one
per GPU), or on Colab T4 (interactive, disconnect-prone). A rented A10/L4 is the fallback (§9.5). The T4 has 16 GB
and **no bf16**. Sessions end without warning (R-03). The dataset is 3,600 training examples, and three seeds are
reported.

v1.0 defaulted to QLoRA for every size. The ERPROT training research showed that for ≤ 2B bases an fp16 base fits in
about 4–6 GiB (estimate). It also showed that QLoRA on these sizes adds risk for no memory need: the NF4 merge
mismatch, TRL's bf16 cast of adapter weights (unsafe on T4), and Unsloth's advice against QLoRA for Qwen3.5.

Which fine-tuning method and toolchain should be used, and how is it reported?

## Decision Drivers

* Fits a T4: fp16 only, 16 GB, session limits, with checkpoint and resume.
* Numerical safety on T4 (explicit precision, fp32 trainable weights).
* Brief alignment and reviewer legibility (the code lives in the repo; notebooks are thin wrappers).
* Reproducibility: pinned configs (`config_sha`), manifest hashes, 3 seeds, MLflow.
* Honest reporting: the method used (LoRA vs QLoRA) is named everywhere.

## Considered Options

1. HF Transformers + PEFT + TRL: **LoRA fp16 for ≤ 2B, QLoRA NF4 for 3–4B** (chosen)
2. Full fine-tuning
3. Unsloth
4. Axolotl

## Decision Outcome

Chosen option: "Transformers + PEFT + TRL, with the method chosen by base size", because it keeps the canonical,
transparent stack the brief names. It also picks the lower-risk method for the ≤ 2B default and keeps QLoRA where
memory actually requires it.

| Setting | LoRA (≤ 2B) | QLoRA (3–4B) |
|---|---|---|
| Base | fp16, no quantization | 4-bit NF4 + double quant, fp16 compute; `prepare_model_for_kbit_training` |
| Optimizer | `adamw_torch` | `paged_adamw_8bit` |
| Adapter dtype | fp32 trainable weights | re-cast trainable adapter weights to fp32 after trainer init (TRL ≥ 0.26 casts them to bf16) |

Common settings:
* `fp16=True, bf16=False` set explicitly;
* `attn_implementation="sdpa"` (no FlashAttention-2 on Turing);
* LoRA r/alpha/dropout 16/32/0.05, `bias="none"`, `target_modules="all-linear"`;
* lr 2e-4 cosine with 3% warmup (set explicitly, since TRL's default lr is 2e-5);
* 3 epochs with early stopping on val loss (patience 4); the final checkpoint is chosen by generation-based val
  macro-F1;
* batch 4 × grad-accum 8;
* `max_length=2048` set explicitly (over-length rows rejected at dataset build; packing off);
* completion-only loss via prompt-completion data or pre-tokenized `input_ids`/`labels` (TRL's "Mismatch between
  tokenized prompt…" warning is a hard failure);
* gradient checkpointing on;
* `eval_steps = save_steps = 25`, `save_total_limit=3`, Hub push per seed, `resume_from_checkpoint` tried at start;
* seeds 42, 1337, 2026, with the **deployed seed chosen on val**.

**Pins to re-verify at P3 (research `qlora-training-on-t4`):** trl 1.14.0, transformers 5.17.0, peft 0.21.0,
accelerate 1.15.0, datasets ≥ 4.7.0, bitsandbytes 0.50.2 (QLoRA only), `huggingface-hub<2`, platform torch 2.11.
Also check whether `loss_type="chunked_nll"` constructs with the PEFT model (else `nll`).

**Smoke test per finalist** (`python -m tw_ml.train.smoke --config … --steps 20`) asserts:
* fp16 forward/backward with no inf/NaN on 8 real rows;
* trainable parameters are fp32;
* the loss type constructs;
* peak memory < 13 GiB;
* the projected time is ≤ 2 h per seed for 2B-class (≤ 4 h for 4B);
* the Qwen3.5 fast path usage is logged;
* a Hub push → kill → resume round trip gives the same next-step loss (±1e-3).

**Export:** merge on CPU in fp32. For QLoRA, merge into both the bf16 weights and the dequantized NF4 weights, and
keep whichever has the smaller val disagreement (verify). Then run the drift gate (ADR-0014).

### Consequences

* Good, because the ≤ 2B default avoids NF4 merge mismatch and bitsandbytes/CUDA fragility, and trains fast.
* Good, because the 25-step Hub checkpoints make preemption cheap (R-03), and the smoke test measures time instead
  of estimating it.
* Good, because the registry name (`tw-triage-<base>-lora|qlora`), model card, README and resume all name the method
  actually used (A-03).
* Bad, because there are two code paths (LoRA and QLoRA) to test. The config selects one, and the smoke test runs per
  finalist.
* Bad, because TRL/PEFT/Transformers churn, hence the pins re-verified at P3 (R-14).
* Neutral, because Unsloth stays out of the main pipeline (its wheel pins transformers ≤ 5.5.0 and trl ≤ 0.24.0). At
  most it is a separately locked speed experiment.

### Confirmation

* The smoke-test assertions above, per finalist, logged to MLflow.
* MLflow run logs params, `config_sha`, manifest hashes, git SHA, library versions, GPU name, seed and per-split
  metrics (§9.6).
* P3 exit: E4 − E3 ≥ +0.10 macro-F1 on val, and JSON validity ≥ 99% (phase gate; the P10 release target is 99.5%).
  P10: 3 seeds with per-seed values, mean ± SD and a two-level bootstrap CI (ADR-0032).
* `model_versions.training_method` and `deployed_seed` are recorded. The proposed `readme-claims` CI check
  (ADR-0005) compares the method in the README and resume bullet with `training_method`.
* Pydantic validation of `ml/configs/*.yaml`. `nbstripout` on notebooks (proposed). gitleaks repo-wide; `HF_TOKEN`
  never printed.

## Pros and Cons of the Options

### Transformers + PEFT + TRL, method by size (chosen)

* Good, because it is the brief-named, transparent, widely supported stack, and it uses the safest method per size.
* Bad, because there are two methods to maintain, plus API churn in TRL.

### Full fine-tuning

* Good, because it has the highest quality ceiling in principle.
* Bad, because optimizer state for 1.5–4B models does not fit a T4 without offload, artifacts are full-size, and
  there is overfitting risk with 3.6k examples.

### Unsloth

* Good, because it is often faster with lower memory, and T4-friendly.
* Bad, because it pins old transformers/trl versions, patches model internals, and advises against QLoRA for
  Qwen3.5. It is kept out of the main pipeline.

### Axolotl

* Good, because it is config-driven with many recipes.
* Bad, because it is another abstraction layer and dependency surface. Our configs are already Pydantic-validated
  YAML.

## More Information

* Spec (private): §9.4 (completion-only loss, deterministic templates), §9.5 (method table, parameters, smoke test,
  hardware plan, export), §9.6, §16 P3, §21 R-03, R-12, R-14, R-21. Change record A-03.
* Brief (private): §6, §8, §9. BR-008, BR-029, BR-030, BR-037, BR-041, BR-059.
* Research: [qlora-training-on-t4](../research/qlora-training-on-t4.md),
  [gguf-export-and-ollama](../research/gguf-export-and-ollama.md).
* Related ADRs: ADR-0002, ADR-0003, ADR-0011, ADR-0013, ADR-0014, ADR-0005 (method-accurate resume bullet).
* Revisit when: a larger GPU budget exists, or TRL/PEFT changes break the pinned recipe.
* Status history: 2026-09-26 Accepted (P0, as "QLoRA SFT"). 2026-09-27 amended for spec v1.1 (LoRA ≤ 2B / QLoRA
  3–4B, T4 settings, 25-step checkpoints, method-accuracy rule); file renamed.
