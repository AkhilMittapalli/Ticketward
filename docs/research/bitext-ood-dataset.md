# Bitext OOD Evaluation Set - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-26
**Status**: Resolved (research questions answered: dataset ids, revisions, license, sizes, fields, the full intent lists and a complete mapping). The spec change (composition and mapping corrections) is applied: ADR-0016 was amended in spec v1.1 (A-13, 2026-09-27).
**Category**: ML Data / Evaluation
**Linked ADR(s)**: ADR-0016 (test set from a different model family + hard set + Bitext OOD), amended 2026-09-27
**Spec sections**: §9.1.5, §9.3 (test_ood), §9.8 (per-split reporting), §13 S-12, §20 L-07, §21 R-10, §23

---

## EXECUTIVE SUMMARY

1. **Primary dataset:** `bitext/Bitext-customer-support-llm-chatbot-training-dataset` (Hugging Face; not gated).
   - License **CDLA-Sharing-1.0**.
   - **26,872 rows**, **27 intents**. The data's `category` column has **11 categories**; the card prose says 10 and uses different category names.
   - Columns: `flags`, `instruction`, `category`, `intent`, `response`. One CSV file.
   - Pinned revision `430d1a89bd93bd1fa23c16f29dd53e73f0087443` (last modified 2024-07-18).
   - The `instruction` texts are **single short chatbot utterances**: 6–92 characters, mean 46.9. They are not tickets.
