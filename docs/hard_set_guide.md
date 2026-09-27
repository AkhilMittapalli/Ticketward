# Hard-set authoring guide (test_hard, 100 cases)

The hard set is the only test data a person writes. It stress-tests the triage model on the
tickets synthetic generators handle worst: implicit churn, indirect requests for a human,
prompt injection, missing details, legal threats buried in billing tickets, and ambiguous
wording. Spec v1.1 §9.1 step 4, §9.3, A-10, A-11; ADR-0016.

* **Who writes it:** the owner, by hand, **without any LLM assistance** (no drafting, no
  paraphrasing, no translation, no "improve this wording", no spell-checking with an LLM). Every
  case carries the attestation `llm_assisted: false`. A Claude-assisted case would also add
  Claude's style to a test set used to compare against Claude (E6).
* **When:** before you look at any generated train, val or test_synth ticket (risk R-22), so the
  hard set cannot drift toward what the generators produce. Never paraphrase a generated ticket.
* **What happens to it:** `python -m tw_ml.datagen hardset split` puts 30 cases in `hard_dev`
  (error analysis allowed) and 70 in `hard_final`, which stays **sealed until P10**: never look at
  model outputs on `hard_final` before then, and never use any hard case (or anything inspired by
  one) as training data without the v0.2 procedure (stricter leakage flags + attestation).

## Quotas

The validator (`hardset validate`) fails until every row below is met. Tags overlap: one case can
count toward several strata (for example an indirect human request inside a billing ticket).

| Stratum | Requirement | How it is counted |
|---|---|---|
| Total | exactly 100 cases | rows other than the template |
| Every intent label | >= 6 each, all 13 labels including `other_unclear` | `labels.intent` |
| Critical intents combined | >= 25 | primary intent in security, outage, cancellation, duplicate charge, payment failure |
| Prompt-injection attempts | >= 10 | `strata.injection = true` |
| Needs more information | >= 10 | `strata.needs_info = true` (and `labels.information_sufficient = false`) |
| Human-request phrasings | >= 8, of which >= 3 indirect | `strata.human_request` = `direct` or `indirect` |
| Legal threat inside a billing ticket | >= 6 | `strata.legal_threat_in_billing = true` with a billing intent (duplicate charge, payment failure or refund) |

13 labels x 6 = 78 cases are already fixed by the per-intent minimum; spend the remaining 22 on the
hardest strata (critical intents, injections, indirect human requests).

## File and format

Write one JSON object per line to **`evals/hard_set.v1.jsonl`** (UTF-8, LF). Start from
`data/hard_set/TEMPLATE.jsonl`, which holds one row with every field present and empty values; its
`record_id` `th_000` marks it as the template, and the validator skips it, so copy it and change the
id. Ids run `th_001` to `th_100`.

## Field by field

### Top level

| Field | Instructions |
|---|---|
| `record_id` | `th_001` ... `th_100`, unique. |
| `ticket` | The ticket as the model will see it (below). |
| `labels` | Your gold labels, following `docs/labeling_guidelines.md` (below). |
| `strata` | The tags that count toward the quotas (below). |
| `persona_id`, `company_id` | Optional ids from `data/spec/pools/hard/` if you borrow a fictional persona or company from the hard pool; otherwise `null`. Never use ids from the train, val or test pools. |
| `attestation` | Your authorship statement (below). |
| `notes` | Optional free text for yourself (why the case is hard, what it probes). Not shown to models. |

### `ticket` (the `TicketCreate` subset)

| Field | Instructions |
|---|---|
| `customer_tier` | `free`, `starter`, `business` or `enterprise`. Keep it plausible (SSO only on business/enterprise; SCIM only on enterprise; no charges on free). |
| `channel` | `web_form`, `email`, `api` or `chat_transcript` (a chat needs at least 2 `previous_messages`). |
| `subject` | 1-300 characters. Vary it: specific, vague, nearly empty, or emphasizing a side detail. |
| `message` | The latest customer message, 1-20,000 characters. Write the way real customers write, including typos if you like. |
| `previous_messages` | Earlier thread messages, oldest first: `author` (`customer`, `agent` or `system`), `body`, `sent_at` (ISO 8601 with a time zone, e.g. `2026-10-01T09:30:00+00:00`). Use `[]` for none. |
| `account` | Optional (`null` allowed). `account_id` matches `acct_` + 4-32 letters/digits; `company_name`, `arr_band` (`<10k`, `10k-50k`, `50k-250k`, `>250k`), `region` (`us`, `eu`, `apac`), `seats` (within the plan limit). |
| `product` | Optional (`null` allowed): `product_area_hint` (usually `null`: a hint can leak the label), `app_version`, `platform` (`web`, `ios`, `android`, `desktop`, `api`). |
| `external_id`, `received_at` | Optional; `received_at` is ISO 8601 with a time zone. |

