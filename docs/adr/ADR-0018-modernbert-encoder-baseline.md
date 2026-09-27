---
status: Proposed
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §9.5 (encoder baseline), §9.7 (E2, honesty rule), §9.8, §21 R-02/R-03; research encoder-baseline, evaluation-statistics
informed: reviewers reading docs/benchmarks.md
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0018: ModernBERT-base as the encoder baseline (E2)

> **Amended in spec v1.1 (2026-09-27; change record A-10, A-26). Status stays *Proposed*.**
> * **E2 runs 3 seeds** (42, 1337, 2026), like E4, so the E2 vs E4 comparison is symmetric (A-10). H3 (E4 vs E2) is
>   part of the Holm-corrected confirmatory family (ADR-0032).
> * The research topic this ADR lacked now exists: **`encoder-baseline`** (A-26). It covers ModernBERT-base vs
>   DeBERTa-v3-base (tokenization, T4 memory, fp16), hyperparameters, class weighting, 3-seed parity, and
>   `calibrated_softmax`.
> * Why still Proposed: spec v1.1 keeps the conditional ("ModernBERT-base, or DeBERTa-v3-base if ModernBERT
>   tokenization issues arise", §9.5), and the new research topic has not yet been resolved.

## Context and Problem Statement

A fine-tuned encoder classifier is the strongest cheap baseline for label prediction. Without one, the claim that the
fine-tuned SLM is the "smallest reliable model" for triage is untested. E2 is a multi-head classifier (intent,
priority, sentiment, churn, product_area, queue) next to E1 rules, E3 zero-shot, E4 LoRA/QLoRA and E5 full pipeline.
The **honesty rule** applies: if E2 beats E4 on classification, it is published and discussed. E4 still provides
entities, rationale and JSON fields in one pass (§9.7, R-02).

Recipe (spec §9.5):
* lr 3e-5, batch 32, 5 epochs, max_len 512, warmup 6%, weight decay 0.01;
* early stop on val macro-F1;
* fp16 on T4;
* inverse-sqrt class weights;
* 3 seeds.

Which encoder should serve as E2, and what must be checked before committing to it?

## Decision Drivers

* Classification quality on 13 labels plus the other heads at about 3.6k examples.
* Tokenization fitness for support text: error codes (`SAML-ERR-302`, `HTTP 429`), `acct_` ids, and masked
  placeholders (`<EMAIL_1>`, `<PERSON_1>`).
* Trainability on a Kaggle/Colab T4 in fp16 (no bf16, no FlashAttention-2 on Turing).
* A fair comparison with E4: same splits and statistics protocol, 3 seeds, a published truncation rate.
* A permissive licence.

## Considered Options

1. ModernBERT-base (proposed)
2. DeBERTa-v3-base (the spec's named fallback)
3. SetFit

## Decision Outcome

**Proposed:** "ModernBERT-base", pending the research topic and the checks below. If either check fails,
DeBERTa-v3-base is used, and this ADR is updated before any E2 result is published.

**Evidence required to move to Accepted:**
1. Research `encoder-baseline` is resolved (ModernBERT vs DeBERTa: tokenization, T4 memory, fp16, hyperparameters,
   calibration).
2. **Tokenization check** (proposed `ml/src/tw_ml/eval/tokenization_check.py`): on a 500-ticket train sample, report
   how error codes, `acct_` ids and placeholders split (no pathological fragmentation; placeholders stable), and the
   share truncated at 512 tokens.
3. **T4 smoke run:** one epoch on 10% of train in fp16 with SDPA/eager attention, with no NaN/inf. The Transformers
   version is recorded (ModernBERT needs a recent release; verify).
4. **Licences verified:** ModernBERT-base (believed Apache-2.0) and DeBERTa-v3-base (believed MIT).
5. E2 is reproduced over 3 seeds from `make eval-baselines`, with per-seed values and CIs (ADR-0032).

### Consequences

* Good, because it gives an honest, strong and cheap baseline that is symmetric with E4. If E2 wins on labels, that
  is reported as a finding.
* Good, because the encoder's `calibrated_softmax` gives a calibrated comparison point for ADR-0017.
* Bad, because the comparison is asymmetric by input length: E2 sees ≤ 512 tokens, while E4 sees up to 6,000
  (§6.1). The truncation rate is reported next to the metrics. A longer-max_len sensitivity run is optional.
* Bad, because ModernBERT depends on fairly recent Transformers, hence pinning in `ml/uv.lock` and the P2 check.
* Neutral, because E2 is not in the product path in v1. `encoder_baseline` exists in `ModelMeta` for completeness.

### Confirmation

* `make eval-baselines` produces E2 metrics (M-01, M-03, M-03c) on test_synth, `hard_final` (at P10) and test_ood,
  with Wilson/bootstrap CIs and the truncation rate.
* `ml/configs/encoder_modernbert.yaml` is Pydantic-validated, and `config_sha` is logged in MLflow.
* H3 (E4 vs E2) paired comparison inside the Holm family, per `evals/ANALYSIS_PLAN.md` (ADR-0032).
* The honesty-rule check at P10: `docs/benchmarks.md` states which system wins per metric.

## Pros and Cons of the Options

### ModernBERT-base

* Good, because it is a modern encoder with efficient attention and long native context, and strong classification
  for its size.
* Bad, because its tokenizer is new to this domain (hence the check), it needs recent Transformers, and its T4
  attention path must be confirmed.

### DeBERTa-v3-base

* Good, because it is a long-standing strong classification baseline with a permissive licence (verify).
* Bad, because it is slower, limited to about 512 positions, and has reported fp16 instability in some setups. That
  matters on T4, and is checked in the smoke run if it becomes the fallback.

### SetFit

* Good, because it is very cheap and works well with few labels.
* Bad, because it is weaker at our data size with multi-head outputs, and would flatter E4 as a "strong baseline".

## More Information

* Spec (private): §6.2 (`encoder_baseline`, `calibrated_softmax`), §9.5 (recipe, 3 seeds), §9.7 (E2, honesty rule),
  §9.8, §16 P2, §21 R-02, R-03. Change record A-10, A-26.
* Research: [encoder-baseline](../research/encoder-baseline.md),
  [evaluation-statistics](../research/evaluation-statistics.md).
* Related ADRs: ADR-0011, ADR-0012, ADR-0016, ADR-0017, ADR-0032.
* Revisit when: the research topic and checks are in (flip to Accepted, or switch to DeBERTa-v3-base), or E2 is
  promoted into the product path.
* Status history: 2026-09-26 Proposed (pending the tokenization check). 2026-09-27 amended for spec v1.1 (3 seeds,
  `encoder-baseline` research topic); still Proposed.
