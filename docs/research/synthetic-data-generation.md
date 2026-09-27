# Synthetic Data Generation (Taskmoor tickets) - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-26
**Status**: Partially resolved (vendor terms, generator choice, matrix, QA protocol and cost resolved; a 50-record pilot per generator family must confirm token counts, refusal rates and artifact rates before full generation)
**Category**: ML Data
**Linked ADR(s)**: ADR-0016 (test set from a different model family + hard set + Bitext OOD), amendment required; ADR-new "Generator families and vendor-terms compliance" (proposed; number assigned at merge)
**Spec sections**: §9.1, §9.2, §9.3, §9.7 (E6), §13 S-12, §16 P1, §20 L-01/L-06, §21 R-01/R-10, §23

---

## EXECUTIVE SUMMARY

1. **The spec's default Family A generator (Anthropic Claude for train/val) is not permitted as written.** Anthropic's Usage Policy (effective 2025-09-15) lists "Utilization of inputs and outputs to train an AI model" as prohibited platform abuse unless Anthropic has given prior authorization. The prohibition covers all AI models, not only competing ones, and it applies to API customers. The Commercial Terms separately bar using the Services to build competing products or train competing models. Spec §9.1 item 9 already defines the fallback: **train/val generation switches to open-weights generators.** This is not legal advice. It is the conservative reading the project adopts.
2. **Recommended generators.** All five roles use different model families:
   - **Family A (train/val):** `openai/gpt-oss-120b`. Apache-2.0; its usage policy only requires compliance with applicable law. Uses prompt family P-A (persona-first) and proposes labels.
   - **Family B (test_synth):** `mistralai/Mistral-Large-3-675B-Instruct-2512`. Apache-2.0, accessed through Mistral's API. Mistral's commercial terms assign Output ownership to the customer; the only output-training restriction found there concerns *image* outputs. Any separate Mistral usage policy is UNVERIFIED. Uses P-B (scenario-first, two-stage). Gold labels come from the scenario spec plus 100% human review, not from the generator.
   - **Student SLM:** Qwen/Llama/Phi family.
   - **E6 frontier baseline:** Claude.
   - **Hard set:** written by a human.
   - **Claude's role:** evaluation only (E6, optional LLM-judge). It never touches any data that trains a model.
3. **Why not Llama or Gemma for Family A.**
   - Llama 3.3's license requires "Llama" at the start of the name of any distributed model trained on its outputs, plus a "Built with Llama" notice.
   - Gemma's terms treat models trained on Gemma synthetic outputs as "Model Derivatives", which carry pass-through use restrictions.
   - Either one is acceptable for **test-only** generation. Avoid whichever family the bake-off picks as the base SLM (ADR-0011).
4. **Diversity approach.** Full factorial coverage is impossible: the matrix has about 1.5M cells for 3,600 records. Instead:
   - a constrained, quota-aware sampler with pairwise coverage targets and plausibility rules (e.g., SSO only on business/enterprise, per §3);
   - persona, company and entity pools that are disjoint per split;
   - lexical-avoidance cards, so critical intents are not always keyword-obvious;
   - deterministic noise injection for typos;
   - measured gates: distinct-n, embedding Vendi score, keyword prevalence, placeholder and meta-text leaks, and a subject-only probe.
5. **Label QA, in order:** rule-checker → cleanlab-ranked targeted review → 15% stratified *random* audit (n=540) → 100% review of test_synth and test_hard → volunteer double-annotation of 20% of test_synth and 100% of test_hard, with Cohen's κ. Recommended pass rule: the Wilson 95% upper bound of the audited error rate is below 5%, which means **≤ 17 errors in 540**. The spec's literal rule (point estimate < 5%) allows up to 26.
6. **Cost (dated prices, arithmetic below).**
   - API spend: about $3.79 for Family A at a mid-priced gpt-oss host and $2.62 for Family B; budget $15 to cover pilots and regeneration.
   - If Anthropic authorization were obtained, Claude Haiku 4.5 via Batch would cost about $10.66 for Family A.
   - The real cost is human time: about 26 owner-hours plus 2 volunteer-hours of labeling and review.
7. **Known artifacts of LLM-generated tickets.** Documented and expected artifacts are listed with detection and mitigation: formulaic openings, label-cue words, name and amount mode collapse, too-clean text, placeholder and meta leaks, safety sanitization of security and legal tickets, subject lines that restate the label, and self-diagnosis. The cross-family test set, the human hard set and the Bitext OOD set exist because these artifacts cannot be fully removed (L-06).

---

## QUESTIONS

| # | Question | Source |
|---|---|---|
| Q1 | Do generator vendor terms allow using outputs to fine-tune our non-competing triage SLM (Anthropic + open-weights alternatives + hosting providers)? | §23, §9.1.9, R-10 |
| Q2 | Which Family A and Family B generators, and how are they accessed? | §23, §9.1.2–3 |
| Q3 | How do we ensure diversity (generation matrix, styles, sampler)? | §23, §9.1.1 |
| Q4 | What is the label QA protocol and its acceptance rule? | §23, §9.1.6, §9.2 |
| Q5 | What does generation cost (dated prices, shown arithmetic)? | §23 |
| Q6 | What are the known artifacts of LLM-generated tickets, and how are they detected and mitigated? | §23, L-06 |
| Q7 | What do the P-A and P-B prompt skeletons look like? | §9.1.2–3 |
| Q8 | (Implementer) Which provenance fields and CI checks enforce the terms decision? | §9.1.8, S-12 |

---

## FINDINGS

All sources accessed 2026-09-26 unless noted. Legal text is summarized; the only direct quote is under 15 words.

### F1. Anthropic terms (Q1)

