---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §10 (users, auth_sessions), §11 (auth and session endpoints, service tokens), §12.2, §12.6, §12.7, §12.12, §24.3; research auth-cookie-jwt-csrf, nextjs-security, owasp-asvs-l2
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0020: Cookie JWT sessions (ES256, rotating refresh, `sid` revocation), signed double-submit CSRF, argon2id

> **Amended in spec v1.1 (2026-09-27; change record A-20, A-30, A-25(l), D-01).**
> * **Cookies:**
>   * `__Host-Http-tw_access` (A-30);
>   * `__Host-tw_csrf`;
>   * `__Secure-tw_refresh` with `Path=/api/v1/auth`. This is a **documented ASVS 3.3.3 deviation**, because
>     `__Host-` requires `Path=/`.
> * **CSRF:** Fetch Metadata → Origin → JSON content type (415) → a **signed, session-bound** double-submit token
>   (HMAC over `sid`). Login and demo-login get the first three steps (login CSRF).
> * **Tokens:** **ES256 only** (EdDSA rejected). `kid` = RFC 7638 thumbprint, two keys in the verify ring, `jku`/
>   `jwk`/`x5u`/`x5c` rejected, `typ=at+jwt`. **Service tokens use a separate ES256 key set** (`iss=tw-svc`,
>   `aud=tw-internal`, `typ=tw-svc+jwt`) on an internal listener, never HS256. PyJWT ≥ 2.15.0 (CVE-2026-48526).
> * **Sessions:**
>   * a `sid` claim checked against a Redis revocation set on every request, failing closed;
>   * **24 h absolute / 60 min idle** in prod, 4 h / 60 min in the demo;
>   * ≤ 5 active families per user;
>   * a 10 s single-shot refresh race grace that issues nothing (409 `REFRESH_SUPERSEDED`);
>   * endpoints to list and revoke sessions (re-authentication required), plus admin revoke;
>   * `Clear-Site-Data` on logout.
> * **Passwords:** 15..128 characters and a **mandatory** breached-password check (offline list always; HIBP optional
>   via the egress proxy). **Activation secrets** for admin-created users. New login throttling (below).
> * **MFA deferred** (ADR-0040). The v1.0 gaps this ADR carried (revocation lag, no absolute lifetime, no session
>   management) are closed by v1.1.

## Context and Problem Statement

Ticketward is used by internal staff (NG-10) with five roles (ADR-0021). The frontend and API are same-origin through
Caddy in prod **and in dev** (`https://localhost`), so there is no CORS anywhere (§12.7). The email-feed worker needs
its own machine identity for `POST /tickets` (§11). The public demo needs shared demo accounts entered through a
demo-login pathway (ADR-0035).

The v1.0 design had gaps the ERPROT auth research documented:
* a stateless access JWT stayed valid for up to 15 min after logout;
* the refresh family had no absolute lifetime;
* there was no self-service session management;
* the refresh cookie could not legally carry `__Host-`;
* HS256 service tokens mixed symmetric and asymmetric verification;
* the password rules (12 chars, optional breach check) were below the current guidance for single-factor passwords.

How should users and services authenticate, and how are sessions protected and terminated?

## Decision Drivers

* Tokens unreachable from JavaScript (XSS), short-lived, revocable within one request.
* Replay detection for long-lived credentials, without false positives from concurrent tabs.
* CSRF resistance for cookie auth, including login CSRF and cross-site reads of JSON/SSE.
* Password storage and policy at current guidance, with no MFA in v1 (D-01).
* A self-contained stack (DoD-1), with no external identity service.
* ASVS 5.0.0 L2 alignment (V3.3, V6, V7, V9) with documented exceptions.

## Considered Options

1. Cookie-carried ES256 access JWT (15 min) + rotating opaque refresh with `sid` revocation + signed double-submit
   CSRF + argon2id (chosen)
2. Bearer tokens stored in `localStorage`
3. Server-side sessions (opaque session id, server store)
4. bcrypt instead of argon2id
5. Hosted identity (Auth0 / Clerk)
6. EdDSA instead of ES256 for token signing

## Decision Outcome

Chosen option: option 1, because it keeps every token out of scripts, bounds replay, and verifies cheaply. The `sid`
check makes logout, admin kill and role changes effective within one request. It needs no external identity
provider.

**Cookies (FastAPI alone sets and clears them; Next.js never does):**

| Cookie | Value | Attributes |
|---|---|---|
| `__Host-Http-tw_access` | ES256 access JWT (15 min) | `Secure; HttpOnly; Path=/; SameSite=Lax; Max-Age=900`; no Domain. Browsers that implement `__Host-Http-` (Chrome/Edge ≥ 140, Firefox ≥ 143; verify) also refuse a script-set cookie of this name; others still enforce the `__Host-` rules |
| `__Host-tw_csrf` | signed CSRF token | `Secure; Path=/; SameSite=Strict`; readable by JS (echoed in `X-CSRF-Token`); Max-Age = remaining absolute lifetime |
| `__Secure-tw_refresh` | opaque 256-bit token | `Secure; HttpOnly; Path=/api/v1/auth; SameSite=Strict`; Max-Age = remaining absolute lifetime. **ASVS 3.3.3 deviation**, with compensating controls: path scoping, Strict, HttpOnly, rejection of duplicate cookie names, rotation with reuse detection |

