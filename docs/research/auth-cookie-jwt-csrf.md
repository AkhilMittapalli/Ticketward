# Auth: Cookie JWT Sessions, Refresh Rotation and CSRF - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Resolved. All research questions are answered. The three owner decisions this doc left open were taken in spec v1.1:
- MFA is deferred to after v1.0, with a documented ASVS exception (owner decision D-01, ADR-0040); SI-A6 is deferred.
- The 24 h / 60 min session lifetimes (4 h in demo mode) are adopted (A-20).
- The `__Secure-tw_refresh` ASVS 3.3.3 deviation is adopted (A-20).

One point to confirm: the spec names the access cookie `__Host-tw_access`, without the optional `__Http-` layer that D1 recommends.
**Category**: Security / Authentication and Session Management
**Linked ADR(s)**: ADR-0020 (cookie JWT + rotating refresh + double-submit CSRF + argon2id), ADR-0021 (RBAC), ADR-0025 (problem+json), ADR-0027 (ASVS L2), ADR-0040 (MFA deferred)
**Spec sections**: §10 (`users`, `auth_sessions`, `audit_log`), §11 (auth endpoints, rate limits, service tokens), §12.2 (Spoofing row), §12.3 (A07), §12.6 (JWT key rotation), §12.7 (CSRF), §16 P4, §21 R-11, §23

---

## EXECUTIVE SUMMARY

- **Standard.** OWASP ASVS 5.0.0 (May 2025) is current. It now splits session management (V7) from self-contained tokens (V9), and it makes cookie rules explicit (V3.3). The spec's design (15-minute access JWT in a cookie, rotating opaque refresh token, double-submit CSRF, argon2id) is sound. For L2 it has seven gaps:
  - JWTs cannot be revoked immediately (7.4.1, 7.4.2, 7.4.5).
  - Users cannot list or kill their own sessions (7.5.2).
  - Timeouts are not documented against NIST (7.1.1, 7.3.x).
  - MFA is deferred, but L2 requires it (6.3.3).
  - The breached-password check is optional, but L2 requires it (6.2.12).
  - The naive double-submit CSRF pattern is used (OWASP now discourages it).
  - The refresh cookie cannot legally carry `__Host-` (3.3.3).
- **Cookie-prefix conflict (spec impact).** A `__Host-` cookie must be `Secure`, must have no `Domain`, and must have `Path=/`. The spec scopes the refresh cookie to `Path=/api/v1/auth`, so it cannot use `__Host-`. Recommended cookie set:
  - `__Host-Http-tw_access`: Path=/, HttpOnly, SameSite=Lax. This is the new `__Http-` prefix family. It degrades safely to `__Host-` semantics in browsers that don't support it.
  - `__Host-tw_csrf`: readable by JS.
  - `__Secure-tw_refresh`: Path=/api/v1/auth, HttpOnly, SameSite=Strict, with a *documented deviation* from ASVS v5.0.0-3.3.3 and compensating controls.
- **Refresh.** Use opaque 256-bit tokens, stored as SHA-256 hashes, rotated on every use. Reuse revokes the whole family, per RFC 9700 §4.14.2. Add a single-shot race grace for multi-tab SPAs, plus client single-flight using the Web Locks API. Enforce both an absolute and an idle expiry.
- **CSRF.** Four layers. The primary control is Fetch Metadata (`Sec-Fetch-Site`), with `Origin` as the fallback. The second is the **signed** (HMAC, session-bound) double-submit token recommended by the OWASP CSRF Cheat Sheet. The third is JSON-only request bodies. The fourth is SameSite. `/auth/login` gets Origin/Fetch-Metadata checks to block login CSRF.
- **Passwords.** The spec's argon2id settings (m=64 MiB, t=3, p=1) are stronger than OWASP's current minimum (m=46 MiB, t=1, p=1, or its listed equivalents). Keep them, benchmark on the demo VM, and bound hash concurrency so a login flood cannot exhaust memory. Raise the minimum length to 15 while passwords are the only factor (NIST SP 800-63B-4).
- **JWT.** Use **ES256 via PyJWT >= 2.13** (2.15.0 is current). The polymorphic JOSE `EdDSA` identifier was deprecated by RFC 9864 (Oct 2025), and PyJWT only implements `EdDSA`, not the new `Ed25519` identifier. Other token rules:
  - `kid` is the RFC 7638 thumbprint, with two keys in the verify set.
  - Reject the `jku`, `jwk`, `x5u` and `x5c` headers.
  - `typ` is `at+jwt`.
  - Add a `sid` claim and check it against a Redis revocation set.
- **Lockout.** Use per-account exponential backoff rather than hard lockout, plus per-IP and global throttles. Hard-disable after 100 consecutive failures (the NIST cap). Always return the generic error. Shared public-demo accounts need a different policy (see D12).
- **14 spec-impact items** are listed in "SPEC IMPACT". The spec was not edited.

---

## QUESTIONS

1. What does ASVS (current version) require for sessions, tokens and cookies at L2?
2. What are the `__Host-` constraints (including `Path=/`)? Can the spec's refresh cookie (`Path=/api/v1/auth`) use it?
3. What is a correct refresh-rotation and reuse-detection design (races, expiry, revocation)?
4. CSRF: double-submit (signed/HMAC) or synchronizer token? What is OWASP's current guidance, and where does Fetch Metadata fit?
5. What argon2id parameters does the current OWASP Password Storage Cheat Sheet recommend?
6. JWT algorithm (EdDSA vs ES256), library (PyJWT vs joserfc), and key rotation via `kid`?
7. What lockout/backoff policy fits OWASP and NIST without enabling lockout DoS?
8. (Derived) How do logout, revocation and session timeouts satisfy ASVS 7.3/7.4 with stateless JWTs?

---

## FINDINGS

### F1. ASVS 5.0.0 requirements that shape this design (accessed 2026-09-26)

ASVS 5.0.0 is the latest stable release ("Version 5.0.0, May 2025"). Requirements are cited as `v5.0.0-<chapter>.<section>.<req>`. See `owasp-asvs-l2.md` for the whole standard. The paraphrases below are ours, and the levels come from the official CSV.

