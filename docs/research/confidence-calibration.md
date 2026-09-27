# Confidence Estimation & Calibration - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: September 26, 2026
**Last Updated**: September 26, 2026
**Status**: Partially resolved
**Status Note**: Q1 (Ollama logprobs) and Q2 (alternatives) are resolved from source code. Q3 and Q4 (method, ECE) are decided. Q5 threshold *values* need the P3 validation outputs; the procedure is decided.
**Category**: ML / Uncertainty, calibration & gating
**Linked ADR(s)**: ADR-0017 (confidence via constrained-token logprobs + calibration; self-consistency fallback), ADR-0010 (policy engine; thresholds as data), ADR-0014 (serving)
**Spec sections**: §6.2 (FieldConfidence, `confidence_method`, confidence estimation 1–3), §7.3 (P8 τ_intent, N1 τ_queue, recall-first design), §7.7 (triage budget 15 s), §9.8 M-03c/M-07/M-12, §20 L-10, §21 R-05, §23

---

## EXECUTIVE SUMMARY

**Ollama exposes token logprobs today.**
- Supported since **v0.12.11 (2025-11-12)**: `logprobs: true` and `top_logprobs: 0–20` on `/api/generate` and `/api/chat`. The current release is v0.34.4.
- Logprobs work together with `format` (constrained decoding), including `raw: true`.
- A llama.cpp-server adapter is **not** needed for logprobs. Spec risk R-05 is mitigated.

**The semantics matter.**
- **Ollama and llama.cpp** compute returned probabilities from a softmax over the **raw logits**. They are taken before the grammar mask and before temperature, because Ollama never sets `post_sampling_probs`.
- **vLLM** applies the grammar bitmask to the logits *before* computing its default `raw_logprobs`. Its probabilities are therefore renormalized over grammar-valid tokens.
- The same model can report different confidences on different providers. **A calibrator is valid only for the provider + quantization + prompt it was fitted on.**

**"First token of each enum value" (spec §6.2) is not enough.**
- Enum values share prefixes, e.g. `billing_duplicate_charge` and `billing_payment_failure`, which are both critical. BPE tokens can also span the opening quote.
- Recommendation: a **prefix-consistency (trie) path probability**, renormalized over grammar-valid alternatives from `top_logprobs`.
- The same pass yields a **P(any critical intent)** score for recall-first gating.

**Calibration method.**
- Primary: **1-parameter temperature scaling** on the logit of the path probability (top-label, binary correctness), fitted on val.
- Compare against Platt (2 parameters) and isotonic using 5-fold cross-fitting on val.
- Isotonic is not the default. scikit-learn warns it overfits below about 1,000 samples, and val has only n = 450.

**ECE.**
- 10 equal-width bins, top-label (the Naeini 2015 definition, as in spec M-12).
- Also report adaptive-bin ECE, Brier, NLL, AURC and a reliability diagram, each with bootstrap 95% CIs. With a fine-tuned model near 95% accuracy, ECE ≤ 0.08 is easy to meet and says little on its own.

**Recall-first gating.**
- Add a **probability union** to the lexicon union: escalate if `P(critical) ≥ τ_crit`.
- τ_crit is set by class-conditional split-conformal logic on val. With about 40 val tickets per critical class, taking τ at the minimum observed score gives a marginal recall guarantee of ≥ n/(n+1) ≈ 0.976, *under exchangeability*. That assumption breaks from val (Family A) to test (Family B), so test is reported empirically.

**Self-consistency** (k = 3, T = 0.7) costs about 3× CPU decode time and yields only 3 confidence levels. Keep it only for providers without logprobs.

---

## SPEC IMPACT (owner action required; spec not edited)

