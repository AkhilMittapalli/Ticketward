---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §1.4, §9.3, §9.8, §9.9, §9.10, §16 P10, §19 DoD-6; research evaluation-statistics
informed: reviewers reading docs/benchmarks.md; model card readers
supersedes: none
amended: none
---

# ADR-0032: Evaluation statistics protocol and pre-registration

## Context and Problem Statement

"The evaluation table is the product." Every headline number is reported per split, reproducible with one command,
and gated: pooled critical recall, forced escalation, citation precision, cost versus frontier-only (§1.4).

v1.0 left the statistics underspecified:
* percentile bootstrap intervals for proportions, which behave badly near 0 and 1;
* per-class critical-recall gates of 0.95 on about 50 items per class, which are statistically unfalsifiable at that
  n;
* a hard set used for both error analysis and headline reporting;
* no rule on how often sealed splits may be evaluated;
* no pre-registration, which leaves room for choosing metrics, seeds or comparisons after seeing results.

The ERPROT evaluation-statistics research proposed a full protocol (change record A-10).

How should Ticketward estimate, compare and gate its metrics so that published claims are honest and reproducible?

## Decision Drivers

* Correct interval methods for proportions near the boundaries, and for non-decomposable metrics (macro-F1, ECE).
* Controlled error rates for the few claims that matter (E4 vs E3, E1, E2), and clear labelling of everything else.
* Gates that are falsifiable at realistic n, and decisions published with their CIs.
* Holdout hygiene: no tuning, selection or repeated peeking at sealed splits.
* Seed honesty: no best-of-3 on test.
* Commitment before results: a hashed analysis plan.

## Considered Options

1. The v1.1 protocol: Wilson intervals, stratified bootstrap B = 10,000, paired tests with a Holm family, per-seed
   reporting, pooled critical-recall gate, `hard_dev`/`hard_final`, and `evals/ANALYSIS_PLAN.md` (chosen)
2. Percentile bootstrap for proportions
3. Per-class 0.95 critical-recall gates
4. Reusing test_hard for development

## Decision Outcome

Chosen option: option 1 (spec §9.8), because it uses the right interval for each metric type, confines hypothesis
testing to a small pre-declared family, and makes every gate a published decision with its uncertainty.

**Intervals:**

| Metric type | Method |
|---|---|
| Proportions (accuracy, per-class recall, JSON validity, escalation/abstention rates, M-11 rates, citation precision) | Wilson score interval; Clopper–Pearson (exact) when k = 0 or k = n |
| Non-decomposable metrics (macro-F1, sentiment/churn macro-F1, entity F1, ECE) | percentile bootstrap, B = 10,000, `numpy.random.default_rng(2026)` (seed recorded), stratified by gold class, or clustered by ticket/draft for multi-unit metrics |

The same resample indices are used for every system in a comparison. BCa is run as a sensitivity check on
test_synth.

**Comparisons:**
* Paired stratified bootstrap CI of the difference, plus an approximate-randomization p-value, plus McNemar mid-p.
* The **confirmatory family** is H1: E4 > E3, H2: E4 > E1 and H3: E4 vs E2, on test_synth macro-F1,
  Holm-corrected at α = 0.05.
* Everything else is descriptive. Exploratory screens use BH-FDR and are labelled. p-values appear only for the
  confirmatory family.

**Seeds:** 3 seeds (42, 1337, 2026) for E4 **and E2**. Each seed's value is reported, plus mean ± SD (with its χ²
CI), range, and a two-level bootstrap CI of the seed mean. The deployed seed is chosen on val.

**Gates (decisions published with CIs):**
* M-03c: E5 **pooled** critical recall ≥ 0.95 on test_synth (n ≈ 600, since test_synth has ≥ 120 per critical
  class), and each class ≥ 0.90, reported with n and Wilson CIs. E4 ≥ 0.90 per class. `hard_final`: pooled ≥ 0.90.
* M-07a: 1.00 observed, published with n and the one-sided exact 95% lower bound 0.05^(1/n).
* M-06: automatic ≥ 0.90 (draft-cluster bootstrap), and human audit ≥ 0.85 on 250 shown sentences (Wilson), with 50
  verifier-removed sentences shuffled in blind.
