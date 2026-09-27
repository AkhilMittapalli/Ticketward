# Prompt-Injection Defense - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Partially resolved. The control architecture is decided and mapped to OWASP, and the sanitizer and lexicon snippets are tested.
- **Detector chosen by owner decision D-05 (2026-09-26): Llama Prompt Guard 2 22M.** The remaining owner action is accepting the Llama 4 Community License on Hugging Face (gated model) by P6.
- Still open: the evaluation on our corpus (D7) and the benign-FPR threshold fit on val.

**Category**: Security (OWASP LLM01), Architecture
**Linked ADR(s)**: ADR-0010 (deterministic policy engine as data), ADR-0015 (gated frontier), ADR-0019 (Presidio masking), **ADR-0034** (prompt-injection detector as a secondary, non-terminal control, written from this doc's proposal).
**Spec sections**: §6.3 (`injection_echo`), §7.3 (P0–P5), §7.4 (prompt delimiters), §7.5, §8.1 (adversarial seed docs), §9.1 (hard set: 10 injection cases), §9.8 M-13, §12.4, §12.7 (CSP), §13 S-01, §21 R-11, §23
**Method**: ERPROT §0. OWASP canonical sources, vendor model cards, papers as referenced by OWASP, HF/GitHub APIs for licenses and status. All accessed 2026-09-26.

---

## EXECUTIVE SUMMARY

1. **OWASP moved on.** The spec cites the **2025** LLM Top 10. The GenAI Security Project published the **2026 edition** (repo README: "Current release: 2026 — published August 4, 2026") with new ordering. Prompt Injection stays at **LLM01:2026**, Excessive Agency moves to LLM03, and **LLM08:2026 "Hidden Context Exposure"** replaces System Prompt Leakage. §12.4's mapping should be renumbered (Spec impact SI-1).
2. **OWASP now says outright that detection cannot be the primary defense.** LLM01:2026: "no reliable prevention mechanism exists today… Defense is therefore architectural rather than interceptive." Its control #4 says to hold state-change capability in application code and "route privileged calls through a deterministic policy engine that re-validates intent and arguments at execution time." That is Ticketward's design (§7.3). OWASP also cites Nasr et al. (2025), who found "static attack success near zero while adaptive attack success exceeded 90% for most of 12 recent defenses."
3. **Why the policy engine is the primary control here.** The model has no tools and cannot send (S-01). Its outputs are enums, forced categories fire on **lexicon ∪ model**, priority floors can only raise priority, queue changes are allow-listed, the frontier is deny-listed for sensitive intents, and only approved KB content is retrievable. The worst a successful injection can do is mislabel within bounded enums, which the lexicon union and human review catch for critical categories, or cause *more* escalation, which fails safe. The detector is a secondary signal. That is why P0 is **non-terminal**.
4. **The named detector is archived.** The ProtectAI `deberta-v3-base-prompt-injection-v2` model card now opens with "THIS PROJECT HAS BEEN ARCHIVED… no longer under active development or maintained", and GitHub reports `protectai/llm-guard` as `archived: true`. It is still Apache-2.0 and usable as a pinned, frozen artifact. Its own post-training evaluation shows **precision 91.59% / recall 99.74%** on 20,000 prompts, and the card notes it misses jailbreaks and non-English text and produces false positives on system prompts.
   - **Llama Prompt Guard 2** (22M/86M): Llama 4 Community License, HF-gated with manual approval, 512-token window. Meta reports AUC .995/.998 and, on AgentDojo, attack-prevention rates of 78.4%/81.2% vs ProtectAI's 22.2%. These are vendor numbers.
   - **PIGuard** (MIT) targets over-defense but needs `trust_remote_code=True`, which conflicts with A08.
5. **Test corpus.** Three strata: direct ticket-borne attacks with CX-specific attacker goals, indirect KB-borne attacks, and **benign hard negatives** (customers really do write "please ignore my previous email"), plus an **adaptive** red-team round. Seed data (licenses verified): deepset/prompt-injections (Apache-2.0), Lakera/gandalf_ignore_instructions (MIT), microsoft/llmail-inject-challenge (MIT), leolee99/NotInject (MIT). Tooling: garak (Apache-2.0), promptfoo (MIT).

---

## QUESTIONS

| # | Question (spec §23 + implementer needs) | Answered in |
|---|---|---|
| Q1 | What is the current OWASP LLM Top 10 guidance (2025 as specified, and the 2026 update)? | F1 |
| Q2 | Which detector models exist, under which licenses, with what accuracy caveats? | F3, D5 |
| Q3 | How is the injection test corpus built? | F5, D7 |
| Q4 | How is indirect injection via the KB handled? | F4, D4, D5 |
| Q5 | Why is the deterministic policy engine the primary control, and what can an attacker still achieve? | F2, F4, D2 |
| Q6 | How are the sanitizer, delimiters, lexicon, detector windowing, output checks and metrics implemented? | D3–D7 |

---

## FINDINGS

All links below were accessed 2026-09-26.

### F1. OWASP guidance

**LLM01:2025 (as specified in §12.4)** ([genai.owasp.org](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)). It covers direct and indirect injection and lists seven mitigations:
1. constrain model behavior
2. define and validate output formats
3. input and output filtering
4. enforce privilege control and least privilege
5. require human approval for high-risk actions
6. segregate and identify external content
7. adversarial testing

It states: "It is unclear if there are fool-proof methods of prevention for prompt injection."

**2026 edition** ([canonical repo](https://github.com/GenAI-Security-Project/GenAI-LLM-Top10), [publication page](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/), published 2026-08-04 per the repo; the project announcement is dated 2026-09-01/02):

| 2026 ID | Name | 2025 counterpart |
|---|---|---|
| LLM01:2026 | Prompt Injection | LLM01:2025 |
| LLM02:2026 | Sensitive Information Disclosure | LLM02:2025 |
| LLM03:2026 | Excessive Agency | LLM06:2025 |
| LLM04:2026 | Supply Chain | LLM03:2025 |
| LLM05:2026 | Data and Model Poisoning | LLM04:2025 |
| LLM06:2026 | Unbounded Consumption | LLM10:2025 |
| LLM07:2026 | Misinformation | LLM09:2025 |
| LLM08:2026 | **Hidden Context Exposure** | LLM07:2025 System Prompt Leakage (broadened) |
| LLM09:2026 | Vector and Embedding Weaknesses | LLM08:2025 |
| LLM10:2026 | Improper Output Handling | LLM05:2025 |

The 2026 preface confirms these moves: "Excessive Agency climbed to third", "Unbounded Consumption rose four places", "Improper Output Handling fell the furthest, from fifth to tenth", and "What used to be System Prompt Leakage is now Hidden Context Exposure, a broader framework…" ([LLM00_Preface.md](https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/blob/main/2026/final/LLM00_Preface.md)).

**LLM01:2026 controls** ([source file](https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/blob/main/2026/final/LLM01_PromptInjection.md)), summarized:
1. Constrain role and capabilities in the system prompt (a "partial control only").
2. Enforce a strict output schema validated in trusted code (it "catches format violations, not semantic manipulation").
3. Filter at every modality boundary.
4. Keep credentials and state change in app code, routed through a **deterministic policy engine**.
5. **Strip tag-block (U+E0000–E007F), variation-selector (U+FE00–FE0F) and zero-width (U+200B, U+200C, U+200D, U+2060) characters** at every ingest and render boundary.
6. Use a provenance-labelled channel for external content (it "reduces attack success in non-adaptive tests only").
7. Require human confirmation of privileged actions, showing the exact rendered action.
8. Apply the **Rule of Two** (untrusted input, sensitive data, state change/external communication).
9. Treat memory writes as privileged.
10. Pin, sign and verify tools and MCP servers.
11. **Test against adaptive attackers**, with AgentDojo and JailbreakBench as baselines.

It also names support tickets as a *trusted-surface* injection vector: text planted "through a low-privilege channel (a public form, a customer ticket…)".

**LLM08:2026 Hidden Context Exposure** ([source file](https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/blob/main/2026/final/LLM08_HiddenContextExposure.md)) says to "design under the assumption that hidden context is discoverable". Hidden context must not hold credentials and must not be "relied upon as a security boundary for authorization, privilege separation, policy enforcement, or content filtering".

### F2. Research consensus cited by OWASP 2026 (links from its [references.md](https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/blob/main/2026/final/references.md))

- Nasr, Carlini, … Tramèr (2025). *The attacker moves second: Stronger adaptive attacks bypass defenses against LLM jailbreaks and prompt injections*. https://arxiv.org/abs/2510.09023
- UK NCSC (2025-12). *Prompt injection is not SQL injection*. https://www.ncsc.gov.uk/blog-post/prompt-injection-is-not-sql-injection
- NIST AI 100-2e2025. *Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations*. https://csrc.nist.gov/pubs/ai/100/2/e2025/final
- Debenedetti et al. (2025). *Defeating prompt injections by design* (CaMeL). https://arxiv.org/abs/2503.18813
- Willison (2025-06-16). *The lethal trifecta for AI agents*. https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- Meta AI (2025-10-31). *Agents rule of two*. https://ai.meta.com/blog/practical-ai-agent-security/
- Microsoft Research. *Defending against indirect prompt injection attacks with spotlighting*. https://www.microsoft.com/en-us/research/publication/defending-against-indirect-prompt-injection-attacks-with-spotlighting/
- Chen et al. (2025). *StruQ*, USENIX Security '25, which OWASP notes "was bypassed under adaptive attack".

### F3. Detector models

| Model | License / access | Size / window | Scope | Published numbers (vendor) | Status and caveats |
|---|---|---|---|---|---|
| `protectai/deberta-v3-base-prompt-injection-v2` | Apache-2.0; open | DeBERTa-v3-base; `max_length=512` in the card's pipeline | English, injection only ("does not detect jailbreak attacks") | Post-training eval on 20k prompts: Acc 95.25%, **Precision 91.59%**, Recall 99.74%, F1 95.49% ([card](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2)) | **ARCHIVED**: "no longer under active development or maintained". The card says "we do not recommend using this scanner for system prompts, as it produces false-positives". `llm-guard` is archived on GitHub, and its last PyPI release (0.3.16, 2025-05-19) requires Python <3.13. |
| `meta-llama/Llama-Prompt-Guard-2-22M` / `-86M` | **Llama 4 Community License**; HF-gated (manual) | 22M (DeBERTa-xsmall) / 86M (mDeBERTa-base); **512-token** window ("split prompts into segments and scan them in parallel") | Injection **and** jailbreak; the 86M is multilingual | AUC(en) .995 / .998; Recall@1%FPR 88.7% / 97.5% (private benchmark); AgentDojo attack-prevention @3% utility loss 78.4% / 81.2% vs ProtectAI 22.2%, Deepset 13.5%; latency on A100 at 512 tokens 19.3 ms / 92.4 ms ([model card](https://github.com/meta-llama/PurpleLlama/blob/main/Llama-Prompt-Guard-2/86M/MODEL_CARD.md)) | Card limitations: "Vulnerability to Adaptive Attacks", and "Application-Specific Prompts… Fine-tuning on application-specific datasets improves performance". License: "Built with Llama" display plus the AUP (see D5). |
| `leolee99/PIGuard` (formerly InjecGuard) | MIT | DeBERTa-v3-base | Injection; designed against **over-defense**; NotInject benchmark (339 benign samples with trigger words) | ACL 2025 ([card](https://huggingface.co/leolee99/PIGuard)) | Load snippet uses `trust_remote_code=True`, which **conflicts with A08** unless the code is vendored and reviewed. |
| `deepset/deberta-v3-base-injection` | MIT | DeBERTa-v3-base | Injection | AgentDojo 13.5% (Meta's table) | Older (last modified 2024-10). |
| `qualifire/prompt-injection-sentinel` | "other"; HF-gated (auto) | — | — | — | License not assessed. Not recommended. |

All detector numbers are **vendor-reported on their own benchmarks**. None were measured on support tickets. The spec's P0 threshold of 0.8 is therefore an unvalidated starting point.

### F4. Ticketward attack surface: what an injection can and cannot reach

| Decision or output | Who decides | Can injected text change it? | Why that is bounded |
|---|---|---|---|
| Forced review (P1–P5) | Engine: model **∪** lexicon ∪ incident matcher | It can only *add* escalations. Suppressing one needs the lexicon *and* the model to miss. | The lexicon runs on raw masked text, independent of model output |
| Priority | Model, then engine floors (N3) | It can lower the model's label | Floors for security, outage and payment raise it back; nothing can go below a floor |
| Queue | Model, then engine allow-list (§5.8) | It can pick another *allowed* queue | Not-allowed alternates revert to the rule default (`queue_overridden_by_rule`) |
| Frontier eligibility | Engine (§7.5) | It can inflate complexity (a cost attack) | Denylist, evidence gate, per-ticket $0.05 cap and daily budget |
| Draft wording | Model | Yes (claims, links, tone) | Claim guards, the verifier, the URL allow-list, `injection_echo`, and mandatory human approval (S-01). There is no send path. |
| Tools / state change | — | None exist | No tools or function calling (§7.5) |
| Data exfiltration | — | Via the draft only | The agent sees the draft first. CSP `img-src 'self' data:` (§12.7) blocks external image beacons in rendered markdown. |

Rule of Two check (OWASP control #8): Ticketward has (A) untrusted input and (B) sensitive data (masked tickets, internal KB), but **not (C)** state change or external communication. The frontier call has a fixed vendor destination with masked text only. That is an `[A,B]` configuration, which OWASP says needs "an explicit residual-risk assessment". Record it in `docs/security/threat-model.md`.

### F5. Seed datasets and tooling (licenses via HF/GitHub APIs)

| Resource | License | Use |
|---|---|---|
| `deepset/prompt-injections` (HF dataset) | Apache-2.0 | Seed attack phrasings (detector eval only) |
| `Lakera/gandalf_ignore_instructions` | MIT | Seed attack phrasings |
| `microsoft/llmail-inject-challenge` | MIT | Adaptive indirect-injection examples (email-borne, close to our email feed) |
| `leolee99/NotInject` | MIT | Benign-with-trigger-words hard negatives (over-defense) |
| `jackhhao/jailbreak-classification` | Apache-2.0 | Jailbreak-style negatives and positives |
| NVIDIA/garak | Apache-2.0 (active) | Automated probes against the draft endpoint |
| promptfoo | MIT (active) | Red-team configs in CI (manual workflow) |
| ethz-spylab/agentdojo | MIT | Agentic benchmark, of little relevance here (we have no tools) |
| Azure/PyRIT, microsoft/BIPIA | GitHub reports **archived** (BIPIA license NOASSERTION) | Not used |

---

## DECISION / RECOMMENDATION

**D1 Control stack, with the deterministic engine as primary.** The table maps each control to OWASP LLM01:2026.

| Layer | Control | OWASP LLM01:2026 # |
|---|---|---|
| 1 | No tools, no send integration, no account-state change; human approval of every message (S-01, NG-01) | 4, 7, 8 |
| 2 | **Deterministic policy engine**: lexicon ∪ model forced categories, priority floors, queue allow-list, frontier denylist and budget (§7.3/§7.5) | 4 |
| 3 | Enum-constrained JSON output, validated server-side with no unvalidated data reaching the UI (§6.6) | 2 |
| 4 | Input sanitation: NFKC, invisible-character stripping, delimiter and placeholder neutralization (D3) | 5 |
| 5 | Provenance-labelled channels: `<ticket>` and `<source>` wrappers with a per-request nonce, content marked untrusted (D4) | 6, 1 |
| 6 | Approved-only KB, four-eyes approval, KB lint (D5) | 6, (LLM05/LLM09:2026) |
| 7 | Output checks: claim guards, citation verifier, URL allow-list, `injection_echo`, CSP (see `citation-verification.md`) | 2, (LLM10:2026) |
| 8 | Detector (P0, non-terminal, D5) | 3 |
| 9 | Adaptive red-teaming before release (D7) | 11 |

**D2 Invariants for the policy engine, enforced as property tests (§14.3).** These make "primary control" testable rather than rhetorical.
- For any `TriageModelOutput` (hypothesis-generated) combined with a ticket matching a forced lexicon, `policy_decision == human_escalation`.
- `final_priority ≥ floor(ticket, triage)` for every generated input.
- `final_queue ∈ {default} ∪ allowed_alternates(intent)`.
- `frontier_draft ⇒ intent ∉ {security_report, privacy_legal_request} ∧ evidence ∧ budget ∧ residual_pii_clear`.
- The engine never reads draft text, retrieved text or model free-text (`rationale`). Its only inputs are enums, scores, lexicon hits and metadata. An import-linter contract (`policy` must not import `retrieval.chunking`, `providers`, …) keeps it that way.

**D3 Input sanitation (tested with stdlib).** Run it at ingestion (ticket, KB submit) and before rendering.

```python
# backend/src/ticketward/policy/injection.py (sanitize part)
import re
import unicodedata

_INVISIBLE = re.compile(
    "[\U000E0000-\U000E007F"            # tag block (ASCII smuggling), OWASP LLM01:2026 #5
    "︀-️\U000E0100-\U000E01EF"  # variation selectors (+ supplement)
    "​‌‍⁠﻿"      # zero-width + BOM
    "‪-‮⁦-⁩]"         # bidi embedding/override/isolate controls (extra hardening)
)
_DELIMITER = re.compile(r"</?\s*(?:system|assistant|user|ticket|source|instructions?)\b[^>]*>", re.I)


def sanitize(text: str) -> tuple[str, dict[str, int]]:
    text = unicodedata.normalize("NFKC", text)
    text, n_invisible = _INVISIBLE.subn("", text)
    text, n_delims = _DELIMITER.subn(lambda m: m.group(0).replace("<", "‹").replace(">", "›"), text)
    return text, {"invisible_chars": n_invisible, "spoofed_delimiters": n_delims}
```

A non-zero count is recorded as detector evidence (`rules_fired`). The PII masker separately escapes customer-typed `<TYPE_n>` placeholders (see `pii-masking-presidio.md`).

**D4 Prompt assembly (spotlighting-style provenance; §7.4 extended).**
- Wrap untrusted content as `<ticket nonce="{uuid4}">…</ticket>` and each KB chunk as `<source id="{n}" nonce="{uuid4}" doc_type="…">…</source>`. The system prompt states that only text outside these tags is instruction. The nonce is generated per request so an attacker cannot pre-compute a closing tag. D3 already neutralized any literal `</ticket>`.
- The system prompt contains **no secrets and no policy logic that matters for security** (LLM08:2026), because policy lives in the engine. Treat the prompt as public.
- Put a canary string (`CANARY-{random}`) in the system prompt. If the canary, or 8 or more consecutive tokens of the system prompt, appears in a draft, the `injection_echo` flag fires (§6.3, LLM08:2026).

**D5 Detector (P0, secondary, non-terminal).**
- **Model:** `meta-llama/Llama-Prompt-Guard-2-22M`, **if the owner accepts the Llama 4 Community License**. It is gated, requires "Built with Llama" to be displayed prominently when the product is made available, requires following the AUP, and carries the >700M MAU clause. If the license is not accepted, pin the archived `protectai/deberta-v3-base-prompt-injection-v2` by revision and treat it as frozen. Both are evaluated on our corpus (D7) before one is fixed in the new ADR.
- **Inputs:** subject + message + previous messages (masked). Also **KB documents at submit and approve time** (KB lint). A hit blocks approval unless the approver records a justification, which is audit-logged.
- **Windowing:** 512-token windows with overlap, taking the max malicious probability:

```python
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

DET_ID, DET_REV = "meta-llama/Llama-Prompt-Guard-2-22M", "<pinned sha>"   # or the ProtectAI v2 fallback
_tok = AutoTokenizer.from_pretrained(DET_ID, revision=DET_REV)
_model = AutoModelForSequenceClassification.from_pretrained(DET_ID, revision=DET_REV).eval()
_MAL = next(i for i, name in _model.config.id2label.items() if name.upper() in {"MALICIOUS", "INJECTION"})


@torch.inference_mode()
def injection_score(text: str) -> float:
    enc = _tok(text, truncation=True, max_length=512, stride=64, return_overflowing_tokens=True,
               padding=True, return_tensors="pt")
    enc.pop("overflow_to_sample_mapping", None)
    probs = torch.softmax(_model(**enc).logits, dim=-1)[:, _MAL]
    return float(probs.max())
```

- **Threshold:** fit on the corpus *dev* split so that the benign hard-negative FPR is ≤ 2% (proposed target), then report TPR at that FPR. The spec's 0.8 is only the initial value.
- **Effect (unchanged from P0):** add `prompt_injection_suspected`, disable frontier and restrict the draft to a template. Never terminal, because false positives on "please ignore my previous email" must not block a routine answer, only degrade it. Track the over-escalation impact in M-07c.
- **Lexicon (tested):** the stdlib-tested patterns below require an *instruction-object* ("instructions", "rules", "prompt", "policy"), so "please ignore my previous email" does not fire:

```python
INJECTION_LEXICON = [
    r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:instructions?|rules?|prompts?|guidelines?|polic(?:y|ies))\b",
    r"\b(?:system|developer)\s+(?:prompt|message|instructions?)\b",
    r"\byou are now\b|\bact as (?:an?|the)\b[^.\n]{0,30}\b(?:admin|system|developer|unrestricted)\b",
    r"\b(?:mark|set|change|classify)\b[^.\n]{0,30}\b(?:priority|queue|intent|status|ticket)\b[^.\n]{0,20}\b(?:to|as)\b",
    r"\b(?:do not|don't|never)\s+(?:escalate|flag|route)\b",
    r"</?\s*(?:system|assistant|source|ticket|instructions?)\s*>",
]   # compile with re.I; maintained in backend/policy/lexicons/injection.txt
```

**D6 Indirect injection via the KB.**
1. Only `approved`, current and effective versions are retrievable, enforced in SQL and in the BM25 build (S-09, T-RET-approved-only).
2. Four-eyes approval (§10).
3. KB lint at submit: `sanitize` counts, lexicon plus detector on every chunk, markdown sanitized with `nh3`, HTML comments and hidden text dropped.
4. The 3 adversarial `draft` seed docs (§8.1) must never appear in any retrieval run (CI assertion).
5. **Compromised-approval drill:** a *test-only* fixture approves a poisoned doc and asserts that policy decisions do not change (the engine never reads chunk text) and that the claim guards or verifier strip the injected promise.

**D7 Test corpus and metrics.**

| Stratum | Size (proposal) | Construction |
|---|---|---|
| Direct, ticket-borne | 200 | 20 CX attacker goals × 10 variants. Goals: label flip away from forced intents; priority downgrade; queue change; "do not escalate"; forced promise such as "confirm refund approved"; system-prompt exfiltration; attacker URL; request for other customers' data; inflating complexity to force frontier spend; breaking the JSON; delimiter spoofing (`</ticket>`); placeholder spoofing (`<EMAIL_1>`). Positions: subject, body, quoted thread, forwarded email, signature. Obfuscations: base64, ROT13, leetspeak, Unicode tags, zero-width characters, payload split across messages, burial past the 6,000-token truncation boundary. |
| Indirect, KB-borne | 50 | Poisoned chunks (instructions, fake policies, hidden text) inside test-only approved fixtures, per D6.5 |
| Benign hard negatives | 300 | NotInject (MIT) rewritten as tickets, plus 100 hand-written CX cases ("ignore my last email", "override the SSO setting", "our system admin", "prompt payment", pasted logs and configs) |
| Human-written | 10 (plus the hard set) | §9.1, never used for tuning |
| Adaptive round | ≥ 50 | A red-teamer who has read this document, the lexicon and the delimiter scheme (OWASP #11). Seeds come from LLMail-Inject (MIT). |

Split every stratum into dev (tuning) and test (reporting). Metrics:
- **M-13** (spec): policy-bypass-free = 100% (release-blocking) and label-intact ≥ 95%.
- Detector: TPR at the fixed FPR, and ROC-AUC.
- Over-escalation delta on benign cases (M-07c).
- Echo, URL and claim-guard catch rates on successful attacks.
- A separate row for the adaptive round, never merged into the static numbers (Nasr et al.).

---

## SPEC IMPACT (recorded; the spec was NOT edited)

| # | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §12.4 "OWASP Top 10 for LLM Applications (2025)" | The 2026 edition exists with renumbering and the new LLM08 Hidden Context Exposure. | Re-key the table to the 2026 IDs (see the F1 mapping) and keep the 2025 IDs in a column for traceability. |
| SI-2 | §12.4 LLM01 "ProtectAI DeBERTa prompt-injection model, verify" | That model and `llm-guard` are **archived/unmaintained**. | Name Llama Prompt Guard 2 (22M) as primary, subject to license acceptance, and ProtectAI v2 (pinned, frozen) as fallback. PIGuard is excluded by A08. |
| SI-3 | §7.3 P0 "classifier score ≥ 0.8" | The detectors have 512-token windows, and their thresholds are vendor-benchmark-specific. | Say "max over 512-token windows; threshold fitted to benign-FPR ≤ 2% on the dev corpus". |
| SI-4 | §12.4 LLM01 controls, §7.4 | OWASP 2026 control #5 (invisible-character stripping) and nonce-based provenance tags are missing. | Add `sanitize()` at ingest and render, and per-request nonces on `<ticket>`/`<source>`. |
| SI-5 | §9.8 M-13 | Static-only attack results overstate robustness (Nasr et al. 2025). | Report an adaptive-round row separately. The policy-bypass criterion also applies there. |
| SI-6 | §20 / threat model | The Rule of Two `[A,B]` configuration needs a residual-risk assessment (OWASP #8). | Add it to `docs/security/threat-model.md`. |

---

## IMPLEMENTATION CHECKLIST

- [ ] `policy/injection.py`: `sanitize()`, the lexicon from `backend/policy/lexicons/injection.txt`, `injection_score()` (windowed), and a combined P0 evidence record.
- [ ] Property tests D2 (hypothesis) plus an import-linter contract: `policy` must not import `providers` or chunk text.
- [ ] Prompt builder: per-request nonces, escaped delimiters, canary string, and an `injection_echo` check (canary or an 8-token system-prompt overlap).
- [ ] KB lint on submit and approve (sanitize counts, lexicon, detector). Block unless a justification is recorded (audit `kb.approve_with_lint_override`).
- [ ] Detector decision: owner accepts or declines the Llama 4 Community License (record in the new ADR). Download from HF with a token and pin the revision. If PG2 is used, add a "Built with Llama" notice to the README and UI footer.
- [ ] Build the D7 corpus in `evals/injection/` (dev/test), with provenance fields and licenses listed in `data/README.md`.
- [ ] CI: M-13 smoke on the dev fixture. Nightly: the full test corpus plus garak/promptfoo probes against the Compose stack with a stub or real SLM.
- [ ] Measure detector CPU latency (P50/P95 per ticket) on the reference box.

## OPEN RISKS / TO VERIFY

| Item | Status |
|---|---|
| Detector accuracy on support-ticket prose (all published numbers are vendor benchmarks) | **UNVERIFIED**; measured by D7 |
| PG2 license acceptance and gating (manual approval may take time) | Owner decision; ProtectAI fallback ready |
| ProtectAI v2 is archived, so no fixes will come for new attack styles | Accepted for a secondary control; revisit yearly |
| Adaptive attacks will beat any detector and lexicon | Expected. The engine invariants (D2) and human approval are what must hold. |
| Cost attack: injected text inflating complexity to trigger frontier calls | Bounded by the per-ticket cap and daily budget. Add a test that injection text cannot raise `complexity_score` (computed from retrieval and metadata only). |
| Over-escalation from lexicon and detector false positives | Measure M-07c. Tune on dev only. |

## LINKED ADR

- **ADR-0010** (policy engine as data): add the D2 invariants as acceptance tests.
- **ADR-0015** (frontier gating): P0 disables frontier (unchanged).
- **New ADR (proposed)**: "Prompt-injection detector = Llama Prompt Guard 2 22M (fallback: ProtectAI v2 pinned), non-terminal P0, windowed, FPR-calibrated". Alternatives: PIGuard (A08), deepset, commercial APIs (vendor plus data egress).

## SOURCES (all accessed 2026-09-26)

1. OWASP LLM01:2025 Prompt Injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
2. OWASP GenAI LLM Top 10 2026 canonical repo and README list: https://github.com/GenAI-Security-Project/GenAI-LLM-Top10 ; publication page https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/ ; announcement https://genai.owasp.org/2026/09/01/owasp-genai-security-project-unveils-2026-top-10-for-llm-applications-new-agent-control-standard-and-sponsors-as-community-tops-30000-members/
3. LLM01:2026 and LLM08:2026 canonical Markdown, plus references.md: `2026/final/` in the repo above
4. ProtectAI deberta-v3-base-prompt-injection-v2 card (archive banner, metrics, limitations): https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2 ; llm-guard repo status (GitHub API `archived: true`): https://github.com/protectai/llm-guard ; PyPI https://pypi.org/pypi/llm-guard/json
5. Llama Prompt Guard 2 model card and LICENSE (Llama 4 Community License): https://github.com/meta-llama/PurpleLlama/tree/main/Llama-Prompt-Guard-2 ; HF gating via https://huggingface.co/api/models/meta-llama/Llama-Prompt-Guard-2-22M
6. PIGuard card: https://huggingface.co/leolee99/PIGuard (paper https://aclanthology.org/2025.acl-long.1468.pdf)
7. deepset/deberta-v3-base-injection (license via HF API): https://huggingface.co/deepset/deberta-v3-base-injection
8. Datasets (licenses via HF API): https://huggingface.co/datasets/deepset/prompt-injections ; https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions ; https://huggingface.co/datasets/microsoft/llmail-inject-challenge ; https://huggingface.co/datasets/leolee99/NotInject ; https://huggingface.co/datasets/jackhhao/jailbreak-classification
9. Tools (GitHub API license and archive status): https://github.com/NVIDIA/garak ; https://github.com/promptfoo/promptfoo ; https://github.com/ethz-spylab/agentdojo ; https://github.com/Azure/PyRIT ; https://github.com/microsoft/BIPIA
10. Papers and posts listed in F2 (links as given there)

---

**Document Version**: 1.0
**Next Update**: After the owner accepts the Prompt Guard 2 license on Hugging Face and the D7 corpus evaluation runs (P6/P10)
