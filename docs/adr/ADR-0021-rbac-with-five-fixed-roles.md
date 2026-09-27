---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §3; spec §2 (personas, RBAC matrix, matrix notes), §10 (user_queue_memberships), §11, §12.2, §24.3; research owasp-asvs-l2
informed: all personas; contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0021: RBAC with five fixed roles plus queue-membership object scoping

> **Amended in spec v1.1 (2026-09-27; change record A-25(b)(k), W-9, W-m11, A-23).**
> * **Queue scoping** comes from the new table `user_queue_memberships(user_id, queue, created_by, created_at)`. It
>   defines a support_agent's "own queues", the approve rule, and the IDOR tests. ops_lead and admin are org-wide.
> * **404 outside scope, 403 inside:** objects outside the caller's scope return 404 (no enumeration). An in-scope
>   action the role or membership does not allow returns 403. **Approving a human-decision draft without queue
>   membership is 403** (not the v1.0 409).
> * **Role changes and disables revoke all of the user's sessions** immediately (via the `sid` revocation set,
>   ADR-0020).
> * Explicit role lists replace the undefined "`support_agent+`". The feedback roles are the actual roles
>   (support_agent, ops_lead, csm, engineering; admin reads only).
> * New read endpoints for matrix rows that lacked one: `GET /api/v1/models` (ops_lead, engineering, admin) and
>   `GET /api/v1/metrics/csm` (csm, own escalations and outcomes).
> * In the public demo every privileged admin action is `403 DEMO_LOCKED` (ADR-0035).

## Context and Problem Statement

The brief defines four user groups (brief §3). The spec adds an administrator and a full permission matrix (§2):
`support_agent`, `ops_lead`, `csm`, `engineering`, `admin`, with create/read/update/approve rights per resource.

Access is also **object-scoped**:
* support agents see tickets in the queues they belong to;
* CSMs see tickets escalated to CSM plus high-churn tickets;
* engineering sees engineering escalations;
* PII reveal is limited to a member of the ticket's queue, or an admin.

v1.0 had no data model for queue membership, which left "own queues" and the approval rule unimplementable. It also
used undefined role shorthand and a status-code convention that leaked existence.

How should authorization be modelled and enforced?

## Decision Drivers

* Least privilege and deny-by-default (A01:2025; ASVS V8).
* IDOR/BOLA prevention on every object and list endpoint, including SSE.
* A matrix a reviewer can read and a test can enumerate exhaustively.
* Prompt effect of permission changes (role change or disable → sessions revoked).
* Fit with personas, queues, escalation targets and demo-mode locks.

## Considered Options

1. Five fixed roles, `require_roles` per route, plus queue-membership scoping in repository queries (chosen)
2. ABAC (attribute-based access control)
3. Casbin (policy-engine library)

## Decision Outcome

Chosen option: "five fixed roles plus queue-membership object scoping", because it maps one-to-one to the personas,
can be tested exhaustively (5 roles × every route), and puts object scoping into SQL, so list endpoints return only
authorized rows.

Enforcement:

* **Function level:** every router declares `Depends(require_roles(...))` with explicit role lists and the full
  `/api/v1` prefix. The only public routes are `/auth/login`, `/auth/activate`, `/auth/demo-login` (demo mode only,
  404 otherwise), `/health/live` and `/health/ready`, all allow-listed.
* **Object level:** a `Scope` (user id, role, org id, queue memberships, assignment) is built per request and required
  by every repository method. Predicates are applied to `SELECT`, `UPDATE` and `DELETE`, and to SSE subscription.
  Out of scope → 404; in scope but forbidden → 403.
* **Field level:** role-specific response models. Unmasked text is only available through the audited reveal. CSM and
  engineering briefs expose only their variant fields.
* **Approval rule:** if `needs_human_review`, a support_agent must be a member of the ticket's current queue, else
  **403 `FORBIDDEN`**.
* **Changes:** role changes and disables (admin only, audited `user.update`) revoke all of the user's sessions
  immediately. Membership changes are audited too.
* **Demo:** privileged actions return `403 DEMO_LOCKED` for every demo account (ADR-0035).

### Consequences

* Good, because permissions are legible and deny-by-default is test-enforced. IDOR is prevented at the query layer,
  including lists and streams.
* Good, because 404-outside-scope prevents enumeration, and 403-inside keeps errors honest for legitimate users.
* Good, because role and membership changes take effect within one request.
* Bad, because roles are coarse. New personas mean code changes and an ADR.
* Bad, because scoping lives in many repositories. Mitigation: base-class helpers that require a `Scope`, plus the
  IDOR suite with queue memberships.

### Confirmation

* `T-SEC-ROUTE-AUTH`: FastAPI route iteration finds every route, requires an explicit auth dependency, the full
  `/api/v1` prefix, and allow-listed public routes (A-29).
* `T-SEC-RBAC-matrix` (proposed): table-driven 5 roles × every endpoint vs the expected status, generated from the §2
  matrix, including `GET /models` and `GET /metrics/csm`.
* `T-SEC-IDOR-tickets/-drafts/-escalations/-handoffs/-feedback`: with `user_queue_memberships` fixtures,
  out-of-scope gives 404, in-scope-forbidden gives 403, lists never include out-of-scope rows, and approve without
  membership gives 403.
* `T-SEC-SSE-authz`: an out-of-scope ticket stream gives 404.
* `T-SEC-AUTH-sid-revocation`: a role change or disable revokes sessions within one request.
* `T-SEC-DEMO-mode`: `DEMO_LOCKED` on every privileged route in demo mode.
* Playwright "RBAC views": each demo role sees only its screens.

## Pros and Cons of the Options

### Five fixed roles + queue-membership scoping (chosen)

* Good, because it is simple, exhaustively testable and persona-aligned, and handles IDOR for lists and streams.
* Bad, because it is coarse-grained, with scoping discipline spread across repositories.

### ABAC

* Good, because it is fine-grained and flexible for future tenants.
* Bad, because policies are harder to author, test and review, and it is overkill for five personas.

### Casbin

* Good, because it is a mature allow/deny library.
* Bad, because it is another DSL and policy store to protect, and it produces no SQL filters. List IDOR would still
  need repository scoping.

## More Information

* Spec (private): §2 (personas, RBAC matrix, matrix notes: queue scope, read endpoints, public demo), §5.2, §10
  (`user_queue_memberships`, `users.is_demo`), §11 (roles per endpoint, 404/403 rule, approve 403), §12.2
  (Elevation), §14.3, §24.3. Change record A-25 (b)(k), W-9, W-m11, A-23.
* Brief (private): §3. BR-011..BR-014, PR-001.
* Research: [owasp-asvs-l2](../research/owasp-asvs-l2.md) (V8 applicability).
* Related ADRs: ADR-0020 (`sid` revocation), ADR-0027, ADR-0035 (`DEMO_LOCKED`).
* Security docs: [threat model](../security/threat-model.md) AC-04, AC-05, AC-16.
* Revisit when: multi-tenancy (NG-05) is lifted, or a persona needs permissions the fixed roles cannot express.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (queue memberships, 404/403 rule,
  approve 403, session revocation on role change, explicit role lists, new read endpoints).
