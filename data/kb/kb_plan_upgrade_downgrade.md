---
doc_key: kb_plan_upgrade_downgrade
doc_type: help_article
title: "Upgrading or Downgrading Plans"
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
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Taskmoor offers four plans -- Free, Starter, Business, and Enterprise -- each with increasing features, seat limits, and capabilities. This article explains how to upgrade or downgrade your workspace plan, what changes to expect, and how billing is handled during plan transitions.

## Plan Comparison

| Feature | Free | Starter ($8/seat/mo) | Business ($16/seat/mo) | Enterprise (Custom) |
|---|---|---|---|---|
| Seats | 5 | 50 | 500 | Unlimited |
| Custom fields | No | Yes | Yes | Yes |
| Timeline view | No | Yes | Yes | Yes |
| SAML SSO | No | No | Yes | Yes |
| SCIM provisioning | No | No | No | Yes |
| Audit log | No | No | No | Yes |
| API rate limit | None | 300/min | 600/min | 1200/min |
| Automation runs/month | 100 | 1,000 | 10,000 | Unlimited |
| File upload limit | 10 MB | 100 MB | 250 MB | 1 GB |

For a full feature comparison, see the pricing page in Taskmoor.

## Upgrading Your Plan

### From Free to Starter or Business

1. Log in as a **Workspace Owner**.
2. Navigate to **Settings > Billing > Subscription**.
3. Click **Upgrade Plan**.
4. Select the target plan (Starter or Business).
5. Choose the number of seats (minimum is your current member count).
6. Select monthly or annual billing.
7. Enter or confirm your payment method.
8. Review the total and click **Confirm Upgrade**.

The upgrade takes effect immediately. All features of the new plan are available right away.

### From Starter to Business

1. Go to **Settings > Billing > Subscription**.
2. Click **Upgrade Plan**.
3. Select **Business**.
4. Review the price difference. A prorated credit for the unused portion of your current Starter billing cycle is applied to the first Business charge.
5. Confirm the upgrade.

### Upgrading to Enterprise

Enterprise upgrades require contacting Taskmoor sales:

1. Go to **Settings > Billing > Subscription**.
2. Click **Contact Sales** under the Enterprise plan.
3. Fill out the inquiry form with your workspace size and requirements.
4. A Taskmoor sales representative will contact you to discuss pricing and contract terms.

Enterprise plans include dedicated support, custom integrations (such as Salesforce), and tailored onboarding.

## Downgrading Your Plan

### From Business to Starter

1. Go to **Settings > Billing > Subscription**.
2. Click **Change Plan**.
3. Select **Starter**.
4. Review the impact:
   - Features exclusive to Business (SAML SSO, task dependencies, milestones, swimlanes, webhooks, workload reports, time tracking, workspace export) become unavailable.
   - If your workspace has more than 50 members, you must reduce to 50 or fewer before downgrading.
   - Existing data is retained but Business-only features become read-only.
5. Acknowledge the feature changes.
6. Click **Confirm Downgrade**.

The downgrade takes effect at the end of your current billing cycle.

### From Starter to Free

1. Go to **Settings > Billing > Subscription**.
2. Click **Change Plan**.
3. Select **Free**.
4. Review the impact:
   - If your workspace has more than 5 members, you must reduce to 5 or fewer.
   - Starter features (custom fields, task templates, timeline view, guest access, API tokens, dashboards, automation rules, Excel import) become unavailable.
   - Automation runs reset to the Free limit of 100 per month.
   - API access is removed.
5. Acknowledge the feature changes.
6. Click **Confirm Downgrade**.

### From Enterprise

Enterprise downgrades are managed through your account representative. Contact Taskmoor sales to discuss contract changes.

## What Happens to Data During a Downgrade

When you downgrade, Taskmoor preserves your data but restricts access to plan-specific features:

- **Custom fields**: Values are retained but the fields are hidden and cannot be edited. If you upgrade again, the fields and values reappear.
- **SAML SSO configuration**: Disabled on downgrade from Business to Starter. Members can log in with password. The SSO configuration is saved and reactivated if you upgrade back to Business.
- **Webhooks and API tokens**: Deactivated but not deleted. They reactivate upon upgrade.
- **Automation rules**: Rules above the new plan's limit are paused. The most recently modified rules remain active up to the new plan limit.
- **Files**: Existing files remain accessible. New uploads must comply with the new plan's file size limit (Free: 10 MB, Starter: 100 MB).

## Billing During Plan Changes

### Upgrades (Immediate)

- A prorated credit for the unused portion of the current plan is calculated.
- The new plan charge is applied immediately, minus the prorated credit.
- Future billing cycles charge the full new plan rate.

### Downgrades (End of Cycle)

- The current plan remains active until the end of the billing cycle.
- No prorated refund is issued for the current cycle.
- The new (lower) plan rate applies starting the next billing cycle.

## Troubleshooting

### BILL_ERR_SEAT_LIMIT when downgrading

You cannot downgrade to a plan whose seat limit is lower than your current member count. Deactivate or remove members until your count is at or below the target plan's seat limit, then retry the downgrade.

### Features are missing after upgrade

Clear your browser cache and reload Taskmoor. New plan features may not appear until the page is refreshed. If features are still missing after a reload, log out and log back in.

### PAY_ERR_DECLINED during upgrade

Your payment method was declined. Try a different card or contact your bank. See the payment methods article for detailed error handling.
