# Citation Verification and Claim Guards - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-26
**Status**: Partially resolved. The verifier architecture, model shortlist (licenses and published accuracy) and claim-guard patterns are decided, and the patterns are tested. The thresholds need a human-labelled calibration set (P6), and CPU latency must be measured.
**Category**: Grounding / Safety (LLM09 Misinformation)
**Linked ADR(s)**: ADR-0009 (today the cross-encoder doubles as the verifier). Proposes a **new ADR** "Citation verifier: lexical anchors + NLI + claim guards" (number TBD; next free after ADR-0030).
**Spec sections**: §6.3 (`DraftSentence`, `guard_flags`), §7.2 (routine path "NLI-lite"), §7.6 A3, §8.7, §8.9, §9.8 M-06, §12.4 LLM09, §13 S-04..S-07, §14.3, §23
**Method**: ERPROT §0. Model cards and configs, papers, leaderboard, library source. All accessed 2026-09-26.

---

## EXECUTIVE SUMMARY

1. **The current verifier measures relevance, not support.** Spec §7.2/§8.7 scores each cited sentence with `ms-marco-MiniLM` and treats a sigmoid of ≥ 0.5 as supported. That model's card says it "was trained on the MS Marco Passage Ranking task" and is meant to "sort the passages" for a query. Its score is a **relevance** score. It has no entailment or contradiction output, so an on-topic sentence that *contradicts* or *overstates* its chunk can still score highly. The same model cannot produce the "contradiction score ≥ 0.7" that §7.6 A3 relies on.
2. **Recommendation: a layered verifier.**
   - L0 structural checks.
   - L1 **lexical anchors**: every number, amount, percentage and error code in the sentence must appear in the cited chunk. This is deterministic and tested.
   - L2 **3-class NLI** with `cross-encoder/nli-deberta-v3-base` (Apache-2.0; SNLI 92.38 / MNLI-mm 90.04 per its card). The premise is windowed to fit 512 tokens, following SummaC's sentence-level finding.
   - L3 doc-type-aware **claim guards** (regex, tested).
   - L4 human approval, which always happens (S-01).
   Grounding-specialised models are the challengers for L2: **FactCG-DeBERTa-v3-Large** (MIT, 0.4B, LLM-AggreFact avg 75.6) and **MiniCheck-Flan-T5-Large** (MIT, 0.8B, 75.0).
3. **Excluded, with reasons.** Bespoke-MiniCheck-7B is **CC BY-NC 4.0**. HHEM-2.1-Open needs `trust_remote_code=True`, which conflicts with A08. AlignScore recommends PyTorch 1.12.1, an old stack. Granite Guardian 3.3 (8B) is too heavy for the CPU budget.
4. **Gotcha: NLI label order differs between models.** `cross-encoder/nli-deberta-v3-base` uses `{0: contradiction, 1: entailment, 2: neutral}`, while `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` uses `{0: entailment, 1: neutral, 2: contradiction}`. Always read `config.id2label`. Also, neither model applies softmax by default in sentence-transformers.
5. **Calibration.** Fit thresholds on a **separate** calibration set of about 300 human-labelled (sentence, cited chunk) pairs, not on the 150-sentence M-06 audit. Freeze them, then report M-06 on the audit with Wilson CIs and Cohen's κ. At n=150, an observed 0.85 has a Wilson 95% CI of [0.784, 0.898], so the audit is too small to prove "≥ 0.85" unless the observed value is around 0.90 or higher.

---

## QUESTIONS

| # | Question (spec §23 + implementer needs) | Answered in |
|---|---|---|
| Q1 | Is a cross-encoder good enough as a support scorer, or is an NLI model needed? | F1, F2, D1 |
| Q2 | Which NLI or grounding models fit (license, size, CPU, published accuracy)? | F2, D1 |
| Q3 | How are thresholds calibrated against the human audit? | F4, D3 |
| Q4 | What claim-guard patterns cover pricing, refund eligibility, account status and incident status? | F5, D4 |
| Q5 | How are long chunks, multi-citation sentences, A3 conflicts, latency and UI output handled? | F3, D2, D5 |

---

## FINDINGS

All links below were accessed 2026-09-26.

### F1. What the MS MARCO cross-encoder actually scores

