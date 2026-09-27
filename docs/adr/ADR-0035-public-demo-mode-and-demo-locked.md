---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §3, §11 (auth and demo routes), §12.7, §12.12, §15, §16 P11, §17, §19 DoD-13, §21 R-09/R-11, §24.2–§24.5; research public-demo-deployment
informed: demo visitors (banner); reviewers of the public demo; operators (nightly reset)
supersedes: none
amended: none
---

# ADR-0035: Public demo mode (`TW_DEMO_MODE`) with `403 DEMO_LOCKED` privileged actions

## Context and Problem Statement

The project ends with a public demo on a single host (DoD-13; ADR-0026). Anonymous visitors should experience the
real workflow:
* submit a ticket;
* watch triage and policy;
* edit and approve a draft ("mark sent" only; S-01);
* escalate;
* leave feedback.

The demo must not become a way to change security-relevant state, spend money, lock accounts, or keep visitor-entered
content.

v1.0 left the demo's permission model, account handling and reset behaviour underspecified. The spec review and the
ERPROT public-demo research (W-10, SI-D1..D10) found:
* shared demo credentials invite password changes and lockout DoS;
* a read-only demo cannot show the product;
* backups taken before a reset would capture visitor content;
* a reset must not destroy the audit trail.

How does Ticketward run a public demo that is useful to visitors, bounded against abuse, and auditable?

## Decision Drivers

* Show the real workflow: workflow writes must work (W-10).
* No privileged state change by visitors: org settings, rules, models, users, purge, exports, KB publication.
* Abuse bounds: per-IP and global limits, quotas, input caps, and cost caps (R-09, R-11).
* No visitor content in backups, and a daily return to a known state.
* The audit trail survives resets, with the hash chain continuous.
* Honest disclosure: synthetic data, daily reset, fictional company, attribution.
* Safe by construction: the app refuses to boot in demo mode with any control missing.

## Considered Options

1. Demo mode: seeded role accounts with quota-limited workflow writes, privileged actions `403 DEMO_LOCKED`,
   demo-login, nightly reset before backup with the audit log preserved (chosen)
2. Read-only demo
3. Published passwords only (normal login with shared credentials)
4. No public demo (video only)

## Decision Outcome

Chosen option: demo mode (spec §24.3–§24.5), because it keeps the full workflow visible while every privileged action
is closed by one uniform guard. Visitor state is bounded by quotas and erased nightly.

**Activation:**
* `TW_DEMO_MODE=true`;
* startup validation **refuses to boot** unless every control below is configured;
* `POST /api/v1/auth/demo-login` exists only in demo mode (404 otherwise).

**Accounts and entry:**
* seeded users, **one per role**: `agent.demo`, `ops.demo`, `csm.demo`, `eng.demo`, `admin.demo`
  (`users.is_demo = true`);
* `agent.demo` is a member of all six queues, so the §17 flow works;
* no sign-up;
* entry is `POST /api/v1/auth/demo-login {role}` → 204 + the normal session cookies (`__Host-Http-tw_access`,
  `__Host-tw_csrf`, `__Secure-tw_refresh`). Login-CSRF defences apply (Fetch Metadata, Origin, JSON). There is a
  per-IP limit and optional Turnstile (Cloudflare Phase 2);
* each demo-login creates a new session family.
* This is a **documented extra authentication pathway** (ASVS 6.1.3 / 6.3.4; exception register §12.12).

**Account rules:**
* **no per-account lockout** for demo users; the per-IP and global limits stay (a shared account must not be lockable
  by one visitor);
* **no password change** (`403 DEMO_LOCKED`);
* MFA does not apply (ADR-0040);
* sessions last 4 h absolute / 60 min idle. The ≤ 5 families cap is a prod rule (§12.7).

**Workflow writes (allowed, quota-limited, inside the demo org):**
* submit a ticket (10/h per session);
* reprocess/regenerate (10/h);
* draft edit and approve ("mark sent");
* escalate and edit handoffs;
* feedback;
* PII reveal (synthetic data; audited; 10/h).

Global caps: 200 new tickets/day. When queue depth exceeds 20 → `429 RATE_LIMITED` with `Retry-After`. Worker
`max_jobs=2`, with the §7.7 timeouts.

**Privileged actions → `403 DEMO_LOCKED` (problem+json, ADR-0025), for every demo account including `admin.demo`:**
* `PATCH /admin/org-settings`: the frontier toggle, budget and every other org setting;
* policy rule-set activation (dry-run allowed);
* model activation;
* user management: CRUD, role changes, activation links, session revoke for other users, revoke-all;
* `DELETE /tickets/{id}` (purge);
* `GET /admin/feedback/export`;
* KB approve/publish/retire;
* `POST /tickets/batch`;
* `POST /auth/change-password`.

The lock is one reusable dependency applied per route. Only the seed/reset job uses the four-eyes bypass
(`approval_bypass_reason`).

**Input and cost:**
* `TW_DEMO_MAX_MESSAGE_CHARS=8000`; subject 300; no attachments; simulated e-mail feed only;
* frontier off by default. If on: `TW_FRONTIER_DAILY_BUDGET_USD=1.00` (an explicit override of the $2.00 default),
  a per-ticket cap of $0.05, plus the Anthropic workspace spend limit as a hard backstop.

**Disclosure and hidden surfaces:**
* A persistent banner says the data is synthetic, not to enter real personal data, and that it resets daily at
  03:00 UTC.
* The Taskmoor disclaimer and "Built with Llama" appear in the footer; `X-Robots-Tag: noindex`.
* Swagger/OpenAPI off. `/api/v1/metrics` returns 404 at the edge. Grafana, Tempo and Prometheus are internal only.
* Langfuse off.