| Document (effective date as displayed) | What it says about training on outputs | Consequence for Ticketward |
|---|---|---|
| **Usage Policy** (2025-09-15) [A1] | Under the "Do Not Abuse our Platform" heading it prohibits "Utilization of inputs and outputs to train an AI model" (examples given: model scraping, model distillation) without prior authorization from Anthropic. The policy applies to anyone who submits inputs, including through resellers or pass-through access. | Training the triage SLM, the encoder baseline (E2), or any future draft LoRA (G-3) on Claude-generated tickets, labels or drafts needs **prior authorization**. The clause is not limited to "competing" models. |
| **Commercial Terms** (2025-06-17) [A2] | Customers may not access the Services to build a competing product or service, including training competing AI models, unless Anthropic expressly approves. Customers own their Outputs (Anthropic assigns its rights). Anthropic may not train on Customer Content. | Output ownership does not override the AUP use restriction (the AUP is part of the terms customers accept). |
| **Consumer Terms** (2025-10-08) [A3] | Consumer products (Claude.ai, Pro, and similar) prohibit using the services to develop competing products, and name building or training AI/ML models as one such use. API keys and Commercial-Terms users are excluded from these terms. | Generating training tickets through a consumer subscription (for example, chatting on Claude.ai) is also out. |

- **No public authorization process was found.** A web search on 2026-09-26 turned up only secondary commentary, which agrees that the prohibition covers any model. To use Claude for Family A, the owner would need written authorization from Anthropic (sales or support). That authorization would be stored in `docs/legal/` and referenced in the dataset card.
- **What remains allowed.** Evaluation-only uses do not train a model: E6 frontier triage/drafting, the optional masked LLM-judge in §8.9, and flagging suspicious *test* labels for human review. They stay allowed provided those outputs never flow into any training set. That rules out v0.2 retraining, a G-3 draft LoRA, a verifier trained on LLM-judge labels, and feedback exports under NG-08.

### F2. Open-weights and hosting terms (Q1, Q2)

| Candidate | License / terms (as displayed) | Output-use restriction for training? | Notes |
|---|---|---|---|
| `openai/gpt-oss-120b` [O1] | Apache-2.0; repo `USAGE_POLICY` is two sentences (use safely; comply with applicable law) | None found | 117B total / 5.1B active MoE; requires the "harmony" chat format (applied by the Transformers chat template); released Aug 2025 (arXiv 2508.10925) |
| `mistralai/Mistral-Large-3-675B-Instruct-2512` [O2] | Apache-2.0 (model card) | None from the license. Mistral **API** Commercial Terms (2026-09-25) [O5]: customer owns Output; the only output-training restriction found concerns *image* Outputs used for competing image-generation products. A separate Mistral usage policy, if any, is UNVERIFIED (irrelevant for test-only use, relevant if Mistral were ever used for Family A) | ~675B total / ~41B active including a 2.5B vision encoder; 256k context; the card recommends vLLM with a minimum version (exact number UNVERIFIED); listed on OpenRouter as `mistralai/mistral-large-2512` |
| `mistralai/Mistral-Small-4-119B-2603` [O3] | Apache-2.0 | None from the license | 119B total / 6.5B active; hybrid instruct/reasoning (`reasoning_effort` none/high); 256k context. Same family as Mistral Large 3, so it is a *backup* for the Family B role, not a second family |
| Llama 3.3 70B Instruct [O6] | Llama 3.3 Community License (release date 2024-12-06) | Yes, conditional: if outputs are used to create, train, fine-tune or improve a model that is distributed or made available, the model name must start with "Llama", "Built with Llama" must be displayed, and the 700M-MAU clause applies | Acceptable for test-only generation; avoid if the base SLM is Llama (same-family confound) |
| Gemma family [O7] | Gemma Terms of Use (last modified 2026-04-01) | Yes, indirectly: "Model Derivatives" include models trained using synthetic Outputs of Gemma to perform similarly to Gemma; distributing a Model Derivative requires passing through the use restrictions, a copy of the terms and a Notice file. Google claims no rights in Outputs themselves | Acceptable for test-only; avoid for Family A |
| Together AI (host) [O8] | Terms of Service (2026-05-19) | Customer owns Output; third-party model terms govern in case of conflict; clause against using the Services to build a product competing with *Together's* services | A triage SLM does not compete with an inference platform |

Other hosts listed for gpt-oss-120b (Groq, DeepInfra, Cerebras, and others) were **not** term-checked. UNVERIFIED: verify the chosen host's terms at build time.

### F3. Family selection criteria (Q2)

1. **Legal fit for the role.** Family A needs outputs that can be used for training. Family B does not, because test data is never trained on.
2. **Independence.** Families must differ between A and B (spec), from the student SLM candidates (Qwen, Llama, Phi, possibly Gemma; ADR-0011), and from the E6 frontier model (Claude).
   - Panickssery et al. (2024) show that LLMs can recognize their own generations and favor them as evaluators [P4].
   - If Claude generated test_synth, E6 (Claude triaging) would get a home-field advantage. Claude-proposed labels would also bias gold labels toward Claude's own conventions. Both would distort the "smallest reliable model" comparison.
3. **Realism and quality of writing for the test set.** This matters more for test than for train.
4. **Access and cost.** The larger models cannot run on a Kaggle/Colab T4. Mistral Large 3 needs multi-GPU vLLM, so it is accessed via API. A T4-runnable Family B fallback would be Ministral 3 14B Instruct (Apache-2.0, listed on HF [O4]); its quality and throughput are UNVERIFIED.

Resulting assignment:

| Role | Family |
|---|---|
| A (train/val) | OpenAI gpt-oss |
| B (test_synth) | Mistral |
| Student SLM | Qwen (default) |
| Frontier (E6) | Anthropic |
| Hard set | Human |
| OOD | Bitext |

All six are distinct.

### F4. Diversity evidence (Q3)

- **AttrPrompt** (Yu et al., NeurIPS 2023 D&B) [P1]. Class-conditional "simple prompts" produce biased datasets (for example, regional bias). Prompts conditioned on diverse attributes (length, style, and so on) yield better training data, especially for many-class problems, at a fraction of the query cost. **This supports our attribute cards.**
- **Chung et al.** (ACL 2023) [P3]. Diversification by logit suppression or temperature raises diversity but lowers label accuracy. Human **label replacement** recovered 14.4 points of downstream accuracy; out-of-scope filtering helped little. **This supports human QA after diversified generation.**
- **Li et al.** (EMNLP 2023) [P2]. Synthetic data helps less on *subjective* classification. For us, sentiment and churn labels are the subjective fields: expect weaker transfer there, and keep them "assistive signals" (L-02).
- **Persona Hub** (Ge et al., 2024) [P6]. Persona-driven prompting is an effective route to diversity. **This supports P-A.**
- **Guo et al.** (NAACL 2024 Findings) [P8]. Linguistic diversity declines under recursive training on synthetic text. We never train a generator on its own outputs.
- **Vendi Score** (Friedman & Dieng) [P5]. Defined as the exponential of the Shannon entropy of the eigenvalues of a similarity matrix, i.e., an "effective number of distinct samples". It needs no reference set, so it is usable per intent.

