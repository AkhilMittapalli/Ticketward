---
status: Proposed
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §6, §8; spec §6.2, §9.4, §9.5, §9.6, §9.8, §16 P2–P3, §21 R-02/R-06/R-10/R-15/R-21; research slm-model-selection
informed: contributors; model card readers
supersedes: none
amended: 2026-10-13 (E3 evidence)
---

# ADR-0011: Base SLM chosen by bake-off (default candidate: Qwen3.5-2B)

> **Amended in spec v1.1 (2026-09-27; change record A-02). Status stays *Proposed* until the 1-epoch probe.**
> * **Candidates:**
>   * `Qwen/Qwen3.5-2B`: default;
>   * `Qwen/Qwen3-1.7B`: fallback;
>   * `Qwen/Qwen3-4B-Instruct-2507`, `meta-llama/Llama-3.2-3B-Instruct`, `microsoft/Phi-4-mini-instruct`;
>   * optional: `google/gemma-4-E2B-it`, `Qwen/Qwen3.5-0.8B`.
> * **Qwen2.5-3B-Instruct dropped** (Qwen Research License, non-commercial). Rejected alternatives: the Qwen2.5 family
>   and Gemma 4 E4B.
> * A fixed **score formula**, a **1-epoch fine-tune probe** on the top 2, and a pre-agreed **decision rule** (below).
> * **Llama naming and attribution rules** apply if a Llama base wins. **Chat-template determinism** is required
>   (explicit kwargs, fixed date string, template sha256 recorded).
>
> **E3 zero-shot evidence (2026-10-13, `286ba02`).** 4/5 non-optional candidates scored (llama32-3b blocked on HF
> gated-repo auth). val n = 230, hard_dev n = 30; Q4_K_M GGUFs from official safetensors; T = 0, seed 42.
>
> | Candidate | S | macro-F1 [95% CI] | min crit recall | P50 s | P95 s | JSON | M-08 |
> |-----------|-------|-------------------|-----------------|-------|-------|------|------|
> | phi4-mini | 0.794 | 0.898 [0.865, 0.930] | 0.864 | 14.4 | 28.0 | 100% | fail |
> | qwen3-4b-2507 | 0.785 | 0.898 [0.866, 0.926] | 0.909 | 20.5 | 39.1 | 100% | fail |
> | qwen3-1.7b | 0.747 | 0.789 [0.745, 0.831] | 0.792 | 12.0 | 18.7 | 97.0% | fail |
> | qwen35-2b | 0.719 | 0.772 [0.717, 0.821] | 0.727 | 12.7 | 24.9 | 90.4% | fail |
>
> **Provisional winner: qwen3-1.7b** (best le_2b by S). The 3-4B models outscore it by +10.9 F1 points (≥ 3-point
> rule met) but fail M-08 on CPU; the size rule yields them to qwen3-1.7b. **Top 2 for probe: phi4-mini,
> qwen3-4b-2507.** The probe cannot change the winner unless a fine-tuned 3-4B model meets M-08, which is latency
> (unchanged by fine-tuning). In practice the probe confirms qwen3-1.7b or (if qwen3.5-2B's probe F1 is within 1
> point of best) reopens the default rule.
>
> **llama-bench** (CPU, 8 threads, `build 631109b34 (11351)`):
>
> | Candidate | pp1024 tok/s | tg256 tok/s |
> |-----------|-------------|-------------|
> | qwen3-1.7b | 264.80 ± 8.45 | 33.74 ± 3.70 |
> | qwen35-2b | 154.32 ± 42.45 | 24.05 ± 4.89 |
> | qwen3-4b-2507 | 111.32 ± 16.68 | 8.54 ± 4.99 |
> | phi4-mini | 88.51 ± 7.57 | 12.66 ± 4.63 |

## Context and Problem Statement

The central product claim is "use the smallest reliable model for routine support work" (brief §2), and the brief
names "Qwen / Llama / Phi-family compact model" (brief §8). The base is fine-tuned (LoRA ≤ 2B / QLoRA 3–4B,
ADR-0012), merged, exported to GGUF, and served on **CPU** through Ollama (ADR-0014). It must emit constrained JSON
for `TriageModelOutput`, and meet triage P50 ≤ 5 s / P95 ≤ 12 s on the 8 vCPU / 16 GB box (M-08). R-15 warns this is
at risk for every 2–4B candidate.