| ID | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §6.2 item 1 "Ollama logprob support is **verified at build time**"; §21 R-05 | Ollama added logprobs in v0.12.11 (2025-11-12): "Ollama's API and OpenAI-compatible API now support log probabilities". `top_logprobs` is validated 0–20 in v0.34.4 source. | Mark it resolved. The Ollama path uses `confidence_method="token_logprob"`. Downgrade R-05 to "L". Keep the llama.cpp-server adapter optional (for `n_probs` > 20). |
| SI-2 | §6.2 item 1 "token logprob of the first token of each enum value" | Shared prefixes (`billing_*`, `escalate_to_*`, `forced_*`) and quote-merged tokens make first-token probabilities ambiguous. llama.cpp logprobs are pre-grammar, so they must be renormalized over valid tokens. | Replace with "path probability of the emitted value, renormalized over grammar-valid alternatives (prefix-consistency algorithm, `top_logprobs=20`)". |
| SI-3 | §6.2 `ModelMeta` | Confidence depends on provider semantics, quantization and prompt. | Add `calibrator_version: str` and `calibration_fit_run_id: UUID` to `ModelMeta`, and record them in `model_versions`. Re-fit on every change of GGUF, quant, prompt or provider. |
| SI-4 | §6.2 item 2 "self-consistency, k=3 samples at T=0.7" | This is 3× decode time within a 15 s CPU triage budget (§7.7). It gives 3 discrete confidence levels, which makes a 10-bin ECE degenerate. | Use it only when logprobs are unavailable. If used offline, k ≥ 5. Never the default on the Ollama path. |
| SI-5 | §9.8 M-12 "10-bin ECE of intent confidence ≤ 0.08" | ECE is bin-sensitive (Nixon et al. 2019), and scaling calibrators are "less calibrated than reported" (Kumar et al. 2019). At high accuracy, ECE is dominated by the top bin. | Keep M-12. Also report adaptive ECE, Brier, NLL, AURC (risk–coverage), a reliability diagram, and critical recall *under the chosen gates*, all with bootstrap CIs. |
| SI-6 | §7.3 recall-first design "model ∪ lexicon" | The model only contributes through its argmax. | Add a rule to P2–P5 detection: `P(critical intent) ≥ τ_crit` (model probability) ∪ argmax ∪ lexicon. τ_crit is stored in `policy_rules` with its `eval_run_id`. This is a policy change and needs an ADR. |
| SI-7 | §6.2 item 3 "temperature scaling or isotonic regression fitted on the validation split" | n = 450, and a good SFT model makes only tens of errors on val, so fits are high-variance. | Use 5-fold cross-fitting on val to choose among TS, Platt and isotonic, with the default TS. Report the ECE CI. |

---

## QUESTIONS (from SPEC §23)

1. Does Ollama expose token logprobs for structured output in the current version?
2. What are the llama.cpp and vLLM alternatives?
3. Temperature scaling or isotonic regression?
4. How is ECE computed?
5. What thresholds should recall-first gating use?

---

## FINDINGS

### Q1. Ollama logprobs with structured output

**Availability**

