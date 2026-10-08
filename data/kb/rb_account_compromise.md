---
doc_key: rb_account_compromise
doc_type: escalation_runbook
title: "Account Compromise Response"
product_areas:
  - user_admin_permissions
  - sso_identity
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

# Account Compromise Response

## Purpose

This runbook defines the response process when a customer reports suspected unauthorized access to their Taskmoor account or organization. Speed is critical: the goal is to contain the compromise, preserve evidence, and restore secure access.

## Trigger Conditions

Escalate using this runbook when:

- A customer reports that their account was accessed by someone other than themselves.
- A customer sees unfamiliar activity in their account (tasks created, settings changed, members added or removed that they did not authorize).
- A customer reports receiving a password reset email they did not request.
- An organization admin reports unauthorized changes to SSO configuration, API keys, or member permissions.
- Automated anomaly detection flags suspicious activity on an account (unusual login location, bulk data export, rapid permission changes).

## Required Information

1. **Account details**: User email, organization name, and account ID.
2. **Reported symptoms**: What the customer observed that triggered the report (specific actions, timestamps, unfamiliar IP addresses in login history).
3. **Account type**: Individual user or organization admin. If organization, how many members are potentially affected.
4. **Authentication method**: Password-based, SSO (which IdP), or API key.
5. **Timeline**: When the customer first noticed the issue and when they believe unauthorized access began.

## Escalation Procedure

### Step 1: Immediate Containment (Target: 15 minutes)

Take these actions immediately upon receiving a confirmed or strongly suspected compromise report:

1. **Reset the user's password** and invalidate all active sessions. The customer will need to set a new password.
2. **Revoke all API keys and personal access tokens** associated with the affected account.
3. If the affected user is an organization admin, **disable any recently added members** (added in the last 7 days) pending review by the legitimate admin.
4. If SSO configuration was altered, **revert to the last known good configuration** or disable SSO temporarily and notify the organization admin.

### Step 2: Evidence Preservation (Target: 1 hour)

Before the customer changes anything further, capture:

1. **Login history**: Last 30 days of login events including IP addresses, user agents, and authentication methods.
2. **Audit log**: All account and organization-level changes in the last 30 days (member additions, permission changes, API key creation, SSO changes, data exports).
3. **API access log**: Requests made with the account's API keys in the last 30 days.

Export these logs and attach them to the incident ticket. Do not share raw logs with the customer; instead, provide a summary of findings.

### Step 3: Scope Assessment (Target: 2 hours)

Determine the scope of the compromise:

- **Single user**: Only one user's credentials were compromised; no organization-level changes detected.
- **Organization-level**: Admin credentials were compromised; settings, members, or permissions were altered.
- **Data exfiltration suspected**: Bulk exports, API-based data extraction, or unusual data access patterns detected.

### Step 4: Escalation by Scope

**Single user compromise:**
- Complete containment steps above.
- Guide the customer through setting a new password and reviewing their recent activity.
- Recommend enabling two-factor authentication if not already active.
- Close the ticket once the customer confirms their account is secure.

**Organization-level compromise:**
- Escalate to the security engineering team via `#security-incidents` and PagerDuty.
- The security team will conduct a thorough investigation and may need to coordinate with the customer's IT team.
- Enterprise-tier customers should have their account manager notified as well.

**Data exfiltration suspected:**
- Escalate to the security engineering team and the privacy team immediately.
- This may trigger breach notification obligations under GDPR or other regulations.
- The privacy team will assess notification requirements.

### Step 5: Customer Communication

- Be transparent about what was found without revealing specific security architecture details.
- Provide the customer with a list of recommended actions (password changes for all org members, review of connected integrations, rotation of any secrets stored in Taskmoor).
- For enterprise customers, offer a follow-up call with the security team.

## SLA Expectations

| Action | Target |
|---|---|
| Initial containment | 15 minutes |
| Evidence preservation | 1 hour |
| Scope assessment | 2 hours |
| Customer notification of findings | 4 hours |
| Full investigation (org-level) | 24 hours |

## Handoff Checklist

When escalating to the security engineering team, include:

- [ ] Account ID and organization name
- [ ] Containment actions already taken
- [ ] Preserved evidence (login history, audit log, API log)
- [ ] Scope assessment (single user, org-level, or data exfiltration)
- [ ] Customer communication sent so far
- [ ] Authentication method in use (password, SSO provider, API keys)
- [ ] Whether the customer is an enterprise-tier account