### F5. Matrix arithmetic (Q3)

- **Full factorial is infeasible.** Spec §9.1.1 dimensions multiply to 13 intents × 12 product areas × 4 plans × 4 channels × 5 sentiments × 6 difficulties × 4 length buckets × 5 styles = **1,497,600 cells**. With 3,600 train records, full coverage is impossible, so we target *marginal quotas + pairwise coverage + plausibility constraints*.
- **The intent allocation in §9.3 is inconsistent with the total.**
  - "≈300/intent incl. other_unclear, oversample critical ×1.3" does not add up to 3,600.
  - Solving 8·b + 5·1.3·b = 3,600 gives b ≈ 248.3: ≈248 per non-critical intent (7 intents + other_unclear) and ≈323 per critical intent. That totals 3,599; add 1 to `how_to_question`.
  - A literal 300 base would require 4,350 records.
  - See Spec impact.

### F6. Known artifacts of LLM-generated tickets (Q6)

- **Documented in the literature:**
  - LLM-influenced text overuses specific style words (Kobak et al., Science Advances 2025, excess-vocabulary method) [P7].
  - Dataset-construction artifacts let models predict labels from superficial cues; hypothesis-only NLI baselines reached about 67% on SNLI (Gururangan et al., NAACL 2018) [P9].
  - Diversified generation drifts from the requested label (Chung et al.) [P3].
- **Expected practitioner artifacts:** the other rows in the table below. Rates are **UNVERIFIED until the pilot measures them.**

| # | Artifact | Why it hurts | Detection (automated in `validate.py`) | Mitigation |
|---|---|---|---|---|
| A1 | Formulaic openings and closings ("hope this finds you well", sign-offs) | Style cue unrelated to the label; inflates similarity | Phrase regex; rate per split | Style card says when a greeting is allowed; post-filter strips boilerplate in ≥ 70% of records |
| A2 | Label-cue words (every cancellation says "cancel"; every duplicate charge says "charged twice") | Keyword shortcut; E1 looks artificially strong; poor transfer to implicit phrasing | Keyword prevalence per intent vs P-B and the hard set | 30% of critical-intent cards carry a banned-word list (implicit churn: "not renewing", "moving to another tool") |
| A3 | Subject line restates the intent ("Duplicate charge on invoice") | Near-label leakage in one field | Subject-only logistic-regression probe accuracy | `subject_style` attribute: vague / blank-ish / wrong-emphasis / specific |
| A4 | Mode collapse on names, companies, amounts, dates | Memorization shortcuts; cross-split near-duplicates | Top-k entity frequency; entropy | Split-disjoint pools; entity values sampled by code and passed in, not invented |
| A5 | Placeholders and meta text ("[Your Name]", "Here is the ticket:", JSON fences) | Unrealistic; parse failures | Regex; must be 0 after filtering | Reject + regenerate |
| A6 | Too-clean prose; caricatured typos when asked for "non-native" | Distribution gap vs real tickets | Spell-error rate; length histogram vs bucket targets | Deterministic noise functions (keyboard-adjacent swaps, dropped letters) applied after generation, recorded in `noise_ops` |
| A7 | Over-specification: numbered repro steps, exact timestamps, self-diagnosis ("probably the SAML cert expired") | Makes triage and needs_info easier than reality | Rate of lists and diagnosis phrases | `difficulty` cards; `must_omit` fields; the needs_info quota |
| A8 | Safety sanitization or refusal on security/legal/injection tickets | Critical classes under-represented or softened | Refusal regex; per-intent yield | Framing as fictional QA data; tolerate refusals by regenerating; report yield per intent |
| A9 | Product facts inconsistent with Taskmoor (e.g., SSO on the free plan) | Label noise; wrong KB grounding | Constraint validator against the fact sheet | Fact sheet in the prompt; plausibility constraints in the sampler |
| A10 | Uniform length, or lengths clustered at the target | Length becomes a proxy for style/difficulty | Length vs bucket distribution | Sample a word target *within* the bucket; accept ±30% |
| A11 | Secondary intent always appended at the end | Positional shortcut for multi-intent | Position statistic | Card specifies the order (primary first/second/interleaved) |
| A12 | Human requests always explicit | M-07d indirect recall overestimated | Direct vs indirect ratio | `human_request: direct/indirect` quota; an indirect phrasing list authored by the owner (P-A only) |

### F7. Label QA statistics (Q4)

- **The 15% train audit.**
  - 15% of 3,600 = **540** audited records, about 41–48 per intent.
  - With a Wilson 95% interval, the largest error count that keeps the **upper bound < 5% is 17/540** (3.1%). The interval at 17 errors is [2.0%, 5.0%). The spec's point-estimate rule (< 5%) allows k ≤ 26.
  - **Per intent (n≈45), even 0 errors gives an upper bound of 7.9%.** An intent-level "< 5%" claim is therefore impossible at this sample size. Certify the aggregate rate and use per-intent counts only as triggers for re-review.
  - Computed with the Wilson score formula. Reproduce with `proportion(k, 540)` in evaluation-statistics.md D10.
- **Test-set label errors are common and change conclusions.** Northcutt et al. (NeurIPS 2021 D&B) estimate at least 3.3% label errors on average across 10 benchmark test sets, and show that model rankings can flip [P10]. This justifies the spec's 100% review of test_synth and test_hard, and adding a second annotator.
- **cleanlab 2.9.0** (Apache-2.0) [P11]. `cleanlab.filter.find_label_issues(labels, pred_probs, ...)` ranks likely label errors. It is accurate only with **out-of-sample** (cross-validated) `pred_probs`. Targeted review fixes errors but is a *biased* sample, so it must not be used to estimate the error rate.

