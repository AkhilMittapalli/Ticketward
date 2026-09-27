---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §7.3, §8.6, §8.7, §8.9; research hybrid-retrieval, citation-verification
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0009: RRF fusion (k=60) plus ms-marco-MiniLM-L6-v2 cross-encoder reranking (retrieval only)

> **Amended in spec v1.1 (2026-09-27; change record A-14, A-15).**
> * Reranker id is now **`cross-encoder/ms-marco-MiniLM-L6-v2`** (the old `ms-marco-MiniLM-L-6-v2` id redirects),
>   Apache-2.0, pinned by HF revision, `max_length=512`, with the 20 pairs scored in one batch.
> * Its config uses an Identity activation, so `predict()` returns raw logits. The **sigmoid is applied explicitly**,
>   and **τ_ret is derived per reranker** in that sigmoid space (§7.3.1).
> * **Narrowed to retrieval.** Citation support and contradiction (abstention rule A3) move to the NLI verifier of
>   ADR-0033. This resolves the v1.0 "relevance is not support" and "A3 needs a contradiction score" issues this ADR
>   flagged.
> * RRF is unweighted, with 1-based ranks and a deterministic tie-break (best rank, then id).
> * CPU latency is **unverified until P5** (the only published figure is for a V100 GPU). Challengers now include
>   ModernBERT-based rerankers.

## Context and Problem Statement

Hybrid retrieval produces two ranked lists on different score scales: BM25 top-30 (ADR-0007) and vector top-30
(ADR-0008). They are fused, reranked, and cut to the top 5 chunks the drafter sees as numbered sources (§8.6, §8.7).

The top rerank score also gates the pipeline. Rule P9 fires when no approved chunk has sigmoid score ≥ τ_ret, and
the path becomes `human_escalation` with a "we'll check" template. The frontier is never selected (S-07).

Everything runs on CPU, and M-08 targets retrieval P95 ≤ 600 ms. Ablations (BM25, vector, RRF, RRF+rerank) must be
reported. In v1.0 the same cross-encoder also doubled as the citation verifier. The ERPROT citation research showed
that an MS MARCO model scores *relevance*, not *support*, and cannot produce the contradiction score A3 needs.

How should the two candidate lists be fused and reranked, and what should the reranker be used for?

## Decision Drivers

