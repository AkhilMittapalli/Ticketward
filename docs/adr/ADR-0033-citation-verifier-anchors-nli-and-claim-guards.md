---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §6.3, §7.2, §7.6 (A3), §7.7, §8.7, §8.9, §9.8 (M-06), §12.4 (LLM07:2026), §13 S-04..S-07; research citation-verification
informed: contributors; agents (struck-out and contradicted sentences in the UI)
supersedes: none
amended: none
---

# ADR-0033: Citation verifier: lexical anchors + 3-class NLI + claim guards

## Context and Problem Statement

Every factual or procedural sentence in a draft must cite an approved source (S-07). Pricing, refund eligibility,
account status, incident status, capabilities and timing must never be invented (S-04..S-06; LLM07:2026
Misinformation). M-06 requires citation-support precision ≥ 0.90 (automatic) and ≥ 0.85 (human audit).

v1.0 used the retrieval cross-encoder (`ms-marco-MiniLM`) as an "NLI-lite" verifier, with sigmoid ≥ 0.5 counting as
supported. The ERPROT citation research showed this measures **relevance, not support**: the model was trained to
sort passages for a query. It cannot produce the contradiction score that abstention rule A3 needs, and it would pass
topically related but unsupported claims (for example "$18" where the chunk says "$16").

How should each drafted sentence be checked against its cited chunks, and how is conflicting evidence detected?

## Decision Drivers

* Precision of "passes verifier" (the M-06 base) over recall. A human reviews everything anyway (S-01).
* Deterministic handling of the claims that matter most: numbers, codes, prices and dates.
* A real contradiction signal for A3 and for flagging contradicted sentences.
* Licence (no non-commercial), no remote code (ASVS/A08), and CPU latency (P95 ≤ 3 s per draft).
* Thresholds calibrated on data separate from the M-06 audit (no tuning on the reporting set).

## Considered Options

1. Layered verifier: L0 structure → L1 lexical anchors → L2 3-class NLI (`cross-encoder/nli-deberta-v3-base`) → L3
   doc-type claim guards → L4 human (chosen)
2. MS MARCO cross-encoder (relevance only; the v1.0 approach)
3. FactCG (`yaxili96/FactCG-DeBERTa-v3-Large`) as the L2 model
4. MiniCheck (`lytang/MiniCheck-Flan-T5-Large` and variants)
5. AlignScore
6. HHEM-2.1-Open
7. Bespoke-MiniCheck-7B
8. An LLM judge

## Decision Outcome

Chosen option: the layered verifier (spec §8.7), because it combines deterministic checks for the high-risk tokens,
a genuine entailment/contradiction model, and doc-type-aware guards. Each layer catches what the others miss.

| Layer | Check | Failure effect |
|---|---|---|
| L0 structure | `citation_ids` non-empty for `factual`/`procedural`; indices 1..5; mapped to `chunk_id` | removed, counted unsupported |
| L1 anchors | every money amount, percentage, error code and number with ≥ 2 digits appears (whitespace/comma-insensitive) in a cited chunk | unsupported |
| L2 3-class NLI | `cross-encoder/nli-deberta-v3-base` (Apache-2.0, pinned revision; **label order read from `config.id2label`, never hard-coded**; softmax applied explicitly). The premise is each 3-sentence window (stride 1) of the cited chunk(s), plus their concatenation when it fits 512 tokens; `entail = max P(entailment)`, `contra = max P(contradiction)`. Supported iff `entail ≥ τ_entail` | unsupported; flagged *contradicted* if `contra ≥ τ_contra` and `entail < τ_entail` |
| L3 claim guards | regex guards run on **every** sentence, including empathy, holding and question kinds | strip, flag, or force the holding template |
| L4 human | the draft is always reviewed; struck-out and contradicted sentences stay visible | – |

**Claim-guard rules (doc-type aware):**

| Claim | Allowed only when |
|---|---|
| Pricing | a cited `policy_pricing_and_plans` chunk, and L1 matches |
| Refund eligibility | **never** (forces `holding_reply_template`) |
| Account status | **never** |
| Incident status | the cited chunk is the matched `known_incident` record, and the status word equals its `incident_meta.status` |
| Capability | a `product_doc`/`help_article` citation that L2 supports |
| Timing (`claims_timing_without_source`) | a `policy_sla` citation |
| URLs | the URL resolves to a KB `url_slug` (else stripped, `contains_url_not_in_kb`) |

Negations and hedges ("a billing specialist will review your refund request") must not fire.

**A3 conflicting evidence (rule P9):** among the top-5 reranked chunks, pairs with the same `doc_type` and overlapping
`product_areas` are scored with the NLI model in both directions over sentence windows. There is a conflict if
`max P(contradiction) ≥ τ_conflict` (initial 0.7, calibrated on about 50 synthetic conflicting/consistent pairs built
from the adversarial seed docs).

**Calibration (P6):**
* about 300 (sentence, cited chunk) pairs from `val_dev` drafts (local and frontier), stratified by guard type and
  doc_type, with risky kinds oversampled;
