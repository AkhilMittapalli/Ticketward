# Ticketward evaluation analysis plan (pre-registration)

> **DRAFT v0.1 (2026-09-27). Not frozen.** Committed and hashed before the first P10 run (P10.25). Every report carries `analysis_plan_sha` = SHA-256 of this file with LF line endings (`tw_ml.eval.report.analysis_plan_sha`). The P10 report job fails if it is missing or changes after the first P10 run. Until the freeze, changes are allowed only with an entry in §16; none may be motivated by a sealed-split result (none has been evaluated).

Sources: spec v1.1 §9.3, §9.7, §9.8, §9.10, §16, A-10; ERPROT `evaluation-statistics`; ADR-0032. The spec wins on conflict, and this plan is amended before the freeze.

## 1. Purpose
Fix, before any sealed data is seen, what is measured, on which data, how uncertainty is quantified, which comparisons are confirmatory, and what happens when a gate is missed. This covers every number in `docs/benchmarks.md`, the model card and the dashboard.

## 2. Systems
| ID | System | Seeds | Identity |
|---|---|---|---|
| E1 | Rules baseline (`tw_ml.baselines.rules`) | deterministic | `tw-rules-baseline@rules_baseline.v<N>+<sha12>` |
| E2 | ModernBERT multi-head encoder | 42, 1337, 2026 | run id per seed |
| E3 | Base SLM zero-shot, constrained (unconstrained on val only) | T = 0 (determinism checked) | base + `triage.v1` + GGUF sha |
| E4 | LoRA/QLoRA SLM (method actually used is named) | 42, 1337, 2026 | `tw-triage-<base>-<method>@<semver>` |
| E5 | E4 + retrieval + policy engine | deployed seed | model version + `policy_version` |
| E6 | Frontier reference, 120-ticket subset, masked; never trains anything | cassettes | model id + date |
| A1-A4 | BM25 / vector / RRF / RRF + rerank | deterministic | retrieval config sha |

E1's decision is a "rules preview" (lexicons and rules intents only); its M-07 numbers are labelled "E1 (rules preview)", never E5.

## 3. Hypotheses (confirmatory family, test_synth, intent macro-F1 over 12 intents)
| ID | Hypothesis | Test | Alternative |
|---|---|---|---|
| H1 | E4 > E3 | paired approximate randomization, R = 10,000 | greater |
| H2 | E4 > E1 | same | greater |
| H3 | E4 vs E2 | same | two-sided |

- Holm at family-wise α = 0.05.
- E4 enters as the deployed seed. The test is repeated per seed and on the seed mean; a claim needs all three seeds to agree in direction.
- Acceptance: E4 − E3 ≥ +0.10 on the point estimate, with the paired stratified bootstrap CI. Superiority additionally needs Holm p < 0.05 and a CI lower bound > 0.
- If E2 ≥ E4, it is published.
- McNemar mid-p and the Δ-accuracy CI are secondary evidence.
- Everything else is descriptive.

## 4. Splits
| Split | n | Status | Uses | First touch |
|---|---|---|---|---|
| train | 3,600 | open | fitting | P1 |
| val | 450 | open | early stopping, τ, calibration, prompts, seeds, bake-off | P1 |
| val_dev | 225 | open | pipeline dev, verifier calibration, P6 citation gate | P1 |
| hard_dev | 30 | open | error analysis, P6 exit | P1 |
| qrels_dev | 170 | open | retrieval selection, τ_ret | P5 |
| test_synth | 1,045 | sealed | headline, once per registered version | P10 |
| hard_final | 70 | sealed | hard-set headline; never inspected before P10 | P10 |
| test_ood | 500 | sealed | separate OOD table | P10 |
| e2e_scenarios | 120 | sealed | E5, reviewer study | P10 |
| qrels_test | 170 | sealed | M-05 only | P10 |

- `tw_ml.eval.holdout` refuses sealed data without `--phase P10 --i-understand-sealed`, logs every sealed access to `evals/sealed_access.jsonl`, and publishes `eval_count_on_split`.
- Nightly runs use val (200-ticket sample) + hard_dev.
- Splits are never pooled.

## 5. Metrics
Primary (headline):
- M-01 intent macro-F1;
- M-03c pooled critical recall (E5);
- M-07a forced escalation;
- M-04 JSON validity.

Secondary:
- M-01 accuracy and the separate `other_unclear` F1/precision/recall;
- M-02;
- M-03 fields: priority exact and within-one, sentiment and churn macro-F1, product area, entity F1 with exact type and value;
- M-03c per class, model and system level;
- M-05, M-06 (auto and human), M-07b–d, M-08–M-13 as defined in spec §9.8.

