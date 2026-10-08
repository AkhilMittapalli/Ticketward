---
doc_key: rb_legal_request
doc_type: escalation_runbook
title: "Legal and Privacy Request Handling"
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

# Legal and Privacy Request Handling

## Purpose

This runbook covers the escalation process for legal requests that are not standard data deletion requests (which are handled by rb_data_deletion). This includes subpoenas, law enforcement requests, Data Subject Access Requests (DSARs), data portability requests, regulatory inquiries, and customer requests for legal documentation such as DPAs and SOC 2 reports.

## Trigger Conditions

Escalate using this runbook when:

- A law enforcement agency or court issues a subpoena, court order, or warrant for customer data.
- A regulatory body contacts Taskmoor regarding a customer complaint or compliance inquiry.
- A customer requests a Data Subject Access Request (DSAR) — a copy of all their data.
- A customer requests data portability under GDPR Article 20.
- A customer requests execution of a Data Processing Agreement (DPA).
- A customer requests SOC 2 reports, penetration test summaries, or other compliance documentation.
- A customer's legal counsel contacts support regarding contract terms, liability, or indemnification.

## Required Information

1. **Request type**: Classify as law enforcement, regulatory, DSAR, portability, DPA, compliance documentation, or legal counsel inquiry.
2. **Requesting party**: Name, title, organization, contact information, and legal authority (badge number, court case number, regulatory reference, etc.).
3. **Scope**: What data, documents, or actions are being requested.
4. **Deadline**: Any legally mandated response deadline.
5. **Customer account**: The Taskmoor account(s) referenced in the request.

## Escalation Procedure

### Step 1: Do Not Fulfill Directly

Support agents must never fulfill legal requests directly. Do not provide customer data, account information, or documentation to any requesting party without legal team approval. Acknowledge receipt and state that the request will be reviewed by the appropriate team.

### Step 2: Classify and Route

**Law enforcement / subpoena / court order:**
- Forward immediately to `legal@taskmoor.com` with the subject line "LEGAL: [request type] — [case reference]".
- Do not notify the customer about the request unless the legal team instructs you to.
- Target acknowledgment to the requesting party: 24 hours.

**Regulatory inquiry:**
- Forward to `legal@taskmoor.com` and `privacy@taskmoor.com`.
- Target acknowledgment: 24 hours.

**DSAR (data access request):**
- Log in the privacy request tracker as PRIV-YYYY-NNNN.
- Verify the requestor's identity (same process as rb_data_deletion).
- Forward to the privacy team via `#privacy-requests`.
- GDPR deadline: 30 days from receipt.

**Data portability request:**
- Log as a privacy request.
- Forward to the privacy team. Data must be provided in a structured, commonly used, machine-readable format (JSON or CSV).
- GDPR deadline: 30 days from receipt.

**DPA execution request:**
- Direct the customer to the standard DPA available at `taskmoor.com/legal/dpa`.
- If the customer requires a custom DPA or modifications to the standard DPA, escalate to `legal@taskmoor.com`.

**Compliance documentation (SOC 2, pen test summaries):**
- SOC 2 Type II reports can be shared under NDA. Direct the customer to request access through their account manager or `security@taskmoor.com`.
- Penetration test summaries are available to enterprise-tier customers under NDA. Escalate to the security team.

**Legal counsel inquiry:**
- Forward to `legal@taskmoor.com` without providing substantive responses.

### Step 3: Track and Follow Up

All legal and privacy requests must be tracked to closure. Set reminders for regulatory deadlines and follow up with the legal or privacy team if a deadline is approaching without resolution.

## SLA Expectations

| Request Type | Acknowledgment | Resolution Target |
|---|---|---|
| Law enforcement | 24 hours | Per legal team |
| Regulatory inquiry | 24 hours | Per legal team |
| DSAR | 24 hours | 30 calendar days |
| Data portability | 24 hours | 30 calendar days |
| DPA (standard) | 4 hours | Same day |
| DPA (custom) | 24 hours | Per legal team |
| Compliance docs | 4 hours | 5 business days |

## Handoff Checklist

When escalating to legal or privacy teams, include:

- [ ] Request classification
- [ ] Requesting party details and legal authority
- [ ] Scope of the request
- [ ] Deadline (regulatory or court-imposed)
- [ ] Affected customer account(s)
- [ ] All original correspondence (forwarded, not summarized)
- [ ] Tracking ID (if privacy request)
