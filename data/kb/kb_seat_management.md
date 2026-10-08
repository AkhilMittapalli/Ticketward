---
doc_key: kb_seat_management
doc_type: help_article
title: "Managing Seats and Licenses"
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

Seats in Taskmoor represent the number of active user accounts in your workspace. Each active member (excluding guests on Starter+ plans) occupies one seat. Managing seats effectively ensures you stay within your plan limits and control costs.

Seat management is available on all plans.

## Seat Limits by Plan

| Plan | Maximum Seats | Price |
|---|---|---|
| Free | 5 | $0 |
| Starter | 50 | $8/seat/month |
| Business | 500 | $16/seat/month |
| Enterprise | Unlimited | Custom pricing |

On paid plans (Starter, Business, Enterprise), you are billed for the number of seats you have provisioned, not the number of active users. If you purchase 20 seats but only 15 are occupied, you are still billed for 20 seats.

## Viewing Current Seat Usage

1. Go to **Settings > Billing > Subscription**.
2. The **Seats** section shows:
   - **Provisioned seats**: The number of seats you are paying for.
   - **Occupied seats**: The number of seats currently in use by active members.
   - **Available seats**: Provisioned minus occupied.
3. On the Free plan, this section shows your current member count out of the 5-seat maximum.

## Adding Seats

### On Starter and Business Plans

1. Go to **Settings > Billing > Subscription**.
2. Click **Change Seats**.
3. Enter the new total number of seats (must be more than currently occupied seats).
4. Review the prorated cost for the remainder of the billing cycle.
5. Click **Confirm**.

The additional seats are available immediately. Your next invoice reflects the new seat count. If you add seats mid-cycle, you are charged a prorated amount for the remaining days in the current billing period.

### On the Enterprise Plan

Seat changes on Enterprise plans are managed through your account representative. Contact Taskmoor sales to adjust your seat count.

### On the Free Plan

The Free plan is limited to 5 seats and cannot be expanded. To add more members, upgrade to the Starter plan.

## Reducing Seats

To reduce the number of provisioned seats:

1. Ensure the number of occupied seats is less than or equal to your target seat count. If necessary, deactivate or remove members first.
2. Go to **Settings > Billing > Subscription**.
3. Click **Change Seats**.
4. Enter the new (lower) total number of seats.
5. Click **Confirm**.

Seat reductions take effect at the start of your next billing cycle. You continue to have access to the current seat count until the cycle ends.

You cannot reduce seats below the number of currently occupied seats. Attempting to do so shows an error prompting you to remove members first.

## Deactivating Members to Free Seats

If you need to free up seats:

1. Go to **Settings > Members**.
2. Find the member you want to deactivate.
3. Click their name, then click **Deactivate Member**.
4. Confirm the action.

Deactivated members:
- Cannot log in to Taskmoor.
- Do not occupy a seat.
- Retain their data (tasks, comments, files) in the workspace.
- Can be reactivated later if a seat is available.

### Removing Members

To permanently remove a member:

1. Go to **Settings > Members**.
2. Find the member and click **Remove from Workspace**.
3. Choose whether to reassign their tasks to another member or leave them unassigned.
4. Confirm the removal.

Removed members lose access immediately and their seat is freed. Their historical contributions remain in the workspace.

## BILL_ERR_SEAT_LIMIT

This error appears when you attempt to invite a new member or convert a guest to a member and the workspace has no available seats. To resolve:

1. **Deactivate inactive members**: Review your member list for users who have not logged in recently and deactivate them.
2. **Add more seats**: On Starter and Business plans, increase your provisioned seat count from billing settings.
3. **Upgrade your plan**: If you are at the plan's maximum seat count (Starter: 50, Business: 500), consider upgrading to the next tier.

## Seat Billing FAQ

### Are guests counted as seats?

No. Guests on Starter, Business, and Enterprise plans do not consume seats. They have their own separate limits (Starter: 10 guests, Business: 100 guests, Enterprise: unlimited).

### What happens if I remove a member mid-cycle?

The seat remains provisioned and billed until the end of the current billing cycle. You can reduce your provisioned seats in billing settings, and the change takes effect at the start of the next cycle.

### Do pending invitations consume seats?

Yes. Each pending invitation reserves one seat. If you revoke the invitation before it is accepted, the seat is released.

### How do I monitor seat usage over time?

On Enterprise plans, the audit log tracks member additions and removals. On Starter and Business plans, review your monthly invoices, which include the seat count for each billing period.