## 6. Methods
- **Proportions:** Wilson 95%, Clopper-Pearson at k = 0 or n. M-07a also gets the one-sided exact 95% lower bound (0.05^(1/n) at n/n).
- **Macro-F1 type metrics:** percentile bootstrap, B = 10,000, `default_rng(2026)`, stratified by gold class.
- **Clustered metrics:** entity F1 resamples tickets; citation precision resamples drafts.
- **BCa check:** on test_synth only. If it differs from percentile by more than 0.01, both are reported (percentile is primary; NaN falls back to percentile).
- **Identical resamples:** records are sorted by `record_id`, so every system sees the same resample indices.
- **Paired comparisons:** stratified bootstrap Δ CI; approximate randomization with p = (1 + #extreme)/(1 + R); McNemar mid-p, with the exact p reported alongside.
- **Seeds:** every value, mean, SD (ddof 1) with its χ² CI, range, and the two-level bootstrap CI of the mean; the deployed seed's own value is labelled.
- **M-08:** ticket bootstrap of P50/P95. **M-10:** paired bootstrap of the ratio of means. **M-12:** ECE-10 with bootstrap CI, plus adaptive ECE, Brier, NLL and AURC.
- **Agreement:** Cohen's κ with an item-bootstrap CI, % agreement, prevalence, PABAK and Gwet's AC1; Fleiss' κ (item bootstrap) for three raters.

## 7. Multiple comparisons
- Only H1–H3 carry p-values in headline tables.
- Exploratory screens (per-class McNemar, ablations, descriptive `compare` runs) are labelled exploratory and use BH-FDR at 5%.
- No confirmatory hypothesis is added after the freeze.

## 8. Seeds and selection
- E2 and E4 use seeds 42, 1337 and 2026, each early-stopped on val.
- The deployed seed is the best val macro-F1 (ties go to the lower val loss). It is recorded before any sealed run and never picked on test.
- E3 runs twice on val to confirm determinism.
- All thresholds and calibrators are fitted on val only.

## 9. Gates (decisions, not tests)
§9.8 table:
- M-01: E4 ≥ 0.85 test / ≥ 0.70 hard_final.
- M-02: E5 ≥ 0.90 / ≥ 0.80.
- M-03: priority ≥ 0.80 and entity F1 ≥ 0.80.
- M-03c: E5 pooled ≥ 0.95 with each class ≥ 0.90; E4 each class ≥ 0.90; hard_final pooled ≥ 0.90.
- M-04: validity ≥ 0.995, first pass ≥ 0.98, repair ≤ 0.02.
- M-07a: = 1.00.
- M-07b: ≥ 0.90 / ≥ 0.85.
- M-07c: ≤ 0.15.
- M-07d: explicit = 1.00, indirect ≥ 0.90.
- M-12: ECE ≤ 0.08.

Phase gates: P3 validity ≥ 0.99 on val; P6 M-07a = 1.00 on smoke and hard_dev.

Gates are applied to the point estimate and published with CI, n and k (`tw_ml.eval.gates`). A miss whose CI covers the threshold is "inconclusive", but it still blocks promotion unless an ADR waives it.

## 10. Reviewer study (M-11)
- **Materials:** 40 e2e tickets (20 routine, 10 complex, 10 high-risk), excluding the demo tickets and hard_dev items.
- **Design:** fully crossed; the owner and 2 volunteers each review all 40. Pipeline outputs are frozen cassettes; order is seeded per reviewer; reviewers are blind to gold; 3 practice tickets are not analyzed.
- **Measures:** accept (edit ratio < 0.05), edit, reject, field overrides, time-to-decision.
- **Primary:** volunteers pooled (80 decisions), with ticket-cluster bootstrap CIs.
- **Secondary:** all three reviewers; per reviewer (Wilson, n = 40); Fleiss' κ; pairwise κ.
- Descriptive only (±0.15 per reviewer, ±0.11 pooled).

## 11. Citation audit (M-06 human)
- **Sample:** 250 shown sentences (population A, stratified by provider × doc_type) plus 50 verifier-removed sentences (B), shuffled blind.
- **Annotation:** 2 annotators after 10 calibration items; partially supported counts as not supported; disagreements adjudicated.
- **Precision:** consensus supported / 250, with a Wilson CI (lower bound reported).
- **Agreement:** κ with an item bootstrap, % agreement, prevalence, PABAK and AC1.
- Verifier-vs-human agreement over A ∪ B is descriptive. An LLM judge, if used, is reported separately and never trains anything.

## 12. Exclusions and missing data
- Exclusions: none. No test item is removed or relabelled after the freeze; a defect means a new split version and a full re-run.
- A missing prediction or invalid output is scored as wrong (`__invalid__`). System level scores the fallback labels the system actually applied.
- A decision-level item without a decision counts as not escalated.
- Classes absent from a split score 0 in macro-F1, and reports name them.

## 13. Failed gates: report, don't p-hack
- Every gate outcome is published with estimate, CI and n.
- A miss is reported as a miss, with error analysis on val and hard_dev only.
- After unsealing it is forbidden to:
  - change metrics, thresholds, splits, seeds, prompts or this plan;
  - re-run to pick a better run;
  - drop or relabel items;
  - fish in subgroups;
  - select seeds on test.
- A fix means a new model version and a new, counted sealed evaluation, published next to the failed one.
- A waiver needs an ADR.
- Losses to baselines are published.

## 14. Reporting
- Every number is `point [low, high]` (method, n, k).
- One `eval_report.v1` per experiment × split × system, carrying git SHA, manifest/gold/prediction hashes, `analysis_plan_sha`, B and seed.
- OOD is reported separately, with the caveat that it covers only 2 of the 5 critical classes. hard_final and M-11 carry small-n caveats.

## 15. Expected precision
- test_synth pooled critical recall (n ≈ 600, p = 0.95): ±0.017. Per class (n = 120): ±0.04.
- test_synth macro-F1: about ±0.02–0.025.
- hard_final (n = 70): about ±0.07–0.08.
- M-07a with zero misses: lower bound 0.995 at n = 600, 0.958 at n = 70.

## 16. Amendment log
| Version | Date | Change | Reason |
|---|---|---|---|
| v0.1 | 2026-09-27 | First draft (P2) | P2.24 |
