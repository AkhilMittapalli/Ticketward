---
doc_key: rb_security_report
doc_type: escalation_runbook
title: "Security Vulnerability Report Handling"
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

# Security Vulnerability Report Handling

## Purpose

This runbook defines the process for receiving, triaging, and escalating security vulnerability reports submitted by customers, researchers, or internal staff. All security reports must be treated as confidential and handled with urgency regardless of initial perceived severity.

## Trigger Conditions

Escalate using this runbook when:

- A customer or external researcher reports a potential security vulnerability.
- A customer reports suspicious activity on their account that may indicate a platform-level vulnerability.
- An internal team member discovers a vulnerability during routine work.
- A report is received through the `security@taskmoor.com` alias or the bug bounty program portal.

## Required Information

Gather the following while being careful not to ask the reporter to reproduce the issue if doing so could cause further harm:

1. **Reporter details**: Name, email, and affiliation (customer, researcher, or internal).
2. **Vulnerability description**: What the reporter observed, how they discovered it, and what they believe the impact is.
3. **Reproduction steps**: If safely reproducible, the steps to trigger the issue. Do not ask the reporter to exploit the vulnerability further.
4. **Affected components**: Which part of Taskmoor is affected (API, web app, mobile app, authentication, data storage, etc.).
5. **Evidence**: Screenshots, logs, request/response captures, or proof-of-concept code (if provided).
6. **Disclosure timeline**: Whether the reporter intends to disclose publicly and, if so, their expected timeline.

## Escalation Procedure

### Step 1: Acknowledge Receipt (Target: 1 hour)

Send an acknowledgment to the reporter confirming receipt of their report. Use the standard security acknowledgment template. Do not confirm or deny the validity of the report in this initial response. Assign a tracking ID using the format `SEC-YYYY-NNNN`.

### Step 2: Initial Triage (Target: 4 hours)

Classify the report severity:

- **Critical**: Remote code execution, authentication bypass, data exfiltration, privilege escalation to admin.
- **High**: Cross-site scripting (stored), SQL injection, SSRF with internal access, insecure direct object references exposing other customers' data.
- **Medium**: Reflected XSS, CSRF on sensitive actions, information disclosure of non-sensitive system details.
- **Low**: Missing security headers, verbose error messages, theoretical attacks with no practical exploit path.

### Step 3: Escalation by Severity

**Critical or High:**
- Immediately notify the security engineering lead via the `#security-incidents` Slack channel and PagerDuty.
- Page the on-call security engineer if outside business hours.
- Do not attempt to fix the issue yourself; the security engineering team owns the remediation.
- If active exploitation is suspected, also trigger the account compromise runbook (rb_account_compromise).

**Medium:**
- File a security issue in the internal bug tracker with the `security` and `triage` labels.
- Notify the security engineering team via `#security-incidents` (non-urgent).
- Target remediation within 30 days.

**Low:**
- File a security issue in the internal bug tracker with the `security` label.
- Include in the next security review cycle.
- Target remediation within 90 days.

### Step 4: Communication with Reporter

- Provide status updates to the reporter at least every 7 days until the issue is resolved.
- Once fixed, notify the reporter and offer them the opportunity to verify the fix.
- If the report qualifies for the bug bounty program, coordinate with the security team lead on the reward assessment.

### Step 5: Closure

- Confirm the fix with the reporter and close the tracking ticket.
- If the reporter requested public disclosure coordination, work with the security team lead and communications team on the disclosure timeline.

## SLA Expectations

| Severity | Acknowledgment | Triage | Remediation Target |
|---|---|---|---|
| Critical | 1 hour | 4 hours | 24 hours |
| High | 1 hour | 4 hours | 7 days |
| Medium | 4 hours | 24 hours | 30 days |
| Low | 24 hours | 72 hours | 90 days |

## Handoff Checklist

When escalating to the security engineering team, include:

- [ ] Tracking ID (SEC-YYYY-NNNN)
- [ ] Reporter contact information
- [ ] Vulnerability description and severity assessment
- [ ] Reproduction steps (if available)
- [ ] Evidence files (attached, not inline)
- [ ] Disclosure timeline (if reporter has one)
- [ ] Whether active exploitation is suspected
