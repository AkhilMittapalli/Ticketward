---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §4, §9, §14; spec §9.1–§9.3, §9.8, §9.10, §13 S-12, §20 L-01/L-06/L-07, §21 R-01/R-10/R-22; research synthetic-data-generation, leakage-and-dedup, bitext-ood-dataset, evaluation-statistics
informed: reviewers reading docs/benchmarks.md; dataset card readers
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0016: Cross-family test set, human hard set and Bitext OOD set

> **Amended in spec v1.1 (2026-09-27; change record A-10, A-11, A-12, A-13, A-27).**
> * **Generator families** are fixed by ADR-0031: Family A `openai/gpt-oss-120b` (train/val) and Family B
>   `deepseek-ai/DeepSeek-V3.2` (test_synth; owner decision D-07 of 2026-09-27 replaced Mistral Large 3,
>   which stays a config-only alternative). Never Claude.
> * **test_synth = 1,045**, with ≥ 120 per critical class. **test_hard = `hard_dev` 30 + `hard_final` 70**, where
>   `hard_final` is sealed until P10. **`val_dev`** = a fixed, stratified 50% of val (225), for pipeline development.
> * **Label QA:**
>   * pass only if the Wilson 95% upper bound of the audited error rate is < 5% (≤ 17/540);
>   * a second annotator on 20% of test_synth and 100% of test_hard, reporting κ (< 0.80 triggers a guideline
>     revision);
>   * `llm_assisted=false` for the hard set.
> * **Leakage C1–C7:**
>   * char-5 shingles, LSH candidates at 0.5 plus **exact Jaccard ≥ 0.70** (exact all-pairs is the CI truth);
>   * `datasketch==2.0.0` pinned;
>   * τ_emb 0.92 as a start value, calibrated on P1 data;
>   * explicit split pairs;
>   * replace duplicates before the freeze, version the split after it;
>   * the leakage embedder is pinned independently of retrieval.
> * **Bitext OOD** = CS + TEL at pinned revisions, with the mapping fixes, 5 × 80 + 50 human-request probes + 50
>   cancellation hard negatives, **pointers + build script only** (CDLA-Sharing-1.0), and critical recall on 2 of 5
>   classes only (stated).
> * Nightly regression runs on val + `hard_dev` only. Sealed splits are evaluated **once per registered model
>   version**, and the count is published.

## Context and Problem Statement

The brief allows only synthetic, public or de-identified data (brief §4, S-12). It requires a held-out test set
covering ordinary, ambiguous, severe-incident, cancellation-language, security-report and needs-more-information
tickets (brief §9, BR-038), and warns that synthetic data cannot prove production performance (brief §14, L-01).

When the same LLM writes training and test tickets, a fine-tuned model can learn the generator's style instead of the
task, which inflates metrics (R-01, M/H). The headline claims (pooled critical recall ≥ 0.95, forced escalation =
100%) would then be unreliable.

v1.0 also left gaps:
* the test set was too small for per-class critical CIs;
* a single hard set was used for both error analysis and reporting;
* the leakage method was underspecified;
* the Bitext mapping had errors (`cancel_order` is an e-commerce order, `SUBSCRIPTION` is a newsletter).

How should evaluation data be built and protected so the headline metrics are credible?

## Decision Drivers

* Separating task skill from generator style (R-01).
* Statistically meaningful critical-class estimates (≥ 120 per class; ADR-0032).
* A sealed human-written stress set that is never used for development.
* An out-of-distribution check on public, non-synthetic text, with honest coverage statements.
* Licence and terms compliance (generators, Bitext) (R-10).
* A reproducible, CI-enforced leakage and provenance regime.

## Considered Options

1. Family A train/val, Family B test_synth, human hard set split `hard_dev`/`hard_final`, pinned Bitext OOD, and the
   C1–C7 leakage regime in CI (chosen)
2. A random split from a single generator only

## Decision Outcome

Chosen option: "cross-family test + split hard set + Bitext OOD + CI leakage regime", because it is the only design
that separates task skill from generator style while keeping a sealed stress set and an OOD view.

| Split | Source | Size | Use |
|---|---|---|---|
| train | Family A / P-A | 3,600 (248 per non-critical label, 323 per critical intent, +1) | SFT, encoder |
| val | Family A / P-A (disjoint templates, seeds, pools) | 450 (`val_dev` = 225 of it) | thresholds, calibration, early stopping, seed choice |
| test_synth | Family B / P-B (scenario-first; gold from the scenario spec + 100% human review) | 1,045 (5 × 120 critical + 7 × 55 + 60 other_unclear) | headline |
| test_hard | owner-written, `llm_assisted=false` | 30 `hard_dev` + 70 `hard_final` (sealed until P10) | error analysis / headline |
| test_ood | Bitext CS + TEL (pinned revisions) | 400 strict + 50 P-H + 50 P-N | separate OOD table |
| e2e_scenarios | curated from test_synth + hard | 120 (items from `hard_dev` flagged `dev_exposed`) | E5 |

