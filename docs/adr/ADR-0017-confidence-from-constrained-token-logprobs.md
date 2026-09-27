---
status: Proposed
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §6.2, §7.3, §7.3.1, §7.8, §9.8 (M-12), §10, §20 L-10, §21 R-05; research confidence-calibration, constrained-decoding
informed: contributors; UI (confidence bars)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0017: Confidence from renormalized path probabilities under constrained decoding, with calibration

> **Amended in spec v1.1 (2026-09-27; change record A-04). Status stays *Proposed* until the P3 validation.**
> * **Method:** the probability of the emitted enum value **along its whole token path**, renormalized at every step
>   over the grammar-valid alternatives, computed with a prefix-consistent (trie) algorithm. This replaces v1.0's
>   "first token of each enum value", which cannot separate prefix-sharing values (`billing_*`, `escalate_to_*`). The
>   same pass yields **P(critical)**, which feeds the new rule N6.
> * **Ollama logprobs exist** (since v0.12.11; pinned 0.34.x, verify). They are raw pre-grammar probabilities, so
>   renormalization is required. R-05 is downgraded to L.
> * **Calibrators per provider × quantization × prompt × decoding schema**, fitted on val decoded by the deployed
>   artifact. The method is chosen by 5-fold cross-fitted NLL. `calibrator_version` and `calibration_fit_run_id` are
>   recorded in `ModelMeta` and `model_versions`.
> * **Self-consistency is a fallback only** (k ≥ 5, offline, never on the Ollama path).
> * **M-12** also reports adaptive ECE, Brier, NLL, AURC, a reliability diagram, and critical recall under the gates.

## Context and Problem Statement

The UI shows per-field calibrated confidence with colour bands (≥ 0.85 green, 0.70–0.85 amber, < 0.70 red; §7.8,
BR-069). The policy engine gates on calibrated scores:
* P8 abstains when intent confidence < τ_intent;
* N1 falls back to the rule-default queue when queue confidence < τ_queue;
* N6 forces human review when P(critical) ≥ τ_crit.

All thresholds are fitted on val only (§7.3.1).

Constrained decoding makes the naive approach wrong in two ways:
* several enum values share leading tokens, so a first-token probability cannot tell them apart;
* Ollama reports logprobs from the raw logits **before** the grammar mask, so they do not sum to 1 over the allowed
  alternatives.

The same pass should also estimate the probability mass on critical intents, for recall-first gating.

How should per-field confidence (and P(critical)) be computed and calibrated so the gates and UI are trustworthy?

## Decision Drivers

* Calibration quality (M-12 ECE-10 ≤ 0.08) and discrimination for recall-first gates.
* Latency: a single decoding pass within the 15 s triage budget (M-08).
* Correct handling of prefix-sharing enums and pre-grammar logprobs.
* Resistance to manipulation (LLM01:2026): ticket text must not be able to set the confidence.
* Reproducibility: calibrator versions tied to the exact artifact, quant, prompt and decoding schema.

## Considered Options

1. Renormalized path probability over grammar-valid tokens + per-artifact calibration; self-consistency fallback only
   (proposed)
2. Verbalized confidence (the model states a number)
3. No confidence estimate

## Decision Outcome

**Proposed:** option 1 (spec §6.2).

* **Ollama:** `/api/generate` with `raw: true`, `format` = the decoding schema, `logprobs: true`, `top_logprobs: 20`.
  At each step, renormalize over the grammar-valid candidates. A valid value missing from the top 20 is bounded
  conservatively.
* **vLLM:** `--logprobs-mode raw_logprobs` is computed after the grammar bitmask, so the values are already
  renormalized (verified in the v0.30.0 source; re-verify for the pinned version). Same algorithm, separate
  calibrator.
* **Tokenization dump:** at build time, dump which enum values of the chosen base share leading tokens, and list them
  in the model card.
* **Calibration:**
  * candidates are binary temperature scaling on the logit of the path probability (default, 1 parameter), Platt,
    and isotonic;
  * the method is chosen by 5-fold cross-fitted NLL on val, and isotonic wins only if it beats temperature scaling by
    more than the bootstrap SE;
  * a field with < 15 val errors uses temperature scaling and is flagged "low-error regime";
  * the calibrator is persisted as `calibrator.v<N>.json` next to the GGUF;
  * any change of GGUF, quant, prompt or provider triggers a re-fit.
