---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §4 (PR-002, PR-003), §12, §12.12, §14.5, §16 P9, §18, §19 DoD-9; research owasp-asvs-l2, owasp-top10-2025
informed: reviewers; contributors (PR security checklist)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0027: Target OWASP ASVS 5.0.0 Level 2, with documented exceptions

> **Amended in spec v1.1 (2026-09-27; change record A-21, D-01).**
> * **ASVS v5.0.0 is pinned** (tag `v5.0.0`; re-check for 5.0.1 at P9 and adopt it if released). Requirements are
>   cited as `v5.0.0-<chapter>.<section>.<req>`.
> * **Claim wording:** "targets OWASP ASVS 5.0 L2 **with documented exceptions**", quoted with the Met / N/A /
>   Deferred counts, self-assessed, with the last verification date and commit.
> * **Generated checklist:** `scripts/asvs_checklist.py` renders `docs/security/asvs-l2-checklist.md` from the
>   official CSV (pinned SHA-256) merged with `docs/security/asvs-status.yaml`. The **`asvs-checklist` CI job** fails
>   if any L1/L2 row lacks a status, or a "Met" row lacks evidence.
> * **Exceptions and deviations register** (§12.12, `docs/security/risk-acceptances.md`; IDs as in the checklist):
>   * EX-01 MFA deferred (6.3.3, confirmed against the official CSV; ADR-0040);
>   * EX-02 refresh cookie `__Secure-` (3.3.3);
>   * EX-03 internal TLS on the single-host demo (12.3.1–12.3.4);
>   * EX-04 the demo-login pathway (6.1.3/6.3.4);
>   * EX-05 secrets manager / off-host logs, if not in place by P9 (13.3.1; 16.4.3).
> * The other v1.0 L2 gaps (session timeouts, revocation, CSP `object-src`, Redis auth, egress enforcement) are
>   closed by v1.1 controls.

## Context and Problem Statement

PR-002 requires OWASP ASVS L2 with documented exceptions, and PR-003 requires OWASP LLM Top 10 (2026) controls. DoD-9
requires:
* the ASVS 5.0.0 L2 checklist generated from the official CSV and complete with evidence;
* the documented exceptions recorded with compensating controls;
* the threat model published (including the Rule of Two assessment).

Ticketward handles content that may contain personal data. It is synthetic in the demo (S-12), but the controls are
designed as if it were real. It also has five roles and privileged admin functions, and third-party processing
(masked frontier calls).

ASVS 5.0.0 (released 2025-05-30, per the research) reorganised the standard. All requirement IDs changed from 4.0.3.
The official CSV has 253 L1+L2 requirements. The interim per-requirement checklist (2026-09-27) finds 179 of them
applicable to Ticketward, and 185 once G-4 MFA (TOTP + recovery codes) is built.

The owner decided to defer MFA (D-01), which ASVS L2 expects. That is requirement 6.3.3, confirmed against the
official v5.0.0 CSV. Claiming "ASVS L2" unqualified would be false.

Which level should Ticketward target, how is conformance tracked, and how is the claim worded honestly?

## Decision Drivers

* Proportionality to the data and functions handled.
* A recognised, verifiable benchmark with machine-readable requirements (CSV).
* An honest public claim: exceptions are stated, counted and justified.
* Evidence that CI enforces, rather than a hand-maintained list that drifts.
* Effort that fits the production overflow budget (+12 d, §16).

## Considered Options

1. ASVS 5.0.0 Level 2 with a documented exceptions register and a generated, CI-checked checklist (chosen)
2. ASVS Level 1
3. ASVS Level 3

## Decision Outcome

Chosen option: "ASVS 5.0.0 L2 with documented exceptions", because L2 is the level ASVS recommends for applications
handling sensitive data. The exceptions register keeps the claim true despite the MFA deferral and the single-host
TLS deviation.

Tracking rules (spec §12, research `owasp-asvs-l2`):

