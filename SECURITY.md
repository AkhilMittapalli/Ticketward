# Security policy

Ticketward is a portfolio project that runs on **synthetic data only**. It still
follows a production security baseline: it **targets OWASP ASVS 5.0 L2 with documented
exceptions** (MFA is deferred to after v1.0; see the README "Safety model and security"),
plus the OWASP Top 10:2025 and the OWASP Top 10 for LLM Applications (specification §12).

## Supported versions

| Version | Supported |
|---|---|
| `main` (pre-release, `0.x`) | Yes: fixes land on `main` |
| Tagged `0.x` releases | Latest tag only |
| `>= 1.0.0` (after the public demo) | Latest minor release |

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for security problems.**

Report privately through GitHub's private vulnerability reporting: on the repository page
choose **Security -> Report a vulnerability**. Please include:

- affected component (API, frontend, pipeline/model, container/CI) and version or commit;
- steps to reproduce or a proof of concept, and the impact you observed;
- whether the issue involves prompt injection, PII exposure, authentication/authorization,
  or supply chain.

What to expect (best effort for a single-maintainer project):

- acknowledgement within 5 business days;
- an initial assessment and severity within 10 business days;
- a fix or mitigation plan for confirmed issues, then coordinated disclosure with credit
  (unless you prefer to stay anonymous).

## Patch SLA

Targets from the moment an issue is confirmed, or an advisory for a pinned dependency is
published:

| Severity | Target |
|---|---|
| Critical / high in **Next.js** (`next` is exact-pinned, floor 16.3.6) | upgrade within **72 hours** and record it here (spec §12.8) |
| Critical in any other dependency or in our code | fix or mitigate within 7 days |
| High | within 14 days |
| Medium / low | next scheduled release |

The GitHub Advisory Database is re-checked for `next` at the start of P8 and before every
release; weekly Dependabot, pip-audit and Trivy runs surface other advisories.

Recorded Next.js upgrades: none yet.

## Scope

In scope:

- code and configuration in this repository: backend, frontend, ML tooling, Docker and
  Compose files, CI workflows;
- the public demo deployment once it exists (P11), within the limits below;
- LLM-specific issues: prompt injection that bypasses the policy engine or forced human
  review, leakage of masked PII to models/logs, citation or claim-guard bypasses.

Out of scope:

- denial-of-service or volumetric testing against the demo, spam, social engineering and
  physical attacks;
- findings that require a compromised host, a malicious local administrator or already
  leaked credentials;
- vulnerabilities in third-party services or dependencies without a demonstrated impact on
  this project (report those upstream; we track advisories via Dependabot and pip-audit);
- missing best-practice headers or banners without a concrete exploit.

## Safe harbor

Good-faith research that respects this policy, avoids privacy violations and service
degradation, and gives us reasonable time to fix before disclosure will not be pursued.
Never use real personal data in reports. **If you find anything that looks like real
customer data in this repository, report it immediately**: the project must only contain
synthetic, public or authorized de-identified data.
