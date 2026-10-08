---
doc_key: rb_payment_failure
doc_type: escalation_runbook
title: "Payment Failure Escalation"
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

# Payment Failure Escalation

## Purpose

This runbook covers the process for handling customers who contact support about failed payment attempts, declined cards, and accounts at risk of downgrade due to payment issues. The goal is to resolve payment issues quickly while preventing unnecessary account disruptions.

## Trigger Conditions

Follow this runbook when:

- A customer reports that their payment was declined when attempting to subscribe, upgrade, or renew.
- A customer receives an automated email about a failed payment and contacts support.
- A customer's account is in the dunning grace period (payment failed, downgrade pending).
- A customer reports being unexpectedly downgraded due to a payment failure they were unaware of.

## Required Information

1. **Account details**: Organization name, account ID, current plan, and billing contact.
2. **Payment method**: Type (credit card, debit card), last four digits, expiration date. Do not ask for or record full card numbers.
3. **Error details**: The specific error code or message the customer received (e.g., PAY_ERR_DECLINED, PAY_ERR_3DS).
4. **Transaction history**: Pull the last 3 payment attempts from the billing dashboard, noting dates, amounts, and decline reasons.
5. **Dunning status**: Whether the account is in the grace period and when the downgrade is scheduled.

## Escalation Procedure

### Step 1: Diagnose the Failure

Check the billing dashboard for the decline reason. Common causes and resolutions:

**Insufficient funds / Generic decline:**
- Ask the customer to verify with their bank and retry.
- Suggest trying a different payment method.
- Do not retry automatically without the customer's explicit request.

**Expired card:**
- Inform the customer that the card on file has expired.
- Guide them to update their payment method in **Settings > Billing > Payment Methods**.

**3D Secure authentication failure (PAY_ERR_3DS):**
- Explain that their bank requires additional verification.
- Recommend retrying the payment and completing the bank's authentication prompt (SMS code, banking app confirmation, etc.).
- If the customer's bank does not support 3D Secure or they cannot complete it, suggest an alternative card.

**Card blocked for international transactions:**
- Taskmoor processes payments through Stripe, which may appear as an international transaction depending on the customer's bank location.
- Advise the customer to contact their bank to authorize the transaction or whitelist the Taskmoor merchant ID.

**Duplicate transaction detection:**
- If the customer retried quickly, the bank may have flagged it as a duplicate.
- Wait 24 hours before retrying, or use a different payment method.

### Step 2: Grace Period Management

Taskmoor provides a 14-day grace period after a payment failure before downgrading an account. During this period:

- The customer can update their payment method and retry.
- All features remain accessible.
- Automated retry attempts occur on days 3, 7, and 12 of the grace period.

If a customer contacts support during the grace period:

- Reassure them that their account and data are safe.
- Help them update their payment method if needed.
- Trigger a manual retry after they update the payment method.

### Step 3: Post-Downgrade Recovery

If the account was already downgraded due to payment failure:

- Confirm the customer's data is still intact (data is retained for 90 days after downgrade).
- Help them re-subscribe to their previous plan.
- Once payment succeeds, the account is restored to the previous plan with all data intact.
- If the customer lost access to features they need urgently, escalate to the billing team lead to request a temporary plan restoration while payment is resolved (maximum 48 hours).

### Step 4: Escalation for Complex Cases

Escalate to the billing team lead when:

- The customer has experienced 3 or more consecutive payment failures across different payment methods.
- The customer disputes the payment amount.
- The customer requests an alternative payment method not currently supported (wire transfer, purchase order).
- An enterprise customer's payment failure affects their contractual SLA.

## SLA Expectations

| Scenario | Response Target | Resolution Target |
|---|---|---|
| Simple card update | 2 hours | Same interaction |
| 3DS failure assistance | 2 hours | 24 hours |
| Grace period inquiry | 2 hours | Same interaction |
| Post-downgrade recovery | 1 hour | 4 hours |
| Complex escalation | 1 hour | 48 hours |

## Handoff Checklist

When escalating to the billing team lead:

- [ ] Account ID and organization name
- [ ] Payment failure history (last 3 attempts with decline reasons)
- [ ] Payment methods tried
- [ ] Dunning status and days remaining in grace period
- [ ] Steps already taken to resolve
- [ ] Whether the account has been downgraded
- [ ] Enterprise tier flag and SLA implications
