---
doc_key: rb_outage_comms
doc_type: escalation_runbook
title: "Outage Communications Procedure"
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

# Outage Communications Procedure

## Purpose

This runbook defines how support agents should communicate with customers during platform outages, coordinate with the engineering team for status updates, and manage customer expectations while an incident is being resolved.

## Trigger Conditions

Follow this runbook when:

- An active known incident has been declared by the engineering team.
- Multiple customers report the same issue and it appears to be a platform-wide or region-wide problem.
- The Taskmoor status page (status.taskmoor.com) shows an active incident.
- An outage is suspected but not yet confirmed by engineering.

## Required Information

Before communicating with customers, confirm the following with the engineering team or incident commander:

1. **Incident scope**: Which services, regions, and plan tiers are affected.
2. **Current status**: Investigating, identified, monitoring, or resolved.
3. **Estimated time to resolution**: If available; if not, state that the team is actively working on it.
4. **Customer-facing impact description**: What users are experiencing in plain language.
5. **Workarounds**: Any temporary steps customers can take to reduce impact.

## Communication Procedure

### Step 1: Verify the Incident

Check the `#incidents` Slack channel and the internal status dashboard before responding to customers. If no incident is declared but multiple customers are reporting the same issue:

- Post in `#incidents` with a summary of the reports (count, regions, symptoms).
- Tag the on-call engineering lead.
- Respond to customers acknowledging the issue while investigation is underway.

### Step 2: Customer Communication During Active Incident

Use the following communication principles:

- **Be honest about what is known and unknown.** Do not speculate about causes or timelines.
- **Acknowledge the impact.** Validate that the customer's work is disrupted.
- **Provide workarounds when available.** Reference the known incident document if one exists.
- **Set expectations for updates.** Tell customers when they will next hear from you (e.g., "We will provide an update within 2 hours or sooner if the situation changes").
- **Do not share internal technical details.** Reference error codes and user-facing symptoms only.

**Template for initial response during an outage:**

> We are aware of an issue affecting [service description] in the [region] region. Our engineering team is actively investigating. [Workaround if available.] We will provide an update within [timeframe]. You can also monitor status.taskmoor.com for real-time updates. We apologize for the disruption to your work.

### Step 3: Update Cadence

| Incident Duration | Update Frequency |
|---|---|
| 0-2 hours | Every 30 minutes |
| 2-8 hours | Every 1 hour |
| 8+ hours | Every 2 hours |

Post updates in the customer's ticket even if there is no new information. A brief "Our team continues to work on this issue; no new updates at this time" is better than silence.

### Step 4: Resolution Communication

When the incident is resolved:

- Notify all customers who opened tickets related to the incident.
- Confirm the specific symptom they reported is resolved.
- Ask them to verify on their end and reopen if they are still experiencing issues.
- Do not promise a post-mortem or credits unless the ops lead has approved it.

### Step 5: Post-Incident Follow-Up

For enterprise-tier customers affected by incidents lasting more than 1 hour:

- Schedule a follow-up check-in within 48 hours of resolution.
- If SLA credits are applicable under their contract, flag the account for the billing team to review.

## SLA Expectations

| Action | Target |
|---|---|
| Acknowledge customer report during active incident | 15 minutes |
| First customer-facing update after incident declared | 30 minutes |
| Update cadence during incident | Per table above |
| Resolution notification to affected customers | 1 hour after resolved |
| Enterprise follow-up scheduling | 48 hours after resolved |

## Handoff Checklist

When handing off an incident-related customer conversation to another agent or shift:

- [ ] Incident tracking link and current status
- [ ] Summary of what the customer was told and when
- [ ] Workarounds provided (if any)
- [ ] Whether the customer has been promised a follow-up
- [ ] Enterprise tier flag (if applicable)
- [ ] Any SLA credit implications noted