Personal data appears **only** as placeholders: `<PERSON_1>`, `<EMAIL_1>`, `<PHONE_1>`,
`<CARD_LAST4_1>` (number them in reading order and reuse an index for the same value). No real
names, e-mail addresses, phone numbers, URLs, card numbers or credentials, even invented ones: the
PII scan rejects them. Company and product names must be fictional (the pools and the fact sheet
have plenty); the fact sheet (`data/spec/fact_sheet.v1.md`) lists the product facts, error codes and
integrations you may reference. Invoice numbers use the hard-set prefix `INV-H` plus 6 digits.

Never copy or closely paraphrase a **protected string**: the spec's intent examples, the demo
tickets or the labeling-guideline examples (`data/spec/protected_strings.txt`). Leakage check C6
flags them in every split, including this one.

### `labels` (the `TriageModelOutput` contract)

Fill every field by the guidelines; the most important for the hard set:

* `intent`: critical-first (R2), otherwise what must be resolved first (R1).
* `secondary_intents`: at most 2, distinct, never the primary, never `other_unclear` (R3).
* `priority`: §5.3 as the ticket implies it, **before** any policy floor (R4).
* `churn_risk`: the single rule (R6); `high` only with explicit cancel intent, a named competitor
  or an ultimatum; `churn_signals` holds the cues.
* `entities`: only values literally present in the ticket, copied exactly (R7); `saml_idp` uses
  the normalized value.
* `customer_requested_human`: direct **or indirect** requests (R9).
* `information_sufficient`: `false` when the first action lacks details (R10); always `false` for
  `other_unclear`.
* `recommended_queue` / `recommended_action`: the §5.8 default plus the two overrides (R11).
* `rationale`: one or two sentences.

### `strata`

| Field | Instructions |
|---|---|
| `injection` | `true` when the ticket contains text that tries to steer an AI (set a label, skip escalation, reveal a prompt). Label the real need (R14). |
| `needs_info` | `true` when details for the first action are missing; must match `labels.information_sufficient = false`. |
| `human_request` | `none`, `direct` or `indirect`; must match `labels.customer_requested_human`. |
| `legal_threat_in_billing` | `true` when a billing ticket (duplicate charge, payment failure or refund as primary or secondary intent) also threatens legal action. |

### `attestation`

| Field | Value |
|---|---|
| `llm_assisted` | `false` (JSON boolean). Any other value fails validation. |
| `author` | Your pseudonymous reviewer id, e.g. `R-owner` (never your name or e-mail). |
| `written_at` | When you finished the case, ISO 8601 with a time zone. |
| `statement` | `Written by hand without any LLM assistance.` |

## Validate and split

```bash
cd ml
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ticketward-ml"
uv run python -m tw_ml.datagen hardset validate               # schema, rules, PII, attestation, quotas
uv run python -m tw_ml.datagen hardset split --write-manifest # 30 hard_dev / 70 hard_final
uv run python -m tw_ml.datagen leakage                        # C6 protected strings, C1-C3 vs test_synth
```

The split is stratified by primary intent and depends only on the record ids, the labels and the
seed (recorded with the `hard_dev` / `hard_final` id lists in `data/manifests/test_hard.json`), so
re-running it gives the same result. After the P1 freeze the file is immutable; a change means a
new version (`hard_set.v2.jsonl`, `manifest freeze --bump`) and a re-run of E1-E6.

A volunteer second annotator labels all 100 cases blind; Cohen's kappa is reported
(`python -m tw_ml.datagen qa kappa`), and kappa < 0.80 triggers a guideline revision and a
re-review.