**Nightly reset (03:00 UTC, `scripts/demo_reset.py`, §24.4):**
1. maintenance mode (mutations → 503 `MAINTENANCE`);
2. drain the worker and email-feed;
3. **export the audit rows and ledger rows** off-host, and write an `audit_chain_checkpoints` row (reason
   `demo_reset`);
4. `pg_restore --clean` of the SHA-256-verified golden dump, **excluding** `audit_log`, `audit_chain_checkpoints`
   and `deletion_ledger`, which are preserved;
5. `FLUSHDB` the app Redis DB (every session ends);
6. restart the services;
7. run `scripts/smoke_demo.py` (the 3 demo tickets hit their expected deciding rules, reasons, templates and queues);
8. clear maintenance and write `demo.reset_completed`;
9. **then** back up (§24.5), so no backup ever holds visitor content.

### Consequences

* Good, because visitors can run the whole workflow, including approve and escalate, which is what the demo needs to
  show.
* Good, because a single guard closes every privileged action for every demo role. A route-enumeration test keeps it
  complete as routes are added.
* Good, because visitor content lives at most about 24 h and never reaches a backup. The audit trail and deletion
  ledger survive resets with a continuous hash chain.
* Bad, because shared accounts mean visitors can see each other's tickets until the reset. The banner tells them not
  to enter real data, and quotas bound the volume. Offensive content can be visible until the reset (residual risk,
  threat model).
* Bad, because demo-login is an extra authentication pathway with no per-account lockout. It is a documented ASVS
  exception with per-IP and global limits, optional Turnstile, and 4 h sessions.
* Bad, because every privileged route carries the demo guard, and a missed route would be a hole. The enumeration test
  is the control.
* Neutral, because the demo differs from prod only by configuration. The same code paths are exercised, which keeps
  the demo honest.

### Confirmation

* `T-SEC-DEMO-locked`:
  * enumerates the privileged routes;
  * each returns `403 DEMO_LOCKED` for every demo role, `admin.demo` included;
  * rule-set dry-run still works;
  * a privileged route added without the guard fails the test.
* `T-SEC-DEMO-login`:
  * 404 when demo mode is off;
  * login-CSRF matrix (cross-site `Sec-Fetch-Site`, missing/foreign Origin, `text/plain` → 415);
  * per-IP 429;
  * a new `sid` per demo-login;
  * no lockout for demo users after repeated failures elsewhere.
* `T-SEC-DEMO-quota`: the 11th ticket in an hour per session → 429 with `Retry-After`; the global 200/day cap; queue depth
  > 20 → 429.
* Startup validation test: demo mode with any control missing refuses to boot.
* `T-SEC-DEMO-reset` (`make demo-reset` in CI against Compose):
  * audit tables and the ledger are preserved;
  * the chain verifies across the `demo_reset` checkpoint;
  * Redis is flushed (old sessions get 401);
  * `demo.reset_completed` is written;
  * the smoke passes.
  * The systemd timer order puts the backup after the reset.
* E2E `demo.spec.ts`: the banner and footer are present, and the 3 demo cases pass. The edge returns 404 for
  `/api/v1/metrics`, `/api/docs*` and `/api/openapi.json`.

## Pros and Cons of the Options

### Demo mode with `DEMO_LOCKED` (chosen)

* Good, because it gives the real workflow with privileged actions closed, bounded abuse, nightly clean state, and a
  preserved audit trail.
* Bad, because of shared-account visibility, an extra authentication pathway, and a per-route guard to maintain.

### Read-only demo

* Good, because it is the smallest attack surface and trivial to reason about.
* Bad, because it cannot show approve, escalate, feedback or reprocessing, which are the product (W-10).

### Published passwords only

* Good, because it needs no extra endpoint.
* Bad, because visitors could change or lock the shared passwords (lockout DoS), credentials get scraped, there is no
  role picker, and the same per-account rules would apply to real and demo users.

### No public demo

* Good, because it has no exposure and no hosting cost.
* Bad, because it fails DoD-13 and the portfolio goal. A video cannot be interacted with.

## More Information

* Spec (private): §3 (Taskmoor disclaimer), §11 (`/auth/demo-login`, `DEMO_LOCKED` routes, rate limits), §12.7
  (sessions, login CSRF), §12.12 (demo-login exception), §15 (backup order), §16 P11, §17, §19 DoD-13, §21 R-09/R-11,
  §24.2 (edge rules, Cloudflare), §24.3 (controls), §24.4 (reset), §24.5 (backups). Change record A-23, W-10; lead
  confirmation 3.
* Research: [public-demo-deployment](../research/public-demo-deployment.md).
* Related ADRs: ADR-0020 (sessions and cookies), ADR-0021 (RBAC), ADR-0025 (problem codes), ADR-0026 (host and
  edge), ADR-0037 (ledger preserved across resets), ADR-0040 (MFA exemption).
* Security docs: [threat model](../security/threat-model.md) (demo abuse cases), [audit
  events](../security/audit-events.md) (`auth.demo_login`, `demo.reset_completed`, `DEMO_LOCKED` denials),
  [ASVS checklist](../security/asvs-l2-checklist.md) (exception register).
* Open item: the spec gives no number for the demo-login per-IP limit. It is set in config; the login limits (5/min,
  50/day) are the suggested default.
* Revisit when: the demo is retired (the exception closes), abuse appears (Cloudflare Phase 2), or a real customer
  pilot starts (demo mode off).
* Status history: 2026-09-27 Accepted (new in spec v1.1, change record A-23).