* Statuses per requirement:
  * **Met**: at least one T/S/C evidence item (test, scanner, reviewed config), or D (documentation) for
    documentation requirements;
  * **Partial** / **Deferred**: a compensating control, a risk owner (the project owner) and a target version,
    recorded in `docs/security/risk-acceptances.md`;
  * **N/A**: a one-line architectural rationale.
* The checklist is generated. Until the generator lands (P0 task), `docs/security/asvs-l2-checklist.md` is
  maintained by hand at section level, and its statuses seed `asvs-status.yaml`.
* Reviews happen at the security-relevant phase exits (P4, P5, P7, P8, P9, P11). The final claim is made at P11.
* The README states: "targets OWASP ASVS 5.0 L2 with documented exceptions", with the Met / N/A / Deferred counts,
  "self-assessed", the last verification date and commit, and the known gaps in plain words (**MFA deferred**,
  refresh-cookie prefix deviation, single-host internal-TLS deviation).

### Consequences

* Good, because security work is driven by an evidence-checked requirement list, and reviewers can audit every row.
* Good, because the public claim is honest: exceptions are named, counted and compensated, not hidden.
* Good, because a patch release (5.0.1) can be adopted by re-running the generator against a new pinned CSV.
* Bad, because the generator and the status file must exist before evidence can be tracked per requirement. Until
  then the hand-maintained section-level view is the interim record.
* Bad, because some L2 requirements (MFA) are unmet in v1. They are Deferred with compensating controls and a target
  version (after v1.0, G-4).
* Neutral, because ASVS does not cover LLM risks. Those are tracked through the OWASP LLM Top 10 (2026) mapping in
  the threat model.

### Confirmation

* CI job `asvs-checklist` (§14.5 step 8): fails on any L1/L2 row without a status, or any "Met" row without
  evidence.
* DoD-9 at P11: the generated checklist is complete, `risk-acceptances.md` lists every Partial/Deferred item, the
  README carries the claim with counts, and the threat model is published.
* The PR template security checklist includes "ASVS checklist rows touched by any new route, cookie or external
  integration" (§14.4).
* Security CI: Bandit, Semgrep, CodeQL (incl. `actions`), pip-audit, `pnpm audit --prod`, gitleaks, Trivy, the SBOM,
  and the pytest security suite.

## Pros and Cons of the Options

### ASVS 5.0.0 L2 with documented exceptions

* Good, because it is proportionate, recognised and machine-readable, with an honest, verifiable claim.
* Bad, because the extra scope (session controls, internal TLS decisions, egress enforcement) is significant, and the
  exceptions must be maintained.

### Level 1

* Good, because it has the lowest effort.
* Bad, because it is too weak for personal data and privileged operations, so it would not justify
  "production-grade".

### Level 3

* Good, because it is the highest assurance.
* Bad, because it is disproportionate for a synthetic-data demo (hardware-backed factors, in-use data protection,
  and more). It would take over the schedule.

## More Information

* Spec (private): §4 (PR-002, PR-003), §12 (target, generation, claim), §12.12 (exceptions), §14.4 (PR template),
  §14.5 (`asvs-checklist` job), §16 P9, §18 (README claim), §19 DoD-9. Change record A-21, D-01.
* Research: [owasp-asvs-l2](../research/owasp-asvs-l2.md) (version, counts, applicability, evidence plan),
  [owasp-top10-2025](../research/owasp-top10-2025.md).
* Security docs: [ASVS L2 checklist](../security/asvs-l2-checklist.md) (exceptions register),
  [threat model](../security/threat-model.md), [audit events](../security/audit-events.md).
* Related ADRs: ADR-0020, ADR-0021, ADR-0026, ADR-0030, ADR-0035, ADR-0036, ADR-0037, ADR-0040.
* Revisit when: 5.0.1 is released (P9 check), MFA ships (remove the exception), or a multi-host deployment removes the
  internal-TLS deviation.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (5.0.0 pinned, "with documented
  exceptions" claim, generated checklist + CI job, exceptions register).