### F8. Dated prices and cost arithmetic (Q5)

**Price table** (per million tokens; accessed 2026-09-26):

| Model / endpoint | Input $/MTok | Output $/MTok | Source |
|---|---|---|---|
| gpt-oss-120b, DeepInfra (bf16) via OpenRouter | 0.037 | 0.17 | [O9] |
| gpt-oss-120b, Together / Groq via OpenRouter | 0.15 | 0.60 | [O9] |
| gpt-oss-120b, Cerebras via OpenRouter | 0.35 | 0.75 | [O9] |
| Mistral Large 3 (`mistral-large-2512`), Mistral endpoint via OpenRouter (EU endpoint $0.55/$1.65) | 0.50 | 1.50 | [O10] |
| Claude Haiku 4.5 Batch (only if authorized) | 0.50 | 2.50 | [A4] |
| Claude Sonnet 5 Batch (only if authorized) | 1.00 | 5.00 | [A4] |

Notes on the Claude rows:
- Sonnet 5's $2/$10 standard price is now permanent; the September increase was cancelled [A4].
- Claude 4.7-and-later models use a newer tokenizer that produces about 30% more tokens for the same text; Haiku 4.5 uses the previous one [A4].
- Minimum cacheable prefix: 4,096 tokens on Haiku 4.5 and 1,024 on Sonnet 5 (Anthropic prompt-caching docs via the claude-api skill cache). A ~1.6k-token generator prefix would not cache on Haiku 4.5.

**Token assumptions** (UNVERIFIED; the pilot measures them):
- P-A: 1,800 input tokens per call (fact sheet + taxonomy + label rules ≈1,600, plus a card ≈200). Output: 450 visible tokens (ticket ≈300 + proposed labels ≈150) plus about 300 reasoning tokens for gpt-oss at low reasoning effort, so 750 in total.
- P-B, two stages per scenario: 900 in / 350 out, then 1,400 in / 500 out, so 2,300 in / 850 out.
- Over-generation: ×1.3 for train/val (schema, rule-check, dedup and leakage rejects) and ×1.5 for test (strict quotas plus 100% review rejects).

**Arithmetic:**

| Item | Calls | Input | Output | Cost |
|---|---|---|---|---|
| Family A, gpt-oss-120b @ $0.15/$0.60 | (3,600 + 450) × 1.3 = **5,265** | 5,265 × 1,800 = 9.477M × $0.15 = **$1.42** | 5,265 × 750 = 3.949M × $0.60 = **$2.37** | **$3.79** (low host $1.02, high host $6.28) |
| Family B, Mistral Large 3 @ $0.50/$1.50 | 720 × 1.5 = **1,080** scenarios × 2 stages | 1,080 × 2,300 = 2.484M × $0.50 = **$1.24** | 1,080 × 850 = 0.918M × $1.50 = **$1.38** | **$2.62** |
| *Alternative, only with Anthropic authorization:* Family A, Haiku 4.5 Batch | 5,265 | 9.477M × $0.50 = $4.74 | 5,265 × 450 = 2.369M × $2.50 = $5.92 | $10.66 |
| *Alternative:* Family A, Sonnet 5 Batch (×1.3 tokenizer, thinking disabled) | 5,265 | 12.320M × $1.00 = $12.32 | 3.080M × $5.00 = $15.40 | $27.72 |

**Recommended API budget: $15.** That covers $6.41 of expected spend plus pilots, prompt iterations and v0.2 top-ups.

**Human time (the real cost):**

| Task | Owner hours |
|---|---|
| test_synth 100% review (720 × 45 s) | 9.0 |
| Hard set writing and labeling (100 × 6 min) | 10.0 |
| Train random audit (540 × 30 s) | 4.5 |
| cleanlab-ranked review (150 × 30 s) | 1.25 |
| Bitext mapped-set review (500 × 8 s) | 1.1 |
| **Total** | **≈ 26 h** |

Volunteer double-annotation: 144 + 100 records × 30 s ≈ **2.0 h**. P1 in §16 is budgeted at D1–D2 +1d. **This is tight; see Open Risks.**

---

## DECISION / RECOMMENDATION

### D1. Generators and access