* labelled supported / partially_supported / unsupported / contradicted, with two annotators on a 60-pair overlap
  (Cohen's κ);
* `τ_entail` = the smallest threshold with precision of "passes verifier" ≥ 0.95 (partial counts as unsupported);
* `τ_contra` gives contradicted recall ≥ 0.9;
* **thresholds are frozen before the M-06 audit and never re-tuned on it.** Re-calibrate when the draft model, prompt
  or verifier changes.

**Model selection (P6):** L2 is chosen by AUROC for "unsupported" on the calibration set, subject to verification
P95 ≤ 3 s per draft on the reference box.
* Challengers: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` (MIT; a different label order),
  `tasksource/deberta-small-long-nli`, FactCG-DeBERTa-v3-Large (MIT; label semantics to verify), and MiniCheck
  variants (MIT).
* CPU latency is **unverified** for every candidate and must be measured.
* Budget behaviour: sentences not verified within the 3 s stage budget count as unsupported (§7.7). If more than 30%
  of sentences are removed, the draft falls back to clarifying mode.

**Storage:**
* `draft_citations.support_score` = the L2 entail value;
* `contra_score` and `verdict` ∈ {supported, unsupported, contradicted} are recorded;
* the whole draft is verified in one batched call in a bounded thread.

### Consequences

* Good, because "$18" vs "$16"-class errors are caught deterministically (L1), before any model runs.
* Good, because contradiction is now a real signal. It drives A3 escalation and a "contradicted" label in the UI.
* Good, because thresholds come from a separate labelled set, so M-06 remains an honest measurement.
* Bad, because there is an extra model in the worker (CPU and memory), whose latency is unmeasured until P6. The 3 s
  budget with fail-closed "unsupported" bounds the impact.
* Bad, because NLI models misread long or multi-hop premises. Windowing and concatenation help, and humans review
  every draft (L4).
* Neutral, because an optional frontier LLM judge (masked) may be reported separately. It never replaces the human
  audit, and its labels never train anything (ADR-0031).

### Confirmation

* Unit tests: L1 anchors ("$18" vs "$16"; percentages; error codes); **label order read from `config.id2label`**,
  tested with a fixture model whose order differs; explicit softmax; guard positives and negatives, including hedges
  and negations.
* Property test (§14.3): no sentence with an unmatched number is ever marked supported.
* Eval smoke: verifier decisions match golden on the fixture (§9.10). `T-GUARD-claims` covers every guard.
* The calibration report: κ on the 60-pair overlap, τ values with CIs, thresholds frozen with an `eval_run_id`.
* M-06: automatic ≥ 0.90 (draft-cluster bootstrap), and human ≥ 0.85 on 250 shown sentences (Wilson), plus κ,
  PABAK and Gwet's AC1 (ADR-0032).
* P6 latency measurement: verification P95 ≤ 3 s per draft on the reference box, recorded.

## Pros and Cons of the Options

### Layered verifier with nli-deberta-v3-base (chosen)

* Good, because it combines deterministic anchors, a true NLI signal (entail and contradict), doc-type guards, and a
  permissive licence.
* Bad, because of the extra model latency, and the label-order and premise-length pitfalls (handled explicitly).

### MS MARCO cross-encoder (v1.0)

* Good, because it was already loaded for reranking, at no extra cost.
* Bad, because it scores relevance, not support, and has no contradiction output. That fails A3 and inflates M-06.

### FactCG-DeBERTa-v3-Large

* Good, because it is grounding-specialised, with strong published results (MIT).
* Bad, because it is larger (about 0.4B) with label semantics to verify. It remains a P6 challenger.

### MiniCheck (Flan-T5-Large and variants)

* Good, because it is grounding-specialised (MIT).
* Bad, because it is heavier on CPU. It remains a P6 challenger.

### AlignScore

* Good, because it is a well-known factual-consistency scorer.
* Bad, because it recommends an old PyTorch stack, which conflicts with the pinned dependencies.

### HHEM-2.1-Open

* Good, because it is a hallucination-evaluation model.
* Bad, because it needs `trust_remote_code=True`, which conflicts with the no-remote-code rule.

### Bespoke-MiniCheck-7B

* Good, because it is highly accurate on grounding benchmarks.
* Bad, because it is CC BY-NC 4.0 (non-commercial) and 7B on CPU.

### LLM judge

* Good, because it is flexible and strong on paraphrase.
* Bad, because it is slow and costly, sends drafts to a vendor, is nondeterministic, and cannot be the primary gate.
  It is allowed only as a separately reported secondary measure.

## More Information

* Spec (private): §6.3 (`guard_flags`, `claims_timing_without_source`), §7.2 (routine path), §7.6 (A3), §7.7 (3 s
  budget), §8.7 (layers, guards, model selection, calibration), §8.9 (audit design), §9.8 (M-06), §12.4, §13
  S-04..S-07, §14.3. Change record A-15.
* Research: [citation-verification](../research/citation-verification.md).
* Related ADRs: ADR-0009 (reranker is retrieval-only), ADR-0010 (P9/A3), ADR-0032 (audit statistics), ADR-0031 (judge
  outputs never train).
* Revisit when: P6 model selection picks a challenger (amend), M-06 misses its target, or CPU latency exceeds the
  budget.
* Status history: 2026-09-27 Accepted (new in spec v1.1, change record A-15). The L2 model is confirmed or replaced
  at P6 by the procedure above.