- The [card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2) says: "This model was trained on the MS Marco Passage Ranking task… Given a query, encode the query with all possible passages… Then sort the passages in a decreasing order."
- It outputs a single raw logit (config activation `Identity`). A single score cannot separate *entails*, *neutral but on-topic* and *contradicts*. Illustration (not measured): the draft sentence "SSO is available on the Starter plan" against a chunk saying "SAML SSO is available on Business and Enterprise" is highly relevant but contradicted.
- Keep it where it belongs, as the retrieval reranker (see `hybrid-retrieval.md`). Do not use it for verification.

### F2. Verifier candidates (licenses verified via the HF API; accuracy as published)

| Model | License | Size | Output | Max len | Published accuracy (source) | Fit |
|---|---|---|---|---|---|---|
| **`cross-encoder/nli-deberta-v3-base`** | Apache-2.0 | DeBERTa-v3-base | 3-class, `id2label {0: contradiction, 1: entailment, 2: neutral}` | 512 | SNLI test 92.38, MNLI-mismatched 90.04 ([card](https://huggingface.co/cross-encoder/nli-deberta-v3-base)) | **Default L2**. Native `CrossEncoder`; gives the contradiction score for A3. |
| `cross-encoder/nli-deberta-v3-small` | Apache-2.0 | DeBERTa-v3-small | 3-class | 512 | card | Faster fallback if base misses the budget. |
| `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` | MIT | DeBERTa-v3-base | 3-class, `{0: entailment, 1: neutral, 2: contradiction}` | 512 | card | Challenger; trained on more fact-checking-style data (FEVER/ANLI). |
| `tasksource/deberta-small-long-nli` | Apache-2.0 | DeBERTa-v3-small | NLI | 1,680 ("context length of 1680 tokens", [card](https://huggingface.co/tasksource/deberta-small-long-nli)) | card | Challenger for whole-chunk premises without windowing. |
| **`yaxili96/FactCG-DeBERTa-v3-Large`** | MIT | 0.4B | 2-class (loaded with `num_labels=2`; label semantics per repo, **verify**) | 512 | LLM-AggreFact avg 75.6 ([leaderboard](https://llm-aggrefact.github.io/)); NAACL 2025 ([card](https://huggingface.co/yaxili96/FactCG-DeBERTa-v3-Large)) | **Challenger L2 (support)**. Best small open model on the leaderboard view. |
| **`lytang/MiniCheck-Flan-T5-Large`** (plus RoBERTa-L, DeBERTa-v3-L variants) | MIT (all three) | 0.8B (T5-L) | supported probability | internal chunking (library) | LLM-AggreFact 75.0; paper: "GPT-4-level performance but for 400x lower cost" ([arXiv 2404.10774](https://arxiv.org/abs/2404.10774), EMNLP 2024) | Challenger / offline audit judge. The `minicheck` repo is Apache-2.0. |
| `bespokelabs/Bespoke-MiniCheck-7B` | **CC BY-NC 4.0** (card: "For commercial licensing, please contact…") | 7B | supported probability | long | LLM-AggreFact 77.4 | **Excluded** (license and size). |
| `yzha/AlignScore` (base 125M / large 355M) | MIT | 125M/355M | alignment score | splits context into ~350-token chunks and claims into sentences | ACL 2023 ([repo](https://github.com/yuh-zha/AlignScore)) | Not preferred: "PyTorch 1.12.1 (recommended)", old dependencies versus our transformers v5 stack. |
| `vectara/hallucination_evaluation_model` (HHEM-2.1-Open) | Apache-2.0 | flan-t5-base | consistency 0..1 | "unlimited" | Card: "<600MB RAM at 32-bit precision and ~1.5 second for a 2k-token input on a modern x86 CPU" | **Excluded by A08**: requires `trust_remote_code=True`. |
| `KRLabsOrg/lettucedect-base-modernbert-en-v1` (/large) | MIT | ModernBERT base/large | **token-level** hallucinated spans | 8,192 | large: RAGTruth example-level F1 79.22% ([card](https://huggingface.co/KRLabsOrg/lettucedect-base-modernbert-en-v1)) | Optional: highlight unsupported *spans* in the UI. Not a gate. |
| `ibm-granite/granite-guardian-3.3-8b` | Apache-2.0 | 8B | groundedness risk | long | LLM-AggreFact 76.5 | Too heavy for the CPU pipeline. |

LLM-AggreFact reference rows: Bespoke-MiniCheck-7B 77.4, Claude-3.5 Sonnet 77.2, Granite Guardian 3.3 76.5, FactCG-DeBERTa-L 75.6, MiniCheck-Flan-T5-L 75.0. The leaderboard page states neither its update date nor its threshold protocol. Treat these as relative indicators only.

### F3. Long premises and granularity

- The DeBERTa NLI cross-encoders have `max_position_embeddings = 512`. Our chunks target 350 tokens with a max of 512 (§8.3), so chunk plus sentence can exceed 512 and the premise gets truncated.
- SummaC ([Laban et al., TACL, arXiv 2111.09525](https://arxiv.org/abs/2111.09525)) attributes the failure of earlier NLI-based checking to "a mismatch in input granularity between NLI datasets (sentence-level), and inconsistency detection (document level)". It fixes this by scoring at sentence level and aggregating. AlignScore uses the same idea with ~350-token chunks.
- Design consequence: score each draft sentence against **sliding windows of 3 chunk sentences** (stride 1) and take the max entailment. For a sentence citing two chunks, score both and take the max. Also try the concatenation when it fits in 512 tokens, for claims that combine facts.

### F4. Calibration: what is available and what we must build

- No source gives a threshold for our domain. The model cards report accuracy on generic benchmarks, and LLM-AggreFact reports balanced accuracy without describing its threshold protocol on the page. **Thresholds must come from our own labelled data.**
- Sample sizes (Wilson 95% intervals, computed): n=150 at p=0.85 gives [0.784, 0.898]; n=150 at p=0.90 gives [0.842, 0.938]; n=300 at p=0.90 gives [0.861, 0.929]; n=300 at p=0.95 gives [0.919, 0.969].

### F5. Claim guards (spec S-04..S-06, LLM09)

The patterns in D4 were run against positive and negative sentences with the Python stdlib (all assertions pass). Negations and hedges were tested explicitly: "A billing specialist will review your refund request…" and "I can't confirm refund eligibility here…" must **not** fire.

---

## DECISION / RECOMMENDATION

**D1 Layered verifier (replaces "NLI-lite: cross-encoder support ≥ 0.5").**

| Layer | Check | Failure effect |
|---|---|---|
| L0 structure | `citation_ids` non-empty for `factual`/`procedural`; indices in 1..5; mapped to `chunk_id` (§8.7) | sentence removed, counted as unsupported |
| L1 lexical anchors | Every money amount, percentage, error code and number ≥ 2 digits in the sentence must appear (whitespace/comma-insensitive) in a cited chunk | unsupported (this catches "$18" vs "$16") |
| L2 NLI | For windows W of the cited chunk(s): `entail = max P(entailment)` and `contra = max P(contradiction)`. Supported iff `entail ≥ τ_entail` (initially 0.5, calibrated) | unsupported. If `contra ≥ τ_contra` and `entail < τ_entail`, the sentence is contradicted and flagged. |
| L3 claim guards | D4 patterns plus doc-type rules | block, strip or flag per rule |
| L4 human | Draft always reviewed (S-01); struck-out sentences are visible (§7.8) | — |

The rule that more than 30% of sentences removed triggers `clarifying_questions` (§7.2) stays. `DraftCitation.support_score` stores the L2 `entail` value.

```python
# backend/src/ticketward/retrieval/citations.py  (sketch; regexes tested with stdlib)
from __future__ import annotations

import re
from dataclasses import dataclass

import torch
from sentence_transformers import CrossEncoder

NLI_ID, NLI_REV = "cross-encoder/nli-deberta-v3-base", "<pin sha at build>"
_nli = CrossEncoder(NLI_ID, revision=NLI_REV, max_length=512, device="cpu",
                    activation_fn=torch.nn.Softmax(dim=-1))          # default is Identity for 3 labels
_IDX = {label.lower(): int(i) for i, label in _nli.config.id2label.items()}   # NEVER hard-code label order
ENT, CON = _IDX["entailment"], _IDX["contradiction"]

_ANCHOR = re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?\s?%"
                     r"|\b[A-Za-z]+(?:[_-][A-Za-z0-9]+)*[_-]\d+\b|\b\d{2,}(?:\.\d+)?\b")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def _norm(s: str) -> str:
    return re.sub(r"[\s,]", "", s).lower()


def anchors_ok(sentence: str, evidence: str) -> bool:
    ev = _norm(evidence)
    return all(_norm(m.group(0)) in ev for m in _ANCHOR.finditer(sentence))


def windows(chunk: str, size: int = 3) -> list[str]:
    sents = [s for s in _SENT.split(chunk.strip()) if s]
    return [" ".join(sents)] if len(sents) <= size else [" ".join(sents[i:i + size]) for i in range(len(sents) - size + 1)]


@dataclass(frozen=True)
class Verdict:
    supported: bool
    contradicted: bool
    entail: float
    contra: float


def verify(sentence: str, cited_chunks: list[str], tau_entail: float, tau_contra: float) -> Verdict:
    evidence = "\n".join(cited_chunks)
    if not cited_chunks or not anchors_ok(sentence, evidence):
        return Verdict(False, False, 0.0, 0.0)
    premises = [w for c in cited_chunks for w in windows(c)]
    if len(cited_chunks) > 1:
        premises.append(evidence)                     # combined claims; CrossEncoder truncates at 512
    probs = _nli.predict([(p, sentence) for p in premises], batch_size=16, show_progress_bar=False)
    entail, contra = float(probs[:, ENT].max()), float(probs[:, CON].max())
    return Verdict(entail >= tau_entail, contra >= tau_contra and entail < tau_entail, entail, contra)
```

Run the whole draft as one batched `predict` call in a bounded thread (§14.2). Challengers (FactCG, MiniCheck) plug in behind the same `verify` signature.

**D2 Model selection on the calibration set.** Choose the L2 model by **AUROC for "unsupported"** on the calibration pairs, subject to verification P95 ≤ 3 s per draft on the reference box (up to about 15 factual sentences × about 3 windows). The candidates are nli-deberta-v3-base (default), MoritzLaurer base, FactCG-DeBERTa-L and MiniCheck-DeBERTa-L/Flan-T5-L. **CPU latency is UNVERIFIED for all of them**, so measure it. Only HHEM publishes a CPU figure, and HHEM is excluded.

**D3 Calibration protocol (our design, not from a source).**
1. **Calibration set (new, P6):** about 300 (sentence, cited-chunk) pairs sampled from **dev** drafts (local and frontier), stratified by guard type and doc_type. Oversample risky kinds: numbers, capability and incident. Labels: `supported`, `partially_supported`, `unsupported`, `contradicted`, following a one-page guideline in `docs/labeling_guidelines.md`. Two annotators label a 60-pair overlap, and Cohen's κ is reported.
2. **Fit:** with `partially_supported` counted as unsupported, choose `τ_entail` as the smallest threshold at which **precision of "passes verifier" ≥ 0.95** on calibration. This gives margin above M-06's auto ≥ 0.90. Choose `τ_contra` so that contradicted recall is ≥ 0.9, then check the false-contradiction rate. Store both in `policy_rule_sets.thresholds.support_min` with the justifying `eval_run_id` (§7.3 convention).
3. **Freeze, then test:** evaluate on the **separate** 150-sentence human audit (M-06). Report automatic precision, human precision, verifier-vs-human κ and Wilson CIs. Do not re-tune on the audit.
4. **Drift check:** re-run calibration when the draft model, prompt or verifier model changes (regression gate §9.10).

**D4 Claim guards: patterns (tested) and doc-type rules.**

```python
MONEY = r"(?:[$€£]\s?\d[\d,]*(?:\.\d{1,2})?|\b\d[\d,]*(?:\.\d{1,2})?\s?(?:usd|eur|gbp|dollars?)\b)"
GUARDS = {
  "claims_pricing_without_source": re.compile(
      rf"{MONEY}|\b(?:per|/)\s?(?:seat|user|month|mo|year|yr)\b|\b(?:costs?|priced at|price (?:is|of))\b", re.I),
  "claims_refund_eligibility": re.compile(
      r"\b(?:you(?:'re| are)?|your (?:account|order|subscription|payment|charge)s?)\b[^.?!]{0,40}?"
      r"\b(?:(?:is|are|will be|qualif(?:y|ies)|eligible)[^.?!]{0,20}?\brefund(?:ed|able)?|(?:be|been) refunded)\b"
      r"|\b(?:we(?:'ll| will| have|'ve)?|i(?:'ll| will| have|'ve)?)\s+(?:issued?|process(?:ed)?|approved?|refund(?:ed)?)\b[^.?!]{0,30}?\brefund\b"
      r"|\brefund (?:has been|was|is) (?:approved|issued|processed)\b", re.I),
  "claims_account_status": re.compile(
      r"\byour (?:account|workspace|subscription|plan|invoice|payment)s? (?:is|are|has been|have been|was|were)\s+"
      r"(?:now\s+)?(?:active|suspended|locked|reactivated|cancel(?:l)?ed|past due|overdue|in good standing|paid|unpaid"
      r"|renewed|downgraded|upgraded|closed|deleted|restored)\b", re.I),
  "claims_incident_status_without_record": re.compile(
      r"\b(?:the|this|our)\s+(?:issue|incident|outage|problem|degradation)\s+(?:is|has been|was)\s+(?:now\s+)?"
      r"(?:resolved|fixed|mitigated|identified|under investigation|being investigated|monitored|over)\b"
      r"|\b(?:we are|we're)\s+(?:currently\s+)?(?:investigating|monitoring)\b|\b(?:eta|root cause)\b"
      r"|\bshould be (?:back|restored|fixed)\b", re.I),
  "claims_capability_without_source": re.compile(
      r"\b(?:taskmoor|the app|the platform|it)\s+(?:now\s+)?(?:supports?|does(?:n't| not) support|can(?:not|'t)?"
      r"|allows?|lets you|integrates? with)\b|\byou can(?:not|'t)?\s+(?:now\s+)?(?:use|enable|export|import|connect"
      r"|configure|set up)\b", re.I),
  # proposed new flag (see SI-4): timing promises must come from policy_sla
  "claims_timing_without_source": re.compile(
      r"\bwithin\s+\d+\s*(?:business\s+)?(?:minutes?|hours?|days?)\b|\bby\s+(?:tomorrow|today|tonight"
      r"|end of (?:the )?day|eod|monday|tuesday|wednesday|thursday|friday)\b|\b(?:today|immediately|right away)\b", re.I),
}
```

| Guard | Allowed only if | Action when violated |
|---|---|---|
| pricing | a cited chunk is from `doc_key = policy_pricing_and_plans` **and** L1 anchors match (S-05) | strip sentence, set flag, approve needs `acknowledged_warnings` |
| refund eligibility | **never** (S-06, A4) | strip, flag, force `holding_reply_template` |
| account status | **never** (S-04, A4); account facts appear only in the metadata panel | strip and flag |
| incident status | the cited chunk is the matched `known_incident` record **and** the status word equals `incident_meta.status` (investigating, identified, monitoring or resolved; P4) | strip and flag |
| capability | a cited chunk is `product_doc` or `help_article` and L2 supports the sentence (S-05) | strip and flag |
| timing (new) | a cited chunk is `policy_sla` | strip and flag |
| URL | the URL resolves to a KB `url_slug` (§8.7) | strip the URL, set `contains_url_not_in_kb` |

Guards run on **every** draft sentence, including `empathy`, `holding` and `question` kinds, because a model can hide a claim in an "empathy" sentence.

**D5 A3 conflicting evidence.** Among the top-5 reranked chunks, take pairs with the same `doc_type` and overlapping `product_areas`. Run NLI in both directions over sentence windows. If `max P(contradiction) ≥ τ_conflict` (initially 0.7, calibrated on about 50 synthetic conflicting and consistent pairs built from the adversarial seed docs, §8.1), the result is `human_escalation` with `conflicting_evidence`. This needs the 3-class model from D1, which is a further reason not to keep the relevance cross-encoder as the verifier.

---

## SPEC IMPACT (recorded; the spec was NOT edited)

| # | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §7.2 (routine path), §8.7 | "NLI-lite: cross-encoder support ≥ 0.5" uses a passage-*relevance* model (MS MARCO card) as a *support* scorer. | Replace it with the D1 layered verifier (anchors + 3-class NLI + guards). Keep the cross-encoder for retrieval only. |
| SI-2 | §7.6 A3 | A "verifier contradiction score ≥ 0.7" cannot come from the single-logit relevance cross-encoder. | Specify the 3-class NLI model and the calibrated `τ_conflict`. |
| SI-3 | §8.9, §9.8 M-06 | If thresholds are fitted on the 150-sentence audit, M-06 is optimistic. n=150 also gives a ±~5.7-point CI. | Add a separate ~300-pair calibration set with a 60-pair double-annotated overlap, and report Wilson CIs. |
| SI-4 | §6.3 `guard_flags` | High-risk replies must avoid "timing promises beyond the SLA doc" (§7.2), but there is no flag for that. | Add `claims_timing_without_source` (pattern in D4). |
| SI-5 | §12.3 A08 × candidate models | HHEM-2.1-Open needs remote code, and Bespoke-MiniCheck-7B is CC BY-NC. | Record both as excluded alternatives in the new ADR. |

---

## IMPLEMENTATION CHECKLIST

- [ ] `retrieval/citations.py`: implement L0–L3 per D1/D4. Pin the NLI `revision`, derive labels from `config.id2label`, and apply softmax explicitly.
- [ ] Unit tests: the D4 positives and negatives (copied from the tested set), plus anchor tests (`$16` vs `$18`, `1,000` vs `1000`), window tests, and a label-order test that loads the config and asserts that `entailment` and `contradiction` indices exist.
- [ ] Property test (hypothesis): no sentence with an unmatched number is ever marked supported.
- [ ] Build the calibration set (about 300 pairs, 60 double-labelled) from **dev** drafts and write `evals/verifier/calibration.v1.jsonl` with provenance.
- [ ] Run D2 model selection (AUROC plus CPU P95 per draft) and record the result in the new ADR with the `eval_run_id`.
- [ ] Fit `τ_entail`, `τ_contra` and `τ_conflict` (D3), store them in `policy_rule_sets.thresholds`, and gate them in CI (§9.10 smoke: verifier decisions match golden on the fixture).
- [ ] UI (§7.8): strike through unsupported sentences and show guard flags. Optionally highlight LettuceDetect spans (not a gate).
- [ ] M-06: report automatic and human precision, κ, Wilson CI, and the breakdown by guard type and provider (local vs frontier).

## OPEN RISKS / TO VERIFY

| Item | Status |
|---|---|
| CPU latency per draft for every L2 candidate | **UNVERIFIED**; measure (D2) |
| FactCG label semantics (which index means "supported") | **UNVERIFIED**; check the repo before use |
| Transfer of MNLI/SNLI-trained NLI to support-ticket prose | Unknown; the calibration set measures it |
| Regex guards are English-only and pattern-based, and can miss paraphrases ("we'll send the money back") | Known limitation. L2 and the human reviewer are the backstops. Extend the positives from reviewer flags (feedback `wrong_citation`/`hallucination`). |
| Over-blocking of legitimate SLA statements quoted from `policy_sla` | Allowed by the doc-type rule. Test that it passes. |
| An LLM-judge secondary metric (§8.9) must never replace the human audit | Unchanged (spec) |

## LINKED ADR

- **ADR-0009**: narrow it to retrieval reranking only.
- **New ADR (proposed)**: "Citation verifier = lexical anchors + 3-class NLI (default `cross-encoder/nli-deberta-v3-base`) + doc-type claim guards; thresholds calibrated on a separate labelled set". Alternatives: MS MARCO CE (relevance only), FactCG, MiniCheck, AlignScore, HHEM (excluded, A08), Bespoke-MiniCheck (excluded, CC BY-NC), LLM-judge.

## SOURCES (all accessed 2026-09-26)

1. ms-marco-MiniLM-L6-v2 card and config: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2
2. cross-encoder/nli-deberta-v3-base card and config (`id2label`): https://huggingface.co/cross-encoder/nli-deberta-v3-base
3. MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli config (`id2label`): https://huggingface.co/MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
4. tasksource/deberta-small-long-nli card: https://huggingface.co/tasksource/deberta-small-long-nli
5. FactCG-DeBERTa-v3-Large card: https://huggingface.co/yaxili96/FactCG-DeBERTa-v3-Large (paper https://arxiv.org/abs/2501.17144)
6. MiniCheck repo: https://github.com/Liyan06/MiniCheck ; paper https://arxiv.org/abs/2404.10774 ; HF licenses via https://huggingface.co/api/models/lytang/MiniCheck-Flan-T5-Large (and RoBERTa/DeBERTa variants)
7. Bespoke-MiniCheck-7B card (license section): https://huggingface.co/bespokelabs/Bespoke-MiniCheck-7B
8. LLM-AggreFact leaderboard: https://llm-aggrefact.github.io/
9. AlignScore repo: https://github.com/yuh-zha/AlignScore ; checkpoints https://huggingface.co/yzha/AlignScore
10. HHEM-2.1-Open card: https://huggingface.co/vectara/hallucination_evaluation_model
11. LettuceDetect card: https://huggingface.co/KRLabsOrg/lettucedect-base-modernbert-en-v1
12. Granite Guardian 3.3-8B (license via HF API): https://huggingface.co/ibm-granite/granite-guardian-3.3-8b
13. SummaC (Laban et al.): https://arxiv.org/abs/2111.09525
14. sentence-transformers CrossEncoder default activation (source): https://github.com/huggingface/sentence-transformers/blob/main/sentence_transformers/cross_encoder/model.py

---

**Document Version**: 1.0
**Next Update**: After the calibration set is labelled and D2/D3 are run (P6). Then fill in thresholds and latency and flip Status to Resolved.