The base model determines:
* the chat template (rendered deterministically, §9.4);
* the tokenizer (and so the 6,000-token budget and the enum tokenization behind path-probability confidence,
  ADR-0017);
* llama.cpp/GGUF support at the pinned Ollama build;
* licence obligations for publishing the adapter, merged model and GGUFs (DoD-10);
* the registry name (`tw-triage-<base>-<method>`).

The spec requires the choice to be **measured** in P2, with model versions and licences re-checked at P2 start
(R-14).

Which base model should be fine-tuned?

## Decision Drivers

* Intent macro-F1 on val (zero-shot, constrained), then post-probe.
* Worst-case (minimum) critical-class recall.
* CPU triage latency on the dev laptop (M-08, R-15).
* Licence: commercial use, derivatives, HF publishing, attribution and naming duties.
* Hard constraints:
  * GGUF conversion at the pinned llama.cpp build;
  * a deterministic chat template;
  * a T4 fp16 smoke test that passes (R-21);
  * fits T4 memory for the chosen method.

## Considered Options

1. **v1.1 bake-off set**, default Qwen3.5-2B, fallback Qwen3-1.7B, with the score, probe and decision rule below
   (proposed)
2. Qwen2.5 family (e.g. Qwen2.5-1.5B/3B-Instruct)
3. Gemma 4 E4B

## Decision Outcome

**Proposed:** option 1. The protocol is fixed in advance (spec §9.5).

* **Protocol:**
  * every HF repo is pinned by commit SHA in `ml/configs/bakeoff.yaml`;
  * GGUFs are converted from the official safetensors with the llama.cpp build the pinned Ollama ships (b11351 for
    Ollama v0.40.2), BF16 → `Q4_K_M` without imatrix, for parity; no library tags or third-party GGUFs (R-12);
  * the same deterministic `triage.v1` prompt, sent raw with the decoding schema: `temperature 0`, `num_ctx 8192`,
    `num_predict 512`, `seed 42`;
  * val n = 230 (actual split size after generation).
* **CPU speed:** `llama-bench -p 1024 -n 256 -t 8 -ngl 0 -r 5`, plus a 50-ticket Ollama sample (`num_gpu: 0,
  num_thread: 8`) recording prompt/decode rates and triage wall-time P50/P95.
* **Score:** `S = 0.40·macroF1 + 0.25·min_critical_recall + 0.20·min(1, 5 s / triage_P50) + 0.15·Lic`, where
  Lic = 1.0 for Apache/MIT, 0.5 for the Llama 3.2 Community License, and non-commercial licences are excluded.
* **Probe:** 1 epoch, seed 42, on the top 2 by S. The choice uses post-probe val macro-F1 and critical recall, with
  the latency and licence terms unchanged.
* **Decision rule:** Qwen3.5-2B wins if (a) its T4 smoke test passes, (b) its CPU triage P50 is within 1.2× the best
  candidate's, and (c) its probe macro-F1 is within 1 point of the best. Otherwise Qwen3-1.7B wins. Qwen3-4B-Instruct-
  2507 wins only under the ≥ 3-point rule and only if M-08 still holds.
* **If a Llama base wins:** registry name `Llama-tw-triage-3.2-3b-<method>`, "Built with Llama" in the README and
  model card, and model-card licence `llama3.2`.
* **Template determinism:** explicit `add_generation_prompt=True, enable_thinking=False`; a fixed `date_string` for
  Llama; the sha256 of the chat template and of one golden rendering stored in `model_versions` and the model card.

**Evidence required to move to Accepted:**
1. [x] Research `slm-model-selection` updated at P2 start, with pinned SHAs, licences re-read, and any newer small
   models considered (R-14). Done 2026-10-11 (`13eed45`).
2. [x] `evals/reports/2026-10-13/bakeoff.md` and `baselines.md`, reproducible from `make eval-baselines`, with the S
   table, per-criterion values and CIs. bakeoff.md rendered 2026-10-13; baselines.md rendered 2026-10-11 (`751dcc0`).