| Role | Model | Access | Sampling | Output |
|---|---|---|---|---|
| Family A (train, val) | `openai/gpt-oss-120b` | Hosted API with verified terms (Together verified; others UNVERIFIED), or self-hosted vLLM on a rented 80 GB GPU (the model card's single-GPU claim is UNVERIFIED) | Model-card-recommended sampling (verify); reasoning effort **low**; one ticket per call (no multi-ticket batches, which correlate outputs) | Ticket JSON + `proposed_labels` |
| Family B (test_synth) | `mistralai/Mistral-Large-3-675B-Instruct-2512` (API id `mistral-large-2512`; verify on Mistral's model list) | Mistral API directly, or via OpenRouter (Mistral endpoint) | Temperature ≈ 0.8 for stage 2 and ≈ 0.5 for stage 1 (initial values; tune in the pilot) | Stage 1: case timeline. Stage 2: customer message. **No labels** |
| Fallback A | `Qwen/Qwen3-235B-A22B-Instruct-2507` or DeepSeek (license **UNVERIFIED**; verify before use) | Hosted | – | – |
| Fallback B | `mistralai/Mistral-Small-4-119B-2603` (Apache-2.0) | Mistral API | – | – |
| Claude | Evaluation only: E6, optional masked LLM-judge, optional test-label *flagging* | Anthropic API | – | Outputs never enter `data/` training splits |

If the owner later obtains written Anthropic authorization:
- Claude may replace gpt-oss as Family A. Record the authorization and amend the ADR.
- **Family B still must not be Claude** (the E6 home-field effect, F3).

### D2. Enforcement via provenance and CI (extends T-DATA-provenance, S-12)

- **Provenance fields.** Every record carries the §9.1.8 provenance fields plus:
  - `generator_family` ∈ {`openai_gpt_oss`, `mistral`, `human`, `public_bitext`};
  - `generator_endpoint` (host + model id + request date; plus the HF revision SHA when self-hosted);
  - `template_id`, `scenario_seed`, `persona_id`, `company_id`, `noise_ops[]`;
  - `terms_snapshot_id` (a pointer to `docs/legal/generator-terms-2026-09-26.md`).
- **CI assertions:**
  1. train/val records have `generator_family` in {`openai_gpt_oss`, `human`}. `human` is for owner-written v0.2 additions.
  2. test_synth is only `mistral`. test_hard is only `human`, with an attestation field `llm_assisted=false`. test_ood is only `public_bitext`.
  3. No file under `data/` has `generator_family=anthropic`. E6 and judge outputs live under `evals/runs/`.
  4. Any training-export job (feedback curation per NG-08, a G-3 draft LoRA) filters out rows where `drafts.provider='anthropic'` or `llm_calls.provider='anthropic'`.

### D3. Generation matrix and sampler (Q3)

`data/spec/generation_matrix.yaml` (v1). The proportions are **initial proposals** to be tuned after the pilot:

```yaml
taxonomy_version: "2026-09-v1"
splits:
  train:      {n: 3600, family: openai_gpt_oss, prompt_family: P-A, templates: [pa.t1, pa.t2, pa.t3, pa.t4], pools: train}
  val:        {n: 450,  family: openai_gpt_oss, prompt_family: P-A, templates: [pa.t5, pa.t6], pools: val}
  test_synth: {n: 720,  family: mistral,        prompt_family: P-B, templates: [pb.s1+pb.m1, pb.s2+pb.m2], pools: test}
intent_allocation:
  train: {non_critical_each: 248, critical_each: 323, other_unclear: 248, plus_one: how_to_question}  # 8*248 + 5*323 + 1 = 3600
  val:   {per_intent: proportional_to_train}                                                            # ~31 / ~40
  test_synth: {per_intent_min: 55, other_unclear: 60}                                                   # 12*55 + 60 = 720
marginals:            # sampled with deficit-weighting toward these shares
  plan:        {free: 0.15, starter: 0.30, business: 0.35, enterprise: 0.20}
  channel:     {web_form: 0.35, email: 0.40, api: 0.05, chat_transcript: 0.20}
  sentiment:   {positive: 0.05, neutral: 0.35, confused: 0.20, frustrated: 0.28, angry: 0.12}
  difficulty:  {ordinary: 0.40, ambiguous: 0.15, multi_intent: 0.12, severe: 0.10, needs_info: 0.13, adversarial_injection: 0.10}
  length_bucket: {terse: [5, 40], short: [40, 120], medium: [120, 300], long: [300, 700]}   # words; shares 0.2/0.4/0.3/0.1
  style:       {terse: 0.2, rambling: 0.2, non_native: 0.2, angry_caps: 0.1, forwarded_thread: 0.1, plain: 0.2}
  human_request: {none: 0.92, direct: 0.04, indirect: 0.04}
  subject_style: {specific: 0.45, vague: 0.30, blankish: 0.10, misleading_emphasis: 0.15}
  lexical_avoid: {critical_intents: 0.30, others: 0.10}
  pii_placeholders: 0.20            # §9.1.7: inject masked tokens <EMAIL_1>, <PERSON_1>, ...
  legal_threat_inside_billing: 0.05 # of billing intents; mirrors the hard-set stratum
constraints:                        # rejection rules; all derived from §3/§5
  - {if: {intent: sso_login_failure}, require: {plan: [business, enterprise]}}           # SSO is not on free/starter (§3)
  - {if: {topic: scim}, require: {plan: [enterprise]}}
  - {if: {intent: [billing_duplicate_charge, billing_payment_failure, refund_request]}, require: {product_area: [billing_subscriptions]}}
  - {if: {intent: service_outage}, require: {product_area: [platform_availability, sso_identity, integrations_api, notifications_email]}}
  - {if: {style: forwarded_thread}, require: {channel: [email]}}
  - {if: {style: angry_caps}, require: {sentiment: [frustrated, angry]}}
  - {if: {difficulty: needs_info}, set: {information_sufficient: false}}
  - {if: {difficulty: multi_intent}, set: {secondary_intents: "1-2"}}
  - {if: {channel: chat_transcript}, require: {previous_messages: ">=2"}}
coverage:
  pairwise: [[intent, difficulty], [intent, style], [intent, channel], [intent, plan], [intent, sentiment], [intent, length_bucket], [intent, product_area]]
  min_per_feasible_pair: {train: 3, test_synth: 1}
```

**Sampler (`ml/src/tw_ml/datagen/generate.py`).** For each split:
1. Iterate over the intent quotas.
2. For each record, draw attributes in a fixed order. Weight each value by `target_share / (observed_share + 0.01)` (deficit weighting) and reject combinations that violate the constraints.
3. Draw `persona_id`, `company_id` and entity values from the **split-specific pools** using `scenario_seed`.
4. After the pass, compute pairwise coverage and top up the missing feasible pairs.

This is deterministic given a `seed` in the manifest.

**Pools** (`data/spec/pools/{train,val,test,hard}/`):
- Person and company names are generated with a fixed seed and de-duplicated *across* splits. Company names are also checked against a small denylist of well-known brands, for trademark hygiene per §3.
- Invoice ids, amounts (plausible vs the §3 prices × seats) and dates are generated by code and passed into the card.
- Error codes and product vocabulary are **shared**; they are product facts the KB covers.

### D4. Label QA protocol (Q4)

1. **Schema validation.** `TriageModelOutput.model_validate(proposed_labels)` in strict mode. On failure, regenerate once; if it fails again, quarantine.
2. **Rule-checker** (`validate.py`; deterministic):
   - R1: proposed intent equals the card's `goal_intent`, or the record is quarantined with the generator's `self_check` note.
   - R2: the queue is the §5.8 default or an allowed alternate.
   - R3: the action is valid for the intent.
   - R4: every entity value appears verbatim in the text (§9.2).
   - R5: `churn_risk=high` has a cue that appears in the text.
   - R6: `customer_requested_human` matches the card and the direct-request lexicon.
   - R7: `information_sufficient=false` if and only if the card has needs_info or omissions.
   - R8: secondary intents are ≤ 2, differ from the primary, and are non-empty for multi_intent.
   - R9: priority plausibility vs §5.3 (warning only).
   - R10: Presidio finds no unmasked PII apart from the injected placeholders.
3. **Targeted review (train).**
   - Out-of-fold intent probabilities come from a 5-fold TF-IDF+LR (fast) or the E2 encoder.
   - `find_label_issues(labels, pred_probs, return_indices_ranked_by="self_confidence")` ranks candidates; the owner reviews the top 150.
   - Corrected records get `label_source=human_verified`. This sample is **not** used for the error-rate estimate.
4. **Random audit (train).**
   - 540 records sampled stratified by intent × difficulty with a fixed seed, **before** targeted fixes.
   - The reviewer picks the intent **blind** (proposal hidden), then sees the other proposed fields and confirms or edits each one.
   - A record counts as an error if intent, priority, recommended_queue, customer_requested_human or information_sufficient is wrong, or if an entity is missing or hallucinated. Sentiment and churn disagreements are logged separately because they are subjective [P2].
   - **Pass:** Wilson 95% upper bound < 5% (≤ 17/540).
   - **Otherwise:** fix the root cause (prompt or rules), regenerate the affected intents, and re-audit a fresh sample.
   - Any intent with ≥ 4/45 errors triggers a full re-review of that intent.
5. **test_synth.**
   - Gold labels come from the scenario spec. The owner reviews 100% of records, with a blind-first intent pick.
   - Scenario/reviewer disagreements are adjudicated with notes. Ambiguous records are relabeled, or replaced from the same stratum **before freeze**.
   - A volunteer double-labels a 20% stratified subset (144 records). Report Cohen's κ for intent with a bootstrap CI (method in evaluation-statistics.md). A κ below 0.80 triggers a guideline revision and re-review.
6. **test_hard.**
   - The owner writes the cases without LLM assistance (`llm_assisted=false`).
   - A volunteer double-labels all 100; report κ and adjudicate disagreements.
7. **Record fields:** `label_source` ∈ {generator_proposed, human_verified, human_written}, `reviewed_by` (pseudonymous R-ids), `review_round`, `label_notes`.

### D5. Artifact gates (Q6)

Computed per split by `validate.py` and written to `data/manifests/<ver>.quality.json`. The initial thresholds below are **proposals**; calibrate them on the pilot.

- **Hard gates (reject the record):**
  - placeholder/meta leak;
  - schema or rule-checker failure;
  - unmasked PII;
  - exact duplicate within the split.
- **Soft gates (regenerate the offending intent if breached):**
  - greeting-formula rate ≤ 10%;
  - Vendi score per intent ≥ 0.5 × the median across intents;
  - within-split near-duplicate rate (char-5 Jaccard ≥ 0.7) ≤ 2%;
  - for critical intents, the share of tickets containing the intent keyword ≤ 75% in train.
- **Report only:**
  - subject-only probe accuracy;
  - adversarial-validation AUC (a classifier distinguishing train from test_synth text: high is *expected* across families; record it in the dataset card);
  - length histograms;
  - refusal yield per intent.

### D6. Prompt skeletons (Q7)

Both prompt families are **zero-shot** (no exemplars that could be copied or shared) and use different wording, framing, output schemas, pools and families.

- **P-A**, file `ml/prompts/datagen/pa.t1.v1.txt`. Variants t2–t6 are paraphrased and re-ordered versions; t5–t6 are reserved for val.

```text
[SYSTEM]
You create fictional support tickets for QA of a triage model. The product is Taskmoor, a fictional
B2B project-management SaaS. All people and companies are invented; use ONLY the names and values
given in the card. Never output real brands, real emails, URLs, or placeholders such as [Your Name].
Write in the customer's own voice, not as an assistant. Output one JSON object and nothing else.

TASKMOOR FACT SHEET (the only product facts you may use):
{fact_sheet}      # plans + seat limits + SSO/SCIM availability, product areas, feature and integration
                  # names, error-code catalog, regions. NO KB article text, NO example tickets.
LABEL RULES:
{label_rules}     # compact §5 enums with one-line definitions + §9.2 labeling rules (primary = resolve first,
                  # critical-first, entities only if literally present, human request direct/indirect, ...)

[USER]
PERSONA: {persona.first_name} {persona.last_name}, {persona.role} at {company.name}
         ({company.seats} seats, plan={plan}, region={region}); writing habits: {persona.habits}
SITUATION CARD (the ticket must make all of this true):
  primary need: {intent} (definition: {intent_def})     secondary: {secondary or "none"} (order: {order})
  product area: {product_area}   channel: {channel}   difficulty: {difficulty}
  latest-message sentiment: {sentiment}   churn cue: {churn_cue or "none"}
  include these values verbatim: {entities}             # e.g. error_code=SAML_ERR_302; charge_amount=USD 1,280
  deliberately leave out: {omissions or "nothing"}      # needs_info cells
  asks for a human: {none|direct|indirect}              injected text to include verbatim: {injection or "none"}
STYLE CARD: about {target_words} words ({length_bucket}); style={style}; subject style={subject_style};
  greeting/sign-off allowed: {yes|no}; do NOT use these words: {banned_words or "none"}
Return: {"subject": str, "message": str,
         "previous_messages": [{"author": "customer"|"agent", "body": str}],
         "proposed_labels": <TriageModelOutput JSON>,
         "self_check": {"card_satisfied": bool, "note": str}}
```

- **P-B, stage 1** (scenario-first), file `ml/prompts/datagen/pb.s1.v1.txt`:

```text
[SYSTEM]
You are drafting internal case timelines for a fictional software company, Taskmoor (B2B project
management). Write neutral third-person facts only, no dialogue, no advice, 5-8 bullet points.
[USER]
Account: {company.name}, plan {plan}, {company.seats} seats, region {region}.
Event type: {scenario_type}              # derived from intent, e.g. "invoice paid twice", "EU login 5xx since 09:00 UTC"
Timeline anchors: {timestamps}; systems involved: {product_area}, {feature_or_integration}
What the customer already tried: {attempts}; what is unknown to them: {unknowns}
Severity context: {severity}; people involved (fictional): {persona.first_name} ({persona.role})
Return: {"timeline": [str], "customer_goal": str, "facts_customer_knows": [str], "facts_customer_does_not_know": [str]}
```

- **P-B, stage 2** (the email), file `ml/prompts/datagen/pb.m1.v1.txt`:

```text
[SYSTEM]
Write the message a real customer would send to Taskmoor support right now. You are that customer.
Only mention facts from "facts_customer_knows". Keep their knowledge gaps. No greetings unless the
channel style asks for one. Output JSON only.
[USER]
Case timeline: {stage1.timeline}   Customer goal: {stage1.customer_goal}
Facts you know: {stage1.facts_customer_knows}
You: {persona.first_name}, {persona.role}; mood: {sentiment}; you {human_request_phrase_or_nothing}
Channel: {channel} ({channel_format_hint}); length: about {target_words} words; style: {style}
Return: {"subject": str, "message": str, "previous_messages": [{"author": "customer"|"agent", "body": str}]}
```

- **Gold labels for P-B** come from the scenario spec (the intent, secondaries, entities passed in, the human-request flag, omissions → information_sufficient), followed by 100% human verification. The generator is never asked to label.

---

## SPEC IMPACT (do not edit the spec here; raise via ADR-0016 amendment + version bump)

| # | Spec text | Research finding | Proposed change |
|---|---|---|---|
| SI-1 | §9.1.2 "Family A (e.g., Anthropic Claude via API)" | The Anthropic Usage Policy (2025-09-15) prohibits training *any* AI model on inputs/outputs without prior authorization [A1] | Trigger the §9.1.9 fallback: Family A = `openai/gpt-oss-120b` (Apache-2.0). Claude is evaluation-only |
| SI-2 | §9.1.3 Family B "Llama/Mistral/Gemma" | All three are acceptable for test-only use. Llama or Gemma would share a family with a possible base SLM (ADR-0011), and Claude must not be B (E6 home-field, [P4]) | Family B = Mistral Large 3 (Apache-2.0), with Mistral Small 4 as backup |
| SI-3 | §9.3 "≈300/intent incl. other_unclear, oversample critical ×1.3" with train = 3,600 | Arithmetically inconsistent: 3,600 implies ≈248 per non-critical and ≈323 per critical intent; a base of 300 implies 4,350 | State the allocation explicitly (D3) |
| SI-4 | §9.1.6 "reported label error rate must be < 5%" | At n=540 the point rule allows k ≤ 26 (upper CI bound up to ~7%). A per-intent claim is impossible at n≈45 | Pass rule: Wilson 95% upper bound < 5% (k ≤ 17/540); report the CI |
| SI-5 | §9.1.6 "owner reviews 100% of test/hard sets" (single annotator) | Single-annotator gold labels have unknown reliability; benchmark test sets average ≥ 3.3% label errors [P10] | Add a volunteer double-annotation (20% of test_synth, 100% of test_hard) with κ reported |
| SI-6 | §9.1.4 hard set "hand-written by the owner" | LLM-assisted writing would break `label_source=human_written`, and Claude-assisted writing would add Claude style to a test set used for E6 | Require `llm_assisted=false` attestation |
| SI-7 | NG-08 feedback export; stretch G-3 draft LoRA; §8.9 LLM-judge | Anthropic outputs (frontier drafts, judge labels) cannot be used for training without authorization | Add provenance filter + CI rule (D2) to S-12/T-DATA-provenance |
| SI-8 | §9.1.1 matrix | Needs plausibility constraints (e.g., SSO only on business/enterprise per §3) and pairwise coverage, since the full factorial has 1.5M cells | Add a `constraints:` / `coverage:` section (D3) |
| SI-9 | §21 R-10 | Risk realized for the Anthropic generator | Mitigation = SI-1; snapshot the terms in `docs/legal/` with retrieval dates |

---

## IMPLEMENTATION CHECKLIST

- [ ] `docs/legal/generator-terms-2026-09-26.md`: summaries + URLs + effective dates of A1–A3, O5–O8. Re-check at P1 start; re-snapshot if any date changed.
- [ ] ADR-0016 amendment + ADR-new "Generator families and vendor-terms compliance" (SI-1, SI-2, SI-7).
- [ ] `data/spec/generation_matrix.yaml` (D3) + `data/spec/fact_sheet.v1.md` (no KB prose, no spec example tickets) + `data/spec/pools/*` (split-disjoint, seeded).
- [ ] `ml/prompts/datagen/pa.t1..t6.v1.txt`, `pb.s1|s2.v1.txt`, `pb.m1|m2.v1.txt`, mirrored into `prompt_versions`.
- [ ] `ml/src/tw_ml/datagen/generate.py`: sampler + provider clients (gpt-oss host; Mistral API), retry/backoff, JSON validation, provenance stamping, cost logging (tokens × dated price table in config).
- [ ] `ml/src/tw_ml/datagen/validate.py`: schema + rules R1–R10 + artifact metrics (A1–A12) + Vendi/distinct-n + quality report.
- [ ] **Pilot:** 50 P-A + 50 P-B records (~4 per intent). Measure tokens, refusal yield, artifact rates and rule-check pass rate. Update this doc's cost table with measured numbers.
- [ ] Full generation (train 3,600, val 450, test_synth 720) with over-generation; run leakage-and-dedup.md checks; fill quotas.
- [ ] Label QA D4 (rule-checker → cleanlab top-150 → 540 random audit → 100% test review → volunteer κ).
- [ ] CI: extend T-DATA-provenance with the D2 assertions; fail if any `anthropic` family appears in `data/`.
- [ ] Dataset card: generator families + endpoints + dates, prompt families, sizes, QA results (error-rate CI, κ), artifact metrics, adversarial-validation AUC, known limitations (L-01, L-06), terms notes. Mark test_synth "evaluation only".
- [ ] Session log + system-status updated (ERPROT step 6).

---

## OPEN RISKS / TO VERIFY

| Risk / item | Status | Action |
|---|---|---|
| Terms can change (all effective dates recorded above) | Open | Re-verify A1–A3, O5, O8 at P1 start and before publishing datasets |
| Terms of hosts other than Together for gpt-oss-120b | UNVERIFIED | Check the chosen host's terms (ownership, no training/competition restrictions) |
| gpt-oss reasoning-token overhead and harmony handling on the chosen host | UNVERIFIED | Measure in the pilot; set reasoning effort low |
| Mistral Large 3 API model id and price on Mistral's own pricing page (OpenRouter shows $0.50/$1.50) | UNVERIFIED | Confirm on mistral.ai before the run |
| A separate Mistral usage/acceptable-use policy (only the Commercial Terms were reviewed) | UNVERIFIED | Review before generation; test-only use limits the exposure |
| Refusal or sanitization of security/legal/injection tickets | Open | Pilot yield per intent; adjust framing; report yield in the dataset card |
| 26 owner-hours of review inside P1 (D1–D2 +1d) | Open | Start test_synth review in parallel with P2; sequence hard-set writing before generation to avoid contamination |
| Residual shared "LLM style" between Family A and Family B (L-06) | Accepted | Hard set + Bitext OOD; report adversarial-validation AUC |
| Fallback-A licenses (Qwen3-235B, DeepSeek) | UNVERIFIED | Verify on HF before any use |
| Anthropic authorization (if the owner wants Claude as Family A) | Open, optional | Request in writing; store; amend the ADR |

---

## LINKED ADR

- **ADR-0016** (Test set from a different model family + hard set + Bitext OOD): amend it with the family assignment (D1), the matrix constraints (D3) and the QA protocol (D4).
- **ADR-new** "Generator families and vendor-terms compliance" (proposed): records SI-1, SI-2 and SI-7 and the CI enforcement (D2).
- **Related ERPROT docs:** `leakage-and-dedup.md` (cross-split checks), `evaluation-statistics.md` (κ and CI methods), `bitext-ood-dataset.md` (OOD set), `frontier-provider-anthropic.md` (E6 usage and data retention).

---

## SOURCES (all accessed 2026-09-26)

**Vendor terms and licenses**
- [A1] Anthropic Usage Policy (effective 2025-09-15). https://www.anthropic.com/legal/aup
- [A2] Anthropic Commercial Terms of Service (effective 2025-06-17). https://www.anthropic.com/legal/commercial-terms
- [A3] Anthropic Consumer Terms of Service (effective 2025-10-08). https://www.anthropic.com/legal/consumer-terms
- [A4] Claude API pricing (model, batch and cache pricing; tokenizer note). https://platform.claude.com/docs/en/about-claude/pricing
- [O1] openai/gpt-oss-120b model card and USAGE_POLICY. https://huggingface.co/openai/gpt-oss-120b; https://huggingface.co/openai/gpt-oss-120b/blob/main/USAGE_POLICY
- [O2] mistralai/Mistral-Large-3-675B-Instruct-2512 model card. https://huggingface.co/mistralai/Mistral-Large-3-675B-Instruct-2512
- [O3] mistralai/Mistral-Small-4-119B-2603 model card. https://huggingface.co/mistralai/Mistral-Small-4-119B-2603
- [O4] Hugging Face API, mistralai model listing (licenses, dates). https://huggingface.co/api/models?author=mistralai&sort=createdAt&direction=-1&limit=40
- [O5] Mistral AI Commercial Terms of Service (effective 2026-09-25 as displayed). https://legal.mistral.ai/terms/commercial-terms-of-service
- [O6] Llama 3.3 Community License (release date 2024-12-06). https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/LICENSE (llama.com redirects to an identity check)
- [O7] Gemma Terms of Use (last modified 2026-04-01). https://ai.google.dev/gemma/terms
- [O8] Together AI Terms of Service (effective 2026-05-19). https://www.together.ai/terms-of-service
- [O9] OpenRouter endpoints and pricing, openai/gpt-oss-120b. https://openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints
- [O10] OpenRouter endpoints and pricing, mistralai/mistral-large-2512. https://openrouter.ai/api/v1/models/mistralai/mistral-large-2512/endpoints

**Research**
- [P1] Yu et al., "Large Language Model as Attributed Training Data Generator: A Tale of Diversity and Bias", NeurIPS 2023 D&B. https://arxiv.org/abs/2306.15895
- [P2] Li et al., "Synthetic Data Generation with Large Language Models for Text Classification: Potential and Limitations", EMNLP 2023. https://arxiv.org/abs/2310.07849
- [P3] Chung et al., "Increasing Diversity While Maintaining Accuracy: Text Data Generation with LLMs and Human Interventions", ACL 2023. https://arxiv.org/abs/2306.04140
- [P4] Panickssery et al., "LLM Evaluators Recognize and Favor Their Own Generations", 2024. https://arxiv.org/abs/2404.13076
- [P5] Friedman & Dieng, "The Vendi Score: A Diversity Evaluation Metric for Machine Learning". https://arxiv.org/abs/2210.02410
- [P6] Ge et al., "Scaling Synthetic Data Creation with 1,000,000,000 Personas", 2024. https://arxiv.org/abs/2406.20094
- [P7] Kobak et al., "Delving into LLM-assisted writing in biomedical publications through excess vocabulary", Science Advances 11(27), 2025. https://arxiv.org/abs/2406.07016
- [P8] Guo et al., "The Curious Decline of Linguistic Diversity: Training Language Models on Synthetic Text", NAACL 2024 Findings. https://arxiv.org/abs/2311.09807
- [P9] Gururangan et al., "Annotation Artifacts in Natural Language Inference Data", NAACL 2018. https://arxiv.org/abs/1803.02324
- [P10] Northcutt et al., "Pervasive Label Errors in Test Sets Destabilize Machine Learning Benchmarks", NeurIPS 2021 D&B. https://arxiv.org/abs/2103.14749
- [P11] cleanlab 2.9.0 (Apache-2.0) on PyPI and `find_label_issues` docs. https://pypi.org/project/cleanlab/; https://docs.cleanlab.ai/stable/cleanlab/filter.html

**Computation:** the Wilson bounds and cost arithmetic were computed during this research session. Everything is reproducible from the formulas and tables above; the Wilson code is `proportion()` in evaluation-statistics.md D10.

---

**Document Version**: 1.0
**Next Update**: after the 50+50 pilot (replace assumed token counts with measured ones; tune the D5 gates)