- The v0.12.11 release notes (2025-11-12) say: "Ollama's API and OpenAI-compatible API now support log probabilities"; `"logprobs": true`; and `"top_logprobs"` "a number of most-likely tokens are also provided" ([release](https://github.com/ollama/ollama/releases/tag/v0.12.11), accessed 2026-09-26).
- API docs:
  - request: `logprobs`, "Whether to return log probabilities of the output tokens", and `top_logprobs`, "Number of most likely tokens to return at each token position";
  - response entries: `token`, `logprob`, `bytes` and `top_logprobs`.
  - Source: [generate](https://docs.ollama.com/api/generate), [chat](https://docs.ollama.com/api/chat).
- Limits in the v0.34.4 source:
  - `api/types.go`: "Valid values are 0-20. Default is 0 (only return the selected token's logprob)".
  - `server/routes.go`: `if req.TopLogprobs < 0 || req.TopLogprobs > 20 { … "top_logprobs must be between 0 and 20" }`.
- The Python client supports `generate(..., logprobs=..., top_logprobs=..., raw=..., format=...)` since `ollama-python` v0.6.1 (2025-11-13, "client/types: add logprobs support") ([_client.py](https://github.com/ollama/ollama-python/blob/main/ollama/_client.py)).

**How Ollama ≥ 0.30 computes them**

It forwards to llama-server ([llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go), accessed 2026-09-26):

- completion path: `if req.Logprobs { lsReq.NProbs = max(req.TopLogprobs, 1) }`;
- chat path: `body["logprobs"] = true; body["top_logprobs"] = max(req.TopLogprobs, 1)`;
- `post_sampling_probs` is **never set**.

llama-server's behaviour:

- With `post_sampling_probs` false, `populate_token_probs` calls `get_token_probabilities(ctx, idx, n_probs)`. That function reads `llama_get_logits_ith`, sorts by logit, and applies softmax. It does not look at the grammar sampler ([server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp), [server-common.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp), accessed 2026-09-26).
- The llama-server README adds that for greedy sampling "token probabilities are still being calculated via a simple softmax of the logits without considering any other sampler settings" ([README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)).

**⇒ Ollama logprobs are the model's unconstrained, temperature-1 next-token distribution.** Probability mass on grammar-invalid tokens is included.

**Known limitations and inconsistencies**

- [ollama#18579](https://github.com/ollama/ollama/issues/18579) (2026-09-22): "logprobs/top_logprobs can only report tokens that rank within the model's top-K guesses".
- The proposed fix [PR #18580](https://github.com/ollama/ollama/pull/18580) (`logprob_tokens`) was closed in favour of "raising the top_logprobs cap". The API may change; re-check at build.
- [ollama#16117](https://github.com/ollama/ollama/issues/16117) (2026-05-12, closed "not planned") says `/v1/chat/completions` lacks logprobs, which contradicts the v0.12.11 notes. **Use the native `/api/generate`.**
- `cache_prompt` (always on in Ollama): "enabling this option can cause nondeterministic results" because batch sizes differ between prompt processing and generation (llama-server README). Expect tiny logprob jitter between cached and uncached runs.

### Q2. Alternatives

**llama.cpp `llama-server` directly**

- `n_probs` (any N) and `post_sampling_probs` ("Returns the probabilities of top `n_probs` tokens after applying sampling chain") ([README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)).
- The post-sampling candidates are grammar-masked only when the rejection-sampling path triggered (`common/sampling.cpp`), and greedy sampling makes them degenerate. **Use the raw mode and renormalize yourself.** The advantage over Ollama is N > 20.

**vLLM**

- `logprobs_mode` supports `raw_logprobs` (default), `processed_logprobs`, `raw_logits` and `processed_logits`. "Raw means the values before applying any logit processors, like bad words. Processed means the values after applying all processors, including temperature and top_k/top_p" ([engine args](https://docs.vllm.ai/en/stable/configuration/engine_args/), accessed 2026-09-26).
- In `vllm/v1/worker/gpu_model_runner.py` (`sample_tokens`), `apply_grammar_bitmask(...)` modifies the logits **before** `self._sample(logits, …)`, and the sampler computes `raw_logprobs = self.compute_logprobs(logits)` from those masked logits ([source](https://github.com/vllm-project/vllm/blob/main/vllm/v1/worker/gpu_model_runner.py), accessed 2026-09-26).
- **⇒ vLLM's default logprobs are renormalized over grammar-valid tokens and are not temperature-scaled.** This is an inference from code order. **UNVERIFIED** empirically; test with a 2-value enum.
- vLLM also offers `prompt_logprobs`, and `logprob_token_ids` (Model Runner V2 support in v0.21.0; exposed on the Python OpenAI endpoints in v0.26.0, per the [release notes](https://github.com/vllm-project/vllm/releases)). With these, exact per-class probabilities can be scored on GPU (production path).

**Self-consistency**

k samples at T = 0.7 multiply decode cost by k. The CPU triage budget is 15 s (§7.7), and M-08 wants P50 ≤ 5 s.

### Q3. Temperature scaling vs isotonic

- **Guo et al. 2017, ICML** ([arXiv:1706.04599](https://arxiv.org/abs/1706.04599)): "temperature scaling — a single-parameter variant of Platt Scaling — is surprisingly effective".
- **scikit-learn** ([calibration guide](https://scikit-learn.org/stable/modules/calibration.html), accessed 2026-09-26):
  - sigmoid "is most effective for small sample sizes";
  - isotonic is "more prone to overfitting on small datasets" and "will perform as well as or better than 'sigmoid' when there is enough data (greater than ~ 1000 samples)";
  - `CalibratedClassifierCV(method="temperature")` was added in **scikit-learn 1.8** ([v1.8 changelog](https://scikit-learn.org/stable/whats_new/v1.8.html)); its advantage is "calibrated multi-class probabilities with just one free parameter";
  - `FrozenEstimator` wraps an already-fitted model;
  - the current version is 1.9.1 (PyPI, accessed 2026-09-26).
- **Kumar, Liang & Ma, NeurIPS 2019** ([arXiv:1909.10155](https://arxiv.org/abs/1909.10155)): Platt and temperature scaling "are (i) less calibrated than reported, and (ii) current techniques cannot estimate how miscalibrated they are". Histogram binning needs O(B/ε²) samples. The proposed **scaling-binning calibrator** needs O(1/ε² + B).
- **Our constraint:** we have only the *path probability of the emitted value* and partial branch distributions, not a full softmax over 13 intents. Multi-class TS therefore does not apply directly. Use **binary (top-label) TS**, i.e. `sigmoid(logit(p)/T)`, or Platt, i.e. `sigmoid(a·logit(p)+b)`.
- The **E2 encoder baseline** *does* have a full softmax, so sklearn `method="temperature"` applies to it directly (`confidence_method="calibrated_softmax"`).

### Q4. ECE computation

- **Definition** (Naeini, Cooper & Hauskrecht, AAAI 2015, [PMC4410090](https://pmc.ncbi.nlm.nih.gov/articles/PMC4410090/)): "ECE = Σᵢ P(i)·|oᵢ − eᵢ|" and "MCE = maxᵢ |oᵢ − eᵢ|", with predictions partitioned into K = 10 bins.
- **Pitfalls** (Nixon et al. 2019, [arXiv:1904.01685](https://arxiv.org/abs/1904.01685)):
  - the ECE metric "has numerous flaws";
  - bin count changes conclusions;
  - "Adaptive binning schemes lead to more stability of metric rank ordering";
  - class-conditional evaluation is more informative.

### Q5. Thresholds for recall-first gating

- **Selective classification** (Geifman & El-Yaniv 2017, [arXiv:1705.08500](https://arxiv.org/abs/1705.08500)): a reject option trades coverage for risk. A threshold can be chosen "to guarantee a desired risk with high probability".
- **Split conformal prediction** (Angelopoulos & Bates, [arXiv:2107.07511](https://arxiv.org/abs/2107.07511); [HTML](https://arxiv.org/html/2107.07511v6)):
  - quantile q̂ = Quantile(s₁…sₙ, ⌈(n+1)(1−α)⌉/n) gives P(Y_test ∈ C(X_test)) ≥ 1 − α under exchangeability;
  - §4.2 "Class-Conditional Conformal Prediction" gives coverage "on *every* ground truth class".
- **Arithmetic from that formula:** with n calibration examples, α = 1/(n+1) is the smallest achievable level. It corresponds to thresholding at the most extreme observed score, giving coverage ≥ n/(n+1). For n = 40 that is ≈ 0.976.
- **Exchangeability** holds within Family-A val. It does **not** hold for Family-B test_synth or the hard set (L-06, L-10), so the guarantee is for val-like data only and test results are reported empirically.

---

## DECISION / RECOMMENDATION

### 1. Extract confidences from Ollama (`/api/generate`, `raw: true`, `format`, `logprobs: true`, `top_logprobs: 20`)

Reference algorithm: `backend/src/ticketward/ml/confidence.py`. It is pure and unit-testable. It handles shared prefixes, quote-merged tokens and pre-grammar mass.

```python
import math
from dataclasses import dataclass

@dataclass(frozen=True)
class Tok:
    text: str                                   # Ollama logprobs[i].token (use bytes for partial UTF-8)
    logprob: float                              # chosen token logprob (raw, pre-grammar)
    top: tuple[tuple[str, float], ...]          # logprobs[i].top_logprobs as (token, logprob)

def enum_value_probability(toks: list[Tok], value_start: int, allowed: list[str], emitted: str,
                           critical: frozenset[str] = frozenset()) -> tuple[float, float]:
    """(p_value, p_critical) for one enum field of the generated JSON.

    value_start = char offset of the first value character (just after the opening quote);
    locate it with the key pattern '"<field>":"' (safe: JSON strings escape quotes; keys are unique and
    order is fixed by the decoding schema). Alternatives are renormalised over grammar-valid tokens
    (those whose text keeps the output a prefix of '<head><value>"' for a still-possible value).
    """
    text = "".join(t.text for t in toks)
    head = text[:value_start]
    target = {v: head + v + '"' for v in allowed}
    starts, pos = [], 0
    for t in toks:
        starts.append(pos); pos += len(t.text)

    def cons(ctx: str, tok: str, alive: frozenset[str]) -> frozenset[str]:
        s = ctx + tok
        return frozenset(v for v in alive if target[v].startswith(s) or s.startswith(target[v]))

    alive, p_value, carry, p_crit = frozenset(allowed), 0.0, 1.0, None
    for i, t in enumerate(toks):
        if starts[i] + len(t.text) <= value_start:
            continue
        ctx = text[: starts[i]]
        alts = dict(t.top); alts.setdefault(t.text, t.logprob)          # chosen token always counted
        groups = [(math.exp(lp), cons(ctx, tok, alive), tok == t.text) for tok, lp in alts.items()]
        groups = [g for g in groups if g[1]]                              # grammar-valid only
        floor = math.exp(min(lp for _, lp in t.top)) if len(t.top) >= 20 else 0.0
        unseen = alive - frozenset().union(*(vs for _, vs, _ in groups))  # valid values not in top-20
        denom = sum(m for m, _, _ in groups) + floor * len(unseen)        # conservative upper bound
        if p_crit is None:                                                # first decision point
            p_crit = (sum(m for m, vs, _ in groups if vs & critical)      # mixed branches count as critical
                      + floor * len(unseen & critical)) / denom
        p_value += carry * sum(m for m, vs, ch in groups if not ch and vs == {emitted}) / denom
        chosen_mass = next(m for m, _, ch in groups if ch)
        carry *= chosen_mass / denom
        alive = cons(ctx, t.text, alive)
        if alive == {emitted}:
            p_value += carry
            break
    return p_value, (p_crit if p_crit is not None else float(emitted in critical))
```

Notes:

- `p_value` is a *lower bound* on P(emitted value). Mass on non-chosen tokens that could still lead to the emitted value, but also to other values, is not credited.
- `p_crit` is an *upper-leaning* P(any critical intent), which suits recall-first gating.
- Apply it to `intent`, `priority`, `sentiment`, `churn_risk`, `product_area` and `recommended_queue` (the `FieldConfidence` fields). Each `secondary_intents` element is handled the same way, with its offset found after `[` or `,`.
- Unit tests must cover:
  - a single-token value;
  - a shared prefix (`billing_*`);
  - a quote-merged token (e.g. token `":"b`);
  - a chosen token absent from top-20 (zero-shot);
  - `top_logprobs` fewer than 20.
- At build time, dump the tokenization of all enum values in context (`'"intent":"' + v + '"'`) with the chosen tokenizer. List the shared first tokens in the model card (**UNVERIFIED** today: exact tokenization depends on the chosen base).

### 2. Calibrator

- **Fit data:** val (n = 450), decoded by the **deployed artifact**: the same GGUF quant, Ollama version, raw prompt and decoding schema. Never HF fp16 outputs for a Q4 deployment. Never test data.
- **Features:** `z = logit(clip(p_value, 1e-6, 1-1e-6))` per field. Target: `correct = (emitted == gold)`.
- **Candidates:**
  - (a) binary TS, `σ(z/T)`, 1 parameter, the default;
  - (b) Platt, `σ(a·z + b)`;
  - (c) isotonic (`sklearn.isotonic.IsotonicRegression(out_of_bounds="clip")`).
- **Selection:** 5-fold cross-fitted NLL on val, with the out-of-fold ECE reported. Choose isotonic only if its CV-NLL beats TS by more than the bootstrap SE (it is unlikely at n = 450).
- If a field has fewer than 15 val errors, use TS and flag "low-error regime".
- **Persist** `{field: {method, params}}` as `calibrator.v<N>.json`, alongside the GGUF in the HF repo. Record its sha256 in `model_versions` together with `calibrator_version` (SI-3).

```python
import numpy as np
from scipy.optimize import minimize_scalar

def fit_binary_temperature(p: np.ndarray, correct: np.ndarray) -> float:
    z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    def nll(log_t: float) -> float:
        q = 1.0 / (1.0 + np.exp(-z / np.exp(log_t)))
        q = np.clip(q, 1e-9, 1 - 1e-9)
        return float(-np.mean(correct * np.log(q) + (1 - correct) * np.log(1 - q)))
    return float(np.exp(minimize_scalar(nll, bounds=(-4.0, 4.0), method="bounded").x))
```

### 3. ECE and companion metrics (`tw_ml/eval/calibration.py`)

```python
def ece(conf, correct, n_bins: int = 10, adaptive: bool = False) -> float:
    conf, correct = np.asarray(conf, float), np.asarray(correct, float)
    edges = np.quantile(conf, np.linspace(0, 1, n_bins + 1)) if adaptive else np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.searchsorted(edges, conf, side="right") - 1, 0, n_bins - 1)   # last bin closed at 1.0
    return float(sum((idx == b).mean() * abs(correct[idx == b].mean() - conf[idx == b].mean())
                     for b in range(n_bins) if (idx == b).any()))
```

- **Report per split** (val out-of-fold, test_synth, test_hard):
  - ECE-10 (the M-12 gate, ≤ 0.08 on test_synth) and adaptive ECE-10;
  - MCE, Brier (`sklearn.metrics.brier_score_loss`), NLL (`log_loss`);
  - AURC plus the risk–coverage curve;
  - a reliability diagram (`sklearn.calibration.calibration_curve`, strategy "uniform" and "quantile");
  - bootstrap 95% CIs (1,000 resamples, spec §9.8).
- Cross-check `ece()` against `torchmetrics.classification.MulticlassCalibrationError(norm="l1", n_bins=10)` in a unit test. Use top-label on a synthetic fixture.

### 4. Thresholds (fit on val; stored in `policy_rules` with `eval_run_id`)

- **τ_crit (new, SI-6), the probability union for forced categories.**
  - Choose it as the minimum `p_crit` over val tickets whose gold primary *or* secondary intent is critical.
  - Under exchangeability this gives ≥ N/(N+1) marginal recall (N ≈ 200 critical val tickets → ≥ 0.995). The per-class view (Mondrian) gives ≥ n_c/(n_c+1) ≈ 0.976 at n_c ≈ 40.
  - Report the added over-escalation on routine val tickets (M-07c).
  - If over-escalation exceeds 0.15, raise τ_crit only as far as critical recall on val (model ∪ lexicon ∪ probability) stays ≥ 0.98.
- **τ_intent (P8 abstain).**
  - Calibrated intent confidence `< τ_intent` → `abstain_request_info`.
  - Choose it on the risk–coverage curve: the smallest τ such that selective intent accuracy on accepted val tickets is ≥ 0.95, with coverage reported.
  - The initial 0.70 stays until P3 data exists.
- **τ_queue (N1).** Below it, use the rule default queue. Choose the τ that maximizes val routing accuracy of "model if conf ≥ τ else rule default". That fallback is a safe predictor, not an escalation.
- **Always** publish the curves and the chosen operating points, and re-fit them whenever the calibrator version changes.

### 5. Provider matrix (`confidence_method`)

| Provider | Method | Notes |
|---|---|---|
| OllamaProvider (≥ 0.12.11; pinned 0.34.x) | `token_logprob` | Raw pre-grammar logprobs, renormalized by §1. `top_logprobs=20`. |
| llama.cpp server adapter (optional) | `token_logprob` | Same semantics; can use `n_probs` > 20 |
| VLLMProvider | `token_logprob` | Logprobs are already grammar-renormalized (verify). Separate calibrator. |
| AnthropicProvider (frontier) | none / `self_consistency` (offline only) | No token logprobs assumed. Not used for triage in the E5 pipeline. |
| Encoder baseline (E2) | `calibrated_softmax` | sklearn `CalibratedClassifierCV(FrozenEstimator(clf), method="temperature")` (sklearn ≥ 1.8) |

---

## IMPLEMENTATION CHECKLIST

- [ ] `confidence.py` (§1) with the five unit-test cases, plus a property test that `0 ≤ p_value ≤ 1` and that `p_crit ≥ p_value` whenever the emitted value is critical.
- [ ] OllamaProvider requests `logprobs: true, top_logprobs: 20` and maps `logprobs[]` to `Tok`. Use `bytes` to rebuild partial UTF-8.
- [ ] `tw_ml/eval/calibration.py`: fit, CV selection, ECE and companions, bootstrap. Persist `calibrator.v<N>.json`.
- [ ] Contract: add `calibrator_version` and `calibration_fit_run_id` to `ModelMeta` (SI-3).
- [ ] Policy: add the `p_crit ≥ τ_crit` union to the rules.v1 YAML via ADR (SI-6), with table-driven tests.
- [ ] Nightly: recompute ECE on the smoke cassette. If ECE drifts by more than 0.03, flag the calibrator as stale.
- [ ] Record the enum tokenization dump (shared first tokens) in the model card.

---

## OPEN RISKS / TO VERIFY AT BUILD TIME

1. The top-20 cap (Ollama) may hide valid alternatives for low-confidence zero-shot outputs. The algorithm bounds their mass conservatively. The Ollama API may change the cap (PR #18580 discussion).
2. vLLM post-mask semantics are inferred from code order. **UNVERIFIED**; test with a two-value enum and a forced token.
3. Val → test distribution shift (L-10). Calibration and conformal guarantees are val-only, so test ECE may exceed 0.08. Report it honestly.
4. With few val errors, calibrator variance is high. The CV and bootstrap CIs make this visible.
5. CPU vs GPU numerics, and prompt-cache nondeterminism, cause small logprob jitter. Fit and evaluate on the CPU-served artifact.
6. `/v1/chat/completions` logprobs availability in Ollama has conflicting evidence (release notes vs #16117). The native API is used.

---

## LINKED ADR

- **ADR-0017: Confidence.** Update it with SI-1..SI-5, the algorithm, the calibrator choice and the provider matrix.
- **ADR-0010: Policy engine.** Needs a new ADR or amendment for the `τ_crit` probability union (SI-6).

---

## SOURCES (all accessed 2026-09-26)

1. Ollama v0.12.11 release notes (logprobs): https://github.com/ollama/ollama/releases/tag/v0.12.11
2. Ollama API reference, generate / chat (logprobs fields): https://docs.ollama.com/api/generate, https://docs.ollama.com/api/chat
3. Ollama source, `api/types.go`, `server/routes.go` (v0.34.4), `llm/llama_server.go`: https://github.com/ollama/ollama
4. Ollama issue #18579 (top-K limitation): https://github.com/ollama/ollama/issues/18579
5. Ollama PR #18580 (`logprob_tokens`, closed): https://github.com/ollama/ollama/pull/18580
6. Ollama issue #16117 (OpenAI-compat chat logprobs): https://github.com/ollama/ollama/issues/16117
7. ollama-python client (`generate`/`chat` logprobs params; v0.6.1 release): https://github.com/ollama/ollama-python
8. llama.cpp server README (`n_probs`, `post_sampling_probs`, `cache_prompt`): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
9. llama.cpp `tools/server/server-context.cpp` (`populate_token_probs`) and `server-common.cpp` (`get_token_probabilities`): https://github.com/ggml-org/llama.cpp/tree/master/tools/server
10. llama.cpp `common/sampling.cpp`: https://github.com/ggml-org/llama.cpp/blob/master/common/sampling.cpp
11. vLLM engine arguments (`logprobs_mode`): https://docs.vllm.ai/en/stable/configuration/engine_args/
12. vLLM source `vllm/v1/worker/gpu_model_runner.py`, `vllm/v1/sample/sampler.py`: https://github.com/vllm-project/vllm
13. vLLM releases (v0.21.0, v0.26.0 `logprob_token_ids`): https://github.com/vllm-project/vllm/releases
14. Guo et al., "On Calibration of Modern Neural Networks" (ICML 2017): https://arxiv.org/abs/1706.04599
15. scikit-learn, Probability calibration guide: https://scikit-learn.org/stable/modules/calibration.html
16. scikit-learn 1.8 changelog (`method="temperature"`): https://scikit-learn.org/stable/whats_new/v1.8.html
17. Kumar, Liang & Ma, "Verified Uncertainty Calibration" (NeurIPS 2019): https://arxiv.org/abs/1909.10155
18. Nixon et al., "Measuring Calibration in Deep Learning" (2019): https://arxiv.org/abs/1904.01685
19. Naeini, Cooper & Hauskrecht, "Obtaining Well Calibrated Probabilities Using Bayesian Binning" (AAAI 2015): https://pmc.ncbi.nlm.nih.gov/articles/PMC4410090/
20. Angelopoulos & Bates, "A Gentle Introduction to Conformal Prediction…" (§4.2 class-conditional): https://arxiv.org/abs/2107.07511
21. Geifman & El-Yaniv, "Selective Classification for Deep Neural Networks" (2017): https://arxiv.org/abs/1705.08500
22. Park et al., "Grammar-Aligned Decoding" (NeurIPS 2024), distribution distortion under constraints: https://arxiv.org/abs/2405.21047
