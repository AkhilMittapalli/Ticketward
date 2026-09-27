# Evaluation Statistics - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-26
**Status**: Resolved (methods, protocols, gate interpretation and code chosen; `evals/ANALYSIS_PLAN.md` must be committed before the P10 runs)
**Category**: ML Evaluation
**Linked ADR(s)**: ADR-new "Evaluation statistics protocol" (proposed; number assigned at merge); ADR-0016 (test set design; hard-set dev/final split)
**Spec sections**: §9.5 (seeds), §9.7 (E1–E6), §9.8 (protocol, M-01…M-13, 1,000-resample bootstrap), §8.9 (citation audit + κ), §16 (v0.2 iteration, P10), §20 L-06/L-12, §23

---

## EXECUTIVE SUMMARY

1. **Proportions use Wilson score intervals, not the bootstrap.** This covers accuracy, per-class recall, JSON validity, escalation/abstention rates, M-11 rates and citation precision.
   - Call: `scipy.stats.binomtest(k, n).proportion_ci(method="wilson")`. Use Clopper–Pearson (`method="exact"`) when k = 0 or k = n.
   - Brown, Cai & DasGupta (2001) recommend Wilson (or Jeffreys) for small n. Percentile bootstrap intervals collapse to [1, 1] when every item is correct.
   - For M-07a = 1.00 on n items, publish the one-sided exact lower bound 0.05^(1/n) ≈ 1 − 3/n (the "rule of three"; n=385 gives ≥ 0.992).
