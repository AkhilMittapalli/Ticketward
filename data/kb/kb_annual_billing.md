---
doc_key: kb_annual_billing
doc_type: help_article
title: "Switching to Annual Billing"
product_areas:
  - billing_subscriptions
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Taskmoor offers both monthly and annual billing for paid plans. Switching to annual billing provides a discount compared to paying month-by-month and simplifies budgeting with a single yearly payment. This article explains how to switch, what to expect during the transition, and how annual billing affects seat changes.

Annual billing is available on the **Starter**, **Business**, and **Enterprise** plans.

## Annual Billing Pricing

| Plan | Monthly Billing | Annual Billing | Annual Savings |
|---|---|---|---|
| Starter | $8/seat/month | $6.67/seat/month (billed as $80/seat/year) | ~17% |
| Business | $16/seat/month | $13.33/seat/month (billed as $160/seat/year) | ~17% |
| Enterprise | Custom | Custom | Contact sales |

Annual pricing is billed as a single upfront payment for the full year.

## Switching from Monthly to Annual Billing

1. Log in to Taskmoor as a **Workspace Owner**.
2. Navigate to **Settings > Billing > Subscription**.
3. Click **Change Billing Cycle**.
4. Select **Annual**.
5. Review the summary:
   - The annual price is calculated based on your current seat count.
   - A credit is applied for any unused days remaining in your current monthly billing cycle.
   - The net amount due is shown.
6. Click **Confirm Switch**.
7. The annual charge is processed immediately against your default payment method.

Your subscription is now on an annual cycle. The renewal date is 12 months from the switch date.

## What Happens During the Switch

### Credit for Remaining Monthly Period

If you switch to annual billing partway through a monthly billing cycle, Taskmoor calculates a prorated credit for the unused portion of the current month. This credit is subtracted from the first annual payment.

**Example**: You are on the Starter plan with 20 seats, paying $160/month. You switch to annual billing with 15 days remaining in your current monthly cycle. The credit is approximately $80 (15/30 x $160). Your first annual payment would be $1,600 (20 seats x $80/year) minus the $80 credit, totaling $1,520.

### No Service Interruption

The switch is seamless. There is no downtime or feature change during the billing cycle transition.

## Adding Seats on Annual Billing

When you add seats during an annual billing period:

1. Go to **Settings > Billing > Subscription**.
2. Click **Change Seats**.
3. Enter the new total seat count.
4. The prorated charge is calculated for the remaining days in the annual period.
5. Confirm the change.

The prorated charge is billed immediately to your default payment method.

**Example**: You are 6 months into an annual Starter plan. You add 5 seats. The prorated charge is 5 seats x $80/year x (6 remaining months / 12 months) = $200.

## Reducing Seats on Annual Billing

Seat reductions on annual billing take effect at the next annual renewal. You continue to have access to the current seat count for the remainder of the billing year. No refund or credit is issued for unused seats during the current annual period.

1. Go to **Settings > Billing > Subscription**.
2. Click **Change Seats**.
3. Enter the new (lower) seat count.
4. The reduction is scheduled for your next renewal date.
5. A confirmation shows the new seat count and the date it takes effect.

## Switching Back to Monthly Billing

If you want to return to monthly billing:

1. Go to **Settings > Billing > Subscription**.
2. Click **Change Billing Cycle**.
3. Select **Monthly**.
4. The change takes effect at the end of your current annual period. You are not refunded for the remaining annual term.
5. After the annual period ends, monthly billing begins automatically.

## Renewal

Annual subscriptions renew automatically on the anniversary of your switch date. Seven days before renewal, the Workspace Owner receives an email reminder with the upcoming charge amount.

To cancel auto-renewal:

1. Go to **Settings > Billing > Subscription**.
2. Click **Cancel Renewal**.
3. Your workspace continues on the current plan until the annual period ends, then reverts to the Free plan.

## Troubleshooting

### PAY_ERR_DECLINED on Annual Payment

Annual payments are larger than monthly charges and may trigger fraud protection on some cards. Contact your bank to pre-authorize the charge, then retry from **Settings > Billing > Payment Methods**.

### I switched to annual but want a refund

Taskmoor offers a 14-day refund window after switching to annual billing. If you request a refund within 14 days, the full annual charge is reversed and your workspace returns to monthly billing. Contact Taskmoor support to request the refund.

### My credit was not applied correctly

The credit calculation is based on the number of unused days in your monthly cycle at the moment of the switch. If you believe the credit is incorrect, contact Taskmoor support with your workspace URL and the date you made the switch.
