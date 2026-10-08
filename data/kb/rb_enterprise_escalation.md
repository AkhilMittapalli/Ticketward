---
doc_key: rb_enterprise_escalation
doc_type: escalation_runbook
title: "Enterprise Tier Escalation"
product_areas:
  - billing_subscriptions
  - platform_availability
plans_applicable:
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

# Enterprise Tier Escalation

## Purpose

This runbook defines the escalation process for issues reported by enterprise-tier customers. Enterprise accounts have contractual SLAs, dedicated account managers, and elevated support priorities. This runbook ensures those commitments are met consistently.

## Trigger Conditions

Follow this runbook when an enterprise-tier customer:

- Reports any issue that may trigger an SLA violation (availability, response time, resolution time).
- Requests a feature or configuration change that requires engineering involvement.
- Reports a critical issue affecting their production workflows.
- Expresses dissatisfaction with the resolution of a previous ticket.
- Requests a meeting with product, engineering, or leadership.
- Is approaching contract renewal and has unresolved concerns.

## Required Information

1. **Account details**: Organization name, account ID, contract tier, and SLA terms.
2. **Account manager**: Name and contact for the assigned account manager (look up in the CRM).
3. **Issue description**: Clear description of the problem, including business impact.
4. **Severity assessment**: Classify using the enterprise severity matrix (see below).
5. **SLA clock**: Note the time the issue was first reported to start the SLA timer.

## Enterprise Severity Matrix

| Severity | Definition | Response SLA | Resolution SLA |
|---|---|---|---|
| SEV-1 (Critical) | Service fully unavailable or data integrity at risk for the enterprise customer. No workaround available. | 15 minutes | 4 hours |
| SEV-2 (High) | Major feature degraded, business operations significantly impacted. Workaround may exist but is inadequate. | 30 minutes | 8 hours |
| SEV-3 (Medium) | Feature partially impacted, workaround available. Business operations continue with reduced efficiency. | 2 hours | 24 hours |
| SEV-4 (Low) | Minor issue, cosmetic defect, or feature request. No business impact. | 4 hours | 5 business days |

## Escalation Procedure

### Step 1: Identify and Classify (Target: 5 minutes)

Verify the account is enterprise tier by checking the CRM or billing dashboard. Apply the severity matrix above. Start the SLA clock from the time of the customer's first report (not when you first see the ticket).

### Step 2: Notify the Account Manager

For all enterprise escalations (SEV-1 through SEV-4), notify the assigned account manager via Slack DM and email within 15 minutes of receiving the ticket. The account manager may choose to engage directly with the customer or delegate back to support.

### Step 3: Severity-Based Escalation

**SEV-1 (Critical):**
- Page the on-call engineering lead immediately via PagerDuty.
- Post in `#enterprise-incidents` Slack channel with customer name, issue summary, and SLA deadline.
- Stay on the issue continuously until it is resolved or handed off to engineering.
- Provide the customer with updates every 30 minutes.
- If resolution exceeds the 4-hour SLA, escalate to the VP of Engineering and the VP of Customer Success.

**SEV-2 (High):**
- Post in `#enterprise-support` Slack channel and tag the relevant engineering team lead.
- Provide updates to the customer every 2 hours.
- If resolution exceeds the 8-hour SLA, escalate to the engineering team lead and account manager.

**SEV-3 (Medium):**
- File a prioritized ticket in the engineering backlog with the `enterprise` and `sla-tracked` labels.
- Provide updates to the customer every 8 hours during business hours.

**SEV-4 (Low):**
- File in the standard support queue with the `enterprise` label for priority handling.
- Follow standard resolution timelines with periodic updates.

### Step 4: SLA Tracking and Credit Assessment

Track the SLA timer in the CRM. If an SLA breach occurs:

- Document the breach with timestamps and circumstances.
- Notify the account manager immediately.
- The account manager will assess whether SLA credits apply per the customer's contract terms.
- Support agents do not promise or calculate SLA credits; this is the account manager's responsibility.

### Step 5: Post-Resolution Follow-Up

For SEV-1 and SEV-2 issues:

- Schedule a post-incident review call with the customer within 48 hours.
- Prepare a brief incident summary (timeline, root cause, resolution, prevention measures).
- The account manager leads the call; support provides the technical summary.

## SLA Expectations

Per the enterprise severity matrix above. All SLA clocks start at the time of the customer's first report.

## Handoff Checklist

When escalating enterprise issues to engineering or leadership:

- [ ] Account name and enterprise contract tier
- [ ] Account manager name and notification status
- [ ] Severity classification with justification
- [ ] SLA clock start time and current elapsed time
- [ ] Issue description and business impact
- [ ] Steps already taken
- [ ] Customer communication history
- [ ] Whether SLA breach has occurred or is imminent