* M-11: a fully crossed reviewer study (owner + 2 volunteers × the same 40 tickets). The volunteers-only pooled
  estimate is primary; Fleiss' κ is reported.

**Holdout hygiene:**
* val only for thresholds, calibration, prompt choice, early stopping and seed choice;
* `val_dev` (225) for pipeline development;
* `hard_dev` (30) for error analysis;
* `hard_final` (70) sealed until P10;
* protected splits evaluated **once per registered model version**, with the count logged and published
  (`eval_count_on_split`);
* nightly regression runs on val + `hard_dev` only.

**Pre-registration:** `evals/ANALYSIS_PLAN.md` states hypotheses, metrics, splits, seeds, CI methods, B, the RNG seed,
the confirmatory family and exclusion rules (none). It is committed and hashed **before P10**. Every report carries
`analysis_plan_sha`, and CI fails the P10 report if the plan is missing or changed after the first P10 run.

### Consequences

* Good, because intervals are valid at the boundaries (M-07a's 1.00 comes with an honest lower bound, not a false
  "100%").
* Good, because the three confirmatory claims have controlled family-wise error, and everything else is honestly
  descriptive.
* Good, because the pooled gate is falsifiable at n ≈ 600, and the per-class ≥ 0.90 with n still exposes a weak
  class.
* Bad, because test_synth grows to 1,045 records with ≥ 120 per critical class, which adds review workload (R-22).
* Bad, because "once per registered version" limits iteration on sealed splits. That is intentional; development
  runs on `val_dev` and `hard_dev`.
* Neutral, because the protocol lengthens reports. Every number appears as point [low, high] (method, n, k).

### Confirmation

* `make report` writes one record per experiment × split × metric × model version, with point, CI, method, n, k,
  resamples, RNG seed, per-seed values, comparisons, `eval_count_on_split` and `analysis_plan_sha` (§9.9).
* A CI check fails the P10 report if `analysis_plan_sha` is missing or differs from the hash committed before the
  first P10 run.
* Unit tests for `tw_ml.eval.stats`:
  * Wilson and Clopper–Pearson against reference values;
  * bootstrap reproducibility under the fixed seed;
  * identical indices across systems;
  * Holm step-down correctness;
  * the M-07a lower-bound formula.
* `eval-nightly.yml` never touches `hard_final` or test_synth (§9.10). A test asserts the nightly split list.
* DoD-6: all §9.8 thresholds met, or misses documented with analysis; every published number carries its CI and
  `analysis_plan_sha`.

## Pros and Cons of the Options

### The v1.1 protocol (chosen)

* Good, because it uses the right interval per metric, a small Holm family, falsifiable gates, sealed holdouts and
  pre-registration.
* Bad, because it means more data, more review, and longer reports.

### Percentile bootstrap for proportions

* Good, because one method covers everything.
* Bad, because it behaves poorly near 0 and 1, and degenerates when k = n. M-07a's "1.00" would get a zero-width
  interval.

### Per-class 0.95 critical-recall gates

* Good, because the target sounds stricter.
* Bad, because at about 50 items per class a single miss flips the gate, and the CI is far too wide to support the
  claim. At realistic n it is noise, not a decision.

### Reusing test_hard for development

* Good, because it gives more hard examples during development.
* Bad, because inspected items no longer measure generalisation, which contaminates the headline stress numbers. Hence
  the `hard_dev`/`hard_final` split.

## More Information

* Spec (private): §1.4, §9.3 (splits, `val_dev`), §9.8 (protocol, metric table), §9.9 (report schema), §9.10
  (nightly), §16 P10, §19 DoD-6. Change record A-10, A-27.
* Research: [evaluation-statistics](../research/evaluation-statistics.md).
* Related ADRs: ADR-0016 (splits), ADR-0013 (lineage), ADR-0018 (E2 seeds), ADR-0033 (citation audit design).
* Revisit when: the analysis plan needs a change (only before the first P10 run), or a new split or metric is
  introduced.
* Status history: 2026-09-27 Accepted (new in spec v1.1, change record A-10).