* Robust fusion across incomparable score scales, with no weight tuning on a small qrels set.
* Precision in the top 5 (the drafter's context), and a calibrated evidence gate (τ_ret).
* CPU latency: about 20 pairs within the retrieval budget.
* Permissive licence, pinned revision, safetensors, no remote code.
* A correct separation of concerns: relevance for retrieval, entailment for verification.

## Considered Options

1. RRF (k=60) + `cross-encoder/ms-marco-MiniLM-L6-v2`, used for retrieval only (chosen)
2. Weighted score fusion (normalised BM25 + cosine)
3. `BAAI/bge-reranker-v2-m3`
4. ModernBERT rerankers (`Alibaba-NLP/gte-reranker-modernbert-base`, `ibm-granite/granite-embedding-reranker-english-r2`)
5. No reranking (fusion only)

## Decision Outcome

Chosen option: "RRF (k=60) + MiniLM-L6 cross-encoder for retrieval", because RRF needs no normalisation or tuning.
The small cross-encoder reranks 20 candidates within the budget (to be measured) and gives a usable, per-reranker
calibrated evidence score.

Pipeline (spec §8.6):
1. filters as SQL predicates or `weight_mask`: `is_retrievable`, effective window, plan applicability with fallback;
   product-area soft boost +0.05;
2. BM25 top-30 and vector top-30;
3. RRF: `score = Σ 1/(k + rank)`, k = 60, unweighted, 1-based ranks, deterministic tie-break;
4. top-20 to the cross-encoder, scored in one batch;
5. explicit sigmoid, keep the top-5, compare with τ_ret.

Thresholds are **per reranker**. τ_ret is fitted in sigmoid space on val so that no-evidence val queries abstain
(M-07b), and stored in `policy_rule_sets.thresholds` with the justifying `eval_run_id` (§7.3.1). A reranker change
re-derives τ_ret.

**Challenger promotion (ablation A4 on `qrels_dev`):** a challenger (options 3–4) is promoted only if Recall@5 or
MRR@10 improves and P95 stays ≤ 600 ms.

**Verify at build (research `hybrid-retrieval`):** the pinned revision and licence. Measure CPU latency (torch fp32
vs ONNX qint8) on the reference box at P5.

### Consequences

* Good, because RRF is robust and rank-based. k = 60 was confirmed near-optimal in Cormack, Clarke & Büttcher (SIGIR
  2009).
* Good, because the reranker corrects bi-encoder and BM25 ordering errors in the top 20, improving Recall@1 and
  source precision.
* Good, because verification now has its own entailment model (ADR-0033). The relevance score is no longer
  misread as support.
* Bad, because the explicit sigmoid and a per-reranker τ_ret make swaps a two-step change (model plus threshold
  re-fit). This is intentional.
* Bad, because the CPU latency is unmeasured. If P95 > 600 ms at P5, ONNX qint8 or a smaller candidate set is the
  fallback. Degradation modes stay BM25-only or vector-only if one path fails (§7.7).

### Confirmation

* Ablations A1–A4 in the retrieval report, with M-05 per `doc_type` on `qrels_test`. Challenger decisions recorded
  from `qrels_dev`.
* Property test "RRF monotonicity" (§14.3). Unit tests: the RRF formula, 1-based ranks, deterministic tie-break,
  filters before scoring, and an explicit sigmoid (a test fixture asserts `predict()` output is transformed).
* M-08 retrieval P95 ≤ 600 ms (`make bench-latency`). P5 records the torch vs ONNX latency.
* Policy rule-set validation rejects an active rule set whose `tau_ret` lacks a `justified_by_eval_run_id` for the
  configured reranker (proposed).
* `/api/v1/health/ready` (API) and the worker health check report the reranker as loaded.

## Pros and Cons of the Options

### RRF + MiniLM-L6 cross-encoder (retrieval only)

* Good, because fusion needs no tuning, the reranker is small, and its role is now clean (relevance only).
* Bad, because its CPU latency must still be measured.

### Weighted score fusion

* Good, because it can beat RRF when weights are well tuned.
* Bad, because it needs score normalisation and weight tuning on about 150 dev queries. It is fragile when the
  corpus changes.

### bge-reranker-v2-m3

* Good, because it usually reranks better, and it is multilingual.
* Bad, because it is much larger (about 568M parameters, verify), so it threatens the 600 ms P95. Multilingual support
  is not needed (NG-07).

### ModernBERT rerankers

* Good, because they are modern, efficient encoders that may be better at similar cost.
* Bad, because they are unproven on our data. They enter only through the A4 promotion rule.

### No reranking

* Good, because it is the simplest and fastest option.
* Bad, because without a calibrated relevance score the P9 evidence gate and top-5 precision get worse. It also fails
  the brief's "reranker" (brief §6, BR-031).

## More Information

* Spec (private): §7.3 (P9, τ_ret), §7.3.1, §7.7, §8.6, §8.7 (cross-encoder no longer the verifier), §8.9, §9.8
  (M-05, M-07b, M-08). Change record A-14, A-15.
* Brief (private): §6. BR-031, BR-046.
* Research: [hybrid-retrieval](../research/hybrid-retrieval.md) (RRF, reranker id, sigmoid, latency),
  [citation-verification](../research/citation-verification.md) (why relevance ≠ support).
* Related ADRs: ADR-0007, ADR-0008, ADR-0010 (thresholds), ADR-0033 (citation verifier).
* Revisit when: a challenger passes the A4 promotion rule, or GPU serving makes a larger reranker cheap.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (renamed id, explicit sigmoid, per-
  reranker τ_ret, retrieval-only scope).