2. **Non-decomposable metrics use a stratified nonparametric bootstrap over tickets** (strata = gold class), with **B = 10,000** and a percentile CI. This covers macro-F1, sentiment/churn macro-F1, entity F1 and ECE.
   - Stratification matches how the test sets were built (fixed per-intent quotas), and it stops resamples from dropping small classes.
   - BCa (SciPy's default method) is a sensitivity check on test_synth. SciPy returns NaN for BCa when the bootstrap distribution is degenerate.
   - Illustrative widths: macro-F1 ±0.025–0.03 at n=720; ±0.06–0.08 at n≈100.
   - The spec's 1,000 resamples add avoidable Monte-Carlo error; resampling costs seconds.
3. **E3 vs E4 is a paired comparison.**
   - McNemar **mid-p** on per-ticket intent correctness (Fagerland et al., 2013).
   - A paired stratified bootstrap CI for Δmacro-F1.
   - A paired approximate-randomization p-value (`scipy.stats.permutation_test`, `permutation_type="samples"`).
   - Acceptance is "Δ̂ ≥ +0.10" on the point estimate (spec), always published with the CI. A *superiority* claim requires the CI to exclude 0.
4. **Multi-seed (42/1337/2026) reporting.**
   - Report every seed's value, mean ± SD and range.
   - **Three seeds pin down the SD only weakly:** the 95% CI for σ runs from 0.52× to 6.29× the sample SD.
   - A two-level bootstrap (resample items; average the seeds) gives the CI of the seed-mean.
   - The deployed seed is chosen on **val**, never on test.
5. **Reviewer study (M-11).**
   - Fully crossed: owner + 2 volunteers review the **same 40** tickets from e2e_scenarios (20 routine / 10 complex / 10 high-risk). Order is randomized; reviewers are blind to gold; pipeline outputs are frozen.
   - The **volunteers-only** estimate is primary (L-12); owner-inclusive is secondary.
   - Per-rater Wilson CIs, a ticket-cluster bootstrap for pooled rates, and Fleiss' κ across the 3 raters.
   - It is descriptive: ±15 points per rater and about ±11 points pooled over the volunteers.
6. **Citation audit agreement (§8.9).**
   - Two annotators label all sampled sentences. Report Cohen's κ with a bootstrap CI, alongside % agreement, prevalence, **PABAK** and **Gwet's AC1**. A high "supported" prevalence triggers the kappa paradox (Feinstein & Cicchetti, 1990).
   - **Verifier-vs-human κ is undefined if only verifier-passed sentences are sampled.** Add about 50 verifier-removed sentences.
   - n=150 at p̂=0.90 gives Wilson [0.842, 0.938], so the ≥ 0.85 target holds only on the point estimate. n=250 would put the lower bound at 0.857.
7. **Multiple comparisons and adaptivity.**
   - Pre-register three confirmatory tests (E4>E3, E4>E1, E4 vs E2 on test_synth) with **Holm** correction. Everything else is descriptive; exploratory per-class screens use BH-FDR.
   - The spec's v0.2 plan (hard-set error analysis → new train data) turns test_hard into a development set (Dwork et al., 2015). **Split it into test_hard_dev (30) and test_hard_final (70), or write a new hard set before the final numbers.**
8. **Gate volatility.** Take the case where each critical class has a true recall of exactly 0.95 and n=60 per class. The "E5 each ≥ 0.95" gate then passes for all 5 classes only **11%** of the time (57% at true 0.97).
   - With ~5 items per critical class in test_hard, per-class gates carry almost no information: 5/5 has a Wilson lower bound of 0.57.
   - Recommendation: pooled critical-recall gates plus per-class CIs, or larger critical strata (Spec impact).

---

## QUESTIONS

| # | Question | Source |
|---|---|---|
| Q1 | How are CIs computed: bootstrap percentile vs BCa, and proportions? | §23, §9.8 |
| Q2 | How are E3 and E4 compared (McNemar, paired bootstrap)? And E4 vs E1/E2, E5 vs E6? | §23 |
| Q3 | How are multiple seeds reported? | §23, §9.5 |
| Q4 | How is the macro-F1 CI computed specifically? | task |
| Q5 | How is the small-n reviewer study (M-11) designed? | §23 |
| Q6 | How is inter-annotator agreement measured for the citation audit (Cohen's/Fleiss' κ)? | §8.9, task |
| Q7 | What are the multiple-comparison and adaptivity caveats? | task |
| Q8 | (Implementer) What do the acceptance gates mean statistically at our n? | §9.8 |
| Q9 | (Implementer) Code sketch and report schema. | task |

---

## FINDINGS

Sources accessed 2026-09-26, except the classic statistics references at the end of Sources, which are cited bibliographically and were not re-fetched.

### F1. Library APIs, current stable docs (Q1, Q2, Q6, Q9)

| API | Version seen | Key facts |
|---|---|---|
| `scipy.stats.bootstrap` [S1] | SciPy 1.18.0 | Defaults `n_resamples=9999`, `method='BCa'` (also `'percentile'`, `'basic'`). `paired=True` resamples one index array shared by all inputs. `vectorized`, `batch`, `confidence_level`. Returns `confidence_interval` (low/high), `bootstrap_distribution` and `standard_error`. BCa bounds can be **NaN** when the bootstrap distribution is degenerate, with a `DegenerateDataWarning`. **`random_state` became `rng` in 1.15.0**; use `rng` |
| `scipy.stats.permutation_test` [S2] | 1.18.0 | `permutation_type` ∈ {`independent`, `samples`, `pairings`}. `'samples'` randomly swaps paired observations between samples. The p-value adds one to numerator and denominator, and ties within 100×eps count as extreme. Returns `statistic`, `pvalue`, `null_distribution` |
| `scipy.stats.binomtest(...).proportion_ci` [S3] | 1.18.0 | `method` ∈ {`'exact'` = Clopper–Pearson, `'wilson'`, `'wilsoncc'`} |
| `scipy.stats.false_discovery_control` [S4] | 1.18.0 | `method` ∈ {`'bh'`, `'by'`}; returns adjusted p-values |
| `statsmodels...mcnemar(table, exact=True, correction=True)` [S5] | statsmodels 0.15.0 | `exact=True` uses the binomial distribution on the discordant cells. `correction` applies only to the chi-square version |
| `statsmodels...fleiss_kappa(table, method='fleiss')` + `aggregate_raters` [S6] | 0.15.0 | The table is subjects × category counts. **No variance or hypothesis test is provided**, so bootstrap it |
| `statsmodels...multipletests` [S7] | 0.15.0 | Methods include `'holm'`, `'fdr_bh'`, `'bonferroni'`; returns (reject, pvals_corrected, …) |
| `sklearn.metrics.cohen_kappa_score` [S8] | scikit-learn 1.9.1 | `labels`, `weights` ∈ {None, 'linear', 'quadratic'}, `sample_weight`, `replace_undefined_by=nan`; two annotators; symmetric |
| `sklearn.metrics.f1_score` [S9] | 1.9.1 | `labels=` can exclude classes present in the data (for example `other_unclear`) or include absent ones (scored 0). `zero_division` ∈ {"warn", 0.0, 1.0, np.nan} |
| `krippendorff` (PyPI) [S23] | 0.8.2 | **GPL-3.0-or-later**. Keep it out of the Apache-2.0 repo's dependencies, or implement α in-house if α is ever needed |

### F2. Intervals for proportions (Q1)

- **Brown, Cai & DasGupta** (Statistical Science 16(2), 2001) [S17]: the Wald interval's coverage is erratic. They recommend Wilson or equal-tailed Jeffreys for small n, and Agresti–Coull for larger n. Clopper–Pearson is conservative.
- **Rule of three** (Hanley & Lippman-Hand, JAMA 1983) [S18]: with 0 events in n trials, the 95% upper bound on the event rate is about 3/n. Our exact one-sided bound 1 − 0.05^(1/n) matches it: n=60 → 0.9513, n=250 → 0.9881, n=385 → 0.9922.

Computed this session (same formulas as the D10 code):

| k/n | Wilson 95% | Clopper–Pearson 95% | Where it arises |
|---|---|---|---|
| 57/60 = 0.950 | [0.863, 0.983] | [0.861, 0.990] | Critical class in test_synth |
| 60/60 = 1.000 | [0.940, 1.000] | [0.940, 1.000] | – |
| 5/5 | [0.566, 1.000] | [0.478, 1.000] | Critical class in test_hard (~5 each) |
| 4/5 | [0.376, 0.964] | [0.284, 0.995] | One miss in test_hard |
| 24/25 | [0.805, 0.993] | [0.796, 0.999] | Pooled critical in test_hard |
| 90/100 | [0.826, 0.945] | [0.824, 0.951] | test_hard accuracy |
| 612/720 = 0.85 | [0.822, 0.874] | – | test_synth accuracy |

### F3. Bootstrap: percentile vs BCa, stratification, B (Q1, Q4)

- **Methods.** BCa corrects for bias and skewness and is second-order accurate (Efron, 1987). The percentile method is first-order.
  - For a smooth statistic at n=720, the two are expected to agree closely. This has not been measured on our data yet; the D2 check verifies it.
  - At n≈100 with 12 classes of about 8 items each, BCa's jackknife acceleration estimate can be unstable.
  - Either method degenerates for a proportion at 0 or 1, which is why F2 applies there.
- **Stratification.** test_synth, test_hard and test_ood are built with *fixed* per-class quotas. Resampling within each gold class mirrors that design. It also guarantees every class is present in every resample, which avoids spurious 0/0 per-class F1 values that would drag macro-F1 down under `zero_division=0`.
- **Illustrative widths.** Simulated this session: 12 classes, uniform error spread, 2,000 stratified resamples.

  | n | Accuracy | Macro-F1 | 95% CI | Half-width |
  |---|---|---|---|---|
  | 720 (60/class) | 0.85 | 0.850 | [0.825, 0.876] | ±0.025 |
  | 720 | 0.75 | 0.759 | [0.725, 0.790] | ±0.032 |
  | 96 (8/class) | 0.85 | 0.896 | [0.831, 0.948] | ±0.059 |
  | 96 | 0.70 | 0.811 | [0.727, 0.886] | ±0.080 |

  The noisy point estimate in the n=96 rows is itself the lesson: small hard sets are imprecise.
- **B.** Monte-Carlo error in the 2.5%/97.5% endpoints shrinks as B grows. SciPy defaults to 9,999. With vectorized macro-F1 (D10), B=10,000 at n=720 takes about a second, so there is no reason to stop at 1,000.

### F4. Paired tests (Q2)

- **McNemar for one shared test set.** Dietterich (Neural Computation, 1998) recommends McNemar's test when two classifiers are compared on a single test set; it has an acceptable type-I error [classic ref].
- **Mid-p.** Fagerland, Lydersen & Laake (BMC Med Res Methodol 13:91, 2013) [S10] found the **mid-p McNemar test** performs well against the asymptotic tests (with and without continuity correction) and the exact conditional test, and almost as well as the far more complex exact unconditional test. The exact conditional test is conservative.
- **Illustrative McNemar results** (computed; b = E4-only-correct, c = E3-only-correct):

  | b | c | Exact p | Mid-p | Asymptotic p | Comment |
  |---|---|---|---|---|---|
  | 18 | 8 | 0.0755 | 0.0522 | 0.0499 | A 10-point accuracy gap on n=100 may not reach 0.05 |
  | 22 | 8 | 0.0161 | 0.0107 | – | – |
  | 60 | 40 | 0.0569 | 0.0460 | – | – |
  | 130 | 22 | < 1e-4 | – | – | A test_synth-sized E3→E4 gain is decisive |

- **Paired bootstrap** for metric differences: the same resampled indices for both systems (Koehn, 2004). Berg-Kirkpatrick et al. (EMNLP-CoNLL 2012) studied its use empirically in NLP [S12].
- **Approximate randomization** (swap each item's pair of predictions with probability ½) is the standard permutation analog for non-decomposable metrics such as F1.
- **Test choice.** Dror et al. (ACL 2018) give a protocol for choosing a significance test by metric and design, and document frequent misuse [S11].

### F5. Seed variance and few-run reporting (Q3)

- **Dodge et al.** (2020) [S15]: in BERT fine-tuning, weight initialization and data order contribute comparably to the variance of out-of-sample performance. Seed choice alone therefore moves results, which is why several seeds are needed.
- **Bouthillier et al.** (MLSys 2021) [S14]: data sampling, initialization and hyperparameter choice all move benchmark results materially. Randomizing multiple sources of variation gives more reliable comparisons.
- **Agarwal et al.** (NeurIPS 2021) [S16]: with few runs, report interval estimates (stratified bootstrap CIs) and robust aggregates rather than point estimates.
- **The SD of three values is itself very uncertain.** Under normality the 95% CI for σ is [s·√(2/χ²₀.₉₇₅,₂), s·√(2/χ²₀.₀₂₅,₂)] = **[0.521 s, 6.285 s]** (χ²₀.₀₂₅,₂ = 0.0506; χ²₀.₉₇₅,₂ = 7.378; computed).

### F6. Power and sample size (Q8)

- **Card et al.** (EMNLP 2020) [S13]: underpowered comparisons are common in NLP; many test sets cannot detect realistic improvements.
- **What our sets can resolve:**
  - test_synth (n=720) resolves differences of a few points.
  - test_hard (n=100) reliably resolves only large differences (≈ 10+ points; see the McNemar table).
  - test_ood strict classes (n=80 each) give recall CIs of about ±0.07.

### F7. Agreement statistics (Q5, Q6)

- **Coefficients.** Cohen's κ is for two raters. Fleiss' κ is for ≥ 3 raters on nominal categories; statsmodels provides no variance, so use an item bootstrap.
- **The two kappa paradoxes** (Feinstein & Cicchetti, J Clin Epidemiol 43, 1990) [S19]:
  1. high raw agreement can coexist with low κ when the marginals are imbalanced (high prevalence);
  2. κ behaves counter-intuitively under asymmetric imbalance.

  Citation "supported" rates near 0.9 are exactly this regime.
- **Remedies.** Report p_o and the prevalence alongside κ, plus a prevalence-robust coefficient: PABAK = 2·p_o − 1 (Byrt, Bishop & Carlin, 1993) [classic ref], or Gwet's AC1 (Br J Math Stat Psychol 61(1), 2008) [S20], whose chance agreement for 2 categories is p_e = 2π(1−π).
- **Interpretation.** Landis & Koch (1977) give the conventional bands (0.61–0.80 "substantial", 0.81–1.00 "almost perfect"). They are conventions, not standards [classic ref].

### F8. Multiple comparisons and holdout reuse (Q7)

- **Corrections.** Holm (1979) controls the family-wise error rate with more power than Bonferroni. Benjamini–Hochberg (1995) controls the FDR [classic refs]. Both are available: `multipletests(..., method="holm")` [S7] and `scipy.stats.false_discovery_control(..., method="bh")` [S4].
- **Adaptive reuse.** Dwork et al. (Science 349:636, 2015) [S21] show that reusing a holdout adaptively invalidates its estimates unless reuse is controlled.
  - Using test_hard failures to write v0.2 training data is adaptive reuse, even with no textual overlap.
  - Test-label errors (≥ 3.3% on average across benchmarks; Northcutt et al., 2021 [S22]) interact with this: tuning to a noisy test set chases its errors.

### F9. Gate volatility (Q8), computed

The probability that the observed recall clears the gate, for one class and for all 5 critical classes at once:

| True recall (each class) | n per class | Gate | P(one class passes) | P(all 5 pass) |
|---|---|---|---|---|
| 0.95 | 60 | ≥ 57/60 | 0.647 | **0.114** |
| 0.96 | 60 | ≥ 57/60 | 0.781 | 0.291 |
| 0.97 | 60 | ≥ 57/60 | 0.894 | 0.572 |
| 0.98 | 60 | ≥ 57/60 | 0.968 | 0.849 |
| 0.96 | 55 | ≥ 53/55 | 0.622 | 0.093 |

A system that exactly meets the requirement in truth fails the spec's 5-class point gate most of the time. **A gate miss at this n is weak evidence of a real shortfall, and a pass is weak evidence of compliance.**

---

## DECISION / RECOMMENDATION

### D1. Metric → estimator → interval → comparison

| Metric | Estimator | 95% CI | Paired comparison |
|---|---|---|---|
| M-01 intent macro-F1 (12; `other_unclear` excluded via `labels=`) | sklearn-equivalent macro-F1 | Stratified percentile bootstrap, B=10,000; BCa check on test_synth | Paired stratified bootstrap Δ + approximate randomization p |
| M-01 aux: intent accuracy | k/n | Wilson | McNemar mid-p |
| M-02 routing accuracy | k/n | Wilson | McNemar mid-p |
| M-03 priority accuracy, within-one | k/n | Wilson | McNemar mid-p |
| M-03 sentiment/churn macro-F1 | macro-F1 | Stratified (by gold sentiment/churn) bootstrap | Paired bootstrap |
| M-03 entity F1 (exact type+value) | micro-F1 over entities | **Ticket-cluster** bootstrap (entities within a ticket are correlated) | Paired cluster bootstrap |
| M-03c per-class recall (5 critical) | k/n per class | Wilson (exact at 0/n, n/n) | McNemar mid-p per class, Holm over 5 (exploratory) |
| M-04 validity / repair | k/n | Wilson (exact at extremes) | – |
| M-05 Recall@k | k/n over queries | Wilson | Paired bootstrap across ablations A1–A4 |
| M-05 MRR@10, nDCG@10 | per-query mean | Query bootstrap | Paired query bootstrap |
| M-06 citation precision (auto) | supported / cited sentences | **Draft-cluster** bootstrap | – |
| M-06 citation precision (human) | consensus supported / audited | Wilson (D6) | κ (D6) |
| M-07a forced escalation | k/n (must be n/n) | One-sided exact lower bound 0.05^(1/n) | – |
| M-07b/c/d | k/n | Wilson | McNemar mid-p (E5 variants) |
| M-08 latency P50/P95 | Sample quantiles | Percentile bootstrap over tickets (the P95 CI at n=200 is wide; report it) | – |
| M-09/M-10 cost per ticket | Mean | Bootstrap (skewed distribution) | E5/E6 ratio of means: paired bootstrap on the 120-ticket subset |
| M-11 accept/edit/reject/override | Proportions | Per-rater Wilson; pooled ticket-cluster bootstrap (D5) | – (descriptive) |
| M-12 ECE (10-bin) | ECE | Bootstrap (note the upward bias at small n; see confidence-calibration.md) | – |
| M-13 injection | k/n | Wilson (exact at n/n) | – |

- **Rules.** Metrics are reported per split (test_synth, test_hard_final, test_ood) and **never pooled across splits**.
- **Report format.** Every number is published as point [low, high] (method, n, k). The number of evaluations of each protected split is logged in `eval_runs`.

### D2. Bootstrap protocol (Q1, Q4)

- **Resampling:** `B = 10_000`; `numpy.random.default_rng(2026)`, with the seed recorded in the report. Resample **within gold-class strata** for macro-F1-type metrics; resample **clusters** (tickets, drafts) for multi-unit metrics; use the **same indices** for every system in a comparison.
- **Interval:** percentile (2.5%, 97.5%). On test_synth also compute BCa with `scipy.stats.bootstrap(..., paired=True, method="BCa")`. If the two differ by more than 0.01, report both and investigate. If BCa is NaN, fall back to percentile.
- **Seeds:** the two-level bootstrap in D4.

### D3. Paired comparison protocol (Q2)

| Comparison | Split(s) | Primary | Secondary | Claim rule |
|---|---|---|---|---|
| **E4 vs E3** (brief, BR-040/041) | test_synth; also test_hard_final and test_ood (descriptive) | Δmacro-F1 with paired stratified bootstrap CI + approximate-randomization p (one-sided, H1: E4 > E3) | McNemar mid-p on intent correctness | **Acceptance** (spec): Δ̂ ≥ +0.10. **Superiority**: Holm-adjusted p < 0.05 and CI lower bound > 0 |
| E4 vs E1 | test_synth | Same | McNemar | Same (Holm family) |
| E4 vs E2 (honesty rule, §9.7) | test_synth | Two-sided Δ CI + randomization p | McNemar | Report either direction; if E2 ≥ E4, publish it (spec) |
| E5 vs E6 | 120-ticket subset | Paired bootstrap of Δrouting accuracy and of the cost ratio (E5 blended / E6) | McNemar mid-p on routing correctness | Report; cost gate is a ratio ≤ 0.20 on the point estimate, with CI |
| E4 across seeds | as above | Run the E4 vs E3 comparison **per seed** and on the seed-mean | – | Claim only if all three seeds agree in direction; report all p-values |

E3 is decoding at T=0. Verify determinism once by running it twice and asserting identical outputs; if outputs differ, record the nondeterminism and run 3 repeats.

### D4. Multi-seed reporting (Q3)

1. Each seed's model is selected by early stopping on **val**. The **deployed seed** is the one with the best val macro-F1, chosen before any test evaluation.
2. **Headline E4 row:** seed-mean macro-F1 with a **two-level bootstrap CI**: resample test items (stratified), compute each seed's macro-F1 on the same resample, average across seeds.
3. **Alongside:** the three per-seed values, the SD (ddof=1) with its χ² CI, and the min–max. Also the **deployed seed's** own value and CI, clearly labeled. Never report "best of 3 on test".
4. **E2 (encoder baseline) should also use 3 seeds**, so the E2 vs E4 comparison is symmetric (Spec impact SI-3).

### D5. Reviewer study design, M-11 (Q5)

**Objective.** Descriptive estimates of accept/edit/reject/override rates for E5 outputs. There is no threshold (L-01, L-12).

| Element | Specification |
|---|---|
| Participants | R0 = owner; R1, R2 = volunteers, ideally with support or CX experience. Informed consent; pseudonymous ids; synthetic data only; no personal data beyond R-id and an optional short experience question |
| Materials | 40 tickets from `e2e_scenarios`, stratified: **20 routine** (local_draft), **10 complex**, **10 high-risk** (human_escalation). Excludes the 3 §17 demo tickets and any `test_hard_dev` items. **Pipeline outputs are frozen** (recorded cassette) so all reviewers see identical triage, drafts and handoffs |
| Design | **Fully crossed**: every reviewer does all 40 (120 decisions), which enables agreement statistics and removes ticket-sampling differences between raters. Per-reviewer seeded random order. 3 practice tickets (not analyzed). ≤ 90 min with a break. UI in study mode (no gold, no model-version chips) |
| Instructions | Scripted in `docs/eval/reviewer_study_protocol.md`: "Handle each ticket as you would in production: approve, edit, reject or flag the draft; override any triage field you disagree with; escalate if needed." No hints about expected results |
| Measures | Per (ticket, reviewer): draft decision (accept = approved with edit_distance_ratio < 0.05 / edit / reject), overrides per triage field (with value), flags, `time_to_decision_ms`, `edit_distance_ratio`; free-text reason on edit/reject |
| Primary analysis (pre-registered) | **Volunteers pooled (R1+R2, 80 decisions)**: accept/edit/reject/override rates with ticket-cluster bootstrap CIs |
| Secondary analysis | All three reviewers pooled; per reviewer (Wilson, n=40); by stratum (counts only); agreement on the 3-way draft decision via **Fleiss' κ** (3 raters, item bootstrap CI), pairwise Cohen's κ and % agreement; share of overrides that move toward gold; median (IQR) time-to-decision by stratum; top reasons for edits and rejections |
| Precision to expect | Rate 0.60: per reviewer [0.446, 0.737] (±0.15); volunteers pooled ≈ ±0.11; all 120 ≈ ±0.09 before clustering (cluster CIs are wider) |
| Threats | Small n; owner bias (volunteers-only is primary); volunteers are not trained agents; synthetic tickets; learning and fatigue effects (practice, randomization, break) |
| Reporting | "Small-n reviewer study (n=40 tickets × 3 reviewers)"; all counts published; no inferential claims about agent populations |

### D6. Citation audit and agreement (Q6)

**Populations.**
- **A**: cited factual/procedural sentences *shown* to agents (verifier support ≥ 0.5) in E5 drafts over e2e_scenarios + test_hard_final. Add a test_synth sample if needed to reach n.
- **B**: cited sentences the verifier **removed**.

**Sample.**
- **150 from A**, as in the spec: simple random within strata of provider (local/frontier) × doc_type, proportional allocation.
- **Plus 50 from B** (all of B if it has fewer than 50).
- Shuffle A and B together, so annotators cannot tell which population an item came from.

**Annotation.**
- Two annotators (owner + volunteer), independent, blind to verifier scores.
- Each item is a triple: (sentence, cited chunk quote, doc metadata).
- Labels: *supported* (every factual claim is entailed by the chunk) / *partially* / *not supported*. Binary collapse: partially → not supported.
- 10 calibration items first (not in the sample). Disagreements are adjudicated into a consensus label.

**Outputs.**

| Output | Computation |
|---|---|
| M-06 human precision | Consensus supported / 150 (A only), Wilson CI |
| Inter-annotator agreement | Over all 200 items: Cohen's κ + bootstrap CI, % agreement, prevalence, PABAK, Gwet's AC1. Use Fleiss' κ if a third annotator is added |
| Verifier-vs-human agreement | Over A ∪ B: Cohen's κ, sensitivity and specificity of the verifier vs consensus. **Descriptive**, because B is over-sampled; weight by inverse sampling fractions for any population-level figure |
| Optional masked frontier LLM-judge | κ vs human consensus, reported separately. It never replaces the human audit (§8.9). **Its labels are never used to train anything** (see synthetic-data-generation.md, SI-7) |

**Sample size.** At p̂=0.90, n=150 gives [0.842, 0.938]; n=250 gives [0.857, 0.931]. To show the ≥ 0.85 target with the lower bound, audit 250 sentences from A. The cost is about 100 × 2 × 40 s ≈ 2.2 extra hours.

### D7. Multiple comparisons, pre-registration and holdout hygiene (Q7)

1. **`evals/ANALYSIS_PLAN.md`**, committed before P10, pre-registers:
   - the hypotheses, metrics, splits, seeds, CI methods, B and the RNG seed;
   - the confirmatory family **{H1: E4 > E3, H2: E4 > E1, H3: E4 vs E2}** on test_synth macro-F1 (Holm, α = 0.05);
   - exploratory analyses (BH-FDR 5%, labeled "exploratory");
   - exclusion rules: **none** for test items.
2. **Headline tables** show estimates and CIs, not p-values. p-values appear only for the confirmatory family.
3. **Val only** is used for thresholds (τ), calibration, prompt choice, early stopping and seed choice. Protected splits are evaluated **once per registered model version**; the count is logged and published.
4. **Hard set:**
   - split `test_hard.v1` (100) into **`test_hard_dev` (30)** for error analysis in v0.1 → v0.2, and **`test_hard_final` (70)**, sealed until P10. Stratify so each stratum keeps about a 30/70 ratio: ~2 of 6 per intent; ~8 of ≥ 25 critical; 3 of 10 injection; 3 of 10 needs-info; 2–3 of 8 human-request; 2 of 6 legal-in-billing.
   - Alternatively, write a fresh `test_hard.v2` after v0.2.
   - e2e_scenarios drawn from `test_hard_dev` are flagged `dev_exposed`.
5. **Gates are decisions, not tests.** Publish every gate outcome with its CI (D8).

### D8. Interpreting acceptance gates (Q8)

- **M-07a = 1.00** (zero misses). Keep as specified. Publish n and the exact one-sided lower bound, for example "385/385; ≥ 0.992 (95%)".
- **M-03c "E5 each ≥ 0.95" on test_synth (n≈55–60 per class).** The gate is volatile (F9). Options, in order of preference:
  - **(b)** gate on **pooled critical recall ≥ 0.95** (n≈280, Wilson half-width ≈ ±0.026) plus **each class ≥ 0.90** on the point estimate, and publish per-class CIs;
  - **(a)** increase each critical class in test_synth to ≥ 100 items (+~225 items, ~3 h review);
  - **(c)** keep the gate and label a miss whose Wilson CI covers 0.95 as "inconclusive" in the narrative. It still blocks promotion unless an ADR waives it.
- **M-03c "E5 each ≥ 0.90" on test_hard** (~5 items per critical class): not informative (5/5 → [0.57, 1.00]; one miss → 0.80). Replace it with **pooled critical recall on test_hard_final ≥ 0.90**, with its CI.
- **M-01 "E4 − E3 ≥ +0.10"**: point estimate plus the paired CI (D3). **"E4 > E1"**: a Holm-adjusted confirmatory test.

### D9. Report record schema (Q9)

One record per (experiment, split, metric, model version), written to `evals/reports/<date>/results.json` and to `eval_runs.metrics`:

```json
{
  "experiment": "E4", "model_version": "tw-triage-qwen-1.5b-qlora@1.0.0", "split": "test_synth",
  "metric": "M-01.macro_f1", "seed": "mean_of_3", "point": 0.873, "low": 0.851, "high": 0.894,
  "method": "two-level stratified percentile bootstrap", "n": 720, "k": null,
  "n_resamples": 10000, "rng_seed": 2026,
  "per_seed": {"42": 0.869, "1337": 0.871, "2026": 0.879}, "sd_seeds": 0.0053, "sd_ci": [0.0028, 0.0333],
  "deployed_seed": "1337", "comparisons": [{"vs": "E3", "delta": 0.214, "low": 0.183, "high": 0.246,
  "p_randomization": 0.0001, "p_mcnemar_midp": 1e-12, "holm_family": "F-confirmatory", "p_holm": 0.0003}],
  "eval_count_on_split": 3, "analysis_plan_sha": "<sha>"
}
```

(The values are placeholders showing the shape, not results.)

### D10. Code sketch (Q9)

`ml/src/tw_ml/eval/stats.py`. Pins to verify at build: `numpy>=2`, `scipy==1.18.*`, `scikit-learn==1.9.*`, `statsmodels==0.15.*`.

```python
"""Interval estimates, paired tests and agreement statistics. ERPROT: evaluation-statistics.md."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from scipy import stats
from sklearn.metrics import cohen_kappa_score, f1_score
from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa
from statsmodels.stats.multitest import multipletests

B_DEFAULT, RNG_SEED, CHUNK = 10_000, 2026, 2_000
INTENTS_12: tuple[str, ...] = (
    "sso_login_failure", "account_access_issue", "billing_duplicate_charge", "billing_payment_failure",
    "refund_request", "cancellation_request", "plan_pricing_inquiry", "service_outage", "bug_report",
    "how_to_question", "security_report", "privacy_legal_request",
)
ALL_LABELS: tuple[str, ...] = INTENTS_12 + ("other_unclear",)
IntArr = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class Estimate:
    metric: str
    point: float
    low: float
    high: float
    method: str
    n: int
    k: int | None = None
    n_resamples: int | None = None
    rng_seed: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


# ------------------------------------------------------------------ proportions
def proportion(metric: str, k: int, n: int, level: float = 0.95) -> Estimate:
    """Wilson score CI; Clopper-Pearson ('exact') at k == 0 or k == n."""
    method = "exact" if k in (0, n) else "wilson"
    ci = stats.binomtest(k, n).proportion_ci(confidence_level=level, method=method)
    return Estimate(metric, k / n, float(ci.low), float(ci.high), f"{method}-binomial", n, k)


def zero_failure_lower_bound(n: int, level: float = 0.95) -> float:
    """One-sided exact lower bound when all n succeed (M-07a). Approximately 1 - 3/n."""
    return (1.0 - level) ** (1.0 / n)


# ------------------------------------------------------------------ encoding + fast macro-F1
def encode(labels: Sequence[str], vocab: Sequence[str] = ALL_LABELS) -> IntArr:
    idx = {c: i for i, c in enumerate(vocab)}
    return np.fromiter((idx[x] for x in labels), dtype=np.int64, count=len(labels))


def macro_f1_matrix(Y: IntArr, P: IntArr, k: int, avg: IntArr) -> NDArray[np.float64]:
    """Row-wise macro-F1 for (R, n) label matrices; equals sklearn f1_score(labels=avg, average='macro',
    zero_division=0) per row. cm[r, gold, pred] via one bincount."""
    r = Y.shape[0]
    codes = Y * k + P + (np.arange(r, dtype=np.int64)[:, None] * k * k)
    cm = np.bincount(codes.ravel(), minlength=r * k * k).reshape(r, k, k)
    tp = np.einsum("rii->ri", cm).astype(np.float64)
    fp = cm.sum(axis=1) - tp            # predicted-as-c minus tp
    fn = cm.sum(axis=2) - tp            # gold-c minus tp
    den = 2 * tp + fp + fn
    f1 = np.divide(2 * tp, den, out=np.zeros_like(den), where=den > 0)
    return f1[:, avg].mean(axis=1)


def stratified_draws(strata: IntArr, n_resamples: int, rng: np.random.Generator) -> IntArr:
    """(B, n) indices resampled within each stratum; per-stratum counts stay fixed."""
    cols = []
    for s in np.unique(strata):
        g = np.flatnonzero(strata == s)
        cols.append(g[rng.integers(0, g.size, size=(n_resamples, g.size))])
    return np.concatenate(cols, axis=1)


def _chunked(fn, draws: IntArr) -> NDArray[np.float64]:
    return np.concatenate([fn(draws[i : i + CHUNK]) for i in range(0, draws.shape[0], CHUNK)])


def _pct(dist: NDArray[np.float64], level: float) -> tuple[float, float]:
    lo, hi = np.quantile(dist, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def macro_f1_ci(y_true: Sequence[str], y_pred: Sequence[str], *, labels: Sequence[str] = INTENTS_12,
                n_resamples: int = B_DEFAULT, level: float = 0.95, seed: int = RNG_SEED) -> Estimate:
    y, p, avg, k = encode(y_true), encode(y_pred), encode(labels), len(ALL_LABELS)
    point = float(macro_f1_matrix(y[None, :], p[None, :], k, avg)[0])
    d = stratified_draws(y, n_resamples, np.random.default_rng(seed))
    dist = _chunked(lambda dd: macro_f1_matrix(y[dd], p[dd], k, avg), d)
    return Estimate("macro_f1", point, *_pct(dist, level), "stratified-percentile-bootstrap", y.size,
                    n_resamples=n_resamples, rng_seed=seed)


def macro_f1_bca_check(y_true: Sequence[str], y_pred: Sequence[str], *, labels: Sequence[str] = INTENTS_12,
                       n_resamples: int = B_DEFAULT, seed: int = RNG_SEED) -> Estimate:
    """Unstratified BCa via SciPy, as a sensitivity check (may return NaN if degenerate)."""
    y, p = encode(y_true), encode(y_pred)
    lab = encode(labels).tolist()
    stat = lambda a, b: f1_score(a, b, labels=lab, average="macro", zero_division=0)  # noqa: E731
    res = stats.bootstrap((y, p), stat, paired=True, vectorized=False, n_resamples=n_resamples,
                          method="BCa", rng=np.random.default_rng(seed))
    ci = res.confidence_interval
    return Estimate("macro_f1", float(stat(y, p)), float(ci.low), float(ci.high), "bca-bootstrap", y.size,
                    n_resamples=n_resamples, rng_seed=seed)


# ------------------------------------------------------------------ paired comparisons
def paired_macro_f1_diff(y_true: Sequence[str], pred_a: Sequence[str], pred_b: Sequence[str], *,
                         labels: Sequence[str] = INTENTS_12, n_resamples: int = B_DEFAULT,
                         level: float = 0.95, seed: int = RNG_SEED) -> Estimate:
    """CI for macro-F1(a) - macro-F1(b); identical stratified resamples for both systems."""
    y, a, b = encode(y_true), encode(pred_a), encode(pred_b)
    avg, k = encode(labels), len(ALL_LABELS)
    f = lambda P, dd: macro_f1_matrix(y[dd], P[dd], k, avg)  # noqa: E731
    full = np.arange(y.size)[None, :]
    point = float(f(a, full)[0] - f(b, full)[0])
    d = stratified_draws(y, n_resamples, np.random.default_rng(seed))
    dist = _chunked(lambda dd: f(a, dd) - f(b, dd), d)
    return Estimate("delta_macro_f1", point, *_pct(dist, level), "paired-stratified-percentile-bootstrap",
                    y.size, n_resamples=n_resamples, rng_seed=seed)


def randomization_pvalue(y_true: Sequence[str], pred_a: Sequence[str], pred_b: Sequence[str], *,
                         labels: Sequence[str] = INTENTS_12, n_resamples: int = B_DEFAULT,
                         alternative: str = "greater", seed: int = RNG_SEED) -> float:
    """Approximate randomization: swap (a_i, b_i) with prob 1/2. p = (1 + #extreme) / (1 + R)."""
    y, a, b = encode(y_true), encode(pred_a), encode(pred_b)
    avg, k = encode(labels), len(ALL_LABELS)
    obs = float(macro_f1_matrix(y[None], a[None], k, avg)[0] - macro_f1_matrix(y[None], b[None], k, avg)[0])
    rng = np.random.default_rng(seed)
    null = []
    for start in range(0, n_resamples, CHUNK):
        r = min(CHUNK, n_resamples - start)
        swap = rng.random((r, y.size)) < 0.5
        Y = np.broadcast_to(y, (r, y.size))
        null.append(macro_f1_matrix(Y, np.where(swap, b, a), k, avg) - macro_f1_matrix(Y, np.where(swap, a, b), k, avg))
    nd = np.concatenate(null)
    extreme = (nd >= obs) if alternative == "greater" else (np.abs(nd) >= abs(obs))
    return float((1 + extreme.sum()) / (1 + nd.size))
    # Cross-check (slower): stats.permutation_test((a, b), lambda x, z: F(x) - F(z),
    #   permutation_type="samples", vectorized=False, n_resamples=9_999, rng=np.random.default_rng(seed))


def mcnemar_midp(correct_a: Sequence[bool], correct_b: Sequence[bool]) -> dict[str, float | int]:
    """Two-sided exact and mid-p McNemar on discordant pairs (Fagerland et al. 2013)."""
    ca, cb = np.asarray(correct_a, dtype=bool), np.asarray(correct_b, dtype=bool)
    n10, n01 = int(np.sum(ca & ~cb)), int(np.sum(~ca & cb))
    n = n10 + n01
    if n == 0:
        return {"n10": 0, "n01": 0, "p_exact": 1.0, "p_midp": 1.0}
    kmin = min(n10, n01)
    cdf, pmf = stats.binom.cdf(kmin, n, 0.5), stats.binom.pmf(kmin, n, 0.5)
    return {"n10": n10, "n01": n01, "p_exact": float(min(1.0, 2 * cdf)), "p_midp": float(min(1.0, 2 * cdf - pmf))}
    # unit test: p_exact equals statsmodels mcnemar([[n11, n10], [n01, n00]], exact=True).pvalue


# ------------------------------------------------------------------ seeds
def seed_mean_macro_f1(y_true: Sequence[str], preds_by_seed: Sequence[Sequence[str]], *,
                       labels: Sequence[str] = INTENTS_12, n_resamples: int = B_DEFAULT,
                       level: float = 0.95, seed: int = RNG_SEED) -> tuple[Estimate, dict[str, float]]:
    y, avg, k = encode(y_true), encode(labels), len(ALL_LABELS)
    ps = [encode(p) for p in preds_by_seed]
    per_seed = np.array([macro_f1_matrix(y[None], p[None], k, avg)[0] for p in ps])
    d = stratified_draws(y, n_resamples, np.random.default_rng(seed))
    dist = _chunked(lambda dd: np.mean([macro_f1_matrix(y[dd], p[dd], k, avg) for p in ps], axis=0), d)
    s = float(per_seed.std(ddof=1))
    dof = per_seed.size - 1
    sd_lo = s * np.sqrt(dof / stats.chi2.ppf(1 - (1 - level) / 2, dof))
    sd_hi = s * np.sqrt(dof / stats.chi2.ppf((1 - level) / 2, dof))
    est = Estimate("macro_f1_seed_mean", float(per_seed.mean()), *_pct(dist, level),
                   "two-level stratified percentile bootstrap", y.size, n_resamples=n_resamples, rng_seed=seed)
    return est, {"sd": s, "sd_low": float(sd_lo), "sd_high": float(sd_hi),
                 "min": float(per_seed.min()), "max": float(per_seed.max())}


# ------------------------------------------------------------------ clusters (reviewer study, drafts)
def cluster_bootstrap_rate(cluster_ids: Sequence[str], outcomes: Sequence[bool], *, metric: str,
                           n_resamples: int = B_DEFAULT, level: float = 0.95, seed: int = RNG_SEED) -> Estimate:
    c, o = np.asarray(cluster_ids), np.asarray(outcomes, dtype=np.float64)
    _, inv = np.unique(c, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=o), np.bincount(inv).astype(np.float64)
    pick = np.random.default_rng(seed).integers(0, sums.size, size=(n_resamples, sums.size))
    dist = sums[pick].sum(axis=1) / cnts[pick].sum(axis=1)
    return Estimate(metric, float(o.mean()), *_pct(dist, level), "cluster-percentile-bootstrap",
                    o.size, int(o.sum()), n_resamples, seed)


# ------------------------------------------------------------------ agreement
def agreement_binary(r1: Sequence[int], r2: Sequence[int], *, n_resamples: int = B_DEFAULT,
                     level: float = 0.95, seed: int = RNG_SEED) -> dict[str, float]:
    a, b = np.asarray(r1, dtype=np.int64), np.asarray(r2, dtype=np.int64)
    po = float(np.mean(a == b))
    pi = float((a.mean() + b.mean()) / 2)
    pe_ac1 = 2 * pi * (1 - pi)
    idx = np.random.default_rng(seed).integers(0, a.size, size=(n_resamples, a.size))
    ks = np.array([cohen_kappa_score(a[i], b[i]) for i in idx])       # ~seconds at n=200
    ks = ks[~np.isnan(ks)]
    lo, hi = _pct(ks, level)
    return {"cohen_kappa": float(cohen_kappa_score(a, b)), "kappa_low": lo, "kappa_high": hi,
            "kappa_undefined_resamples": int(n_resamples - ks.size), "percent_agreement": po,
            "prevalence_positive": pi, "pabak": 2 * po - 1, "gwet_ac1": (po - pe_ac1) / (1 - pe_ac1)}


def fleiss(ratings: NDArray[np.int64]) -> float:
    """ratings: (n_items, n_raters) category codes. No analytic variance in statsmodels -> bootstrap items."""
    table, _ = aggregate_raters(ratings)
    return float(fleiss_kappa(table, method="fleiss"))


def fleiss_ci(ratings: NDArray[np.int64], *, n_resamples: int = B_DEFAULT, level: float = 0.95,
              seed: int = RNG_SEED) -> tuple[float, float, float]:
    idx = np.random.default_rng(seed).integers(0, ratings.shape[0], size=(n_resamples, ratings.shape[0]))
    dist = np.array([fleiss(ratings[i]) for i in idx])
    dist = dist[~np.isnan(dist)]
    return (fleiss(ratings), *_pct(dist, level))


# ------------------------------------------------------------------ multiplicity
def holm(pvals: Sequence[float], alpha: float = 0.05) -> tuple[list[bool], list[float]]:
    reject, p_adj, _, _ = multipletests(list(pvals), alpha=alpha, method="holm")
    return [bool(x) for x in reject], [float(x) for x in p_adj]


def bh(pvals: Sequence[float]) -> list[float]:
    return [float(x) for x in stats.false_discovery_control(list(pvals), method="bh")]
```

**Unit tests** (`ml/tests/test_eval_stats.py`):
- `macro_f1_matrix` equals `sklearn.f1_score(labels=INTENTS_12, average="macro", zero_division=0)` on 200 random label vectors;
- `proportion(…, 57, 60)` ≈ [0.863, 0.983];
- `zero_failure_lower_bound(385)` ≈ 0.9922;
- `mcnemar_midp(b=18, c=8)` → exact 0.0755 and mid-p 0.0522;
- `stratified_draws` preserves per-class counts;
- `randomization_pvalue` is approximately uniform under a simulated null (Kolmogorov–Smirnov p > 0.01 over 200 simulations; nightly only);
- `seed_mean_macro_f1` gives sd CI multipliers ≈ [0.521, 6.285] for 3 seeds.

---

## SPEC IMPACT (do not edit the spec here; raise via ADR-new "Evaluation statistics protocol" + version bump)

| # | Spec text | Finding | Proposed change |
|---|---|---|---|
| SI-1 | §9.8 "Bootstrap 95% CIs (1,000 resamples) for all proportions" | Bootstrap percentile CIs degenerate at 0/n and n/n, and Wilson is recommended for proportions [S17]. 1,000 resamples add avoidable Monte-Carlo error | Wilson/Clopper–Pearson for proportions; stratified/cluster bootstrap with **B=10,000** for non-decomposable metrics |
| SI-2 | §9.8 M-03c "E5 each ≥ 0.95" (test_synth) and "E5 each ≥ 0.90" (test_hard) | P(all 5 pass \| true recall 0.95, n=60) = 0.11. With ~5 items per class in test_hard, per-class gates carry almost no information | Pooled critical recall gates + per-class ≥ 0.90 with CIs, or ≥ 100 items per critical class in test_synth; pooled gate on test_hard (D8) |
| SI-3 | §9.5 "seeds 42, 1337, 2026 (report mean ± std)"; §9.7 E2 has no seed count | A 3-seed SD has a 0.52×–6.29× CI; the deployed seed must be selected on val; an asymmetric seed count biases E2 vs E4 | Report per-seed values, the two-level CI and a val-selected deployed seed; run **3 seeds for E2** too |
| SI-4 | §9.8 M-01 "E4 − E3 ≥ +0.10" | Point-estimate acceptance is fine, but a superiority claim needs a CI or test | Add the paired CI + randomization p; Holm family {E3, E1, E2} |
| SI-5 | §9.8 M-11 "owner + 2 volunteers × 40 tickets each" | Design unspecified; owner bias (L-12) | Fully crossed 40 tickets; volunteers-only primary; Fleiss' κ; frozen outputs (D5) |
| SI-6 | §8.9 "human audit of 150 sampled sentences … plus agreement κ" | κ between verifier and humans is undefined without verifier-rejected items; n=150 at p̂=0.90 cannot put the lower bound at 0.85 | 150 shown + 50 removed; two annotators; κ + PABAK/AC1; consider n=250 (D6) |
| SI-7 | §16 "second fine-tune iteration (v0.2) using hard-set error analysis" | Adaptive reuse makes test_hard a dev set [S21] | Split test_hard 30 dev / 70 final (stratified), or write test_hard.v2; report finals only on test_hard_final |
| SI-8 | §9.8 M-07a "1.00 (any miss blocks release)" | Correct as a gate; "100%" alone overstates certainty | Publish n + the one-sided exact lower bound |

---

## IMPLEMENTATION CHECKLIST

- [ ] `ml/src/tw_ml/eval/stats.py` (D10) + unit tests; `tw_ml.eval.report` uses the `Estimate` records and the D9 schema.
- [ ] `evals/ANALYSIS_PLAN.md` (D7) committed and hashed **before** P10; `analysis_plan_sha` included in every report.
- [ ] Split `test_hard.v1` into `test_hard_dev` (30) and `test_hard_final` (70), stratified, recorded in the manifest (ADR-0016 amendment).
- [ ] `eval_runs` logs every protected-split evaluation; the report shows `eval_count_on_split`.
- [ ] E2 trained with 3 seeds; E4 deployed seed chosen on val and recorded in the model card.
- [ ] Reviewer study: `docs/eval/reviewer_study_protocol.md`, consent text, frozen-cassette study mode in the UI, randomization seeds, analysis notebook implementing D5.
- [ ] Citation audit: sampling script (A 150 + B 50, shuffled), annotation guideline with 10 calibration items, `agreement_binary` report.
- [ ] Dashboard shows CIs on every metric tile; gate tiles show point, CI and n.
- [ ] Model card "Evaluation" section uses the D1 methods and states the small-n caveats (test_hard, M-11).

---

## OPEN RISKS / TO VERIFY

| Risk / item | Status | Mitigation |
|---|---|---|
| Owner bias in M-11 and in the citation audit | Accepted (L-12) | Volunteers-only primary; blind shuffling of A/B; second annotator |
| Stratified bootstrap assumes fixed class counts (true for quota-built sets) | OK for test_synth, test_hard, test_ood | For e2e_scenarios (curated), use an unstratified or scenario-cluster bootstrap |
| BCa instability at n≈70–100 | Known | Percentile is primary; BCa only as a test_synth check |
| Pre-registration discipline slipping under time pressure | Open | The CI job fails the P10 report if `analysis_plan_sha` is missing or changed after the first P10 eval run |
| ECE small-sample bias | Open | See confidence-calibration.md; bootstrap CI plus a reliability diagram |
| krippendorff package license (GPL-3.0-or-later) | Verified | Do not add it as a dependency; κ/AC1 suffice |
| Volunteer availability (2 people × ~1.5 h + audit ~2 h) | Open | Schedule in P10; fallback: one volunteer (report as such) |

---

## LINKED ADR

- **ADR-new "Evaluation statistics protocol"** (proposed): D1–D8 and SI-1…SI-8.
- **ADR-0016** (test set design): hard-set dev/final split (SI-7); OOD composition (see bitext-ood-dataset.md).
- **Related ERPROT docs:** `leakage-and-dedup.md`, `synthetic-data-generation.md` (label QA κ uses `agreement_binary` and Cohen's κ), `bitext-ood-dataset.md`, `confidence-calibration.md` (ECE), `citation-verification.md` (verifier threshold vs the human audit).

---

## SOURCES (accessed 2026-09-26 unless marked "classic")

**Library documentation**
- [S1] SciPy 1.18.0 `scipy.stats.bootstrap`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html
- [S2] SciPy `scipy.stats.permutation_test`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html
- [S3] SciPy `scipy.stats.binomtest` and `BinomTestResult.proportion_ci`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html; https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html
- [S4] SciPy `scipy.stats.false_discovery_control`. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html
- [S5] statsmodels 0.15.0 `mcnemar`. https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html
- [S6] statsmodels `fleiss_kappa`. https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.fleiss_kappa.html
- [S7] statsmodels `multipletests`. https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html
- [S8] scikit-learn 1.9.1 `cohen_kappa_score`. https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html
- [S9] scikit-learn `f1_score`. https://scikit-learn.org/stable/modules/generated/sklearn.metrics.f1_score.html
- [S23] `krippendorff` 0.8.2 on PyPI (GPL-3.0-or-later). https://pypi.org/project/krippendorff/

**Papers (fetched or verified via search)**
- [S10] Fagerland, Lydersen & Laake, "The McNemar test for binary matched-pairs data: mid-p and asymptotic are better than exact conditional", BMC Med Res Methodol 13:91 (2013). https://doi.org/10.1186/1471-2288-13-91 (PMC: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3716987/)
- [S11] Dror, Baumer, Shlomov & Reichart, "The Hitchhiker's Guide to Testing Statistical Significance in NLP", ACL 2018. https://aclanthology.org/P18-1128/
- [S12] Berg-Kirkpatrick, Burkett & Klein, "An Empirical Investigation of Statistical Significance in NLP", EMNLP-CoNLL 2012. https://aclanthology.org/D12-1091/
- [S13] Card et al., "With Little Power Comes Great Responsibility", EMNLP 2020. https://aclanthology.org/2020.emnlp-main.745/
- [S14] Bouthillier et al., "Accounting for Variance in Machine Learning Benchmarks", MLSys 2021. https://arxiv.org/abs/2103.03098
- [S15] Dodge et al., "Fine-Tuning Pretrained Language Models: Weight Initializations, Data Orders, and Early Stopping", 2020. https://arxiv.org/abs/2002.06305
- [S16] Agarwal et al., "Deep Reinforcement Learning at the Edge of the Statistical Precipice", NeurIPS 2021. https://arxiv.org/abs/2108.13264
- [S17] Brown, Cai & DasGupta, "Interval Estimation for a Binomial Proportion", Statistical Science 16(2) (2001). https://projecteuclid.org/journals/statistical-science/volume-16/issue-2/Interval-Estimation-for-a-Binomial-Proportion/10.1214/ss/1009213286.full
- [S18] Hanley & Lippman-Hand, "If nothing goes wrong, is everything all right? Interpreting zero numerators", JAMA 249(13):1743–1745 (1983). https://jhanley.biostat.mcgill.ca/c607/ch08/zero_numerator.pdf
- [S19] Feinstein & Cicchetti, "High agreement but low kappa: I. The problems of two paradoxes", J Clin Epidemiol 43(6):543–549 (1990). https://pubmed.ncbi.nlm.nih.gov/2348207
- [S20] Gwet, "Computing inter-rater reliability and its variance in the presence of high agreement", Br J Math Stat Psychol 61(1):29–48 (2008). https://doi.org/10.1348/000711006X126600
- [S21] Dwork, Feldman, Hardt, Pitassi, Reingold & Roth, "The reusable holdout: Preserving validity in adaptive data analysis", Science 349(6248):636–638 (2015). https://www.science.org/doi/10.1126/science.aaa9375
- [S22] Northcutt et al., "Pervasive Label Errors in Test Sets Destabilize Machine Learning Benchmarks", NeurIPS 2021 D&B. https://arxiv.org/abs/2103.14749

**Classic references** (standard bibliographic citations; not re-fetched this session)
- Efron, "Better Bootstrap Confidence Intervals", JASA 82(397):171–185 (1987).
- Dietterich, "Approximate Statistical Tests for Comparing Supervised Classification Learning Algorithms", Neural Computation 10(7):1895–1923 (1998).
- Koehn, "Statistical Significance Tests for Machine Translation Evaluation", EMNLP 2004.
- Byrt, Bishop & Carlin, "Bias, prevalence and kappa", J Clin Epidemiol 46(5):423–429 (1993).
- Landis & Koch, "The measurement of observer agreement for categorical data", Biometrics 33(1):159–174 (1977).
- Holm, "A simple sequentially rejective multiple test procedure", Scand J Stat 6(2):65–70 (1979).
- Benjamini & Hochberg, "Controlling the false discovery rate", JRSS-B 57(1):289–300 (1995).

**Computation (this session):** the Wilson and Clopper–Pearson intervals, McNemar exact/mid-p values, gate-pass probabilities, χ² SD multipliers and the macro-F1 width simulation were computed with independent pure-Python scripts; the D10 functions reproduce them. The NumPy-only D10 functions were executed against a pure-Python reference implementing sklearn's `f1_score(labels=…, average="macro", zero_division=0)` semantics:
- `macro_f1_matrix` matched exactly on 200 random cases;
- `stratified_draws` preserved per-class counts;
- `macro_f1_ci`, `paired_macro_f1_diff`, `randomization_pvalue` and `cluster_bootstrap_rate` behaved as expected.

The SciPy, statsmodels and sklearn calls could not be executed locally (not installed) and must be covered by the listed unit tests.

---

**Document Version**: 1.0
**Next Update**: when `evals/ANALYSIS_PLAN.md` is drafted (P9/P10); after the first P10 run (confirm BCa vs percentile agreement and the observed CI widths)