Leakage checks run on normalized `customer_text` (spec §9.3):

| Check | What it detects |
|---|---|
| C1 | exact duplicate |
| C2 | lexical near-duplicate (char-5 MinHash candidates verified by exact Jaccard ≥ 0.70) |
| C3 | embedding near-duplicate (pinned bge-small, calibrated τ_emb) |
| C4 | structural disjointness; any violation is a CI failure |
| C5 | copying of KB text |
| C6 | copying of protected strings |
| C7 | near-duplicates within train/val |

A cross-split flag always drops the **trainable** member. Test duplicates found before the freeze are replaced from
the same stratum; after the freeze, a split is immutable and changes are versioned (`.v2`, with E1–E6 re-run).

v0.2 training additions (from `hard_dev` error analysis) get stricter flags and an owner attestation that nothing was
paraphrased from test_hard.

### Consequences

* Good, because headline numbers resist generator-style inflation, and cross-family gaps become visible.
* Good, because `hard_final` stays sealed, so the stress numbers are not tuned on.
* Good, because OOD reporting is honest: macro-F1 over 5 mapped labels, P-H recall, P-N false positives, and an
  explicit "2 of 5 critical classes" caveat.
* Bad, because of workload (R-22): 1,045 test_synth records reviewed 100%, a 540-record audit, and a second
  annotator. Mitigation: start the review in parallel with P2, and report a one-volunteer fallback as such.
* Bad, because the hard set is small (70 sealed), so CIs are wide (L-06). Wilson/bootstrap CIs are always published.
* Neutral, because Bitext data is never committed. Pointers plus a build script satisfy CDLA-Sharing-1.0, and the
  optional HF dataset carries a NOTICE.

### Confirmation

* CI job `leakage` (on `data/**` or datagen changes, and nightly) passes only with:
  * zero C1–C3/C6 flags on trainable × protected pairs after actions;
  * zero C4 violations;
  * zero C5 hits in protected splits;
  * matching manifest hashes.

  Reports: `evals/reports/leakage_<date>.json` and `leakage_calibration_<date>.json`.
* `T-DATA-strata` (BR-038): quotas met (≥ 120 per critical class in test_synth; hard-set strata).
* `T-DATA-provenance` (S-12):
  * train/val only `openai_gpt_oss` or `human`;
  * test_synth only `deepseek` (or `mistral` if the documented alternative is used);
  * test_hard only `human` with `llm_assisted=false`;
  * test_ood only `public_bitext`;
  * no Anthropic family anywhere under `data/`.
* P1 exit: label-error Wilson upper bound < 5% (≤ 17/540), κ reported, protected splits frozen with manifest hashes
  verified on every CI run.
* `eval_count_on_split` is logged and published. Nightly never touches `hard_final` or test_synth (§9.10).

## Pros and Cons of the Options

### Cross-family + split hard set + Bitext OOD + CI regime

* Good, because it is credible and multi-angle, with a sealed stress set and enforced provenance and leakage checks.
* Bad, because of higher cost and review workload, and small-n caveats.

### Random split, single generator

* Good, because it is cheap and fast, with large test sets.
* Bad, because shared style and near-duplicates inflate metrics, and reviewers can't separate that from real skill.
  It fails the spirit of BR-038 and the reproducible-honesty claim.

## More Information

* Spec (private): §1.4, §9.1 (pipeline, label QA, OOD, provenance, terms), §9.2, §9.3 (splits, leakage C1–C7),
  §9.8, §9.10, §13 S-12, §16 P1, §20 L-01, L-06, L-07, §21 R-01, R-10, R-22. Change record A-10..A-13, A-27.
* Brief (private): §4, §9, §14. BR-016, BR-038.
* Research: [synthetic-data-generation](../research/synthetic-data-generation.md),
  [leakage-and-dedup](../research/leakage-and-dedup.md), [bitext-ood-dataset](../research/bitext-ood-dataset.md),
  [evaluation-statistics](../research/evaluation-statistics.md).
* Related ADRs: ADR-0031 (generator families), ADR-0032 (statistics), ADR-0008 (retrieval embedder independent of
  leakage), ADR-0029 (taxonomy).
* Revisit when: authorised de-identified real tickets become available, or the leakage report shows systematic
  cross-family overlap.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (generator families, sizes, hard-set
  split, label QA, leakage method, Bitext composition).
