---
doc_key: rb_data_deletion
doc_type: escalation_runbook
title: "Data Deletion Request (GDPR Art. 17)"
product_areas:
  - user_admin_permissions
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

# Data Deletion Request (GDPR Art. 17)

## Purpose

This runbook defines the escalation process for data deletion requests received under GDPR Article 17 (Right to Erasure), CCPA, and equivalent privacy regulations. These requests have strict regulatory deadlines and must be handled with care to ensure compliance.

## Trigger Conditions

Escalate using this runbook when:

- A customer or individual requests deletion of their personal data.
- A request references GDPR Article 17, the right to erasure, the right to be forgotten, CCPA deletion rights, or similar regulatory language.
- An organization administrator requests full account data deletion upon contract termination.
- A former employee of a customer organization requests removal of their personal data from the platform.

## Required Information

1. **Requestor identity**: Full name, email address, and relationship to the data (account owner, organization member, former member, or non-user).
2. **Identity verification**: The request must come from a verified email address associated with a Taskmoor account, or the requestor must provide sufficient identifying information to locate their data.
3. **Scope of request**: What data the requestor wants deleted (their personal profile, their activity history, all data associated with their account, or data within a specific organization).
4. **Organization context**: Whether the requestor is an individual user or making the request on behalf of an organization. If organizational, whether they have admin authority.
5. **Regulatory basis**: Which regulation the requestor is invoking (GDPR, CCPA, or other).

## Escalation Procedure

### Step 1: Acknowledge and Log (Target: 24 hours)

Acknowledge the request within 24 hours. Log the request in the privacy request tracker with the following fields: requestor identity, date received, scope, and regulatory basis. Assign a tracking ID using the format `PRIV-YYYY-NNNN`.

### Step 2: Identity Verification (Target: 48 hours)

Verify the requestor's identity before proceeding:

- If the request is from a logged-in user through the Taskmoor interface, identity is verified.
- If the request is via email, confirm the email matches an account on file. If it does not match, request additional verification (last four digits of the payment method on file, or the organization name associated with their account).
- Do not process unverified requests. Respond with a verification request within 48 hours.

### Step 3: Scope Assessment

Determine what data must be deleted and what may be retained:

**Must delete:**
- Personal profile information (name, email, avatar, preferences).
- Direct messages and personal notifications.
- Activity logs attributable to the individual.

**May retain (with anonymization):**
- Task and project content created by the user within an organization (this belongs to the organization, not the individual). The user's name is replaced with "Deleted User."
- Audit logs required for security and compliance (anonymized to remove personal identifiers).
- Billing records required by tax and financial regulations (retained for the legally mandated period, then deleted).

### Step 4: Escalate to Privacy Team

Forward the verified, scoped request to the privacy team via `#privacy-requests` Slack channel with the tracking ID and your scope assessment. The privacy team executes the deletion within the system. Do not attempt to perform data deletion directly.

### Step 5: Confirm Completion (Target: 30 days from receipt)

GDPR requires completion within 30 days of the original request (not 30 days from verification). Once the privacy team confirms deletion:

- Notify the requestor that their data has been deleted.
- Specify what was deleted and what was retained with justification (e.g., "Billing records are retained for 7 years per tax regulations and will be deleted automatically after that period").
- Close the tracking ticket.

## SLA Expectations

| Step | Target |
|---|---|
| Acknowledgment | 24 hours |
| Identity verification request (if needed) | 48 hours |
| Escalation to privacy team | 72 hours from receipt |
| Deletion completion | 30 calendar days from receipt |
| Confirmation to requestor | 2 business days after deletion |

## Handoff Checklist

When escalating to the privacy team, include:

- [ ] Tracking ID (PRIV-YYYY-NNNN)
- [ ] Verified requestor identity
- [ ] Regulatory basis cited
- [ ] Scope assessment (what to delete, what to retain and why)
- [ ] Date of original request (for 30-day deadline calculation)
- [ ] Any communication history with the requestor