2. **The spec's example mapping is wrong for this dataset.** §9.1.5 says "cancel/subscription → cancellation_request". In Bitext customer-support:
   - `cancel_order` means cancelling an e-commerce purchase order;
   - the `SUBSCRIPTION` category contains only `newsletter_subscription`, which is (un)subscribing from a newsletter.
   Neither is subscription cancellation. The only proxy in this dataset is `delete_account` (closing one's account), which is lenient.
3. **Supplementary dataset (recommended):** `bitext/Bitext-telco-llm-chatbot-training-dataset`.
   - Same publisher and license. **26,000 rows**, 26 intents × 1,000, 7 categories. It has a `tags` column instead of `flags`.
   - Revision `eacc593a96d75ec6da0887f081ff0dfc442fccab`.
   - Telecom is a subscription business: `cancel_plan` and `change_plan` are the only **clean** Bitext proxies for `cancellation_request` and `plan_pricing_inquiry`, and `human_agent` adds human-request phrasings.
4. **Coverage (strict mapping):** 5 of our 12 intents, including **2 of the 5 critical classes** (payment failure and cancellation). Five intents have **no Bitext analog at all**: `sso_login_failure`, `billing_duplicate_charge`, `service_outage`, `security_report`, `privacy_legal_request`. So the OOD critical-recall figure covers only payment failure and cancellation. It says nothing about security, outage or duplicate charge.
5. **test_ood.v1 = 500 records** (the spec's size). Owner reviews 100% of records (about 1.1 h).
   - **400 strict intent items** (5 classes × 80).
   - **50 human-request probe items** (`contact_human_agent`, `human_agent`), for P1/M-07d on out-of-distribution phrasing.
   - **50 cancellation hard negatives** (`newsletter_subscription` utterances containing "cancel"/"unsubscribe"), which should *not* trigger `cancellation_request`.
   - A lenient Tier-2 set is optional and appendix-only.
6. **License.**
   - CDLA-Sharing-1.0 puts **no obligations on Results** (metrics), so evaluating and publishing numbers is unrestricted.
   - Publishing the materialized OOD file (placeholders filled + our labels) counts as publishing Data/Enhanced Data. It must then be under CDLA-Sharing-1.0, with notices and attribution, and no added restrictions.
   - **Recommendation:** commit only row pointers + mapping + the build script. Optionally publish the materialized set as a *separate* CDLA-Sharing-1.0 HF dataset.
7. **Reporting.**
   - A separate OOD table, never averaged with other splits.
   - Metrics: macro-F1 over the 5 mapped labels (`f1_score(..., labels=MAPPED_5, average="macro")`); per-class recall with Wilson CIs; the OOD gap vs test_synth restricted to the same classes; probe rates; a per-tag breakdown.
   - Explicit caveats on domain, format and coverage.

---

## QUESTIONS

| # | Question | Source |
|---|---|---|
| Q1 | Which Bitext dataset(s) exist on Hugging Face? Exact ids, revisions, size, fields? | §23, §9.1.5 |
| Q2 | What are the license terms and obligations? | §23, R-10 |
| Q3 | What is the full list of intents and categories? | task |
| Q4 | What is the intent mapping table, and which categories are unmappable (with reasons)? | §23 |
| Q5 | How is the data preprocessed? | §23 |
| Q6 | How are the 500 records sampled and composed? | §9.3 |
| Q7 | How is it reported? | §23, §9.8 |

---

## FINDINGS

All sources accessed 2026-09-26.

### F1. Bitext datasets on Hugging Face (Q1)

The HF API lists 13 datasets under `bitext` [B1]. All except the last are tagged `cdla-sharing-1.0`, and none is gated.

| Dataset id | License tag |
|---|---|
| `bitext/Bitext-customer-support-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-telco-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-retail-banking-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-insurance-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-travel-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-hospitality-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-events-ticketing-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-media-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-restaurants-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-mortgage-loans-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-wealth-management-llm-chatbot-training-dataset` | cdla-sharing-1.0 |
| `bitext/Bitext-combined-banking-wealth_management-mortgage_loans` | none listed |

### F2. Primary dataset facts (Q1)

Sources: card [B2], repo API [B3], datasets-server statistics [B4].

| Property | Value |
|---|---|
| Id | `bitext/Bitext-customer-support-llm-chatbot-training-dataset` |
| Pinned revision (commit) | `430d1a89bd93bd1fa23c16f29dd53e73f0087443` |
| Created / last modified | 2023-08-24 / 2024-07-18 |
| Files | `Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv`, `README.md`, `.gitattributes` |
| License | `cdla-sharing-1.0` (card YAML); the card also carries a Bitext Innovations 2024 copyright line |
| Gated | No |
| Rows | **26,872** (datasets-server; the card says "approximately 1,000 per intent") |
| Size | Card: 3.57M tokens across instruction+response. Download size ≈ 19.2 MB per the HF page summary (UNVERIFIED, immaterial) |
| Columns | `flags` (language-generation tags), `instruction` (user request), `category` (high-level category), `intent`, `response` (example assistant reply) |
| `instruction` length (chars) | min 6, max 92, mean 46.89, median 48, sd 10.90 |
| `response` length (chars) | min 57, max 2,472, mean 634.10 |
| `flags` | 394 distinct combinations; the most common is `BL` (5,212 rows) |
| Tags (12) | B basic syntax; C coordinated syntax; E abbreviations; I interrogative; K keyword mode; L semantic variation; M morphological variation; N negation; P politeness; Q colloquial; W offensive language; Z errors and typos |
| Entities (30 placeholders) | `{{Order Number}}`, `{{Invoice Number}}`, `{{Online Order Interaction}}`, `{{Online Payment Interaction}}`, `{{Online Navigation Step}}`, `{{Online Customer Support Channel}}`, `{{Profile}}`, `{{Profile Type}}`, `{{Settings}}`, `{{Online Company Portal Info}}`, `{{Date}}`, `{{Date Range}}`, `{{Shipping Cut-off Time}}`, `{{Delivery City}}`, `{{Delivery Country}}`, `{{Salutation}}`, `{{Client First Name}}`, `{{Client Last Name}}`, `{{Customer Support Phone Number}}`, `{{Customer Support Email}}`, `{{Live Chat Support}}`, `{{Website URL}}`, `{{Upgrade Account}}`, `{{Account Type}}`, `{{Account Category}}`, `{{Account Change}}`, `{{Program}}`, `{{Refund Amount}}`, `{{Money Amount}}`, `{{Store Location}}`. Most occur in responses; instructions contain some (e.g., account type, order/invoice numbers, amounts, person names) |
| Generation method (card) | Hybrid: natural texts as sources → NLP-extracted seeds → NLG expansion, curated by computational linguists. **So this is semi-synthetic, not real customer text** |
| Intended use (card) | Fine-tuning LLMs for customer-support domain adaptation |

### F3. Card vs data discrepancy (Q3)

- **What the card prose says** (retrieved twice, the second time from the raw `README.md`): "27 intents assigned to 10 categories". It names categories such as `CANCELLATION_FEE`, `NEWSLETTER` and `SHIPPING_ADDRESS`, omits `CONTACT`, and lists only 20 intents under them.
- **What the data has:** 11 `category` values: `ACCOUNT, CANCEL, CONTACT, DELIVERY, FEEDBACK, INVOICE, ORDER, PAYMENT, REFUND, SHIPPING, SUBSCRIPTION` [B4].
- **Decision:** code must use the data's values, never the card prose.

### F4. Full intent list, customer-support dataset (Q3)

- **Counts** come from datasets-server statistics [B4].
- **Category membership** is exact. The rows are sorted by intent alphabetically, which was verified at three block boundaries: row 2967/2968, 10909/10910 and 17894. The per-category totals decompose uniquely. The rows were also directly observed for 21 of 27 intents [B5].

| Category (total) | Intents (rows) |
|---|---|
| ACCOUNT (5,986) | create_account (997), delete_account (995), edit_account (1,000), recover_password (995), registration_problems (999), switch_account (1,000) |
| CANCEL (950) | check_cancellation_fee (950) |
| CONTACT (1,999) | contact_customer_service (1,000), contact_human_agent (999) |
| DELIVERY (1,994) | delivery_options (995), delivery_period (999) |
| FEEDBACK (1,997) | complaint (1,000), review (997) |
| INVOICE (1,999) | check_invoice (1,000), get_invoice (999) |
| ORDER (3,988) | cancel_order (998), change_order (997), place_order (998), track_order (995) |
| PAYMENT (1,998) | check_payment_methods (999), payment_issue (999) |
| REFUND (2,992) | check_refund_policy (997), get_refund (997), track_refund (998) |
| SHIPPING (1,970) | change_shipping_address (973), set_up_shipping_address (997) |
| SUBSCRIPTION (999) | newsletter_subscription (999) |

### F5. Telco dataset facts and full intent list (Q1, Q3)

Sources: repo API [B6], statistics [B7], row probes [B8].

| Property | Value |
|---|---|
| Id / revision | `bitext/Bitext-telco-llm-chatbot-training-dataset` @ `eacc593a96d75ec6da0887f081ff0dfc442fccab` (last modified 2024-08-15) |
| File / license / gated | `bitext-telco-llm-chatbot-training-dataset.csv` / `cdla-sharing-1.0` / no |
| Rows | **26,000**; 26 intents × 1,000 each |
| Columns | `instruction`, `intent`, `category`, **`tags`**, `response` |
| `instruction` length (chars) | min 8, max 109, mean 53.46, median 52 |
| Row order | By category (alphabetical), then by intent within category (mostly alphabetical); every block is 1,000 rows |

Telco intent-to-category membership was verified by a row probe at the start of 21 of the 26 blocks. The five unprobed blocks (rows 14000–16999, 18000–18999 and 20000–20999, all in SERVICES) were assigned by elimination: every other intent is pinned to another block, and the 7,000 SERVICES rows hold exactly the 7 remaining intents.

| Category (rows) | Intents |
|---|---|
| BILLING (2,000) | dispute_invoice, invoices |
| COMPLAINTS (3,000) | get_compensation, report_poor_signal_coverage, report_problem |
| CONSUMPTION (3,000) | check_excess_data_charges, check_usage, set_usage_limits |
| CONTACT (2,000) | customer_service, human_agent |
| PAYMENT (4,000) | check_mobile_payments, payment_methods, pay, schedule_payments |
| SERVICES (7,000) | activate_call_management_services, activate_phone, activate_roaming, check_signal_coverage, deactivate_call_management_services, deactivate_phone, install_internet |
| SUBSCRIPTION (5,000) | cancel_plan, change_plan, change_provider, check_cancellation_fee, sign_up_for_plan |

### F6. Observed semantics that decide the mapping (Q4)

Paraphrased from sampled rows [B5, B8]; no rows are reproduced.

- `cancel_order` (CS): cancel a purchase order identified by an order number, sometimes giving affordability as the reason. **Not a subscription.**
- `newsletter_subscription` (CS): subscribe to or unsubscribe from a company newsletter. It frequently uses "cancel the subscription" wording, so it is a lexical trap for cancellation detection.
- `delete_account` (CS): close, remove or cancel one's own account, sometimes because it is no longer used. A churn-like proxy, but a consumer account, not a B2B subscription.
- `check_cancellation_fee` (CS and TEL): asks about termination, withdrawal or early-exit fees.
- `payment_issue` (CS): cannot pay, card declined, wants to report a payment problem.
- `get_refund` (CS): wants money back or a refund. `track_refund`: status of an expected refund. `check_refund_policy`: when refunds are possible and how long they take.
- `recover_password` (CS): recover or reset a password, PIN or access key. `registration_problems`: sign-up errors.
- `switch_account` (CS): a mix of switching to another account tier (freemium, gold, platinum) and switching user profiles.
- `contact_human_agent` (CS) and `human_agent` (TEL): explicit requests for a person, live agent or operator.
- `contact_customer_service` (CS): a mix of "how do I reach support / what hours" and "I want to talk to customer service".
- `cancel_plan` (TEL): cancel or terminate a mobile or internet plan or contract, sometimes citing poor service. `change_plan` (TEL): modify or change a plan or contract. `change_provider` (TEL): switch to another provider. `dispute_invoice` (TEL): challenge unrecognized or incorrect charges. `report_problem` (TEL): report a vague fault.

### F7. License: CDLA-Sharing-1.0 (Q2)

Source: [B9].

- **Definitions:**
  - *Data*: the material received.
  - *Enhanced Data*: the subset of the published Data consisting of your additions and/or modifications.
  - *Results*: outcomes of computational analysis that contain no more than a de minimis portion of the Data.
  - *Publish*: making Data available to people outside your organization.
- **Obligations when publishing Data or Enhanced Data:**
  - use the unmodified CDLA-Sharing-1.0 agreement (full text or link);
  - add prominent notices identifying the changes;
  - preserve credits, attributions, legal notices and metadata;
  - do not restrict others' rights or add further terms.
- **Results:** §3.5 imposes no obligations or restrictions on Use or Publication of Results. Metrics, plots and trained models are Results.
- **Warranty:** Data is provided as-is, without warranties.
- **Consequence:** evaluating Ticketward on Bitext and publishing the numbers is unrestricted. Publishing our materialized OOD file triggers the sharing terms for that file.

### F8. Domain and format mismatch (Q5, Q7)

| Dimension | Bitext | Taskmoor tickets |
|---|---|---|
| Domain | Consumer e-commerce (CS) and consumer telecom (TEL) | B2B SaaS |
| Format | One utterance of ≤ 109 characters (means 46.9 / 53.5); no subject, thread, account tier or product metadata | Multi-sentence, sometimes multi-paragraph tickets with a subject and optional history |
| Style | 12 controlled variation tags (typos, colloquial, offensive, keyword-only, ...) | Varied |

- **Why this is still useful:** it is a robustness check. It is not a proxy for production traffic (L-01, L-07).
- **Other verticals considered and not used in v1.** Banking has `get_password`, `close_account`, `dispute_ATM_withdrawal`, `block_card` and `human_agent` [B10]. Its domain is further from SaaS, and its security-like intents (card blocking) do not match `security_report` semantics. Possible future probes only.

---

## DECISION / RECOMMENDATION

### D1. Datasets and pinning

- **Use both** `bitext/Bitext-customer-support-llm-chatbot-training-dataset@430d1a8…` ("CS") and `bitext/Bitext-telco-llm-chatbot-training-dataset@eacc593…` ("TEL").
- **Load** with `datasets.load_dataset(repo, revision=<full sha>, split="train")`.
- **Record** both SHAs in `data/manifests/<ver>.json`. If the upstream repos change, the pinned revisions keep the build reproducible.

### D2. Mapping tiers

| Tier | Definition | Use |
|---|---|---|
| **T1 strict** | Essentially all utterances of the source intent satisfy exactly one Taskmoor intent definition (§5.1) | Headline OOD intent metrics |
| **T2 lenient** | Plausible single target, but domain-shifted or ambiguous with a second intent | Optional appendix only; never mixed with T1 |
| **Probe** | Maps to a non-intent field (`customer_requested_human`) or to a "must not be X" negative | Probe metrics (M-07d OOD; cancellation false-positive rate) |
| **Excluded** | No Taskmoor analog, or irreducibly ambiguous | Not sampled |

### D3. Complete mapping tables (Q4)

**CS: `bitext/Bitext-customer-support-llm-chatbot-training-dataset` (27 intents)**

| Bitext intent | Category | Rows | Taskmoor target | Tier | Reason |
|---|---|---|---|---|---|
| cancel_order | ORDER | 998 | – | Excluded | Purchase-order cancellation; no orders in Taskmoor. Too ambiguous even as a negative ("purchase" could be read as a subscription) |
| change_order | ORDER | 997 | – | Excluded | Modify an e-commerce order |
| change_shipping_address | SHIPPING | 973 | – | Excluded | Physical shipping |
| check_cancellation_fee | CANCEL | 950 | plan_pricing_inquiry | T2 | Fee/penalty question = pricing mechanics; also a churn cue; some annotators would pick cancellation |
| check_invoice | INVOICE | 1,000 | how_to_question | T2 | Locate or view an invoice (docs-answerable); the taxonomy has no invoice-request intent |
| check_payment_methods | PAYMENT | 999 | how_to_question | T2 | Accepted payment methods (docs-answerable); could be read as plan_pricing_inquiry |
| check_refund_policy | REFUND | 997 | – | Excluded | Policy question torn between refund_request and how_to/pricing; no single target |
| complaint | FEEDBACK | 1,000 | – | Excluded | Wants to file a complaint with no issue stated; the taxonomy is issue-based. (Future probe: "claim against your company" vs the legal lexicon) |
| contact_customer_service | CONTACT | 1,000 | – | Excluded | Mixes contact-hours questions with requests to talk to support |
| contact_human_agent | CONTACT | 999 | `customer_requested_human=true` (intent `other_unclear`) | **Probe P-H** | Explicit person/agent/operator requests; tests P1 and M-07d; not in intent macro-F1 |
| create_account | ACCOUNT | 997 | – | Excluded | Consumer self-sign-up (often for family members); Taskmoor accounts are org-provisioned |
| delete_account | ACCOUNT | 995 | cancellation_request | T2 | Close or cancel one's account (churn); consumer account ≠ subscription; "delete" could be a privacy request (no legal basis stated). Superseded by TEL `cancel_plan` for T1 |
| delivery_options | DELIVERY | 995 | – | Excluded | Physical delivery methods |
| delivery_period | DELIVERY | 999 | – | Excluded | Delivery times |
| edit_account | ACCOUNT | 1,000 | how_to_question | T2 | Edit profile or personal data (usage how-to) |
| get_invoice | INVOICE | 999 | how_to_question | T2 | Download or receive an invoice |
| get_refund | REFUND | 997 | **refund_request** | **T1** | Requests money back; matches "Customer requests money back (not a duplicate)" |
| newsletter_subscription | SUBSCRIPTION | 999 | must **not** be cancellation_request (record-keeping intent: how_to_question) | **Probe P-N** | Newsletter (un)subscribe; "cancel … subscription" wording makes it a hard negative for the cancellation class and the P5 path |
| payment_issue | PAYMENT | 999 | **billing_payment_failure** | **T1** | Cannot pay / card declined / payment problem |
| place_order | ORDER | 998 | – | Excluded | Buying goods |
| recover_password | ACCOUNT | 995 | **account_access_issue** | **T1** | Password/PIN/access-key recovery = password reset |
| registration_problems | ACCOUNT | 999 | account_access_issue | T2 | Sign-up errors; nearest to access, could be bug_report |
| review | FEEDBACK | 997 | – | Excluded | How to leave a review |
| set_up_shipping_address | SHIPPING | 997 | – | Excluded | Physical shipping |
| switch_account | ACCOUNT | 1,000 | plan_pricing_inquiry | T2 | Mixes tier changes (plan mechanics) with switching user profiles |
| track_order | ORDER | 995 | – | Excluded | Order tracking |
| track_refund | REFUND | 998 | refund_request | T2 | Status of an expected refund (follow-up on money back) |

**TEL: `bitext/Bitext-telco-llm-chatbot-training-dataset` (26 intents × 1,000)**

| Bitext intent | Category | Taskmoor target | Tier | Reason |
|---|---|---|---|---|
| dispute_invoice | BILLING | refund_request | T2 | Unrecognized or incorrect charges: "money back for other reasons" per the §5.1 edge case; could also be duplicate charge or fraud |
| invoices | BILLING | how_to_question | T2 | Get or download a bill |
| get_compensation | COMPLAINTS | refund_request | T2 | Compensation or credit after service problems |
| report_poor_signal_coverage | COMPLAINTS | – | Excluded | Radio coverage at a location; not a widespread outage |
| report_problem | COMPLAINTS | bug_report | T2 | Vague fault report; no blast radius stated; could be an outage |
| check_excess_data_charges | CONSUMPTION | – | Excluded | Telco overage |
| check_usage | CONSUMPTION | – | Excluded | Telco metering |
| set_usage_limits | CONSUMPTION | – | Excluded | Telco caps |
| customer_service | CONTACT | – | Excluded | Contact info / reaching support |
| human_agent | CONTACT | `customer_requested_human=true` (intent `other_unclear`) | **Probe P-H** | Explicit agent/person/operator requests |
| check_mobile_payments | PAYMENT | – | Excluded | Telco app payment history |
| payment_methods | PAYMENT | how_to_question | T2 | How to pay by card / accepted methods |
| pay | PAYMENT | – | Excluded | "Make a payment/transfer": action vs how-to ambiguity |
| schedule_payments | PAYMENT | how_to_question | T2 | Scheduling or auto-pay setup |
| activate_call_management_services | SERVICES | – | Excluded | Telco feature |
| activate_phone | SERVICES | – | Excluded | Device activation |
| activate_roaming | SERVICES | – | Excluded | Roaming |
| check_signal_coverage | SERVICES | – | Excluded | Coverage/5G availability |
| deactivate_call_management_services | SERVICES | – | Excluded | Telco feature |
| deactivate_phone | SERVICES | – | Excluded | Deactivate a device; not a plan cancellation |
| install_internet | SERVICES | – | Excluded | Home installation |
| cancel_plan | SUBSCRIPTION | **cancellation_request** | **T1** | Cancel or terminate a plan or contract = subscription cancellation |
| change_plan | SUBSCRIPTION | **plan_pricing_inquiry** | **T1** | Modify or change the plan = upgrade/downgrade mechanics. Owner review drops any "downgrade to free" item (that would be cancellation per §5.1) |
| change_provider | SUBSCRIPTION | cancellation_request | T2 | Switching provider = implicit churn, but some utterances may concern porting in |
| check_cancellation_fee | SUBSCRIPTION | plan_pricing_inquiry | T2 | Early-exit fees |
| sign_up_for_plan | SUBSCRIPTION | plan_pricing_inquiry | T2 | Buying a new plan (consumer purchase) |

### D4. Coverage of the Taskmoor taxonomy (Q4)

| # | Taskmoor intent | Critical? | T1 source | T2 sources | Covered? |
|---|---|---|---|---|---|
| 1 | sso_login_failure | No | – | – | **No analog** (consumer datasets have no SSO/IdP) |
| 2 | account_access_issue | No | CS recover_password | CS registration_problems | Yes |
| 3 | billing_duplicate_charge | **Yes** | – | – | **No analog** (TEL dispute_invoice is not "charged twice") |
| 4 | billing_payment_failure | **Yes** | CS payment_issue | – | Yes |
| 5 | refund_request | No | CS get_refund | CS track_refund; TEL get_compensation, dispute_invoice | Yes |
| 6 | cancellation_request | **Yes** | TEL cancel_plan | TEL change_provider; CS delete_account | Yes |
| 7 | plan_pricing_inquiry | No | TEL change_plan | TEL check_cancellation_fee, sign_up_for_plan; CS check_cancellation_fee, switch_account | Yes |
| 8 | service_outage | **Yes** | – | – | **No analog** (coverage complaints are local, not widespread) |
| 9 | bug_report | No | – | TEL report_problem | Lenient only |
| 10 | how_to_question | No | – | CS edit_account, check_invoice, get_invoice, check_payment_methods; TEL invoices, payment_methods, schedule_payments | Lenient only |
| 11 | security_report | **Yes** | – | – | **No analog** |
| 12 | privacy_legal_request | No | – | – | **No analog** |
| – | other_unclear + human request | – | Probe P-H (CS contact_human_agent, TEL human_agent) | – | Probe |

### D5. test_ood.v1 composition and sampling (Q6)

| Group | Source intents | n | Gold |
|---|---|---|---|
| S1 | CS recover_password | 80 | account_access_issue |
| S2 | CS payment_issue | 80 | billing_payment_failure |
| S3 | CS get_refund | 80 | refund_request |
| S4 | TEL cancel_plan | 80 | cancellation_request |
| S5 | TEL change_plan | 80 | plan_pricing_inquiry |
| P-H | CS contact_human_agent (25) + TEL human_agent (25) | 50 | `customer_requested_human=true`, intent `other_unclear` |
| P-N | CS newsletter_subscription, keeping only utterances with a word starting "cancel" or "unsubscrib" (regex `PN_FILTER` below) | 50 | must not be `cancellation_request` (record intent `how_to_question`) |
| **Total** | | **500** | |

**Sampling procedure** (`ml/src/tw_ml/datagen/bitext_map.py`):

```python
import re

PN_FILTER = re.compile(r"\b(cancel\w*|unsubscrib\w*)\b", re.IGNORECASE)
SOURCES = {  # source key -> (HF id, pinned revision, tag column)
    "cs": ("bitext/Bitext-customer-support-llm-chatbot-training-dataset",
           "430d1a89bd93bd1fa23c16f29dd53e73f0087443", "flags"),
    "tel": ("bitext/Bitext-telco-llm-chatbot-training-dataset",
            "eacc593a96d75ec6da0887f081ff0dfc442fccab", "tags"),
}
GROUPS = {  # group -> ([(source, bitext_intent)], quota, gold)
    "S1": ([("cs", "recover_password")], 80, {"intent": "account_access_issue"}),
    "S2": ([("cs", "payment_issue")], 80, {"intent": "billing_payment_failure"}),
    "S3": ([("cs", "get_refund")], 80, {"intent": "refund_request"}),
    "S4": ([("tel", "cancel_plan")], 80, {"intent": "cancellation_request"}),
    "S5": ([("tel", "change_plan")], 80, {"intent": "plan_pricing_inquiry"}),
    "P-H": ([("cs", "contact_human_agent"), ("tel", "human_agent")], 50,   # 25 + 25
            {"intent": "other_unclear", "customer_requested_human": True}),
    "P-N": ([("cs", "newsletter_subscription")], 50, {"intent": "how_to_question", "not_intent": "cancellation_request"}),
}
# load: datasets.load_dataset(hf_id, revision=sha, split="train"); keep row index as bitext_row
```

1. Filter each group by `intent`; apply `PN_FILTER` for P-N.
2. Shuffle with `numpy.random.default_rng(20260926)`.
3. Iterate in shuffled order:
   - fill placeholders (D6);
   - skip exact duplicates (normalized SHA-256) and near-duplicates of already-selected items in the group (char-5 Jaccard ≥ 0.7, same normalization as leakage-and-dedup.md). Bitext contains many templated paraphrases.
4. Stop at the group quota.

**Owner review:** 100% of records, about 10 s each.
- The owner accepts or rejects each record.
- Rejected items are replaced by the next candidate in the shuffled order. The reject list is committed so the build is deterministic.
- Accepted records get `label_source=human_verified`.

**Optional test_ood_lenient.v1** (appendix only; not part of the 500): 20 per T2 source intent (18 intents → 360), with the same procedure. Review it only if the appendix is run.

### D6. Preprocessing (Q5)

1. **Drop the `response` column.** It is the assistant reply and irrelevant here.
2. **Placeholder fill.** Fill `{{...}}` tokens in `instruction` from the table below, with a per-row seed of `blake2b(f"{source}:{row}")`. **Unknown placeholders fail the build**; add them to the table explicitly.

   | Placeholder(s) | Fill | Why |
   |---|---|---|
   | Person Name, Client First/Last Name, Salutation | `<PERSON_1>` | Matches production PII masking |
   | Customer Support Email | `<EMAIL_1>` | Masking |
   | Customer Support Phone Number | `<PHONE_1>` | Masking |
   | Website URL | "the website" | Neutral |
   | Account Type, Account Category | seeded choice of {standard, premium, pro, gold, platinum, freemium} | Bitext's own vocabulary; avoids Taskmoor plan names (free/starter/business/enterprise) |
   | Order Number, Invoice Number | `#` + 5 seeded digits | Normalized to `0` by leakage checks anyway |
   | Currency Symbol / Refund Amount / Money Amount | `$` / seeded 10.00–500.00 | – |
   | Date / Date Range | seeded 2026 date / "last month" | – |
   | Settings / Live Chat Support / Online Customer Support Channel / Upgrade Account / Profile / Profile Type | "settings" / "live chat" / "online support" / "upgrade" / "profile" / "work profile" | Neutral wording |

3. **Wrap as `TicketCreate`.**
   - `subject="Support request"` (constant). §6.1 requires ≥ 1 character; a constant subject carries no label signal.
   - `message=<filled instruction>`, `channel="chat_transcript"`, `customer_tier="business"` (constant, neutral), `previous_messages=[]`, `account=None`, `product=None`.
   - `external_id=f"bitext:{source}:{row}"`, `received_at` fixed.
4. **Run the production Presidio masker** on the text, as in §7.2 step 1. E3 and E4 then see exactly what production would see.
5. **Keep everything.** No filtering on tags: offensive (W), typo (Z) and keyword-only (K) utterances all stay, because they are part of the robustness check. Tags are kept for the breakdown.
6. **Provenance per record** (S-12):
   - `record_id`, `split="test_ood"`, `source="public:bitext"`, `generator_family="public_bitext"`;
   - `bitext_dataset`, `bitext_revision`, `bitext_row`, `bitext_intent`, `bitext_category`, `bitext_tags`;
   - `mapping_tier`, `probe` (null | "P-H" | "P-N"), `fill_seed`;
   - `gold` (`intent`, plus `customer_requested_human` for P-H);
   - `label_source`, `taxonomy_version`, `content_sha256`.
7. **Leakage checks.** Run the leakage-and-dedup.md checks: test_ood is a protected split. The within-split near-duplicate check must be clean before freeze.

### D7. Reporting plan (Q7)

- **Placement.** A separate "OOD (Bitext: consumer e-commerce + telecom)" table in `evals/reports/<date>/results.md` and on the dashboard. **It is never pooled with test_synth or test_hard.**
- **Experiments shown:** E1, E2, E3, E4 (per seed + mean), E5 (for the system-level probe rates). E6 is optional (500 short items cost little).

| Metric | Definition | CI method |
|---|---|---|
| OOD intent macro-F1 (strict) | On the 400 S-items: `f1_score(y_true, y_pred, labels=MAPPED_5, average="macro", zero_division=0)`. Predictions outside `MAPPED_5` count as misses for the true class; they add no false positives to mapped classes | Stratified bootstrap (evaluation-statistics.md) |
| Per-class recall (S1–S5) | Highlight S2 (payment failure) and S4 (cancellation), the only critical classes covered | Wilson 95% (n=80 → about ±0.07 at recall 0.85) |
| Out-of-taxonomy rate | Share of S-items predicted `other_unclear` or a non-mapped intent | Wilson |
| JSON validity (M-04) | All 500 | Wilson; the exact method if 0 or n |
| OOD gap | macro-F1 on test_synth restricted to gold ∈ MAPPED_5 (same `labels=`) minus OOD macro-F1 | Independent bootstrap of both sets (not paired) |
| P-H human-request recall | Model `customer_requested_human` recall (E3/E4); P1-fired rate (E5) | Wilson (n=50) |
| P-N cancellation false-positive rate | Share predicted `cancellation_request` (model); P5-fired rate (E5) | Wilson (n=50) |
| Tag breakdown | Accuracy by tag letter (Z, Q, W, K, …); descriptive only because per-tag n is small | none (report n) |

```python
from sklearn.metrics import f1_score

MAPPED_5 = ["account_access_issue", "billing_payment_failure", "refund_request",
            "cancellation_request", "plan_pricing_inquiry"]
ood_macro_f1 = f1_score(y_true_strict, y_pred_strict, labels=MAPPED_5, average="macro", zero_division=0)
```

**Mandatory caveat text** (README, model card, dashboard tooltip):
- Bitext is semi-synthetic consumer e-commerce and telecom data made of single short utterances. It has no subjects, threads or account metadata.
- It covers 5 of 12 intents strictly, including 2 of 5 critical classes (payment failure, cancellation). Security, outage, duplicate charge, SSO and privacy/legal are not tested OOD.
- Labels were mapped from Bitext intents and 100% human-verified.

### D8. License and publishing (Q2)

- **In the repo** (Apache-2.0 per §14.1): `evals/ood/test_ood.v1.pointers.jsonl` holds (dataset, revision, row, mapping tier, probe, gold labels, fill seed, content_sha256), plus `bitext_map.py` to materialize the text locally from HF. Materialized text is `.gitignore`d. This avoids distributing Bitext Data in the Apache-2.0 repo.
- **Optional:** publish the materialized file as a separate HF dataset (for example `<owner>/ticketward-test-ood-bitext`) under **CDLA-Sharing-1.0**. It needs the agreement text or link, a NOTICE listing our modifications (placeholder filling, relabeling to the Taskmoor taxonomy, sampling), preserved Bitext attribution and copyright line, and no added restrictions.
- **Metrics, plots and models** (Results) are published freely.

---

## SPEC IMPACT (do not edit the spec here; raise via the ADR-0016 amendment)

| # | Spec text | Finding | Proposed change |
|---|---|---|---|
| SI-1 | §9.1.5 example "cancel/subscription → cancellation_request" | In the CS dataset `cancel_order` is an e-commerce order and `SUBSCRIPTION` is the newsletter; neither is subscription cancellation | Use TEL `cancel_plan` (T1). CS `delete_account` is T2 only. CS `newsletter_subscription` becomes a **negative** probe |
| SI-2 | §9.1.5 "account/password → account_access_issue", "refund → refund_request" | True only for `recover_password` and `get_refund`. Other ACCOUNT and REFUND intents are ambiguous or out of scope | Adopt the D3 table as normative |
| SI-3 | §9.1.5 / §9.3 "Bitext customer-support dataset", "500 examples from categories mappable" | A second Bitext dataset (telco, same license) is needed for clean cancellation and plan proxies | test_ood.v1 = CS + TEL; 400 strict (5 × 80) + 50 P-H + 50 P-N |
| SI-4 | §9.1.5 "critical recall on mapped classes" | Only 2 of 5 critical classes are mappable | State this explicitly in reports (D7 caveat) |
| SI-5 | §20 L-07 "a different domain (consumer/e-commerce)" | The domain now includes consumer telecom; the format is single short utterances | Update the L-07 wording |
| SI-6 | §9.1.6 `label_source ∈ {generator_proposed, human_verified, human_written}` | Mapped public labels fit none of these before review | After the 100% owner review use `human_verified`, and record `mapping_tier`. Otherwise add a `mapped_public` value |
| SI-7 | §6.1 `TicketCreate.subject` min_length=1 | Bitext has no subjects | Constant neutral subject "Support request". Document it; do not tune training toward the OOD format |

---

## IMPLEMENTATION CHECKLIST

- [ ] `ml/src/tw_ml/datagen/bitext_map.py`: pinned loads (D1), the D3 mapping as data (`data/spec/bitext_mapping.v1.yaml`), the D5 sampler, the D6 fill table with fail-on-unknown, TicketCreate wrapping, provenance, pointer export.
- [ ] Owner review UI or CLI (accept/reject with a key press), writing `evals/ood/review_decisions.v1.jsonl`.
- [ ] Freeze: `evals/ood/test_ood.v1.pointers.jsonl` + sha256 in the manifest; the leakage report shows test_ood clean.
- [ ] `tw_ml.eval` OOD report block (D7 metrics + caveat text); dashboard panel.
- [ ] Dataset-card section "OOD set", with license notes (D8).
- [ ] If publishing the materialized OOD set: a separate HF dataset under CDLA-Sharing-1.0 with NOTICE.
- [x] ADR-0016 amendment (SI-1…SI-7), applied in spec v1.1 (A-13).

---

## OPEN RISKS / TO VERIFY

| Risk / item | Status | Mitigation |
|---|---|---|
| Bitext is semi-synthetic (NLG-expanded), so "OOD" means domain and style shift, not real customers | Accepted | Caveat text; the hard set remains the human-written stress test |
| Lexical easiness (`cancel_plan` utterances say "cancel") flatters E1 on S4 | Accepted | P-N negatives expose keyword over-triggering; report E1 alongside |
| Card prose disagrees with the data (10 vs 11 categories; names) | Verified discrepancy | Code uses the data's values only |
| Placeholder fill introduces our own artifacts | Low | Neutral fills, seeded, documented |
| Upstream repo changes or removal | Low | Pinned revisions; pointer file + content hashes; keep a private cached copy for reproducibility |
| The size figure (≈19.2 MB) came from the HF page summary | UNVERIFIED | Immaterial; confirm when downloading |
| SERVICES intent-to-category membership in TEL was assigned by elimination (not probed row by row) | Low | Excluded intents only; confirm at build by grouping on `category` |
| Profanity (tag W) in OOD items | Accepted | Evaluation only; never shown in the demo UI |

---

## LINKED ADR

- **ADR-0016** (test set design): amend with the OOD composition, mapping table and license handling (SI-1…SI-7).
- **Related ERPROT docs:** `evaluation-statistics.md` (CI methods, bootstrap), `leakage-and-dedup.md` (dedup within the OOD sample; protected split), `synthetic-data-generation.md` (provenance fields).

---

## SOURCES (all accessed 2026-09-26)

- [B1] Hugging Face API, datasets by author `bitext` (ids, licenses, gated). https://huggingface.co/api/datasets?author=bitext&limit=100
- [B2] Dataset card, Bitext customer support (license, fields, tags, entities, generation method, intended use; raw README). https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset (raw: https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/raw/main/README.md)
- [B3] Repo API (sha, dates, files). https://huggingface.co/api/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset
- [B4] datasets-server column statistics (exact intent/category counts, lengths). https://datasets-server.huggingface.co/statistics?dataset=bitext/Bitext-customer-support-llm-chatbot-training-dataset&config=default&split=train
- [B5] datasets-server rows (sampled at offsets 0, 2950, 3918, 4940, 5990, 6914, 7980, 8914, 9950, 13899, 14899, 15898, 16895, 19891, 20886, 21885, 25874; filter endpoint for switch_account, delete_account, payment_issue). https://datasets-server.huggingface.co/rows?dataset=bitext/Bitext-customer-support-llm-chatbot-training-dataset&config=default&split=train&offset=0&length=5
- [B6] Telco repo API and card. https://huggingface.co/api/datasets/bitext/Bitext-telco-llm-chatbot-training-dataset; https://huggingface.co/datasets/bitext/Bitext-telco-llm-chatbot-training-dataset
- [B7] Telco column statistics. https://datasets-server.huggingface.co/statistics?dataset=bitext/Bitext-telco-llm-chatbot-training-dataset&config=default&split=train
- [B8] Telco rows (offsets 0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 17000, 19000, 21000, 22000, 23000, 24000, 25000). https://datasets-server.huggingface.co/rows?dataset=bitext/Bitext-telco-llm-chatbot-training-dataset&config=default&split=train&offset=21000&length=12
- [B9] Community Data License Agreement, Sharing, Version 1.0. https://cdla.dev/sharing-1-0/
- [B10] Retail-banking column statistics (intents considered, not used). https://datasets-server.huggingface.co/statistics?dataset=bitext/Bitext-retail-banking-llm-chatbot-training-dataset&config=default&split=train

---

**Document Version**: 1.0
**Next Update**: after the build of test_ood.v1 (record the owner-review reject rate per group; confirm the placeholder table is complete)