**CSRF, deny by default on every `/api/*` request, in this order (spec §12.7):**
1. `Sec-Fetch-Site` present ⇒ must be `same-origin` (GETs also accept `none`). This also blocks cross-site reads of
   JSON and SSE.
2. `Origin` on unsafe methods must equal `TW_PUBLIC_ORIGIN` (`null` rejected), and is mandatory when Fetch Metadata is
   absent.
3. Unsafe requests with a body must be JSON, else 415.
4. `X-CSRF-Token` must equal the cookie (constant-time, bytes), and its HMAC must verify against `sid` (current and
   previous HMAC keys). Bearer-only service requests skip this step.
5. Login and demo-login run steps 1–3.

**Tokens:**
* User access tokens: `alg` fixed to ES256; `kid` = RFC 7638 thumbprint; ring = current private key + previous public
  key; header keys `jku`/`jwk`/`x5u`/`x5c` rejected; `typ=at+jwt`; claims `iss`, `aud`, `exp`, `iat`, `sub`, `role`,
  `org_id`, `sid`, `jti` (no PII).
* Service tokens: **separate ES256 key set**, `iss=tw-svc`, `aud=tw-internal`, `typ=tw-svc+jwt`,
  `sub=svc:email-feed`, 5-min TTL. Accepted only on the internal listener, by a dependency that reads only
  `Authorization: Bearer`. Each verifier rejects the other's audience and issuer.
* Key rotation: add the new key → move the old public key to "previous" → remove it after 15 min + leeway + deploy
  skew. Emergency rotation revokes all sessions.

**Sessions (`auth_sessions`, one row per token, grouped by `family_id` = `sid`):**
* Absolute expiry is fixed at login and never extended. Idle expiry is 60 min.
* Refresh happens only on user activity or a 401. Background SSE reconnects do not extend a session.
* Reuse of a rotated token revokes the whole family, except a single-shot 10 s race grace (same `ua_hash`,
  `reuse_count = 0`) that issues nothing (409 `REFRESH_SUPERSEDED`; the client retries once).
* Every authenticated request checks the Redis revoked-`sid` set (TTL = access TTL + leeway), failing closed: 503 on
  unsafe methods, 401 on reads.
* Logout, admin kill, disable, role change and password change (other sessions) revoke immediately. Logout sends
  `Clear-Site-Data: "cache", "storage"`.
* Endpoints: `GET /auth/sessions`; `POST /auth/sessions/{family_id}:revoke` and `/auth/sessions:revoke-others`
  (current password required, ASVS 7.5.2); admin `POST /admin/users/{id}/sessions:revoke` and
  `/admin/sessions:revoke-all` (`DEMO_LOCKED` in demo mode).

**Credentials and throttling:**
* argon2id m=64 MiB, t=3, p=1 (stronger than the OWASP minimum), with rehash on parameter change, ≤ 4 hashes in
  flight, and a dummy hash for unknown accounts.
* Passwords 15..128 characters, no composition rules, verified exactly as submitted, with a context-word list and
  zxcvbn ≥ 3 as guidance.
* The breached-password check is mandatory: a bundled offline list always, plus the optional HIBP k-anonymity range
  API (`Add-Padding: true`, 2 s timeout, through the egress proxy). CI uses the offline fixture.
