---
doc_key: rb_billing_dispute
doc_type: escalation_runbook
title: "Billing Dispute Escalation"
product_areas:
  - billing_subscriptions
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

# Billing Dispute Escalation

## Purpose

This runbook defines the escalation process for customer billing disputes, including incorrect charges, disputed renewals, duplicate payments, and chargeback handling. It ensures disputes are resolved within SLA while protecting both the customer and Taskmoor from financial exposure.

## Trigger Conditions

Escalate using this runbook when any of the following apply:

- Customer disputes a charge on their statement and requests investigation.
- Customer reports a duplicate charge or unexpected renewal.
- Customer received a chargeback notification from their payment provider.
- Disputed amount exceeds $500 or involves an enterprise-tier account.
- The dispute involves a charge older than 90 days.
- Customer claims they cancelled but were still charged.

## Required Information

Before escalating, collect the following from the customer and internal systems:

1. **Account identifier**: Organization name, account ID, and billing contact email.
2. **Transaction details**: Invoice number(s), transaction date(s), and amount(s) in question.
3. **Payment method**: Last four digits of the card or payment method type on file.
4. **Customer's description**: What the customer believes went wrong, in their own words.
5. **Internal billing history**: Pull the last 6 months of invoices from the billing dashboard for the account.
6. **Subscription change log**: Any recent plan changes, seat adjustments, or cancellation requests.

## Escalation Procedure

### Step 1: Initial Assessment (Target: 15 minutes)

Review the billing history and subscription change log. Determine whether the charge appears correct based on the customer's plan, seat count, and billing cycle. Classify the dispute into one of these categories:

- **Billing error**: Taskmoor charged incorrectly (wrong amount, wrong plan, post-cancellation charge).
- **Customer misunderstanding**: Charge is correct but customer does not recognize it or expected a different amount.
- **Chargeback in progress**: Customer's bank has already initiated a dispute.

### Step 2: Resolution Path

**If billing error confirmed:**
- Apply credit or initiate refund immediately for amounts under $200.
- For amounts $200-$500, apply credit and notify the billing team via `#billing-escalations` Slack channel.
- For amounts over $500, escalate to billing team lead with full documentation. Do not process the refund until billing team lead approves.

**If customer misunderstanding:**
- Explain the charge with reference to their plan details, billing cycle, and any recent changes.
- Offer to walk through the invoice line items.
- If the customer remains dissatisfied, offer a one-time courtesy credit of up to 10% of the disputed amount (maximum $50) and note it on the account.

**If chargeback in progress:**
- Immediately escalate to the billing team lead and finance team via `#billing-escalations`.
- Do not issue a refund while a chargeback is open (this would result in a double refund).
- Compile transaction evidence (invoices, login history, subscription confirmation emails) for the chargeback response.

### Step 3: Documentation and Follow-Up

- Record the dispute outcome in the customer's account notes.
- If a refund or credit was issued, confirm the amount and expected processing time with the customer (3-5 business days for refunds, immediate for account credits).
- For chargebacks, set a follow-up reminder for 30 days to check the dispute status.

## SLA Expectations

| Dispute Type | Initial Response | Resolution Target |
|---|---|---|
| Simple billing error (<$200) | 2 hours | 24 hours |
| Complex dispute ($200-$500) | 2 hours | 48 hours |
| High-value dispute (>$500) | 1 hour | 72 hours |
| Active chargeback | 1 hour | Dependent on bank timeline |

## Handoff Checklist

When escalating to the billing team lead, include:

- [ ] Account ID and organization name
- [ ] Complete billing history extract (last 6 months)
- [ ] Subscription change log
- [ ] Customer's stated concern (verbatim or close paraphrase)
- [ ] Your assessment and recommended resolution
- [ ] Any credits or refunds already applied
- [ ] Chargeback reference number (if applicable)
