# Encoder Baseline (E2): ModernBERT-base vs DeBERTa-v3-base - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-27
**Last Updated**: 2026-09-27
**Status**: Open (stub; research not started)
**Owner phase**: P2 (E2 encoder on Kaggle, 3 seeds)
**Category**: ML / Baselines
**Linked ADR(s)**: ADR-0018 (encoder baseline ModernBERT-base, 3 seeds in v1.1); related ADR-0017 (confidence and calibration), ADR-0032 (evaluation statistics)
**Spec sections**: §9.5, §9.7 (E2), §9.8, §16 P2, §23

---

## EXECUTIVE SUMMARY

- This is a **stub**. It was created for the spec v1.1 topic list (A-26), and no research has been run yet.
- It collects the required questions and points to findings that other research notes have already recorded. Nothing here is new, and nothing has been re-verified.
- Run the full protocol before the P2 E2 runs. See [README.md](README.md) for the process and template.

---

## QUESTIONS (from spec §23)

1. ModernBERT-base or DeBERTa-v3-base for the E2 multi-head classifier? Compare tokenization, T4 memory and fp16 behaviour.
2. Which hyperparameters and class weighting?
3. How do we keep the 3-seed protocol at parity with E4?
4. How is E2 calibrated (`calibrated_softmax`)?

---

## KNOWN SO FAR (recorded in other research notes; not re-verified)

- **Calibration (Q4).** [confidence-calibration.md](confidence-calibration.md) records that the E2 encoder has a full softmax, so temperature scaling applies to it directly (`confidence_method="calibrated_softmax"`). It names sklearn `CalibratedClassifierCV(FrozenEstimator(clf), method="temperature")` (sklearn >= 1.8) as the method for the encoder baseline.
- **Seeds and comparison (Q3).** [evaluation-statistics.md](evaluation-statistics.md) records:
  - E2 should use 3 seeds, so the E2 vs E4 comparison is symmetric (its SI-3, applied in v1.1 via A-10).
  - "E4 vs E2" is one of three pre-registered confirmatory tests (Holm family) on test_synth.
  - Under the honesty rule, an E2 >= E4 result is published.
- **T4 precision (Q1).** [qlora-training-on-t4.md](qlora-training-on-t4.md) records these facts for the SLM trainer. They are **not yet checked for encoder fine-tuning**:
  - The T4 has no bf16 hardware, and emulated bf16 measured about 2× slower than fp16 on a Colab T4, so `fp16=True, bf16=False` must be set explicitly.
  - Kaggle and Colab runtime versions (Python and torch).
- **ModernBERT library support (Q1).** [embedding-model-choice.md](embedding-model-choice.md) and [hybrid-retrieval.md](hybrid-retrieval.md) record that ModernBERT-based embedding and reranker models need transformers >= 4.48, per their model cards. That was recorded for those derived models, not for ModernBERT-base itself.
- **DeBERTa-v3-base (context only).** [citation-verification.md](citation-verification.md) and [prompt-injection-defense.md](prompt-injection-defense.md) list fine-tuned DeBERTa-v3-base checkpoints (NLI, injection detection) with 512-token inputs. These are not the E2 candidate.
- **Not yet researched:** the tokenization comparison on our tickets, T4 memory per sequence length, hyperparameters, class weighting and multi-head design.

---

## FINDINGS

None yet. Research not started.

## DECISION / RECOMMENDATION

None yet. ADR-0018 currently names ModernBERT-base (3 seeds). This topic confirms or amends that choice.

## SPEC IMPACT

None yet.

## IMPLEMENTATION CHECKLIST

- [ ] Run ERPROT research for Q1–Q4 before the P2 E2 runs, from primary sources (model cards, library docs and release notes), with access dates.
- [ ] Record the chosen model, revision, hyperparameters and calibration method, and update this file's status.

## OPEN RISKS / TO VERIFY

- Everything above is inherited from other notes and must be re-checked for the encoder case (precision on T4, library versions).

## LINKED ADR

- **ADR-0018**: confirm or amend the encoder choice and record the training protocol.

## SOURCES

Pointers only. Primary sources, with access dates, are listed in the linked notes: [confidence-calibration.md](confidence-calibration.md), [evaluation-statistics.md](evaluation-statistics.md), [qlora-training-on-t4.md](qlora-training-on-t4.md), [embedding-model-choice.md](embedding-model-choice.md), [hybrid-retrieval.md](hybrid-retrieval.md), [citation-verification.md](citation-verification.md), [prompt-injection-defense.md](prompt-injection-defense.md).

---

**Document Version**: 0.1 (stub)
**Next Update**: Before the P2 E2 runs
