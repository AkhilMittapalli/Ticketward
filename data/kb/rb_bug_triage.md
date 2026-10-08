---
doc_key: rb_bug_triage
doc_type: escalation_runbook
title: "Bug Report Triage and Escalation"
product_areas:
  - platform_availability
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

# Bug Report Triage and Escalation

## Purpose

This runbook defines how support agents should triage, document, and escalate customer-reported bugs to the engineering team. Thorough triage reduces engineering investigation time and ensures critical bugs are addressed promptly.

## Trigger Conditions

Follow this runbook when:

- A customer reports behavior that appears to be a software bug (feature not working as documented, error messages, unexpected results).
- A customer reports a regression (something that previously worked is now broken).
- A customer provides reproduction steps for an issue that is not covered by a known incident.
- An internal team member identifies a bug during testing or customer call.

## Required Information

Collect the following before escalating to engineering. Incomplete bug reports will be returned for additional information.

1. **Reporter details**: Customer name, organization, plan tier, and account ID.
2. **Environment**: Browser type and version (for web issues), OS and app version (for mobile/desktop issues), API client version (for API issues).
3. **Description**: Clear, factual description of what is happening versus what the customer expects.
4. **Reproduction steps**: Numbered steps to reproduce the issue. If the issue is intermittent, note the approximate frequency.
5. **Error codes or messages**: Exact error codes, messages, or HTTP status codes observed.
6. **Screenshots or recordings**: Visual evidence of the issue, if available.
7. **Impact**: How many users are affected, and what is the business impact (blocked workflow, data concern, cosmetic issue).
8. **Workaround**: Whether a workaround exists and has been provided to the customer.

## Triage Procedure

### Step 1: Verify It Is a Bug

Before escalating, rule out these common non-bug causes:

- **User error or misconfiguration**: Review the customer's setup against documentation. Provide guidance if the issue is configuration-related.
- **Known incident**: Check the active known incidents. If the customer's issue matches an active incident, link them to the incident status and follow rb_outage_comms.
- **Known limitation**: Check the product documentation for known limitations of the feature. If the behavior is by design, explain this to the customer.
- **Feature request**: If the customer is requesting behavior that does not exist, log it as a feature request in the feedback system, not as a bug.

### Step 2: Classify Severity

| Severity | Criteria | Examples |
|---|---|---|
| P1 — Critical | Feature completely broken for all users, data loss or corruption, security vulnerability. | Cannot create tasks, data not saving, authentication bypass. |
| P2 — High | Feature broken for a subset of users or under specific conditions, significant workflow disruption. | Board view fails for projects with 100+ tasks, exports produce corrupt files for certain date ranges. |
| P3 — Medium | Feature works but with incorrect behavior, workaround available. | Notification timestamps display in wrong timezone, sort order incorrect on filtered views. |
| P4 — Low | Cosmetic issue, minor inconvenience, edge case with minimal impact. | Tooltip text truncated, avatar image not rendering in dark mode, alignment issue on a specific browser. |

### Step 3: File the Bug Report

Create a bug report in the engineering issue tracker with the following structure:

- **Title**: `[P{severity}] Brief description of the bug`
- **Labels**: `bug`, `support-reported`, plan tier label, product area label
- **Body**: Include all required information from the collection step above.
- **Link**: Include the support ticket URL for engineering to reference.

### Step 4: Escalation by Severity

**P1 — Critical:**
- Post immediately in `#engineering-bugs` Slack channel with the issue tracker link.
- Tag the on-call engineering lead.
- For enterprise customers, also follow rb_enterprise_escalation.
- Monitor the issue and provide the customer with updates every 2 hours.

**P2 — High:**
- Post in `#engineering-bugs` and tag the relevant product team lead.
- Set a follow-up reminder for 24 hours if no engineering response.

**P3 — Medium:**
- File the issue with labels. No immediate Slack notification needed.
- Engineering will prioritize in their regular triage cycle.
- Inform the customer that the issue has been reported and will be addressed in a future update.

**P4 — Low:**
- File the issue with labels.
- Inform the customer that the issue has been logged for future improvement.

### Step 5: Customer Follow-Up

- When engineering provides a fix ETA, update the customer.
- When the fix is deployed, notify the customer and ask them to verify.
- Close the support ticket once the customer confirms resolution or after 7 days without response.

## SLA Expectations

| Severity | Triage and Filing | Customer Update | Engineering Target |
|---|---|---|---|
| P1 | 30 minutes | Every 2 hours | 24 hours |
| P2 | 2 hours | Every 8 hours | 5 business days |
| P3 | 4 hours | On fix deployment | Next sprint |
| P4 | 8 hours | On fix deployment | Backlog |

## Handoff Checklist

When handing off a bug ticket to another agent:

- [ ] Issue tracker link
- [ ] Current severity and justification
- [ ] Engineering response status (acknowledged, investigating, fix in progress, deployed)
- [ ] Customer communication history
- [ ] Workaround provided (if any)
- [ ] Follow-up reminders set