3. [x] Measured CPU P50/P95 per candidate on the dev laptop. Done 2026-10-13: Ollama 50-ticket CPU sample per
   candidate, plus `llama-bench` raw throughput (`evals/reports/2026-10-13/llama_bench.json`). T4 smoke pending (P3).
4. [ ] The 1-epoch probe results for the top 2 (phi4-mini, qwen3-4b-2507), logged in MLflow, and the decision rule
   applied as written. **Pending — requires P3 Kaggle/Colab T4.**

### Consequences

* Good, because the choice is measured, pre-registered and reproducible, and it matches the "smallest reliable model"
  claim.
* Good, because a named fallback (Qwen3-1.7B, pure transformer, lowest tooling risk) removes schedule risk if the
  Qwen3.5 Gated DeltaNet kernels misbehave on T4 (R-21).
* Bad, because the bake-off, probe and smoke tests cost P2 time and some Kaggle quota.
* Bad, because a Llama win brings naming and attribution duties, and a Gemma candidate brings a 7.2 GB Q4 artifact and
  fp16 overflow risk on T4 (spec §9.5).
* Neutral, because P4 integration starts against the zero-shot base through the same provider until the P3 GGUF lands.

### Confirmation

* The four evidence items above. `model_versions.base_model` plus the HF revision SHA and `chat_template_sha256` are
  recorded for the chosen base.
* M-01 (E4 ≥ 0.85; E4 − E3 ≥ +0.10 with the paired CI; E4 > E1 in the Holm family, ADR-0032), M-03c, M-04 and M-08,
  published in `docs/benchmarks.md` (P10).
* CI parity tests: backend prompt rendering equals the HF golden renderings byte for byte, and `prompt_eval_count`
  matches (§9.4).
* Semgrep: no `trust_remote_code=True`. The model card lists the base, its licence and any attribution text (DoD-10).

## Pros and Cons of the Options

### v1.1 bake-off set (Qwen3.5-2B default, Qwen3-1.7B fallback)

* Good, because the permissively licensed defaults (Apache-2.0), in-family size ladder (0.8B–4B) and cross-family
  comparators (Llama, Phi, optional Gemma) test the choice honestly.
* Bad, because of the Qwen3.5 risks on T4 (Gated DeltaNet kernels, fp16 behaviour unverified), CPU latency for its
  hybrid cache, and a 248K vocabulary. These are mitigated by the smoke test and the fallback.

### Qwen2.5 family

* Good, because it is widely used, with mature tooling.
* Bad, because its 3B size is under a non-commercial research licence (dropped), and newer Qwen3/3.5 checkpoints
  supersede the smaller sizes at similar cost.

### Gemma 4 E4B

* Good, because it is a capable, modern checkpoint.
* Bad, because it is larger than E2B, which already shows a 7.2 GB Q4 artifact and fp16 overflow on T4. E4B would
  strain CPU latency (M-08) and T4 memory further, so only E2B remains an optional candidate.

## More Information

* Spec (private): §6.2 (model version naming), §9.4 (deterministic templates, parity), §9.5 (candidates, protocol,
  score, probe, decision rule, Llama rules), §9.6 (registry naming), §9.8, §16 P2–P3, §21 R-02, R-06, R-10, R-15,
  R-21. Change record A-02.
* Brief (private): §2, §6, §8. BR-008, BR-029, BR-040.
* Research: [slm-model-selection](../research/slm-model-selection.md).
* Related ADRs: ADR-0012 (method by size), ADR-0014 (serving, parity), ADR-0017 (tokenization for confidence),
  ADR-0018 (encoder baseline).
* Revisit when: the probe completes (flip to Accepted), or a newer small-model generation meets the hard
  constraints before P3.
* Status history: 2026-09-26 Proposed (pending the P2 bake-off). 2026-09-27 amended for spec v1.1 (new candidate
  set, score, probe, decision rule, Llama rules); still Proposed. 2026-10-13 amended with E3 zero-shot evidence,
  llama-bench results and bakeoff.md; provisional winner qwen3-1.7b; still Proposed (probe pending).
