---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §10 (users.mfa_secret_enc), §11 (rate limits, passwords), §12.2, §12.3 (A07:2025), §12.7 (sessions), §12.12, §18, §19 DoD-9, §20 L-17, §21 R-08; research auth-cookie-jwt-csrf, owasp-asvs-l2
informed: README readers (known gaps); admin and ops_lead users
supersedes: none
amended: none
---

# ADR-0040: MFA deferred to after v1.0, with a documented ASVS L2 exception

## Context and Problem Statement

Ticketward "targets OWASP ASVS 5.0 L2" (ADR-0027). ASVS v5.0.0 **6.3.3** (Level 2) requires either a multi-factor
authentication mechanism or a combination of single-factor mechanisms to access the application. This was checked
against the official v5.0.0 CSV on 2026-09-26; the spec still says "verify the number at build time".

Adding TOTP properly is not a small feature. It needs:
* enrolment and a recovery-code flow;
* encrypted secret storage;
* replay prevention (6.5.1);
* re-authentication integration;
* admin reset;
* tests.

All of this would compete with the v1.0 scope, which already carries +12 days of production-grade additions (R-08).

The owner deferred MFA to after v1.0 (D-01), and kept it as stretch goal G-4.

How is the deferral recorded and compensated, so that the ASVS claim stays honest and the residual risk is bounded?

## Decision Drivers

* An honest claim: "targets OWASP ASVS 5.0 L2 **with documented exceptions**", with the gap named plainly in the
  README.
* Compensating controls that measurably reduce password-only risk.
* Schedule: v1.0 scope and the portfolio deadline.
* The data at stake: synthetic only, in the demo and in development.
* A clear path to closing the exception (G-4).

## Considered Options

1. Defer MFA to after v1.0, with a documented ASVS exception and compensating controls; demo accounts exempt (chosen)
2. TOTP for admin and ops_lead in P4
3. TOTP for all roles

## Decision Outcome

Chosen option: defer with a documented exception (spec §12.12), because the compensating controls bound the risk for a
synthetic-data system with no public sign-up, and the exception is visible to every reader.

**Exception record (register EX-01):**
* requirement: ASVS v5.0.0 6.3.3;
* reason: owner decision D-01;
* risk owner: the project owner;
* target: after v1.0 (G-4);
* recorded in `docs/security/risk-acceptances.md` (planned) and in the exceptions register of the
  [ASVS checklist](../security/asvs-l2-checklist.md);
* the README lists it under known gaps (L-17).

**Compensating controls (all specified elsewhere and tested):**

| Control | Where |
|---|---|
| Short sessions: 24 h absolute / 60 min idle (prod), 4 h (demo); `sid` revocation on logout, password change, role change and disable | ADR-0020, spec §12.7 |
| Per-account exponential backoff from the 5th failure (`min(30 s × 2^(n−5), 15 min)`), hard disable at 100 (audited admin unlock), per-IP 5/min and 50/day, global 300/min | spec §11 |
| Passwords 15..128 with a mandatory breached-password check (offline list; optional HIBP range API) | ASVS 6.2.1/6.2.12; ADR-0020 |
| No public account creation: admin-created users with 24 h single-use activation secrets | ASVS 6.4.1; ADR-0021 |
| Session list and revoke (with re-authentication) and admin revoke | ASVS 7.5.2 |
| Security events and alerts for failed logins, lockouts and refresh reuse | ADR-0024; [audit events](../security/audit-events.md) |
| Synthetic data only; privileged actions `DEMO_LOCKED` in the public demo | ADR-0035 |

**Demo accounts:** MFA does not apply to the shared demo accounts in any case (a shared second factor is not a
factor). Their own exception is the demo-login pathway (EX-04).

**Schema:** `users.mfa_secret_enc` is reserved (NULL) so that G-4 needs no disruptive migration.

**G-4 plan (after v1.0):** TOTP for **admin and ops_lead first**, including:
* single-use codes and replay prevention (6.5.1);
* recovery codes;
* an encrypted secret (app-level AES-GCM);
* step-up for privileged actions.

Other roles follow.

### Consequences

* Good, because v1.0 scope stays deliverable, and the claim wording and README make the gap explicit rather than
  implied.
* Good, because the compensating controls cut the main password threats: credential stuffing (throttles), weak or
  breached passwords, and long-lived sessions.
* Bad, because a phished or reused password is still sufficient to log in. Privileged roles (admin, ops_lead) carry
  the highest risk until G-4. The residual risk is recorded in the threat model.
* Bad, because an ASVS L2 claim with exceptions is weaker than a clean L2. Reviewers must read the register.
* Neutral, because the reserved column and existing re-authentication hooks keep G-4 incremental.

### Confirmation

* The exceptions register (EX-01) exists in the ASVS checklist, and later `risk-acceptances.md`, with the compensating
  controls and the revisit trigger. The `asvs-checklist` CI job (P9) requires every exception row to name a
  compensating control.
* The README security section says "targets OWASP ASVS 5.0 L2 with documented exceptions" and lists "MFA deferred"
  (DoD-9).
* Each compensating control has its tests:
  * backoff/disable/unlock (`T-SEC-AUTH-ratelimit`, `T-SEC-AUTH-lockout-dos`);
  * breached-password check (`T-SEC-AUTH-breached`);
  * session lifetimes and revocation (`T-SEC-AUTH-sid-revocation`, `T-SEC-SESSIONS`);
  * no sign-up route (route enumeration);
  * activation secret single-use and expiry (`T-SEC-AUTH-activation`).
* Revisit checkpoint: before any real (non-synthetic) data is processed, G-4 is required. That becomes a blocking item
  in the release checklist for such a deployment.

## Pros and Cons of the Options

### Defer with a documented exception (chosen)

* Good, because the scope stays realistic, the claim is honest, the controls are compensating, and G-4 has a clear
  path.
* Bad, because password-only access remains for privileged roles until G-4.

### TOTP for admin and ops_lead in P4

* Good, because it closes the highest-risk gap early, and 6.3.3 would be met for privileged roles.
* Bad, because it adds roughly 1–2 days (enrolment, recovery, replay protection, tests) to an already over-budget
  plan (+12 d, R-08), and still leaves the other roles on single-factor authentication.

### TOTP for all roles

* Good, because it gives full 6.3.3 compliance.
* Bad, because it has the largest cost and friction. It is incompatible with shared demo accounts (which would need
  an exemption anyway), and it offers little extra value on synthetic data.

## More Information

* Spec (private): §10 (`users.mfa_secret_enc` reserved), §11 (rate limits, password rules), §12.2 (Spoofing), §12.3
  (A07:2025), §12.7 (sessions), §12.12 (exception register), §18 (README known gaps), §19 DoD-9, §20 L-17, §21 R-08.
  Owner decision D-01.
* Research: [auth-cookie-jwt-csrf](../research/auth-cookie-jwt-csrf.md),
  [owasp-asvs-l2](../research/owasp-asvs-l2.md).
* Related ADRs: ADR-0020 (authentication), ADR-0021 (RBAC, activation), ADR-0027 (ASVS target and exceptions),
  ADR-0035 (demo accounts).
* Revisit when: v1.0 ships (G-4), before any real-data deployment, or if a credential-compromise incident occurs.
* Status history: 2026-09-27 Accepted (new in spec v1.1; owner decision D-01).