* Admin-created users get a single-use activation secret (24 h TTL, stored hashed; `POST /auth/activate`).
* Login throttling (`limits`, sliding window; client IP from Caddy's `X-Real-IP`):
  * per IP: 5/min and 50/day;
  * per account: exponential backoff from the 5th consecutive failure, `min(30 s × 2^(n−5), 15 min)`;
  * hard disable at 100 consecutive failures (audited admin unlock);
  * global: 300 logins/min.

  Demo accounts have no per-account lockout.
* One generic 401 ("Invalid email or password"). Every login creates a new family and CSRF token.
* **Frontend:** client-side session refresh (`SessionRefresher` + Web Locks single-flight). Server Components forward
  only the access cookie (ADR-0023).

**Verify at build (research `auth-cookie-jwt-csrf`):** PyJWT ≥ 2.15.0 behaviour, `__Host-Http-` browser support, and
the argon2 cost on the chosen VM (P9 benchmark).

### Consequences

* Good, because XSS cannot read session tokens, and on supporting browsers `__Host-Http-` also stops script-set
  access cookies.
* Good, because revocation is effective within one request, sessions have absolute and idle limits, and users can
  see and kill their own sessions.
* Good, because the two ES256 key sets with distinct `iss`/`aud`/`typ` and separate verifiers remove alg-confusion
  and audience-confusion paths.
* Bad, because **Redis is now a hard dependency of authentication** (the `sid` check fails closed): a Redis outage is
  an auth outage (R-20). This is accepted for the demo, with a runbook (`redis-outage.md`).
* Bad, because there are more moving parts (key rings, HMAC keys, race grace, revocation set). Mitigation: ≥ 95%
  branch coverage on `core/security` and the security suite's JWT, CSRF and session matrices.
* Bad, because **there is no MFA in v1** (D-01). The documented exception and its compensating controls are in
  ADR-0040.

### Confirmation

* Security suite (§14.3), with the planned locations in the threat model's test register:
  * cookie names, attributes and prefixes on login, refresh and logout (`T-SEC-COOKIE-flags`);
  * the CSRF matrix: cross-site `Sec-Fetch-Site`, `Origin: null`, missing Origin + Fetch Metadata, `text/plain`
    → 415, token mismatch, token for another `sid`, login CSRF (`T-SEC-CSRF-required`, `T-SEC-CSRF-login-origin`,
    `T-SEC-CONTENT-TYPE`);
  * JWT negatives: `alg=none`, HS256 signed with the public key, unknown `kid`, a `jku` header, expired, wrong
    `aud`/`iss`/`typ`, a service token on the user verifier and vice versa (`T-SEC-JWT-validation`,
    `T-SEC-SVC-token-audience`).
* Refresh reuse revokes the family, and the race grace issues nothing (`T-SEC-AUTH-refresh-reuse`). Logout
  invalidates access within one request, and a disabled user loses all sessions (`T-SEC-AUTH-sid-revocation`).
* Lockout progression and the 100-cap (`T-SEC-AUTH-lockout-dos`). Identical responses for unknown vs wrong-password
  users (`T-SEC-AUTH-enumeration`). Password length, breached check and activation single-use
  (`T-SEC-AUTH-password-policy`, `T-SEC-AUTH-activation`).
* Session list and revoke with re-authentication, and admin revoke (`T-SEC-SESSIONS`). `DEMO_LOCKED` on password
  change and admin revoke in demo mode (`T-SEC-DEMO-mode`).
* `core/security` ≥ 95% branch coverage. The ASVS rows for V3.3, V6, V7 and V9, and the exceptions register
  (`../security/asvs-l2-checklist.md`).

## Pros and Cons of the Options

### Cookie ES256 JWT + rotating refresh + `sid` revocation + signed CSRF + argon2id (chosen)

* Good, because tokens stay out of scripts, verification is cheap, revocation is immediate, replay is detected, and
  it is self-hosted.
* Bad, because it depends on Redis, has more components than server sessions, and carries a documented cookie-prefix
  deviation.

### Bearer tokens in `localStorage`

* Good, because it is simple, with no CSRF.
* Bad, because any XSS can exfiltrate long-lived tokens, and it contradicts ASVS client-side storage guidance.

### Server-side sessions

* Good, because revocation is inherent and the model is simpler.
* Bad, because every request needs a session-store lookup anyway. With `sid` revocation the hybrid now has the same
  revocation property, while keeping stateless verification of claims.

### bcrypt

* Good, because it is ubiquitous.
* Bad, because it is not memory-hard, and its 72-byte input limit truncates long passphrases. The spec replaces it
  deliberately (§0).

### Auth0 / Clerk

* Good, because MFA and session management come out of the box.
* Bad, because it adds an external vendor and identity-data egress, and a tenant setup that blocks the clean-clone
  run (DoD-1). It also shows less of the engineering the portfolio is meant to demonstrate.

### EdDSA

* Good, because it has fast, small keys.
* Bad, because RFC 9864 (Oct 2025) deprecates the polymorphic JOSE `EdDSA` identifier in favour of `Ed25519`, and
  PyJWT implements only `EdDSA` (research `auth-cookie-jwt-csrf`). ES256 is unaffected and widely supported.

## More Information

* Spec (private): §0 (argon2id), §10 (`users`, `auth_sessions`), §11 (auth, session and admin-revoke endpoints,
  rate limits, service tokens, `REFRESH_SUPERSEDED`), §12.2 (Spoofing), §12.6 (key inventory), §12.7 (cookies, CSRF,
  sessions), §12.12 (exceptions), §24.3 (demo). Change record A-20, A-30, A-25 (l), D-01.
* Research: [auth-cookie-jwt-csrf](../research/auth-cookie-jwt-csrf.md),
  [nextjs-security](../research/nextjs-security.md), [owasp-asvs-l2](../research/owasp-asvs-l2.md).
* Related ADRs: ADR-0021, ADR-0022 (Redis), ADR-0023, ADR-0027, ADR-0035 (demo-login), ADR-0036 (HIBP via proxy),
  ADR-0040 (MFA).
* Security docs: [threat model](../security/threat-model.md), [ASVS checklist](../security/asvs-l2-checklist.md),
  [audit events](../security/audit-events.md) (`auth.*`).
* Revisit when: MFA (G-4) is implemented, staff SSO is required, or a `Path=/` refresh design removes the 3.3.3
  deviation.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (prefixed cookies incl.
  `__Host-Http-tw_access`, signed CSRF + Fetch Metadata, ES256 + separate service key set, `sid` revocation,
  lifetimes, session endpoints, password policy, activation, throttling).
