---
doc_key: policy_security_disclosure
doc_type: policy
title: "Responsible Security Disclosure Policy"
product_areas:
  - platform_availability
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: admin
review_due_at: "2026-10-13"
effective_from: "2026-07-15"
effective_to: null
---

# Responsible Security Disclosure Policy

## 1. Purpose

Taskmoor is committed to the security of its platform and its customers' data. This policy describes how security researchers and members of the public can report vulnerabilities to Taskmoor, the protections afforded to good-faith reporters, and the timeline for response and remediation.

## 2. Reporting a Vulnerability

Security vulnerabilities should be reported by email to security@taskmoor.com. Reports should include:

- A description of the vulnerability and its potential impact.
- Detailed steps to reproduce the issue, including URLs, request/response data, or proof-of-concept code where applicable.
- The reporter's contact information for follow-up communication.
- Any affected software version, API endpoint, or product area, if known.

Do not report security vulnerabilities through public channels such as GitHub issues, community forums, or social media. Public disclosure before remediation puts customers at risk and may void the safe harbor provisions described in this policy.

## 3. Response Timeline

Taskmoor's security team will follow this timeline upon receiving a valid report:

- **Acknowledgment:** Within 2 business days of receipt, the reporter will receive a confirmation that the report has been received and assigned a tracking identifier.
- **Triage:** Within 5 business days, the security team will perform an initial assessment to determine the severity and validity of the report.
- **Status Update:** The reporter will receive a status update within 10 business days, including the assessed severity and the expected remediation timeline.
- **Remediation:** Critical and high-severity vulnerabilities are targeted for remediation within 30 calendar days. Medium and low-severity issues are addressed according to the standard release cycle.

## 4. Safe Harbor

Taskmoor will not pursue legal action against individuals who report security vulnerabilities in good faith and in compliance with this policy. Good faith means:

- The reporter did not access, modify, or delete customer data beyond what was strictly necessary to demonstrate the vulnerability.
- The reporter did not exploit the vulnerability for personal gain or to cause harm.
- The reporter did not disclose the vulnerability to third parties before Taskmoor had a reasonable opportunity to remediate it.
- The reporter complied with all applicable laws.

Taskmoor considers research conducted under this policy to be authorized activity and will not pursue claims under the Computer Fraud and Abuse Act (CFAA) or equivalent statutes against reporters acting in good faith.

## 5. Scope

This policy covers the Taskmoor production platform (app.taskmoor.com), the Taskmoor API (api.taskmoor.com), and all Taskmoor-maintained mobile applications. The following are out of scope:

- Third-party services, integrations, or plugins not maintained by Taskmoor.
- Vulnerabilities in software or infrastructure operated by Taskmoor's customers.
- Social engineering attacks against Taskmoor employees or customers.
- Denial-of-service (DoS) or distributed denial-of-service (DDoS) attacks.
- Spam or phishing campaigns.

## 6. Recognition

With the reporter's consent, Taskmoor may acknowledge the reporter on the Taskmoor security acknowledgments page. Taskmoor does not currently operate a bug bounty program with monetary rewards but reserves the right to offer discretionary recognition at its sole judgment.

## 7. Contact

All security-related communications should be directed to security@taskmoor.com.
