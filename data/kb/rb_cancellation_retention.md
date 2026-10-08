---
doc_key: rb_cancellation_retention
doc_type: escalation_runbook
title: "Cancellation and Retention Process"
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

# Cancellation and Retention Process

## Purpose

This runbook defines the process for handling customer cancellation requests while identifying appropriate retention opportunities. The goal is to understand the customer's reasons, address solvable issues, and offer relevant alternatives without pressuring the customer into staying.

## Trigger Conditions

Follow this runbook when:

- A customer requests to cancel their Taskmoor subscription.
- A customer requests a downgrade from a paid plan to the free tier.
- A customer indicates they are evaluating alternative products and considering leaving.
- An organization admin initiates cancellation through the self-service flow and contacts support for assistance.

## Required Information

1. **Account details**: Organization name, current plan, seat count, billing cycle, and contract end date (if applicable).
2. **Cancellation reason**: Why the customer wants to cancel. Use open-ended questions to understand the root cause.
3. **Usage data**: Pull the account's usage summary from the admin dashboard (active users, projects, tasks created in the last 90 days, feature adoption).
4. **Contract status**: Whether the account is on a monthly or annual plan, and if annual, how many months remain.
5. **Previous interactions**: Any recent support tickets, complaints, or escalations from this account.

## Retention Procedure

### Step 1: Understand the Reason (Do Not Skip)

Before discussing retention offers, understand why the customer wants to leave. The most common reasons and appropriate responses:

**"Too expensive" / "Budget cuts":**
- Review their current plan and seat count. Are they on the right plan for their usage?
- If they have unused seats, suggest reducing seat count rather than cancelling.
- For annual customers, offer a plan downgrade rather than full cancellation.
- If a promotional discount is available (check with your team lead), you may offer up to 20% off the next renewal cycle for annual plans.

**"Missing features" / "Doesn't meet our needs":**
- Identify the specific features they need. Check the product roadmap (available on the internal wiki) to see if those features are planned.
- If a feature is on the roadmap, share the expected timeline (without making promises) and offer a short-term extension or discount to bridge the gap.
- If the feature is not planned, acknowledge the gap honestly.

**"Switching to a competitor":**
- Ask which product they are switching to and what it offers that Taskmoor does not. This feedback is valuable for the product team.
- Do not disparage competitors.

**"Consolidating tools" / "Not enough adoption":**
- Offer to connect them with the customer success team for an adoption workshop.
- Suggest a 30-day adoption trial with guided onboarding support.

**"Poor experience" / "Support issues":**
- Acknowledge the experience, apologize sincerely, and review the specific incidents.
- Escalate to the team lead if the experience involved a service failure or unresolved issue.

### Step 2: Retention Offers (If Appropriate)

Use these offers only when the customer's concern is addressable. Never pressure the customer.

| Offer | Eligibility | Approval Required |
|---|---|---|
| Seat count reduction | Any plan | No |
| Plan downgrade | Business or Enterprise | No |
| 20% discount on next renewal | Annual plans, first-time request | Team lead |
| 30-day extension for feature evaluation | Annual plans approaching renewal | Team lead |
| Customer success adoption workshop | Any plan, low adoption | No |
| Escalation to account manager | Enterprise tier | No |

### Step 3: Process the Cancellation

If the customer confirms they want to cancel after retention discussion:

1. Confirm the effective date: end of current billing period for monthly plans, or end of contract term for annual plans (no mid-term refunds unless approved by billing team lead).
2. Explain what happens to their data: data is retained for 90 days after cancellation, then permanently deleted. They can export their data before cancellation.
3. Process the cancellation in the billing system.
4. Send a confirmation email summarizing the cancellation date, data retention period, and how to reactivate if they change their mind.

### Step 4: Document Feedback

Record the cancellation reason in the CRM. Categorize it using the standard taxonomy (price, features, adoption, competition, consolidation, experience, other). This data feeds into the monthly churn analysis report.

## SLA Expectations

| Action | Target |
|---|---|
| Respond to cancellation request | 4 hours |
| Retention conversation | Same interaction |
| Process confirmed cancellation | 24 hours |
| Confirmation email | Immediate after processing |

## Handoff Checklist

When escalating retention cases to team lead or account manager:

- [ ] Account details and current plan
- [ ] Cancellation reason (customer's own words)
- [ ] Usage summary
- [ ] Retention offers already discussed
- [ ] Customer's response to offers
- [ ] Contract status and remaining term