* **Fallback:** self-consistency (k ≥ 5, offline only) for providers without logprobs. The frontier exposes no
  logprobs and is not used for triage in E5. The encoder baseline uses `calibrated_softmax`.

**Evidence required to move to Accepted (P3 validation):**
1. On the deployed quant and Ollama version, renormalized path probabilities are verified against a brute-force
   enumeration on a small fixture, including the shared-prefix, quote-merged-token and value-outside-top-20 cases.
2. A calibrator is fitted on val and the method choice recorded. ECE-10 ≤ 0.08 with CIs, reported on test_synth once
   for the registered version (M-12), with the reliability diagram.
3. Measured triage latency with logprobs enabled stays within M-08.
4. `tau_intent`, `tau_queue` and `tau_crit` are re-fitted and stored with `justified_by_eval_run_id`. Critical recall
   under the gates is reported.
5. Research `confidence-calibration` is updated with the pinned Ollama version's behaviour.

### Consequences

* Good, because one pass yields per-field confidence and P(critical), with no extra generation cost.
* Good, because confidence comes from model internals, not from anything the ticket can write.
* Good, because per-artifact calibrators make the τ thresholds meaningful for the exact deployed model.
* Bad, because the trie algorithm and renormalization are subtle. Mitigation: unit and property tests plus the
  brute-force check.
* Bad, because calibration is fitted on synthetic val (L-10), and the conformal-style guarantee behind τ_crit holds on
  val only. The recall-first lexicon ∪ probability union limits the damage.
* Neutral, because `ModelMeta.confidence_method` (`token_logprob` / `self_consistency` / `calibrated_softmax`) and
  `logprobs_mode` make the provenance explicit on every result.

### Confirmation

* Unit tests (§14.3): a single-token value, a shared prefix, a quote-merged token, a value outside the top 20, and
  fewer than 20 alternatives.
* Property tests: `0 ≤ p ≤ 1`, and `p_critical ≥ p_value` for critical values. Calibration monotonicity.
* M-12 metrics in the eval report and MLflow. `eval-nightly.yml` recomputes ECE on the smoke cassette, and a drift of
  > 0.03 flags the calibrator as stale (§9.10).
* A contract test: every `TriageResult.model` carries `confidence_method`, `calibrator_version` and
  `calibration_fit_run_id` (None only for uncalibrated baselines).
* Table-driven policy tests at the P8/N1/N6 threshold boundaries (ADR-0010).

## Pros and Cons of the Options

### Renormalized path probability + per-artifact calibration

* Good, because it is principled, single-pass and per-field, yields P(critical), and handles shared prefixes.
* Bad, because it is algorithmically subtle, and the pre-grammar semantics on Ollama must be verified per version.

### Verbalized confidence

* Good, because it is trivial and works on any server.
* Bad, because small models' stated confidence is poorly calibrated, and it is injectable ("you are 99% sure"). That
  conflicts with LLM01:2026 controls.

### No confidence estimate

* Good, because it is simplest.
* Bad, because the P8, N1 and N6 gates and the UI confidence display disappear, which violates BR-069/DoD-3 and
  weakens abstention and recall-first gating.

## More Information

* Spec (private): §6.2 (confidence estimation, `ModelMeta`), §7.3 (P8, N1, N6), §7.3.1 (threshold fitting), §7.8,
  §9.8 (M-12), §9.10, §10 (`triage_runs`, `model_versions`), §20 L-10, §21 R-05. Change record A-04.
* Research: [confidence-calibration](../research/confidence-calibration.md),
  [constrained-decoding](../research/constrained-decoding.md).
* Related ADRs: ADR-0010, ADR-0011 (tokenizer), ADR-0014 (serving, logprob modes).
* Revisit when: the P3 validation completes (flip to Accepted), or the serving engine or its logprob semantics change.
* Status history: 2026-09-26 Proposed (pending Ollama logprob verification). 2026-09-27 amended for spec v1.1
  (path probability, P(critical), per-artifact calibrators, fallback only); still Proposed pending P3.