| ID | L | Requirement (paraphrased) | Spec as written |
|---|---|---|---|
| 3.3.1 | 1 | Cookies are `Secure`, and use the `__Host-` prefix or else `__Secure-` | Unprefixed names in §11 |
| 3.3.2 | 2 | SameSite is set per the cookie's purpose | Lax everywhere |
| 3.3.3 | 2 | `__Host-` unless the cookie is explicitly designed to be shared with other hosts | Refresh cookie cannot comply (Path-scoped) |
| 3.3.4 | 2 | Cookies not meant for scripts are HttpOnly, and the token is only sent via Set-Cookie | OK for access/refresh |
| 3.5.1-3.5.3 | 1 | Sensitive requests are proven to originate from the app; safe methods never change state | Double-submit + Origin |
| 6.1.1 / 6.3.1 | 1 | Anti-automation (rate limit, lockout) is documented and implemented | Partly (limits only) |
| 6.2.1 / 6.2.9 | 1/2 | Min 8 chars (15 strongly recommended); at least 64 chars permitted | Min 12; max unspecified |
| 6.2.4 / 6.2.12 | 1/2 | Check against the top-3000 list (L1) and a breached-password set (L2) | HIBP optional |
| 6.3.3 | 2 | Access requires MFA or a combination of single-factor mechanisms | MFA deferred (v1.1 / G-4) |
| 6.4.1 | 1 | System-generated initial passwords/activation codes are random and short-lived | Unspecified for `/admin/users` |
| 7.1.1 / 7.1.2 | 2 | Inactivity + absolute lifetime documented (justify deviation from NIST 800-63B); concurrent-session policy documented | Not documented |
| 7.2.3 / 7.2.4 | 1 | Reference tokens are CSPRNG with >= 128 bits; a new token on (re)authentication | OK |
| 7.3.1 / 7.3.2 | 2 | Inactivity timeout and absolute lifetime enforced | Only a 7-day refresh expiry |
| 7.4.1 / 7.4.2 | 1 | Terminated sessions cannot be used again; disabling a user ends all sessions | JWT stays valid up to 15 min |
| 7.4.3 / 7.4.5 | 2 | Option to kill other sessions after an auth-factor change; admin can kill a user's or all sessions | Password change revokes; no admin endpoint |
| 7.5.1 / 7.5.2 | 2 | Re-auth before changing auth attributes; users can view and (after re-auth) terminate sessions | Missing endpoints |
| 9.1.1-9.1.3 | 1 | Signature verified; algorithm allow-list without `none`, with key-confusion controls if symmetric and asymmetric are mixed; keys only from trusted config | HS256 service + EdDSA/ES256 user tokens (mixed) |
| 9.2.1-9.2.3 | 1/2 | `exp`/`nbf` checked; token type checked; `aud` checked | `aud` only for service tokens |
| 11.5.1 | 2 | Unguessable values: CSPRNG, >= 128 bits (the standard notes UUIDs do not qualify) | OK if `secrets.token_*` used |
| 14.3.1 | 1 | Authenticated data is cleared from the client after the session ends (Clear-Site-Data can help) | Not specified |
| 16.3.1 | 2 | All authentication operations logged | `auth.login_failed` only |

### F2. Cookie prefixes: rules, browser support, and the refresh-cookie conflict

- **MDN Set-Cookie (accessed 2026-09-26):**
  - `__Secure-`: the cookie must be set with `Secure` from an HTTPS page.
  - `__Host-`: additionally, no `Domain` attribute and `Path=/`.
  - `__Http-`: `Secure` plus `HttpOnly`, which proves the cookie was set by `Set-Cookie` and not by script.
  - `__Host-Http-`: both sets of rules.
  - MDN warns that browsers without prefix support simply accept prefixed cookies without the extra guarantees.
- **RFC 6265bis:** draft-ietf-httpbis-rfc6265bis-22 (2025-12-01) is in the RFC Editor queue. It has no RFC number yet as of the access date. §4.1.3 defines `__Secure-` and `__Host-` (Path `/`, no Domain). The `__Http-`/`__Host-Http-` prefixes are *not* in draft-22. Chromium's Intent-to-Ship cites httpwg PR #3110 (the layered-cookies work).
- **`__Http-` / `__Host-Http-` support (caniuse, accessed 2026-09-26):**
  - Chrome and Edge 140+: supported.
  - Firefox: partial in 142, supported from 143.
  - Safari: **no support** in any listed version.
  - Because the name `__Host-Http-tw_access` *begins with* `__Host-`, Safari still enforces the `__Host-` rules. Using it costs nothing and gains script-set protection in Chromium and Firefox.
- **Conflict:** `__Host-` forces `Path=/`, so a cookie limited to `Path=/api/v1/auth` cannot be `__Host-`. The spec (§12.2) already limits `__Host-` to "access/csrf" and leaves the refresh cookie unprefixed. ASVS 3.3.1 then *requires* `__Secure-`, and 3.3.3 (L2) requires `__Host-` unless the cookie is designed for other hosts, which this one is not. Two options:
  - **(a) Recommended.** `__Secure-tw_refresh; Path=/api/v1/auth`. The path scoping keeps the refresh token away from every Next.js page request and every non-auth API call, which is a real exposure reduction. Record a documented 3.3.3 deviation with compensating controls:
    - host the demo on a hostname with no untrusted sibling subdomains;
    - HSTS with `includeSubDomains`;
    - reject requests that carry duplicate cookie names (cookie-tossing detection);
    - refresh-token families with reuse detection;
    - SameSite=Strict.
  - **(b) Strict ASVS.** `__Host-Http-tw_refresh; Path=/`. The refresh token then travels on every request to the origin, including Next.js SSR requests, which increases log and exposure surface. Only choose this if a literal 3.3.3 "Met" matters more than exposure.
- **Deleting prefixed cookies.** The deletion `Set-Cookie` must itself satisfy the prefix rules (`Secure`; `Path=/` for `__Host-`; `HttpOnly` for `__Http-`). Otherwise the browser silently ignores it. Starlette's `delete_cookie` defaults (`secure=False`) break this, so pass the attributes explicitly.
- **Localhost.** Browsers treat `Secure` and prefixed cookies on `http://localhost` inconsistently (httpwg issue #2605). Develop through Caddy at `https://localhost` (same origin as prod) rather than cross-origin `http://localhost:3000` → API.

### F3. NIST SP 800-63B-4 (final, published 2025-08-26; accessed 2026-09-26)

- **Passwords.** Passwords used as a single factor SHALL be at least 15 characters. Passwords used only inside MFA may be as short as 8. Verifiers SHOULD allow at least 64 characters. A blocklist check (common, expected, compromised) is SHALL. Composition rules are not recommended.
- **Throttling.** Consecutive failed attempts on one account SHALL be limited to at most 100. Allowed techniques include bot challenges, increasing delays and risk-based signals.
- **Reauthentication.**
  - AAL1: overall timeout SHOULD be <= 30 days; an inactivity timeout is optional.
  - AAL2: overall timeout SHOULD be <= 24 hours; inactivity timeout SHOULD be <= 1 hour.
  - AAL3: <= 12 hours overall and <= 15 minutes inactivity.
- **Implication for the spec.** Password-only login is AAL1, where a 7-day refresh is inside NIST guidance. But ASVS L2 requires MFA (6.3.3), which pushes the app to AAL2 and its 24-hour / 1-hour guidance. The MFA decision and the timeout decision are therefore coupled.

### F4. Refresh rotation and reuse detection (RFC 9700, Jan 2025; accessed 2026-09-26)

RFC 9700 §4.14.2 requires one of two things for public clients: sender-constrained refresh tokens or refresh-token rotation. Its rotation description:

- Every refresh returns a new refresh token, and the previous one is invalidated.
- The authorization server keeps the relationship between the tokens (the family).
- When an invalidated token is presented, the server cannot tell attacker from victim, so it **revokes the active token**, which forces re-authentication.
- Encoding the grant into the token is allowed only if its integrity is protected.
- Refresh tokens SHOULD expire after client inactivity, and MAY be revoked on password change or logout.

The spec's `auth_sessions.family_id` + "reuse of a rotated token revokes the whole family" matches this. The spec is missing four things: an idle expiry, a race-handling rule for multiple tabs, a lock during rotation (to stop double-spend), and revocation of the *access* tokens already issued to the family.

### F5. CSRF: current OWASP guidance and Fetch Metadata (accessed 2026-09-26)

OWASP CSRF Prevention Cheat Sheet:

- Its order of advice:
  1. Use the framework's built-in protection.
  2. Otherwise use tokens: the **synchronizer token** for stateful apps, and the **signed double-submit cookie** for stateless ones.
  3. Modern-browser-only apps can rely on Fetch Metadata, with a fallback.
  4. APIs can use custom request headers.
  5. Add at least one defense-in-depth layer (SameSite, Origin verification).
  6. Never change state on GET.
- The **naive** double-submit pattern (an unbound random value in both a cookie and a header) is described as bypassable through cookie injection from a vulnerable subdomain. It is kept "for reference only". The recommended *signed* variant binds the token to the session with an HMAC. The HMAC runs over a server secret, the session ID, and a random value, using a length-prefixed, delimited message.
- Fetch Metadata is treated as strong but not standalone. A fallback to Origin/Referer verification is mandatory for browsers that don't send `Sec-Fetch-*`. Cross-site unsafe requests are rejected by default, and same-site requests should be allowed only if sibling subdomains are trusted. Coverage is stated as over 98% of browsers (Safari 16.4+).
- If neither `Origin` nor `Referer` is present on an unsafe request, OWASP recommends blocking it. OWASP also recommends the `__Host-` prefix for the CSRF cookie.
- Login CSRF is a real attack. Protect the login request too, with pre-session tokens or a custom header plus origin checks.

web.dev "Protect your resources from web attacks with Fetch Metadata" gives a resource-isolation policy:

- Allow requests without the headers (legacy browsers).
- Allow `same-origin`, `same-site` and `none`.
- Allow simple top-level GET navigations.
- Reject all other cross-site requests.

Filippo Valsorda's CSRF write-up documents the algorithm behind Go 1.25's `http.CrossOriginProtection`: `Sec-Fetch-Site` first, then an Origin-vs-Host fallback. It argues that tokens are no longer needed for modern browsers. We keep tokens anyway as defense in depth, because the OWASP cheat sheet still lists them first.

FastAPI background: GHSA-8h2j-cgx8-6xv7 / CVE-2021-32677, fixed in 0.65.2. FastAPI used to parse JSON bodies sent as `text/plain`, which enabled CSRF. That is why JSON-only bodies are enforced as a separate layer.

### F6. Password storage (accessed 2026-09-26)

- **OWASP Password Storage Cheat Sheet, Argon2id.** The minimum configurations are m=47104 KiB (46 MiB) with t=1, p=1. Equal-strength alternatives are 19 MiB/t=2, 12 MiB/t=3, 9 MiB/t=4 and 7 MiB/t=5 (all p=1). A pepper is optional defense in depth; it must not be stored with the hashes. Legacy hashes should be upgraded at the next login.
- **argon2-cffi 25.1.0** (latest on PyPI, 2025-06-03). `PasswordHasher` defaults to `time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=ID`, which is RFC 9106's second recommended (low-memory) profile. It exposes `check_needs_rehash()` and raises `VerifyMismatchError`, `InvalidHashError` or `VerificationError`. The docs suggest tuning with the bundled CLI benchmark (`python -m argon2`).
- The spec's m=64 MiB, t=3, p=1 is stronger than every OWASP listed configuration. The costs are latency and memory under concurrency: 10 parallel logins take about 640 MiB. That matters on a 16 GB VM that also runs CPU LLM inference.
- **GitHub Advisory Database** (accessed 2026-09-26) lists no advisories for `argon2-cffi`. FastAPI's own security tutorial now uses PyJWT and `pwdlib[argon2]`, which wraps argon2-cffi. Avoid `passlib`.

### F7. JWT algorithm and library (accessed 2026-09-26)

- **RFC 9864** (Oct 2025, Standards Track) introduces "fully specified" algorithm identifiers. It **deprecates JOSE `EdDSA`** in favour of `Ed25519` and `Ed448`. JOSE `ES256` already fixes P-256 + SHA-256 and is unaffected. Only COSE's ES256 (-7) is deprecated there, in favour of ESP256.
- **PyJWT 2.15.0** (PyPI, uploaded 2026-09-23):
  - Supports HS*, ES256/ES256K/ES384/ES512, RS*, PS*, and `EdDSA` (Ed25519 and Ed448 inside one identifier). There is no separate RFC 9864 `Ed25519` identifier. Asymmetric algorithms need the `pyjwt[crypto]` extra.
  - Recent advisories, all fixed in **2.13.0** (2026-06-15):
    - CVE-2026-48526 (high): a public-key JWK was accepted as an HMAC secret, so HS256 tokens could be forged "when mixed families are allowed".
    - CVE-2026-48523: algorithm allow-list bypass with `PyJWK`/`PyJWKClient`.
    - CVE-2026-48522: `PyJWKClient` accepted unsafe schemes (SSRF).
    - CVE-2026-48524 and CVE-2026-48525: DoS.
  - CVE-2026-32597 (high, unknown `crit` headers accepted) is fixed in 2.12.0. 2.11.0 added minimum-key-length warnings.
  - **Minimum acceptable: 2.13.0. Pin the latest (2.15.0) at P0.**
- **joserfc 1.7.5** (PyPI, 2026-08-29) implements the RFC 9864 `Ed25519`/`Ed448` identifiers. Its recent advisories: CVE-2026-49852 (HS* accepted an empty key, fixed 1.6.8), CVE-2026-48990 (fixed 1.6.7), CVE-2026-27932 (fixed 1.6.3), CVE-2025-65015 (fixed 1.3.5/1.4.2). Minimum acceptable: 1.6.8.
- **python-jose 3.5.0.** Its history includes algorithm confusion with OpenSSH ECDSA keys (CVE-2024-33663, critical). Do not use it.
- **Key confusion.** ASVS 9.1.2 requires extra controls when symmetric and asymmetric algorithms coexist. The spec does exactly this (HS256 service tokens next to asymmetric user tokens), which is the class behind CVE-2026-48526.

### F8. Lockout and backoff (accessed 2026-09-26)

- **OWASP Authentication Cheat Sheet:**
  - Count failures per **account**, not per IP.
  - Define a threshold, an observation window and a duration.
  - Prefer exponential lockout that starts at seconds and doubles.
  - Mind the lockout-DoS problem.
  - Always return the same generic message ("invalid user ID or password"), whatever the actual reason.
  - MFA is the strongest defense against credential stuffing.
- **NIST.** The 100-consecutive-failure cap (F3).
- **ASVS.** 6.1.1 (L1) requires this to be documented, and 6.3.1 (L1) requires it to be implemented as documented. 6.3.8 (L3) adds that timing and messages must not reveal whether a user exists. That is cheap to meet with a dummy-hash verify.
- **Library check.** `limits` 5.8.0 provides fixed-window, moving-window and sliding-window-counter strategies only. It has **no token bucket**, although spec §11 says "Redis token bucket via `limits`".

### F9. Other facts used below (accessed 2026-09-26)

- **MDN Clear-Site-Data.** The `"cookies"` directive clears cookies for the **entire registrable domain including subdomains**. `"storage"` clears DOM storage and service workers. `"cache"` clears the HTTP cache. The feature is Baseline "widely available" and needs a secure context.
- **HIBP Pwned Passwords range API.** `GET https://api.pwnedpasswords.com/range/{first 5 SHA-1 hex}`. It needs no API key, has no rate limit, and has no licence or attribution requirement for Pwned Passwords. The `Add-Padding: true` header pads responses to 800-1,000 records.

---

## DECISION / RECOMMENDATION

### D1. Cookie set

| Cookie | Value | Attributes | Why |
|---|---|---|---|
| `__Host-Http-tw_access` | ES256 access JWT (15 min) | `Secure; HttpOnly; Path=/; SameSite=Lax; Max-Age=900`, no Domain | Lax so top-level navigations to SSR pages carry the session. `__Http-` blocks script-set cookies (Chromium 140+, Firefox 143+); Safari still enforces `__Host-` |
| `__Host-tw_csrf` | Signed CSRF token (D7) | `Secure; Path=/; SameSite=Strict; Max-Age=<session absolute TTL>`, **not** HttpOnly | JS must read it to echo it in `X-CSRF-Token` |
| `__Secure-tw_refresh` | Opaque 256-bit token | `Secure; HttpOnly; Path=/api/v1/auth; SameSite=Strict; Max-Age=<remaining absolute TTL>` | Path-scoped away from all non-auth traffic. **ASVS 3.3.3 deviation** (see F2) |

```python
# backend/src/ticketward/core/security/cookies.py
from datetime import timedelta
from fastapi import Response

ACCESS_COOKIE = "__Host-Http-tw_access"
CSRF_COOKIE = "__Host-tw_csrf"
REFRESH_COOKIE = "__Secure-tw_refresh"
REFRESH_PATH = "/api/v1/auth"


def set_session_cookies(resp: Response, *, access: str, access_ttl: timedelta,
                        refresh: str | None = None, refresh_ttl: timedelta | None = None,
                        csrf: str | None = None) -> None:
    # No domain= argument: host-only cookies (required by __Host-).
    resp.set_cookie(ACCESS_COOKIE, access, max_age=int(access_ttl.total_seconds()),
                    path="/", secure=True, httponly=True, samesite="lax")
    if refresh is not None and refresh_ttl is not None:
        resp.set_cookie(REFRESH_COOKIE, refresh, max_age=int(refresh_ttl.total_seconds()),
                        path=REFRESH_PATH, secure=True, httponly=True, samesite="strict")
    if csrf is not None and refresh_ttl is not None:
        resp.set_cookie(CSRF_COOKIE, csrf, max_age=int(refresh_ttl.total_seconds()),
                        path="/", secure=True, httponly=False, samesite="strict")
    resp.headers["Cache-Control"] = "no-store"


def clear_session_cookies(resp: Response) -> None:
    # Deletion must repeat the prefix-mandated attributes or browsers ignore it.
    resp.delete_cookie(ACCESS_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    resp.delete_cookie(CSRF_COOKIE, path="/", secure=True, httponly=False, samesite="strict")
    resp.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, secure=True, httponly=True, samesite="strict")
```

Reject any request whose raw `Cookie` header contains the same name twice. That is how cookie tossing or shadowing shows up (compensating control for the 3.3.3 deviation).

### D2. Access token

- Algorithm **ES256** (P-256), library **PyJWT >= 2.13, pin 2.15.0**, with the `pyjwt[crypto]` extra.
- Header `{"alg":"ES256","typ":"at+jwt","kid":"<RFC 7638 thumbprint>"}`.
- Claims:
  - `iss`: `https://<public host>`
  - `aud`: `tw-api`
  - `sub`: user uuid
  - `sid`: `auth_sessions.family_id`
  - `role`
  - `iat`, `nbf`, `exp` (iat + 15 min)
  - `jti`: 128-bit hex
- **Validation checklist** (ASVS 9.1.x / 9.2.x):
  - fixed `algorithms=["ES256"]`;
  - key chosen **only** from the local key ring by `kid`;
  - reject the `jku`, `jwk`, `x5u` and `x5c` headers;
  - `typ` must equal `at+jwt`;
  - required claims present, with `aud` and `iss` checked;
  - leeway 30 s;
  - then `sid` is not revoked (D6).

```python
# backend/src/ticketward/core/security/jwt_tokens.py
import secrets
from datetime import UTC, datetime, timedelta

import jwt  # PyJWT >= 2.13 (2.15.0 current)
from pydantic import BaseModel

ALGS = ["ES256"]
ACCESS_TTL = timedelta(minutes=15)
LEEWAY_S = 30
_FORBIDDEN_HEADERS = {"jku", "jwk", "x5u", "x5c"}


class AccessClaims(BaseModel, frozen=True, extra="forbid"):
    iss: str; aud: str; sub: str; sid: str; role: str; iat: int; nbf: int; exp: int; jti: str


def issue_access_token(ring: "KeyRing", *, iss: str, user_id: str, sid: str, role: str) -> str:
    now = datetime.now(UTC)
    claims = {"iss": iss, "aud": "tw-api", "sub": user_id, "sid": sid, "role": role,
              "iat": now, "nbf": now, "exp": now + ACCESS_TTL, "jti": secrets.token_hex(16)}
    return jwt.encode(claims, ring.signing_key, algorithm="ES256",
                      headers={"kid": ring.signing_kid, "typ": "at+jwt"})


def verify_access_token(ring: "KeyRing", token: str, *, iss: str) -> AccessClaims:
    header = jwt.get_unverified_header(token)          # only used to select the key
    if header.get("typ") != "at+jwt" or header.get("alg") not in ALGS or _FORBIDDEN_HEADERS & header.keys():
        raise jwt.InvalidTokenError("bad header")
    key = ring.verify_key(header.get("kid"))            # KeyError -> 401, never fetch remote keys
    raw = jwt.decode(token, key, algorithms=ALGS, audience="tw-api", issuer=iss, leeway=LEEWAY_S,
                     options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub"]})
    return AccessClaims.model_validate(raw)             # enforces sid/role/jti presence
```

### D3. Key management and rotation (`kid`)

- Keys are PEM files mounted as Docker secrets:
  - `/run/secrets/jwt_es256_current.pem` (private);
  - `/run/secrets/jwt_es256_previous.pub.pem` (public, verify-only).
- `kid` = base64url(SHA-256(canonical JWK `{crv,kty,x,y}`)) per RFC 7638, computed at startup, so it cannot drift from the key.
- **Rotation runbook** (`docs/runbooks/rotate-secrets.md`):
  1. Generate the new key.
  2. Deploy it as `current`, and move the old public key to `previous`.
  3. After 15 min access TTL + 30 s leeway + deploy skew, remove `previous`.
  4. Record the rotation in the crypto inventory (ASVS 11.1.1/11.1.2).
  - Emergency rotation: skip step 3's wait and revoke all sessions.
- No public JWKS endpoint is needed, because only the API verifies. If one is ever added, serve only public keys, and never use `PyJWKClient` against a user-influenced URL (CVE-2026-48522 class).

```python
import base64, hashlib, json
from jwt.algorithms import ECAlgorithm

def jwk_thumbprint(public_key) -> str:
    jwk = json.loads(ECAlgorithm.to_jwk(public_key))
    canonical = json.dumps({k: jwk[k] for k in ("crv", "kty", "x", "y")}, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()
```

### D4. Refresh rotation with reuse detection

**Schema delta for `auth_sessions`** (spec impact SI-A5):

- Rename or clarify `expires_at` as `absolute_expires_at`. It is fixed at login and never extended.
- Add `idle_expires_at`, `parent_id` (the previous token row), `last_used_at` and `reuse_count smallint default 0`.
- Store `user_agent` as a hash plus a short summary.

**Algorithm** (one DB transaction, `SELECT ... FOR UPDATE` on the presented token's row):

```python
REFRESH_RACE_GRACE = timedelta(seconds=10)

async def rotate_refresh(raw: str, ctx: RequestCtx) -> TokenBundle:
    token_hash = hashlib.sha256(raw.encode()).digest()
    async with uow.transaction():
        row = await sessions.lock_by_hash(token_hash)             # FOR UPDATE; None -> 401
        if row is None or row.revoked_at is not None:
            raise Unauthenticated()
        now = utcnow()
        if row.rotated_at is not None:                            # a superseded token came back
            if (now - row.rotated_at <= REFRESH_RACE_GRACE and row.reuse_count == 0
                    and ctx.ua_hash == row.ua_hash):
                await sessions.bump_reuse(row.id)                 # first re-presentation only
                raise RefreshSuperseded()                         # 409 CONFLICT; no tokens issued
            await revoke_family(row.family_id, reason="refresh_reuse_detected")  # RFC 9700 4.14.2
            await audit.log("auth.refresh_reuse_detected", target_id=row.user_id, request_id=ctx.request_id)
            raise Unauthenticated()
        if now >= row.absolute_expires_at or now >= row.idle_expires_at:
            await revoke_family(row.family_id, reason="expired")
            raise Unauthenticated()
        user = await users.get_active(row.user_id)                # disabled/locked -> revoke family, 401
        new_raw = secrets.token_urlsafe(32)                       # 256-bit CSPRNG (ASVS 7.2.3)
        await sessions.mark_rotated(row.id, now)
        await sessions.insert_child(parent=row, token_hash=hashlib.sha256(new_raw.encode()).digest(),
                                    issued_at=now, idle_expires_at=now + IDLE_TTL, ip=ctx.ip, ua_hash=ctx.ua_hash)
    return TokenBundle(access=issue_access_token(..., sid=str(row.family_id), role=user.role),
                       refresh=new_raw, refresh_ttl=row.absolute_expires_at - now)
```

Notes:

- `revoke_family()` sets `revoked_at` on every row in the family, and writes `tw:revoked-sid:{family_id}` to Redis with TTL = 15 min + leeway (D6). Access tokens already issued to the family die on the next request.
- The grace path **issues nothing**, so an attacker gets no benefit from it. The second re-presentation of a superseded token revokes the family. That covers the case where a thief rotated first and the victim's retry arrives later.
- **Client single-flight.** The API client wraps refresh in `navigator.locks.request("tw-refresh", ...)` (Web Locks API; widely supported, confirm support at build) so only one tab refreshes. On `409 REFRESH_SUPERSEDED` it re-sends the original request once, because the browser already holds the newer cookies set by the other tab.
- **Login** always creates a new family (new `sid`) and a new CSRF token (ASVS 7.2.4).

### D5. Session lifetimes (owner decision; spec impact SI-A5 / SI-A6)

| Profile | Absolute | Idle | When |
|---|---|---|---|
| **AAL2-aligned (recommended for prod mode)** | 24 h | 60 min (no refresh in 60 min ends the session) | With MFA (D8/SI-A6); matches NIST AAL2 SHOULDs |
| Spec as written | 7 d | none | Password-only (AAL1-ish). ASVS 7.1.1 then requires a written justification, and 7.3.1 still requires *some* inactivity timeout |
| **Demo mode** | 4 h | 60 min | Shared demo accounts; nightly reset wipes all sessions |

Rules that go with these profiles:

- Refresh only on user activity or a 401. Don't let background SSE reconnects extend sessions indefinitely.
- The SSE handler re-checks `tw:revoked-sid` on every heartbeat (<= 30 s) and closes the stream on revocation (ASVS 7.4.1).
- Concurrent-session policy (7.1.2): at most 5 active families per user in prod mode, evicting the oldest. Demo users have no per-user cap but a global cap (e.g., 500 families) plus the 4 h absolute limit.

### D6. Revocation and session-management endpoints

- **Revocation store.** Redis key `tw:revoked-sid:{sid}` = `1`, with TTL = `ACCESS_TTL + leeway`. Each authenticated request makes one `EXISTS` round trip. **Fail closed**: if Redis is unavailable, return 503 on unsafe methods and 401 on reads. Sources of revocation:
  - logout;
  - family revocation;
  - admin kill;
  - user disabled or role changed (revoke all families; 7.4.2 and 8.3.x);
  - password change (revoke all *other* families; 7.4.3).
- **New endpoints** (spec impact SI-A9):
  - `GET /auth/sessions`: own active families (created, last used, coarse IP, UA summary, `current`).
  - `POST /auth/sessions/{family_id}:revoke {current_password}` and `POST /auth/sessions:revoke-others {current_password}`. Both require re-authentication per ASVS 7.5.2.
  - `POST /admin/users/{id}/sessions:revoke` and `POST /admin/sessions:revoke-all` (admin, audited; 7.4.5).

### D7. CSRF / origin middleware (deny by default)

Applied to every `/api/*` request, in this order:

1. **Resource isolation (all methods).**
   - If `Sec-Fetch-Site` is present, it must be `same-origin`.
   - GETs also accept `none` (the user typed the URL).
   - Everything else gets 403 `CSRF_FAILED`. This also stops cross-site reads of JSON and SSE (XSSI).
2. **Origin (unsafe methods).**
   - If `Origin` is present, it must equal `TW_PUBLIC_ORIGIN` exactly. `null` is rejected.
   - If `Sec-Fetch-Site` is absent on a cookie-authenticated unsafe request, `Origin` becomes mandatory. When both are absent the request is rejected, as OWASP recommends. Non-browser clients use bearer service tokens and carry no cookies, so they are unaffected.
3. **Content type.** Unsafe requests with a body must be `application/json`; anything else gets 415. This defeats form and `text/plain` CSRF (the CVE-2021-32677 class).
4. **Signed double-submit (cookie-authenticated unsafe requests, including `/auth/refresh` and `/auth/logout`).**
   - The `X-CSRF-Token` header must equal the `__Host-tw_csrf` cookie (constant-time compare).
   - The HMAC must verify against the `sid`: from the access token, or for `/auth/refresh`, from the refresh row.
   - Skipped only for requests authenticated purely by `Authorization: Bearer` (service tokens).
5. **Login and demo-login.** Steps 1-3 only (there is no session yet). This is the login-CSRF defense.

```python
import hashlib, hmac, secrets

def make_csrf_token(sid: str, key: bytes) -> str:
    rnd = secrets.token_hex(32)
    msg = f"{len(sid)}!{sid}!{len(rnd)}!{rnd}".encode()       # OWASP signed double-submit construction
    return f"{hmac.new(key, msg, hashlib.sha256).hexdigest()}.{rnd}"

def verify_csrf(header: str | None, cookie: str | None, sid: str, keys: list[bytes]) -> bool:
    # Compare bytes: hmac.compare_digest raises TypeError on non-ASCII str input (attacker-controlled header).
    if not header or not cookie or not hmac.compare_digest(header.encode(), cookie.encode()):
        return False
    mac, _, rnd = header.partition(".")
    msg = f"{len(sid)}!{sid}!{len(rnd)}!{rnd}".encode()
    return any(hmac.compare_digest(mac.encode(), hmac.new(k, msg, hashlib.sha256).hexdigest().encode())
               for k in keys)
```

- **Keys.** `keys = [current, previous]` from Docker secrets, which allows HMAC-key rotation without logging everyone out.
- **When the token is issued.** At login. On refresh, a new token is issued only if the presented cookie fails verification. A stable token avoids header/cookie races between tabs.
- **Synchronizer vs double-submit.** OWASP prefers the synchronizer token for stateful apps. The signed double-submit bound to the server-side `sid` gives the same forgery resistance without a per-request DB lookup. The overall design is effectively Fetch Metadata + Origin, with the token as defense in depth.

### D8. Password hashing and policy

```python
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import anyio, secrets

_PH = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=1, hash_len=32, salt_len=16, type=Type.ID)
_HASH_LIMITER = anyio.CapacityLimiter(4)                # <= 4 x 64 MiB in flight; tune after benchmark
_DUMMY_HASH = _PH.hash(secrets.token_urlsafe(32))       # equalises timing for unknown accounts (ASVS 6.3.8)

async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_PH.hash, password, limiter=_HASH_LIMITER)

async def verify_password(stored: str | None, password: str) -> tuple[bool, bool]:
    """Return (ok, needs_rehash). Always runs one Argon2 verification."""
    target = stored or _DUMMY_HASH
    try:
        await anyio.to_thread.run_sync(_PH.verify, target, password, limiter=_HASH_LIMITER)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False, False
    return stored is not None, _PH.check_needs_rehash(target)
```

- **Parameters.** Keep the spec's values (they exceed OWASP). Benchmark at P9 with `python -m argon2 -t 3 -m 65536 -p 1` on the demo VM:
  - If a single verify is > 300 ms, or p95 login latency breaches the SLO, switch to OWASP's m=46 MiB, t=1, p=1. It is equally compliant, and `check_needs_rehash()` migrates hashes on the next login.
  - The 300 ms target is our own engineering choice, not an OWASP number.
- **Policy.**
  - Minimum length 15 while passwords are the only factor (8 once MFA is enforced; NIST + OWASP).
  - Maximum 128 (>= 64 per ASVS 6.2.9).
  - No composition rules; verify exactly as submitted, with no truncation or case-folding (ASVS 6.2.8).
  - zxcvbn >= 3 only as UX guidance/blocker for guessable passwords.
  - Context-specific word list (Taskmoor, Ticketward, demo role names; ASVS 6.1.2/6.2.11).
- **Breached-password check** (mandatory at L2):
  - Always check a bundled offline list (the top 100k breached passwords; confirm the list's licence).
  - Optionally also query the HIBP range API (`Add-Padding: true`, 2 s timeout). If it fails, fall back to the offline result.
  - CI uses the offline list only. Add `api.pwnedpasswords.com` to the egress allow-list only when the online check is enabled.
- **MFA** (ASVS 6.3.3; owner decision SI-A6). Recommended: TOTP (RFC 6238), mandatory for `admin` and `ops_lead`, optional for other roles. Applicable rules (all L2):
  - one-time use (6.5.1);
  - CSPRNG seeds (6.5.3);
  - 30 s step (6.5.5);
  - hashed recovery codes (6.5.2);
  - re-auth before enrolment changes (7.5.1).
  - In demo mode MFA is off for shared demo accounts, as a documented deviation.

### D9. Login throttling and lockout

- **Per account.** Key by `user_id`, or by `HMAC(throttle_key, lower(email))` when the account doesn't exist, so behaviour is identical either way. `throttle_key` is a dedicated secret, not a password pepper. Redis counter with a 24 h window, reset on success.
  - From failure 5 onward, lock for `min(30 s * 2^(n-5), 15 min)`.
  - At 100 consecutive failures (NIST cap), set `users.locked_until = 'infinity'`. That needs an audited admin unlock.
- **Per IP.** Keep the spec's 5/min, and add 50/day on `/auth/login`. Key by the real client IP from the trusted `X-Real-IP` set by Caddy (ASVS 15.3.4; see `public-demo-deployment.md`).
- **Global.** 300 login attempts/min system-wide. Above that, return 429 to everyone. This is a credential-stuffing circuit breaker.
- **Strategy.** `limits` sliding-window counter (SI-A12), not a token bucket.
- **Responses.** Every failure (wrong password, unknown user, locked) returns the same 401 problem+json (`UNAUTHENTICATED`, "Invalid email or password"). Throttles return 429 with `Retry-After`.
- **Events.** Log to `audit_log` and metrics: `auth.login_succeeded`, `auth.login_failed` (the internal reason goes only to the audit details), `auth.lockout_engaged`, `auth.account_disabled_bruteforce`, `auth.refresh_reuse_detected`, `auth.logout`, `auth.sessions_revoked`. Also `tw_auth_failures_total{reason}` (ASVS 16.3.1).

### D10. Service tokens (email-feed worker)

- Recommended: **ES256 with a separate key ring** (`svc` keys).
  - Claims: `aud=tw-internal`, `typ=tw-svc+jwt`, `sub=svc:email-feed`, TTL 5 min.
  - Verified by a separate dependency that accepts only `Authorization: Bearer` and never looks at cookies.
  - The user verifier rejects `aud=tw-internal`, and the service verifier rejects `aud=tw-api`.
- If HS256 is kept (spec as written), it needs:
  - PyJWT >= 2.13 (CVE-2026-48526);
  - a dedicated decode path with `algorithms=["HS256"]` and a >= 32-byte random `bytes` secret;
  - no shared code path with the ES256 verifier (ASVS 9.1.2).

### D11. Logout

`POST /auth/logout` is CSRF-protected. It does the following:

- revoke the family and write the Redis revoked `sid`;
- `clear_session_cookies()`;
- `Clear-Site-Data: "cache", "storage"`. Add `"cookies"` only if the demo runs on its own registrable domain, because the directive clears every subdomain of it;
- the client clears the TanStack Query cache and redirects to `/login` (ASVS 14.3.1).

### D12. Demo-mode specifics (with `public-demo-deployment.md`)

- **Shared accounts break per-account lockout.** Anyone could lock `agent.demo`. So in demo mode:
  - the per-account lockout is disabled **for demo users only**, while the per-IP and global limits stay;
  - password change is disabled for demo users (403 `DEMO_MODE_FORBIDDEN`);
  - MFA is off for demo users.
- **Preferred entry.** `POST /api/v1/auth/demo-login {role}`, enabled only when `TW_DEMO_MODE=true`. It is rate-limited per IP, optionally gated by Cloudflare Turnstile, and issues a normal session for the seeded user of that role. It is a documented extra authentication pathway (ASVS 6.1.3/6.3.4). The alternative is publishing demo passwords on the login page.

---

## SPEC IMPACT

Disposition in spec v1.1: every item below was applied (A-20, ADR-0020 amended), except **SI-A6, which is deferred** by owner decision D-01 (MFA after v1.0; documented ASVS exception, ADR-0040). SI-A2 was applied as `__Host-tw_access`, without the optional `__Http-` layer from D1.

| # | Spec location | Finding | Recommendation |
|---|---|---|---|
| SI-A1 | §11 login row (`tw_refresh`, path `/api/v1/auth`); §12.2 | `__Host-` requires `Path=/`, so the path-scoped refresh cookie cannot be `__Host-`, and ASVS 3.3.3 (L2) is not met literally | `__Secure-tw_refresh` + a documented 3.3.3 deviation with compensating controls (F2). The alternative `__Host-Http-tw_refresh; Path=/` is not recommended |
| SI-A2 | §11 cookie names; §12.2 "HTTP-only ... cookies"; §12.7 | Names are unprefixed. The CSRF cookie cannot be HttpOnly | Names `__Host-Http-tw_access`, `__Host-tw_csrf` (non-HttpOnly), `__Secure-tw_refresh`. SameSite: Lax, Strict, Strict |
| SI-A3 | §12.7 CSRF | Naive double-submit is discouraged by OWASP | Signed (HMAC, sid-bound) double-submit + Fetch-Metadata-first + Origin fallback + JSON-only + login-CSRF check (D7) |
| SI-A4 | §11/§12.2 access JWT | A stateless 15-min JWT outlives logout and admin kill (ASVS 7.4.1/7.4.2/7.4.5) | Add a `sid` claim and a Redis revoked-sid check, failing closed (D6) |
| SI-A5 | §11 refresh 7 d; §10 `auth_sessions` | No idle timeout and no documented rationale vs NIST (ASVS 7.1.1, 7.3.1, 7.3.2) | Absolute 24 h + idle 60 min (prod), 4 h (demo). Add `idle_expires_at`, `parent_id`, `reuse_count`, `last_used_at` |
| SI-A6 | §10 `mfa_secret_enc` "v1.1"; §21 R-08 G-4 | ASVS 5.0 L2 6.3.3 requires MFA | Pull TOTP into P4 (at least admin/ops_lead), or record an explicit L2 deviation in the ASVS checklist |
| SI-A7 | §11 change-password "HIBP optional, off in CI" | ASVS 6.2.12 (L2) makes the breached-password check mandatory | Offline list always on; HIBP range API optional; egress allow-list entry |
| SI-A8 | §11 "length >= 12" | NIST SP 800-63B-4 SHALL: >= 15 for single-factor passwords; ASVS 6.2.9 >= 64 permitted | Min 15 (8 once MFA is enforced), max 128 |
| SI-A9 | §11 auth endpoint list | Missing ASVS 7.5.2 / 7.4.5 functions and a 7.1.2 concurrency policy | Add the session list/revoke endpoints (with re-auth), admin revoke endpoints, and a max of 5 families per user |
| SI-A10 | §11 service tokens "HS256" | Mixed symmetric/asymmetric verification is the key-confusion class (ASVS 9.1.2; PyJWT CVE-2026-48526) | ES256 service tokens with a separate key ring, or strictly separated HS256 verification on PyJWT >= 2.13 |
| SI-A11 | §12.2 "EdDSA or ES256" | JOSE `EdDSA` is deprecated by RFC 9864; PyJWT lacks the `Ed25519` identifier | Choose **ES256** (PyJWT). Use joserfc `Ed25519` only if EdDSA is required |
| SI-A12 | §11 "Redis token bucket via `limits`" | `limits` 5.8.0 has no token-bucket strategy | Use the sliding-window counter (or a custom Lua token bucket) |
| SI-A13 | §11 `POST /admin/users` | ASVS 6.4.1: initial secrets must be random and expire after a short time or first use | Admin creation issues a one-time activation link or code with a 24 h TTL, forcing password set on first login |
| SI-A14 | §11 logout | ASVS 14.3.1 wants client data cleared | `Clear-Site-Data: "cache", "storage"` + explicit cookie deletion + client cache clear (D11) |

---

## IMPLEMENTATION CHECKLIST (P4 unless noted)

- [ ] ADR-0020 amendment covering SI-A1..SI-A14. Owner decisions on MFA scope (SI-A6) and lifetimes (SI-A5).
- [ ] Pin `pyjwt[crypto]==2.15.0` (>= 2.13 is the floor), `argon2-cffi==25.1.0`, `cryptography` (latest at P0). Add pip-audit gating in CI.
- [ ] `core/security/cookies.py`, `jwt_tokens.py`, `keyring.py` (RFC 7638 kid), `csrf.py`, `passwords.py`, `revocation.py`.
- [ ] Alembic migration for the `auth_sessions` columns (`idle_expires_at`, `parent_id`, `reuse_count`, `last_used_at`, `ua_hash`); partial index on active families.
- [ ] OriginGuard/CSRF middleware (D7), registered before the routers. Duplicate-cookie rejection.
- [ ] Refresh service with `FOR UPDATE`, grace/reuse logic, family revocation, audit events.
- [ ] Frontend API client: `X-CSRF-Token` from `document.cookie`; Web Locks single-flight refresh; retry once on 409.
- [ ] Session endpoints (D6) + admin revoke endpoints. SSE heartbeat revocation check.
- [ ] Throttling (D9) with the `limits` sliding-window counter; generic errors; dummy-hash timing equalisation.
- [ ] Offline breached list + optional HIBP client; password policy validator (15/128, context words).
- [ ] (If SI-A6 accepted) TOTP enrolment/verify + recovery codes; enforced for admin/ops_lead.
- [ ] Security test suite (`tests/security/`), where each test is ASVS evidence:
  - cookie attributes and prefixes on login, refresh and logout;
  - deletion actually clears cookies;
  - CSRF rejects: cross-site `Sec-Fetch-Site`, `Origin: null`, missing Origin + missing Fetch Metadata, `text/plain` body, token mismatch, token for another sid;
  - login CSRF;
  - refresh reuse revokes the family, and the race grace issues no tokens;
  - logout invalidates access within one request;
  - disabled user loses all sessions;
  - JWT negatives: `alg=none`, HS256 signed with the public key, unknown `kid`, `jku` header, expired, wrong `aud`/`iss`/`typ`;
  - lockout progression and the 100-cap;
  - identical responses for unknown vs wrong-password users.
- [ ] P9: argon2 benchmark on the demo VM; record the result in `docs/security/crypto-inventory.md`.

---

## OPEN RISKS / TO VERIFY

- **`__Http-` prefix spec status.** It ships in Chromium 140+ and Firefox 143+, but it is not in RFC 6265bis-22. It could still change. The name remains valid as `__Host-` in all browsers, so the risk is low. **Verify at build.**
- **Web Locks API.** Treated as widely supported. **UNVERIFIED for the exact minimum browser versions; verify at build.**
- **Unicode normalisation.** NIST suggests NFKC/NFKD normalisation, while ASVS 6.2.8 says verify passwords exactly as received. We do not normalise. Revisit if non-ASCII passwords cause support issues.
- **argon2 latency on the chosen VM** is unknown until P9 benchmarking.
- **Redis as a hard auth dependency.** The revocation check fails closed, so a Redis outage becomes an auth outage. That is acceptable for a demo and must be reflected in the SLO and runbook.
- **Offline breached-password list.** Source and licence to be confirmed. The HIBP API itself has no licence requirement.
- **Cloudflare in front** (if adopted) terminates TLS and sees cookies. That is acceptable for synthetic data, but it must be listed in the data-flow and vendor inventory.

---

## LINKED ADR

- **ADR-0020** (to be amended): cookie names and prefixes, signed double-submit, ES256/PyJWT, the refresh-rotation algorithm, lifetimes, the revocation store, and the MFA decision.
- **ADR-0027**: the ASVS 3.3.3 deviation and the (possible) 6.3.3 deviation are recorded in `docs/security/asvs-l2-checklist.md`.
- **ADR-0021**: role changes trigger session revocation.

---

## SOURCES (all accessed 2026-09-26)

- OWASP ASVS 5.0.0: [V3 Web Frontend Security](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md), [V6 Authentication](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md), [V7 Session Management](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md), [V9 Self-contained Tokens](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x18-V9-Self-contained-Tokens.md), [official CSV](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv)
- [MDN: Set-Cookie (cookie prefixes)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [IETF datatracker: draft-ietf-httpbis-rfc6265bis (rev 22, RFC Ed Queue)](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/) and [draft-22 text](https://www.ietf.org/archive/id/draft-ietf-httpbis-rfc6265bis-22.html)
- [Chromium Intent to Implement and Ship: Http cookie prefix](https://groups.google.com/a/chromium.org/g/blink-dev/c/WsXlDO6oO2E/m/_sKy12M6AwAJ); [caniuse: `__Http-`/`__Host-Http-` prefixes](https://caniuse.com/mdn-http_headers_set-cookie_http_host-http_prefixes); [httpwg issue #2605 (localhost behaviour)](https://github.com/httpwg/http-extensions/issues/2605)
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [RFC 9700 OAuth 2.0 Security BCP §4.14](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [web.dev: Fetch Metadata resource isolation](https://web.dev/articles/fetch-metadata); [Filippo Valsorda: CSRF (Go 1.25 CrossOriginProtection)](https://words.filippo.io/csrf/)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html); [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [argon2-cffi parameters](https://argon2-cffi.readthedocs.io/en/stable/parameters.html), [argon2-cffi API](https://argon2-cffi.readthedocs.io/en/stable/api.html)
- [RFC 9864 Fully-Specified Algorithms for JOSE and COSE](https://www.rfc-editor.org/rfc/rfc9864.html); [joserfc RFC 9864 support](https://jose.authlib.org/en/rfc/9864/)
- [PyJWT changelog](https://pyjwt.readthedocs.io/en/stable/changelog.html), [PyJWT algorithms](https://pyjwt.readthedocs.io/en/stable/algorithms.html)
- GitHub Advisory Database API (`/advisories?ecosystem=pip&affects=pyjwt|joserfc|python-jose|argon2-cffi|fastapi`), e.g. [GHSA-xgmm-8j9v-c9wx (CVE-2026-48526)](https://github.com/advisories/GHSA-xgmm-8j9v-c9wx), [GHSA-752w-5fwx-jx9f (CVE-2026-32597)](https://github.com/advisories/GHSA-752w-5fwx-jx9f), [GHSA-gg9x-qcx2-xmrh (joserfc CVE-2026-49852)](https://github.com/advisories/GHSA-gg9x-qcx2-xmrh), [GHSA-6c5p-j8vq-pqhj (python-jose CVE-2024-33663)](https://github.com/advisories/GHSA-6c5p-j8vq-pqhj), [GHSA-8h2j-cgx8-6xv7 (FastAPI CSRF CVE-2021-32677)](https://github.com/advisories/GHSA-8h2j-cgx8-6xv7)
- PyPI JSON API (`https://pypi.org/pypi/<pkg>/json`) for PyJWT 2.15.0, joserfc 1.7.5, argon2-cffi 25.1.0, python-jose 3.5.0, limits 5.8.0, zxcvbn 4.5.0, pwdlib 0.3.1
- [FastAPI tutorial: OAuth2 with JWT (PyJWT, pwdlib)](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [limits strategies](https://limits.readthedocs.io/en/stable/strategies.html)
- [MDN: Clear-Site-Data](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data)
- [HIBP API v3 (Pwned Passwords range API)](https://haveibeenpwned.com/API/v3)

---

**Change log**: 2026-09-27: status updated to the spec v1.1 decisions (D-01, A-20); identifiers renamed for Ticketward.

**Document Version**: 1.1
**Next Update**: After the P9 argon2 benchmark
