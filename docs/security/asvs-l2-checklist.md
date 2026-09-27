# Ticketward: OWASP ASVS 5.0.0 Level 2 Checklist

| Field | Value |
|---|---|
| Document | `docs/security/asvs-l2-checklist.md` |
| Standard | **OWASP ASVS v5.0.0** (tag `v5.0.0`, released 2025-05-30), **Level 2** (includes all Level 1 requirements). Requirements are cited as `v5.0.0-<chapter>.<section>.<req>`; the tables below drop the prefix. Re-check for 5.0.1 at P9 and adopt it if released (spec §12) |
| Claim | "Targets OWASP ASVS 5.0 L2 **with documented exceptions**" (D-01; ADR-0027), quoted with the Met / N/A / Deferred counts, self-assessed, with the last verification date and commit |
| Version / date | 0.2 · 2026-09-27 (aligned to spec v1.1) |
| Owner | Akhil Mittapalli |
| Status | **Interim, hand-maintained.** From P9 this file is **generated** by `scripts/asvs_checklist.py` from the official CSV (SHA-256 pinned) merged with `docs/security/asvs-status.yaml`, and the `asvs-checklist` CI job fails if any L1/L2 row lacks a status or a Met row lacks evidence. The per-requirement decisions below are the seed for `asvs-status.yaml` |
| Related | [Threat model](threat-model.md) (controls `C-*`, tests `T-*`, exceptions §11) · [Audit events](audit-events.md) · [ADR-0027](../adr/ADR-0027-target-owasp-asvs-level-2.md) · [ADR-0040](../adr/ADR-0040-mfa-deferred-with-documented-asvs-exception.md) |

## How to use this checklist

* **One row per requirement** (L1 and L2 rows of the official CSV). The *Topic* column is a short paraphrase; read the
  requirement text in the standard.
* **Statuses** (spec §12):
  * `Met`: implemented and verified, with evidence.
  * `Partial`: implemented with a known, documented gap (usually an exception below).
  * `Deferred`: not done for v1, with a documented exception and compensating controls.
  * `N/A`: does not apply, with a justification.
  * `Pending` (interim only): planned and not yet verified. By the P9 checklist pass every applicable row must be
    Met, Partial or Deferred.
* **Evidence codes:** `T` automated test, `S` scanner report, `C` reviewed configuration, `D` documentation section,
  `M` dated manual record. Test IDs match the threat model's test register (§14). When a row becomes `Met`, link the
  passing artifact and the commit or CI run.
* **Phase** is the spec §16 phase in which the control is built. "**built in P0**" marks controls the scaffold
  already has; they stay `Pending` until their evidence is linked.
* **Review points:** P4, P5, P7, P8, P9 and P11 exits (ADR-0027). DoD-9 requires the generated checklist to be
  complete, with every exception recorded in `docs/security/risk-acceptances.md`.

## Scope of assessment

In scope: the Next.js frontend (browser and SSR server), the FastAPI API (public and internal listeners), the arq
worker and in-process models, the email-feed container, PostgreSQL + pgvector, Redis, Ollama, Caddy, the egress proxy,
the Compose configuration, the demo mode, the CI/CD release path, and backups.

Out of scope: third-party platforms (Anthropic, GitHub, HF Hub, Cloudflare, the host and storage providers) beyond
how we configure and call them; the offline ML notebooks, except their handling of secrets and data; the host OS,
except the assumptions in threat model §6.

## Summary

Counts are per requirement (L1 + L2 rows of the official v5.0.0 CSV). *Applicable* = everything that is not N/A.

| Chapter | L1+L2 | Applicable | Pending | Partial | Deferred | Met | N/A |
|---|---|---|---|---|---|---|---|
| V1 Encoding and Sanitization | 27 | 16 | 16 | 0 | 0 | 0 | 11 |
| V2 Validation and Business Logic | 11 | 11 | 11 | 0 | 0 | 0 | 0 |
| V3 Web Frontend Security | 19 | 19 | 18 | 1 | 0 | 0 | 0 |
| V4 API and Web Service | 10 | 4 | 4 | 0 | 0 | 0 | 6 |
| V5 File Handling | 9 | 6 | 6 | 0 | 0 | 0 | 3 |
| V6 Authentication | 35 | 22 | 20 | 1 | 1 | 0 | 13 |
| V7 Session Management | 18 | 15 | 15 | 0 | 0 | 0 | 3 |
| V8 Authorization | 7 | 6 | 6 | 0 | 0 | 0 | 1 |
| V9 Self-contained Tokens | 7 | 7 | 7 | 0 | 0 | 0 | 0 |
| V10 OAuth and OIDC | 29 | 0 | 0 | 0 | 0 | 0 | 29 |
| V11 Cryptography | 14 | 14 | 14 | 0 | 0 | 0 | 0 |
| V12 Secure Communication | 9 | 8 | 5 | 1 | 2 | 0 | 1 |
| V13 Configuration | 13 | 13 | 13 | 0 | 0 | 0 | 0 |
| V14 Data Protection | 9 | 9 | 9 | 0 | 0 | 0 | 0 |
| V15 Secure Coding and Architecture | 13 | 13 | 13 | 0 | 0 | 0 | 0 |
| V16 Security Logging and Error Handling | 16 | 16 | 16 | 0 | 0 | 0 | 0 |
| V17 WebRTC | 7 | 0 | 0 | 0 | 0 | 0 | 7 |
| **Total** | **253** | **179** | **173** | **3** | **3** | **0** | **74** |

With G-4 (TOTP + recovery codes), 6 MFA requirements (6.4.4, 6.5.1, 6.5.2, 6.5.3, 6.5.4, 6.5.5) become applicable: 185 applicable in total.

## Exceptions register

Spec §12.12. Each exception has a compensating control, a risk owner (the project owner) and a revisit trigger. From
P9 the same rows live in `docs/security/risk-acceptances.md`. Threat-model cross-references: §11 and the residual
risks in §15.

| ID | Exception / deviation | ASVS v5.0.0 | Rows affected | Reason | Compensating controls | Status | Revisit |
|---|---|---|---|---|---|---|---|
| EX-01 | **MFA deferred** (D-01; ADR-0040) | 6.3.3 (checked against the official v5.0.0 CSV; the spec still says "verify the number") | 6.3.3 | Owner decision: MFA after v1.0 (stretch goal G-4) | Short sessions (24 h / 60 min), per-account backoff + per-IP + global throttles, breached-password check, 15-character minimum, no public account creation, synthetic data only; demo accounts exempt in any case | Deferred | After v1.0 (G-4: TOTP for admin and ops_lead first); required before any real data |
| EX-02 | Refresh cookie `__Secure-tw_refresh` with `Path=/api/v1/auth` | 3.3.3 | 3.3.3 | `__Host-` requires `Path=/`; path scoping keeps the refresh token off all non-auth traffic | HttpOnly, Secure, SameSite=Strict, path-scoped, duplicate-cookie rejection, rotation with reuse detection | Partial | If a `Path=/` refresh design is adopted |
| EX-03 | Internal TLS on the single-host demo | 12.3.1–12.3.4 | 12.3.1 (Partial), 12.3.3–12.3.4 (Deferred); 12.3.2 is met by every TLS client | One host; certificates for every internal hop add cost for no network exposure | `internal: true` networks, no published ports except Caddy, host firewall, key-only SSH (threat model C-CRY-04) | Partial / Deferred | Required before any multi-host deployment |
| EX-04 | Demo-login pathway and shared demo accounts; no per-account lockout for demo users | 6.1.3 / 6.3.4; lockout (6.3.1) | 6.3.4 (Partial); 6.1.3 and 6.3.1 documented | Public demo usability (spec §24.3; ADR-0035) | Per-IP and global limits, optional Turnstile, 4 h sessions, privileged actions `DEMO_LOCKED`, nightly reset | Partial | When the demo is retired |
| EX-05 | Secrets manager and off-host logs, **if not in place by P9** | 13.3.1; 16.4.3 | 13.3.1, 16.4.3 (Pending until the P9 decision) | Tooling decided at P9 | Docker secrets (0400), gitleaks, no secrets in images; nightly encrypted off-host audit copy | Conditional | P9 decision |

The access cookie is `__Host-Http-tw_access` (A-30). Browsers that implement the `__Host-Http-` prefix (Chrome/Edge
≥ 140, Firefox ≥ 143; verify at build) also refuse a script-set cookie with that name; others still enforce the
`__Host-` rules, so 3.3.3 holds for it either way. The CSRF cookie `__Host-tw_csrf` is script-readable by design.

## V1 Encoding and Sanitization

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 1.1.1 | 2 | Decode/canonicalise input once, before validation | JSON parsed once by FastAPI/Pydantic; MIME decoded once in the email feed; sanitizer applies NFKC once before lexicons, detector and masking (C-VAL-06) | T: T-SEC-SANITIZER | P4 | Pending |
| 1.1.2 | 2 | Encode output last, at the interpreter | React escaping at render; SQLAlchemy bind parameters; JSON log renderer (C-INJ-01, C-WEB-05) | S: Semgrep; T: T-SEC-XSS-markdown | P4/P8 | Pending |
| 1.2.1 | 1 | Context-appropriate HTML/HTTP output encoding | React JSX escaping; react-markdown without raw HTML; API returns JSON only (C-WEB-05) | T: T-SEC-XSS-markdown | P8 | Pending |
| 1.2.2 | 1 | Encode untrusted data in built URLs | Frontend builds URLs with the URL API / `encodeURIComponent`; backend builds no URLs from user data; draft links limited to KB slugs | S: ESLint rule (proposed); T: T-GUARD-claims | P6/P8 | Pending |
| 1.2.3 | 1 | Encode data in generated JavaScript/JSON | JSON serialised by Pydantic/FastAPI only; no dynamic script generation; nonce CSP | T: T-SEC-HEADERS; S: Semgrep | P4/P8 | Pending |
| 1.2.4 | 1 | Parameterised database queries | C-INJ-01: SQLAlchemy only; raw SQL only in Alembic, parameterised | S: Semgrep "no raw SQL", Bandit B608 | P4 | Pending |
| 1.2.5 | 1 | OS command injection prevented | No shell execution with untrusted input; scripts use argument lists without `shell=True` | S: Bandit B602/B605, Semgrep | P4 | Pending |
| 1.2.6 | 2 | LDAP injection | No LDAP | — | — | N/A |
| 1.2.7 | 2 | XPath injection | No XPath | — | — | N/A |
| 1.2.8 | 2 | LaTeX injection | No LaTeX processing | — | — | N/A |
| 1.2.9 | 2 | Escape regex metacharacters from input | User input is never compiled into a regular expression; `re.escape` required if that changes | S: Semgrep rule (proposed) | P4 | Pending |
| 1.3.1 | 1 | Sanitise untrusted HTML with a vetted library | `nh3` on KB Markdown bodies and e-mail HTML (C-WEB-05) | T: T-SEC-XSS-markdown | P4/P5 | Pending |
| 1.3.2 | 1 | No eval / dynamic code execution | `eval`, `exec`, `new Function` banned (Semgrep, ESLint) | S: Semgrep, ESLint | P0/P4 | Pending |
| 1.3.3 | 2 | Sanitise data for dangerous contexts | Sanitizer and nonce tags before model prompts; PII masking before models and logs (C-VAL-06, C-LLM-01, C-PII-01) | T: T-SEC-SANITIZER, T-SEC-NONCE-tags | P4/P6 | Pending |
| 1.3.4 | 2 | User-supplied SVG | No user SVG is accepted or rendered; `nh3` strips `<svg>` from KB and e-mail HTML | — | — | N/A |
| 1.3.5 | 2 | Sanitise scriptable content (Markdown, CSS) | Markdown rendered without raw HTML; `nh3` on ingest; links limited to KB slugs (C-WEB-05) | T: T-SEC-XSS-markdown | P5/P8 | Pending |
| 1.3.6 | 2 | SSRF protection with allow-lists | No user-supplied URL is fetched; all egress through the egress-proxy allow-list; image optimizer off (C-CFG-04, C-WEB-07) | T: T-SEC-EGRESS, T-SEC-NEXT-hardening | P9 | Pending |
| 1.3.7 | 2 | Template injection | Templates never built from untrusted input; holding templates are approved KB docs filled only with allow-listed safe fields | T: template-field allow-list test (proposed) | P6 | Pending |
| 1.3.8 | 2 | JNDI injection | No Java/JNDI | — | — | N/A |
| 1.3.9 | 2 | Memcache injection | No memcache | — | — | N/A |
| 1.3.10 | 2 | Untrusted format strings | User input never used as a format string; logging uses structured key/values | S: Semgrep rule (proposed) | P4 | Pending |
| 1.3.11 | 2 | SMTP/IMAP injection | No mail system (S-01; T-NO-SEND static check) | — | — | N/A |
| 1.4.1 | 2 | Memory-safe string and buffer handling | First-party code is Python/TypeScript; native dependencies covered by V15 scanning | — | — | N/A |
| 1.4.2 | 2 | Integer overflow prevention | Memory-safe languages; bounds validated by Pydantic | — | — | N/A |
| 1.4.3 | 2 | Release of freed memory/resources | Memory-safe languages | — | — | N/A |
| 1.5.1 | 1 | Restrictive XML parser configuration | No XML parsing (`.eml` is MIME, parsed by the standard library) | — | — | N/A |
| 1.5.2 | 2 | Safe deserialisation of untrusted data | arq msgpack serializer, primitives only (no pickle); safetensors/GGUF only; `yaml.safe_load`; Pydantic JSON (C-CFG-05, C-SC-06) | T: T-SEC-REDIS-serializer; S: Semgrep bans pickle and unsafe loaders | P4 | Pending |

## V2 Validation and Business Logic

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 2.1.1 | 1 | Input validation rules documented | JSON Schemas (`schemas/json/`), Pydantic models and limits in `docs/api.md` | D: docs/api.md, schemas/json | P4 | Pending |
| 2.1.2 | 2 | Cross-field consistency rules documented | Feedback `corrected_value` vs field enum, citation index ranges, queue-override allow-list documented | D: docs/api.md | P4/P7 | Pending |
| 2.1.3 | 2 | Business limits documented (per user and global) | `docs/security/business-limits.md`: rate limits, quotas, frontier budget, job caps, demo quotas | D: business-limits.md | P7/P11 | Pending |
| 2.2.1 | 1 | Positive validation against expectations | Pydantic strict contracts (C-VAL-01) | T: T-CONTRACT-ticket, schemathesis | P4 | Pending |
| 2.2.2 | 1 | Validation at a trusted service layer | All validation in the API; client-side checks are UX only | T: schemathesis | P4 | Pending |
| 2.2.3 | 2 | Combinations of related items validated | Corrected values vs enums; queue override allow-list + τ_queue; citation index range | T: T-ROUTE-queue-allowlist, feedback tests | P6/P7 | Pending |
| 2.3.1 | 1 | Flows run in order without skipping steps | KB state machine, draft states, escalation states, activation before first login (C-BL-01, C-BL-04) | T: T-KB-workflow, T-SEC-APPROVE-preconditions | P5/P7 | Pending |
| 2.3.2 | 2 | Business limits enforced | Frontier budget, PII reveal 10/h, reprocess/regenerate limits, demo quotas (C-DOS-04, C-AZ-05, C-DOS-06) | T: T-SEC-FRONTIER-budget, T-SEC-PII-reveal-ratelimit, T-SEC-DEMO-quota | P7/P11 | Pending |
| 2.3.3 | 2 | Business operations are transactional | DB transactions around approve, escalate, KB approve and the purge functions; idempotency (C-VAL-03) | T: T-SEC-RACE-approve | P4/P6 | Pending |
| 2.3.4 | 2 | Locking against double use of limited resources | Atomic state transitions; one active rule set / production model (partial unique indexes); row lock on refresh rotation | T: T-SEC-RACE-approve, T-SEC-AUTH-refresh-reuse | P4/P6 | Pending |
| 2.4.1 | 2 | Anti-automation on expensive or abusable functions | Rate limits, login throttles, demo quotas, SSE caps (C-DOS-01, C-AUTH-02, C-DOS-06, C-DOS-03) | T: T-SEC-RATELIMIT, T-SEC-AUTH-ratelimit, T-SEC-SSE-limits | P4/P11 | Pending |

## V3 Web Frontend Security

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 3.2.1 | 1 | Prevent rendering in the wrong context | API CSP `default-src 'none'`, `nosniff`, CORP same-origin; JSON/problem+json only (C-WEB-03, C-WEB-04) | T: T-SEC-HEADERS | P4/P9 | Pending |
| 3.2.2 | 1 | Text rendered as text, not HTML | React text nodes; `dangerouslySetInnerHTML` banned (ESLint) | S: ESLint; T: T-SEC-XSS-markdown | P8 | Pending |
| 3.3.1 | 1 | Cookies Secure with `__Host-`/`__Secure-` prefix | `__Host-Http-tw_access`, `__Host-tw_csrf`, `__Secure-tw_refresh`, all Secure (C-AUTH-05) | T: T-SEC-COOKIE-flags | P4 | Pending |
| 3.3.2 | 2 | SameSite set per cookie purpose | Access Lax; CSRF Strict; refresh Strict | T: T-SEC-COOKIE-flags | P4 | Pending |
| 3.3.3 | 2 | `__Host-` prefix unless shared | Access (`__Host-Http-`, A-30) and CSRF cookies use `__Host-`. The refresh cookie uses `__Secure-` with `Path=/api/v1/auth`: documented deviation **EX-02** | T: T-SEC-COOKIE-flags; D: EX-02 | P4 | **Partial** |
| 3.3.4 | 2 | HttpOnly for non-script cookies | Access and refresh HttpOnly; CSRF cookie readable by design (double-submit) | T: T-SEC-COOKIE-flags | P4 | Pending |
| 3.4.1 | 1 | HSTS on all responses | `max-age=63072000; includeSubDomains` (C-WEB-04) | T: T-SEC-HEADERS | P9 | Pending |
| 3.4.2 | 1 | CORS allow-origin fixed or allow-listed | No CORS header is ever emitted; prod refuses CORS configuration; same-origin in dev too (C-WEB-06) | T: T-SEC-CORS-disabled | P8/P9 | Pending |
| 3.4.3 | 2 | Content-Security-Policy | Nonce CSP for the UI (`object-src 'none'`, `base-uri 'none'`, 128-bit nonce); API CSP; Caddy fallback (C-WEB-03) | T: T-SEC-HEADERS; E2E fresh nonce per navigation | P8/P9 | Pending |
| 3.4.4 | 2 | `nosniff` on all responses | C-WEB-04 | T: T-SEC-HEADERS | P9 | Pending |
| 3.4.5 | 2 | Referrer policy | `strict-origin-when-cross-origin` | T: T-SEC-HEADERS | P9 | Pending |
| 3.4.6 | 2 | `frame-ancestors` on every response | `frame-ancestors 'none'` in both CSPs and the fallback; `X-Frame-Options: DENY` on the API | T: T-SEC-HEADERS | P9 | Pending |
| 3.5.1 | 1 | CSRF defence not relying on preflight | Fetch Metadata → Origin → JSON/415 → signed session-bound double-submit (C-WEB-01) | T: T-SEC-CSRF-required, T-SEC-CSRF-fetch-metadata | P4 | Pending |
| 3.5.2 | 1 | No non-preflighted calls to sensitive functions | Unsafe requests with non-JSON bodies get 415 (**built in P0**), so simple cross-origin requests cannot reach them (C-WEB-02) | T: T-SEC-CONTENT-TYPE | P0/P4 | Pending |
| 3.5.3 | 1 | Sensitive functions use unsafe HTTP methods | No state change via GET/HEAD; Caddy 405 for non-GET/HEAD to Next.js | T: T-SEC-ROUTE-AUTH (method inventory), T-SEC-NEXT-hardening | P4/P9 | Pending |
| 3.5.4 | 2 | Separate applications on separate hostnames | UI and API are one application on one origin; Grafana/Tempo/Prometheus internal only (SSH tunnel) | C: Caddyfile review; T: T-SEC-EDGE-headers | P9 | Pending |
| 3.5.5 | 2 | postMessage origin and syntax checks | No first-party `message` listeners (ESLint rule, proposed); the Turnstile script handles its own iframe messages | S: ESLint rule (proposed) | P8 | Pending |
| 3.7.1 | 2 | Only supported, secure client technologies | Evergreen browsers; no plug-ins; `next` ≥ 16.3.6, React 19.3 | D: README browser support | P8 | Pending |
| 3.7.2 | 2 | No automatic redirect to foreign hosts | Post-login redirect limited to relative in-app paths | T: T-SEC-OPEN-REDIRECT (proposed) | P8 | Pending |

## V4 API and Web Service

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 4.1.1 | 1 | Correct Content-Type with charset | `application/json`, `application/problem+json`, `text/event-stream`, NDJSON export | T: T-SEC-HEADERS, schemathesis | P4 | Pending |
| 4.1.2 | 2 | Only user-facing endpoints redirect HTTP→HTTPS | (proposed) Caddy answers plain-HTTP `/api/*` with an error instead of redirecting; pages redirect; HSTS | T: T-SEC-EDGE-headers (proposed case) | P9 | Pending |
| 4.1.3 | 2 | Intermediary-set headers not user-overridable | Caddy overwrites `X-Real-IP` and strips `x-nonce`, `x-middleware-subrequest`, client CSP; API trusts `X-Real-IP` only from Caddy/web (C-CFG-07, C-WEB-07) | T: T-SEC-RATELIMIT-realip, T-SEC-EDGE-headers | P9 | Pending |
| 4.2.1 | 2 | Consistent HTTP message boundaries (no smuggling) | Caddy normalisation; uvicorn/h11; ambiguous `Content-Length`/`Transfer-Encoding` rejected | T: smuggling probes in `tests/e2e-stack/test_edge.py` (proposed) | P9 | Pending |
| 4.3.1 | 2 | GraphQL query cost limits | No GraphQL | — | — | N/A |
| 4.3.2 | 2 | GraphQL introspection off | No GraphQL | — | — | N/A |
| 4.4.1 | 1 | WebSocket over TLS | No WebSockets (SSE is used; covered by V2, V8, V16) | — | — | N/A |
| 4.4.2 | 2 | WebSocket handshake Origin check | No WebSockets | — | — | N/A |
| 4.4.3 | 2 | WebSocket session tokens | No WebSockets | — | — | N/A |
| 4.4.4 | 2 | WebSocket token bootstrap | No WebSockets | — | — | N/A |

## V5 File Handling

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 5.1.1 | 2 | Permitted file types and sizes documented | No HTTP upload. The simulated e-mail feed (`.eml`/`.json` in `data/email_feed/`) documents accepted types, per-file size cap and attachment handling | D: data/README.md | P4 | Pending |
| 5.2.1 | 1 | Only processable file sizes accepted | (proposed) Per-file size cap, MIME part and depth limits for the feed; KB bodies ≤ 1 MB via JSON | T: T-SEC-EML-malicious | P4 | Pending |
| 5.2.2 | 1 | File extension and content match | Feed accepts `.eml` and `.json` only, parsed and validated; attachments dropped, never stored | T: T-SEC-EML-malicious | P4 | Pending |
| 5.2.3 | 2 | Compressed-file limits | No archives accepted; attachments dropped unparsed | — | — | N/A |
| 5.3.1 | 1 | Stored files not executed | No uploaded or generated file is stored in a web-served folder | — | — | N/A |
| 5.3.2 | 1 | Internally generated file paths | Feed files moved to processed/quarantine under generated names; export filename generated server-side | T: T-SEC-EML-malicious | P4 | Pending |
| 5.4.1 | 2 | User filenames ignored; Content-Disposition set | `GET /admin/feedback/export` sets a server-generated filename from validated dates, never user input (C-AZ-08) | T: T-FEEDBACK-export | P7 | Pending |
| 5.4.2 | 2 | Served filenames encoded (RFC 6266) | Export filename restricted to `[A-Za-z0-9._-]` and quoted per RFC 6266 | T: T-FEEDBACK-export | P7 | Pending |
| 5.4.3 | 2 | Antivirus scan of untrusted files served | No files from untrusted sources are served; the export is generated from masked database rows | — | — | N/A |

## V6 Authentication

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 6.1.1 | 1 | Anti-automation and rate limiting documented | ADR-0020 and `docs/api.md`: per-IP, per-account and global limits, backoff, hard disable, demo exceptions | D: ADR-0020, docs/api.md | P4 | Pending |
| 6.1.2 | 2 | Context-specific word list documented | Context-word list (product, company, role names) documented and versioned | D: docs/api.md | P4 | Pending |
| 6.1.3 | 2 | All authentication pathways documented | Password login, activation, demo-login (demo only) and service tokens (internal listener) documented together (ADR-0020, ADR-0035; EX-04) | D: ADR-0020, ADR-0035 | P4/P11 | Pending |
| 6.2.1 | 1 | Minimum password length | 15 characters minimum (C-AUTH-07) | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 6.2.2 | 1 | Users can change their password | `POST /auth/change-password` (demo users: `DEMO_LOCKED`) | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 6.2.3 | 1 | Change requires current and new password | `{current_password, new_password}` | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 6.2.4 | 1 | Check against common passwords (top 3000+) | Bundled offline list always checked | T: T-SEC-AUTH-breached | P4 | Pending |
| 6.2.5 | 1 | No composition rules | None | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 6.2.6 | 1 | Password fields masked | `type=password` with a show-password toggle | T: E2E login spec | P8 | Pending |
| 6.2.7 | 1 | Paste and password managers allowed | No paste blocking; `autocomplete` attributes set | T: E2E login spec | P8 | Pending |
| 6.2.8 | 1 | Password verified exactly as received | No truncation or case change; length checked before hashing | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 6.2.9 | 2 | Passwords of 64+ characters allowed | Up to 128 characters | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 6.2.10 | 2 | No periodic rotation | No expiry; change on compromise or by the user | D: ADR-0020 | P4 | Pending |
| 6.2.11 | 2 | Context words blocked | Context-word check at set and change | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 6.2.12 | 2 | Breached-password check | Mandatory: offline list always; optional HIBP range API via the egress proxy (C-AUTH-07) | T: T-SEC-AUTH-breached | P4 | Pending |
| 6.3.1 | 1 | Credential-stuffing and brute-force controls | C-AUTH-02: per-IP 5/min and 50/day, per-account backoff, hard disable at 100, global breaker; demo accounts per-IP/global only (EX-04) | T: T-SEC-AUTH-ratelimit, T-SEC-AUTH-lockout-dos | P4 | Pending |
| 6.3.2 | 1 | No default accounts | No built-in or well-known accounts; users created by the seed script or admin API with generated secrets; demo role accounts exist only in demo mode | T: T-SEC-CONFIG-prod, T-SEC-DEMO-mode | P4/P11 | Pending |
| 6.3.3 | 2 | Multi-factor authentication | **Deferred (EX-01, D-01; ADR-0040)** with compensating controls; G-4 TOTP for admin and ops_lead first | D: EX-01, ADR-0040 | after v1.0 | **Deferred** |
| 6.3.4 | 2 | No undocumented pathways; consistent strength | Route inventory proves no undocumented pathway. Demo-login is a documented, weaker pathway in demo mode only (**EX-04**) | T: T-SEC-ROUTE-AUTH; D: EX-04 | P4/P11 | **Partial** |
| 6.4.1 | 1 | Initial secrets random, policy-compliant, expiring | Activation secrets from a CSPRNG, stored hashed, single use, 24 h TTL; the user sets the password under the normal policy (C-AUTH-12) | T: T-SEC-AUTH-activation | P4/P7 | Pending |
| 6.4.2 | 1 | No password hints or secret questions | None | D: ADR-0020 | P4 | Pending |
| 6.4.3 | 2 | Secure forgotten-password process | No self-service reset (no outbound e-mail, S-01). (proposed) The admin issues a new activation secret, which revokes the user's sessions and is audited; not yet defined in the spec | T: T-SEC-AUTH-activation (reset case, proposed) | P7 | Pending |
| 6.4.4 | 2 | Identity proofing for a lost MFA factor | No MFA factor in v1; applies with G-4 | — | — | N/A |
| 6.5.1 | 2 | Single-use lookup secrets / OTPs | No MFA in v1; applies with G-4 (TOTP + recovery codes) | — | — | N/A |
| 6.5.2 | 2 | Stored lookup secrets hashed | No MFA in v1; applies with G-4 recovery codes | — | — | N/A |
| 6.5.3 | 2 | MFA secrets from a CSPRNG | No MFA in v1; applies with G-4 | — | — | N/A |
| 6.5.4 | 2 | Lookup-secret entropy | No MFA in v1; applies with G-4 recovery codes | — | — | N/A |
| 6.5.5 | 2 | OTP lifetimes | No MFA in v1; applies with G-4 (TOTP) | — | — | N/A |
| 6.6.1 | 2 | PSTN OTP restrictions | No out-of-band or PSTN authentication (no outbound messaging by design) | — | — | N/A |
| 6.6.2 | 2 | OOB requests bound to the original request | No out-of-band authentication | — | — | N/A |
| 6.6.3 | 2 | OOB brute-force protection | No out-of-band authentication | — | — | N/A |
| 6.8.1 | 2 | No identity spoofing across IdPs | No external identity provider; users authenticate locally | — | — | N/A |
| 6.8.2 | 2 | IdP assertion signatures validated | No IdP assertions (JWT validation is covered in V9) | — | — | N/A |
| 6.8.3 | 2 | SAML assertions used once | No SAML | — | — | N/A |
| 6.8.4 | 2 | IdP authentication strength checks | No external identity provider | — | — | N/A |

## V7 Session Management

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 7.1.1 | 2 | Timeouts and lifetimes documented | 24 h absolute / 60 min idle (prod), 4 h / 60 min (demo), with rationale (ADR-0020) | D: ADR-0020 | P4 | Pending |
| 7.1.2 | 2 | Concurrent-session policy documented | ≤ 5 active families per user in prod, oldest evicted; demo accounts are shared (EX-04) | D: ADR-0020 | P4 | Pending |
| 7.1.3 | 2 | Federated session systems documented | No federation or SSO | — | — | N/A |
| 7.2.1 | 1 | Token verification in a trusted backend | FastAPI verifies every token; Next.js never authorizes (C-WEB-07) | T: T-SEC-JWT-validation | P4 | Pending |
| 7.2.2 | 1 | Dynamically generated session tokens | ES256 access JWT per session + opaque rotating refresh token | T: T-SEC-JWT-validation | P4 | Pending |
| 7.2.3 | 1 | Reference tokens unique and random (≥ 128 bits) | 256-bit CSPRNG refresh tokens stored as SHA-256 | T: T-SEC-AUTH-refresh-reuse | P4 | Pending |
| 7.2.4 | 1 | New session token on (re)authentication | Every login and demo-login creates a new session family and CSRF token | T: T-SEC-SESSIONS | P4 | Pending |
| 7.3.1 | 2 | Inactivity timeout | 60 min idle (`idle_expires_at`) | T: T-SEC-SESSIONS | P4 | Pending |
| 7.3.2 | 2 | Absolute session lifetime | 24 h (prod) / 4 h (demo), fixed at login | T: T-SEC-SESSIONS | P4 | Pending |
| 7.4.1 | 1 | Terminated sessions unusable | Logout revokes the family and writes the revoked `sid`; the next request is rejected (C-AUTH-06) | T: T-SEC-AUTH-sid-revocation | P4 | Pending |
| 7.4.2 | 1 | Disable/delete terminates all sessions | Disable, delete and role change revoke all families | T: T-SEC-AUTH-sid-revocation | P4/P7 | Pending |
| 7.4.3 | 2 | Option to end other sessions after a factor change | Password change revokes all other sessions automatically | T: T-SEC-AUTH-sid-revocation | P4 | Pending |
| 7.4.4 | 2 | Visible logout on authenticated pages | Logout in the app header | T: E2E | P8 | Pending |
| 7.4.5 | 2 | Admins can end sessions per user or for all | `POST /admin/users/{id}/sessions:revoke`, `/admin/sessions:revoke-all` (C-AUTH-11) | T: T-SEC-SESSIONS | P4/P7 | Pending |
| 7.5.1 | 2 | Re-authentication before sensitive attribute changes | Password change needs the current password; e-mail and role changes are admin-only and audited | T: T-SEC-AUTH-password-policy | P4 | Pending |
| 7.5.2 | 2 | View and terminate own sessions (with re-auth) | `GET /auth/sessions`; revoke with `{current_password}` (C-AUTH-11) | T: T-SEC-SESSIONS | P4 | Pending |
| 7.6.1 | 2 | RP/IdP session behaviour | No federation | — | — | N/A |
| 7.6.2 | 2 | Federated session creation needs user action | No federation | — | — | N/A |

## V8 Authorization

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 8.1.1 | 1 | Function- and data-level rules documented | RBAC matrix (spec §2, §11) and queue-membership scoping (ADR-0021) | D: ADR-0021, docs/api.md | P4 | Pending |
| 8.1.2 | 2 | Field-level rules documented | Role-specific response models; unmasked text only via the audited reveal | D: ADR-0021 | P4 | Pending |
| 8.2.1 | 1 | Function-level access restricted | C-AZ-01 deny by default | T: T-SEC-ROUTE-AUTH, T-SEC-RBAC-matrix | P4 | Pending |
| 8.2.2 | 1 | Data-level access restricted (IDOR) | C-AZ-02: 404 outside scope, 403 inside | T: T-SEC-IDOR-*, T-SEC-SSE-authz | P4 | Pending |
| 8.2.3 | 2 | Field-level access restricted (BOPLA) | Per-role response models; `extra="forbid"` | T: T-SEC-RBAC-matrix, schemathesis | P4 | Pending |
| 8.3.1 | 1 | Authorization at a trusted service layer | API services/repositories only; never the UI or `proxy.ts` (C-WEB-07) | T: T-SEC-RBAC-matrix, T-SEC-NEXT-hardening | P4/P8 | Pending |
| 8.4.1 | 2 | Cross-tenant controls | Single tenant (NG-05); `org_id` scoping exists but multi-tenancy is future scope | — | — | N/A |

## V9 Self-contained Tokens

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 9.1.1 | 1 | Signature validated before use | ES256 signature checked before any claim is used (C-AUTH-03, C-AUTH-08) | T: T-SEC-JWT-validation | P4 | Pending |
| 9.1.2 | 1 | Algorithm allow-list | ES256 only per verifier; `alg=none`, HS256-with-public-key and EdDSA rejected | T: T-SEC-JWT-validation | P4 | Pending |
| 9.1.3 | 1 | Keys from trusted pre-configured sources | Local key ring by `kid` (RFC 7638); `jku`/`jwk`/`x5u`/`x5c` rejected | T: T-SEC-JWT-validation | P4 | Pending |
| 9.2.1 | 1 | Validity period enforced | `exp`/`nbf`/`iat` with bounded leeway | T: T-SEC-JWT-validation | P4 | Pending |
| 9.2.2 | 2 | Token type/purpose checked | `typ=at+jwt` vs `typ=tw-svc+jwt`; each verifier rejects the other | T: T-SEC-JWT-validation, T-SEC-SVC-token-audience | P4 | Pending |
| 9.2.3 | 2 | Audience checked | `aud=tw-api` (user) vs `aud=tw-internal` (service) | T: T-SEC-SVC-token-audience | P4 | Pending |
| 9.2.4 | 2 | Audience restriction when keys are shared | Separate ES256 key sets per token family, plus distinct `aud` | T: T-SEC-SVC-token-audience | P4 | Pending |

## V10 OAuth and OIDC

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 10.1.1–10.7.3 (29 requirements) | 1–2 | Whole chapter | Ticketward implements no OAuth or OIDC role (client, resource server, authorization server or OpenID provider). Outbound API keys are static secrets (V13); GitHub Actions OIDC is CI configuration. Revisit if staff SSO is added. | — | — | N/A |

## V11 Cryptography

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 11.1.1 | 2 | Key-management policy and lifecycle | `crypto-inventory.md` + `rotate-secrets.md`: ES256 key rings, CSRF HMAC keys, KEK/DEKs (ADR-0037) | D: crypto-inventory.md | P4/P9 | Pending |
| 11.1.2 | 2 | Cryptographic inventory | `docs/security/crypto-inventory.md` (C-CRY-06) | D: crypto-inventory.md | P4 | Pending |
| 11.2.1 | 2 | Industry-validated implementations | `cryptography`, `argon2-cffi`, PyJWT with `cryptography`; no custom crypto | S: Semgrep; D: crypto inventory | P4 | Pending |
| 11.2.2 | 2 | Crypto agility | Versioned envelope with key ids; algorithm constants in one module; `kid` key rings | T: T-SEC-CRYPTO-* (rotation) | P4 | Pending |
| 11.2.3 | 2 | At least 128-bit security | AES-256-GCM, ECDSA P-256, SHA-256, HMAC-SHA256, 256-bit tokens, 128-bit nonces | D: crypto inventory | P4 | Pending |
| 11.3.1 | 1 | No insecure modes or padding | AEAD only; Semgrep bans non-AEAD modes | S: Semgrep | P4 | Pending |
| 11.3.2 | 1 | Approved ciphers and modes | AES-256-GCM | T: T-SEC-CRYPTO-* | P4 | Pending |
| 11.3.3 | 2 | Protection against ciphertext modification | AEAD with AAD binding ticket id, purpose and key id (C-CRY-01) | T: T-SEC-CRYPTO-* (bit flip, AAD swap) | P4 | Pending |
| 11.4.1 | 1 | Approved hash functions | SHA-256 family for security uses; the HIBP SHA-1 prefix is a protocol requirement of the range API, not a security use | S: Semgrep | P4 | Pending |
| 11.4.2 | 2 | Password hashing KDF | argon2id m=64 MiB, t=3, p=1 (C-AUTH-01) | T: T-SEC-AUTH-argon2 | P4 | Pending |
| 11.4.3 | 2 | Collision-resistant integrity hashes | SHA-256 for the audit chain, content hashes, GGUF digests, refresh-token hashes | T: T-SEC-AUDIT-chain-verify | P4 | Pending |
| 11.4.4 | 2 | Key stretching when deriving keys from passwords | The app derives no keys from passwords; only restic does, with its own KDF (verify at P9) | D: crypto inventory | P9 | Pending |
| 11.5.1 | 2 | CSPRNG for non-guessable values | `secrets`/`os.urandom`; Semgrep bans `random`/`uuid4` for secrets; 128-bit CSP nonces, not `randomUUID()` | S: Semgrep | P4/P8 | Pending |
| 11.6.1 | 2 | Approved algorithms for keys and signatures | ECDSA P-256 (ES256) via `cryptography`; EdDSA identifier rejected (RFC 9864) | T: T-SEC-JWT-validation | P4 | Pending |

## V12 Secure Communication

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 12.1.1 | 1 | Only current TLS versions | Caddy defaults (TLS 1.2+, 1.3 preferred) (C-CRY-02) | T: T-SEC-TLS | P9/P11 | Pending |
| 12.1.2 | 2 | Recommended cipher suites | Caddy defaults; confirmed by a TLS scan at P11 | T: T-SEC-TLS | P11 | Pending |
| 12.1.3 | 2 | mTLS client certificates validated | No mTLS client certificates | — | — | N/A |
| 12.2.1 | 1 | TLS for all external HTTP connectivity | HTTPS only at the edge; HSTS; plain HTTP only for ACME and the redirect | T: T-SEC-TLS, T-SEC-HEADERS | P9 | Pending |
| 12.2.2 | 1 | Publicly trusted certificates | Let's Encrypt (ZeroSSL fallback) via Caddy | T: T-SEC-TLS | P11 | Pending |
| 12.3.1 | 2 | TLS for all inbound and outbound connections | Edge and outbound connections use TLS; internal hops on the single host are plaintext: documented deviation **EX-03** | D: EX-03 | P9 | **Partial** |
| 12.3.2 | 2 | TLS clients validate certificates | Every TLS client validates (Semgrep bans `verify=False`); listed under EX-03 by the spec for completeness | S: Semgrep; T: T-SEC-EGRESS | P9 | Pending |
| 12.3.3 | 2 | TLS between internal HTTP services | **Deferred (EX-03):** single-host demo; required before any multi-host deployment | D: EX-03 | multi-host | **Deferred** |
| 12.3.4 | 2 | Trusted certificates for internal TLS | **Deferred (EX-03)** together with 12.3.3 | D: EX-03 | multi-host | **Deferred** |

## V13 Configuration

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 13.1.1 | 2 | Communication needs documented | Threat model §5 (DFD, flows), egress allow-list (ADR-0036), networks (ADR-0026) | D: threat-model.md §5 | P9 | Pending |
| 13.2.1 | 2 | Backend components authenticate | Postgres role passwords; Redis ACL user; service JWT; Ollama unauthenticated but internal only (compensating) | T: T-SEC-DB-roles, T-SEC-REDIS-auth, T-SEC-SVC-token-audience | P4/P9 | Pending |
| 13.2.2 | 2 | Least privilege for backend communication | Four DB roles (C-CFG-08); Redis ACL limits (proposed); non-root containers | T: T-SEC-DB-roles | P4/P9 | Pending |
| 13.2.3 | 2 | No default service credentials | Generated secrets (`gen_dev_secrets.py`; SOPS in deployment); prod refuses placeholders and short secrets | T: T-SEC-CONFIG-prod | P0/P4 | Pending |
| 13.2.4 | 2 | Allow-list of external systems | Egress allow-list in `infra/egress-proxy/` (ADR-0036) | T: T-SEC-EGRESS | P9 | Pending |
| 13.2.5 | 2 | Server configured with the allow-list | Enforced by the egress proxy; app containers have no internet route | T: T-SEC-EGRESS, T-SEC-COMPOSE-policy | P9 | Pending |
| 13.3.1 | 2 | Secrets-management solution | SOPS + age → Docker secrets (0400) with a rotation runbook; **EX-05** if not in place by P9 | C: deployment review | P9 | Pending |
| 13.3.2 | 2 | Least privilege for secrets | Each container mounts only its own secrets; the KEK only in API and worker; restic password and age key off the VM | C: compose review | P9 | Pending |
| 13.4.1 | 1 | No source-control metadata deployed | Images built from a clean context (`.dockerignore` excludes `.git`) | C: image inspection | P9 | Pending |
| 13.4.2 | 2 | Debug off in production | `TW_ENV` defaults to `prod`; prod refuses debug (**built in P0**); `OLLAMA_DEBUG` off | T: T-SEC-CONFIG-prod | P0/P4 | Pending |
| 13.4.3 | 2 | No directory listings | No file browsing in Caddy | T: T-SEC-EDGE-headers | P9 | Pending |
| 13.4.4 | 2 | TRACE not supported | Apps return 405; Caddy 405 for non-GET/HEAD to web | T: T-SEC-EDGE-headers | P9 | Pending |
| 13.4.5 | 2 | Docs and monitoring endpoints not exposed | Swagger/OpenAPI off in prod and demo; `/api/v1/metrics`, `/api/docs*`, `/api/openapi.json` 404 at the edge; Prometheus on internal ports | T: T-SEC-EDGE-headers, T-SEC-CONFIG-prod | P9 | Pending |

## V14 Data Protection

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 14.1.1 | 2 | Sensitive data identified and classified | Classes D1–D4 (threat model §2.4) | D: threat-model.md §2.4 | P9 | Pending |
| 14.1.2 | 2 | Protection requirements per level | Handling rules per class; retention per spec §10 | D: threat-model.md §2.4 | P9 | Pending |
| 14.2.1 | 1 | No sensitive data in URLs | Ids and opaque cursors only; search term dropped from access logs; tokens never in URLs | T: T-SEC-LOG-redaction | P4/P9 | Pending |
| 14.2.2 | 2 | No sensitive data in server caches | `Cache-Control: no-store` on ticket data; server-only DAL with `no-store` | T: T-SEC-HEADERS, T-SEC-NEXT-hardening | P4/P8 | Pending |
| 14.2.3 | 2 | No sensitive data to untrusted parties | No trackers; masked text only to the frontier (C-LLM-08); Langfuse off in the demo; egress allow-list | T: T-SEC-EGRESS, T-SEC-PII-residual-gate | P7/P9 | Pending |
| 14.2.4 | 2 | Data controls implemented (encryption, retention, logging, access) | C-CRY-01, C-CRY-05, C-DATA-02..04, C-PII-01..03 | T: T-SEC-DB-no-plaintext, T-RETENTION-shred, T-SEC-CRYPTO-shred, T-DELETE-purge | P4/P9 | Pending |
| 14.3.1 | 1 | Client data cleared after session end | `Clear-Site-Data: "cache", "storage"` on logout; query cache cleared (C-WEB-08) | T: E2E-storage-hygiene | P8 | Pending |
| 14.3.2 | 2 | Anti-caching headers | `Cache-Control: no-store` on API responses with ticket data | T: T-SEC-HEADERS | P4 | Pending |
| 14.3.3 | 2 | No sensitive data in browser storage | No tokens or PII in localStorage/sessionStorage/IndexedDB | T: E2E-storage-hygiene | P8 | Pending |

## V15 Secure Coding and Architecture

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 15.1.1 | 1 | Remediation time frames documented | SECURITY.md: `next` within 72 h of a critical/high advisory; (proposed) CRITICAL ≤ 7 d, HIGH ≤ 30 d for other components (C-OPS-03) | D: SECURITY.md | P8/P9 | Pending |
| 15.1.2 | 2 | SBOM maintained | CycloneDX SBOM via syft attached to releases | S: release.yml | P9 | Pending |
| 15.1.3 | 2 | Resource-demanding functions documented | `docs/security/business-limits.md`: triage, retrieval, NLI, detector, frontier, export, regenerate | D: business-limits.md | P7/P9 | Pending |
| 15.2.1 | 1 | Components within remediation time frames | Dependabot, pip-audit, `pnpm audit`, Trivy gates (C-SC-02) | S: security.yml | P9 | Pending |
| 15.2.2 | 2 | Defences for resource-demanding functions | Rate limits, backpressure, job caps, stage timeouts, frontier budget (C-DOS-01..06) | T: T-SEC-RATELIMIT, T-PIPE-timeouts, T-SEC-FRONTIER-budget | P4/P7 | Pending |
| 15.2.3 | 2 | Only required functionality in production | No Swagger, debug or test routes in prod; demo-login only in demo mode; no Server Actions; image optimizer off | T: T-SEC-CONFIG-prod, T-SEC-ROUTE-AUTH | P4/P9 | Pending |
| 15.3.1 | 1 | Only required fields returned | `response_model` on every route; role-specific models | T: T-SEC-RBAC-matrix, schemathesis | P4 | Pending |
| 15.3.2 | 2 | Outbound calls do not follow redirects unless intended | `core/http.py` clients disable redirects except where documented (HF downloads) | T: T-NO-SEND static test (client settings, proposed) | P4/P9 | Pending |
| 15.3.3 | 2 | Mass-assignment countermeasures | `extra="forbid"`; explicit update models (C-VAL-01) | T: schemathesis | P4 | Pending |
| 15.3.4 | 2 | Original client IP from trusted fields | Caddy sets `X-Real-IP`; the API trusts it only from Caddy/web (C-CFG-07) | T: T-SEC-RATELIMIT-realip | P9 | Pending |
| 15.3.5 | 2 | Strict typing and comparisons | Pydantic strict; `mypy --strict`; TypeScript strict; constant-time comparison for secrets | S: mypy, tsc | P0/P4 | Pending |
| 15.3.6 | 2 | Prototype-pollution prevention | No merging of untrusted objects into plain objects; `Map`/`Set` for dynamic keys; ESLint rules | S: ESLint | P8 | Pending |
| 15.3.7 | 2 | HTTP parameter pollution | Duplicate query parameters and duplicate cookie names rejected or handled deterministically (C-AUTH-05) | T: T-SEC-DUP-cookie, schemathesis | P4 | Pending |

## V16 Security Logging and Error Handling

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 16.1.1 | 2 | Logging inventory | `docs/security/logging-inventory.md` + [audit events](audit-events.md) | D: logging-inventory.md | P4/P9 | Pending |
| 16.2.1 | 2 | Log metadata (when, where, who, what) | UTC timestamp, request_id, trace_id, actor, route, outcome | T: T-SEC-LOG-redaction (field presence) | P4 | Pending |
| 16.2.2 | 2 | Synchronised time, UTC | Host NTP; UTC timestamps | C: host-hardening runbook | P9 | Pending |
| 16.2.3 | 2 | Logs only to documented sinks | stdout → Docker `local` driver → Collector → off-host sink; audit in Postgres + off-host copy | D: logging-inventory.md | P9 | Pending |
| 16.2.4 | 2 | Common, parseable log format | JSON logs (structlog); OTLP | T: T-SEC-LOG-redaction | P4 | Pending |
| 16.2.5 | 2 | Logging respects data protection levels | Redaction keys, regex scrubber, Collector allow-list; ticket text never logged (C-PII-03) | T: T-SEC-LOG-redaction | P4 | Pending |
| 16.3.1 | 2 | All authentication operations logged | Login success/failure, refresh, logout, activation, demo-login, session revoke ([audit events](audit-events.md)) | T: T-AUDIT-coverage | P4 | Pending |
| 16.3.2 | 2 | Failed authorization logged | 403 and out-of-scope 404 counted as security events; `DEMO_LOCKED` denials logged | T: T-SEC-METRICS-events | P4 | Pending |
| 16.3.3 | 2 | Documented security events and bypass attempts logged | CSRF failures, 413/415, rate limits, injection suspected, egress denials | T: T-SEC-METRICS-events | P4/P9 | Pending |
| 16.3.4 | 2 | Unexpected errors and control failures logged | Unhandled exceptions (without PII), masking failures, model integrity failures, revocation-check failures | T: T-SEC-ERRORS, T-SEC-METRICS-events | P4 | Pending |
| 16.4.1 | 2 | Log encoding against injection | JSON renderer; request-id validation (proposed) (C-INJ-02) | T: T-SEC-LOG-injection | P4 | Pending |
| 16.4.2 | 2 | Logs protected from access and modification | Audit append-only + hash chain + checkpoints (C-AUD-02); log volumes not exposed; Grafana internal | T: T-SEC-AUDIT-append-only, T-SEC-AUDIT-chain-verify | P4/P9 | Pending |
| 16.4.3 | 2 | Logs sent to a logically separate system | Off-host shipping of security and audit events (service chosen at P9); minimum nightly encrypted off-host copy; **EX-05** if not in place | C: P9 review | P9 | Pending |
| 16.5.1 | 2 | Generic error messages | RFC 9457 generic `INTERNAL` 500 with relative type URIs (**built in P0**) | T: T-SEC-ERRORS | P0/P4 | Pending |
| 16.5.2 | 2 | Secure operation when external resources fail | Circuit breakers; local fallback when the frontier fails; offline breached list when HIBP fails; P7 on model failure | T: T-PIPE-timeouts, T-SEC-FRONTIER-budget | P4/P7 | Pending |
| 16.5.3 | 2 | Fail securely, no fail-open | Fail closed on masking, revocation-check, schema and verifier failures (A10:2025 controls) | T: T-SEC-PII-fail-closed, T-SEC-AUTH-sid-revocation, T-SCHEMA-gate | P4 | Pending |

## V17 WebRTC

| Req | L | Topic | Ticketward control | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|---|
| 17.1.1–17.3.2 (7 requirements) | 1–2 | Whole chapter | No WebRTC, TURN or media handling (NG-06: voice and chat channels are metadata only). | — | — | N/A |

---

## Beyond ASVS: LLM-specific controls (PR-003)

ASVS does not cover LLM-specific risks. These rows track the OWASP Top 10 for LLM Applications **2026** (2025 IDs in
brackets; three 2026 IDs are UNVERIFIED, see [threat model §10](threat-model.md)). They are not counted in the ASVS
totals.

| ID | OWASP LLM 2026 [2025] | Ticketward controls | Evidence (planned) | Phase | Status |
|---|---|---|---|---|---|
| LLM01 | Prompt Injection [LLM01] | C-LLM-03 (primary), C-VAL-06, C-LLM-01, C-LLM-02, C-LLM-04, C-LLM-05, C-LLM-07, C-LLM-11, C-LLM-13 | T-SEC-INJ-suite (M-13 static and adaptive rows), T-POLICY-forced, T-POLICY-P0 | P6 | Pending |
| LLM02 | Sensitive Information Disclosure [LLM02] | C-PII-01..04, C-LLM-08, C-DATA-01, C-CFG-04 | T-PII-recall, T-SEC-PII-*, T-SEC-LOG-redaction | P4/P7 | Pending |
| LLM03 | Excessive Agency [LLM06] | C-LLM-05, C-LLM-11 | T-NO-SEND, T-SEC-FRONTIER-no-tools | P6/P7 | Pending |
| LLM04 | Supply Chain [LLM03] | C-SC-01..08 | T-SEC-MODEL-sha-mismatch, Semgrep, licence records | P3/P9 | Pending |
| LLM05 | Data and Model Poisoning [LLM04] (ID UNVERIFIED) | C-DATA-01, C-LLM-14, C-AZ-04, C-AUD-04, C-LLM-13; no auto-retraining (NG-08) | Leakage CI job, T-DATA-provenance, T-FEEDBACK-export, T-SEC-KB-four-eyes | P1/P7 | Pending |
| LLM06 | Unbounded Consumption [LLM10] | C-DOS-01..06, C-LLM-12 | T-SEC-FRONTIER-budget, T-SEC-RATELIMIT, T-SEC-DEMO-quota, T-PIPE-timeouts | P4/P11 | Pending |
| LLM07 | Misinformation [LLM09] (ID UNVERIFIED) | C-LLM-06; abstention A1–A4 | T-GUARD-claims, M-06, M-07b | P6 | Pending |
| LLM08 | Hidden Context Exposure [LLM07] | C-LLM-10 | T-SEC-INJ-echo | P6 | Pending |
| LLM09 | Vector and Embedding Weaknesses [LLM08] (ID UNVERIFIED) | C-LLM-07 | T-RET-approved-only, T-SEC-TENANT-filter | P5 | Pending |
| LLM10 | Improper Output Handling [LLM05] | C-LLM-02, C-LLM-09, C-WEB-05, C-WEB-03 | T-SEC-XSS-markdown, T-ROUTE-queue-allowlist | P6/P8 | Pending |

---

## v1.0 gap register: resolution in spec v1.1

| Gap | Area | v1.0 description | Resolution in v1.1 | Rows |
|---|---|---|---|---|
| G-01 | 6.3.3 | MFA not in v1 scope | Owner decision D-01: documented exception EX-01 (ADR-0040) | 6.3.3 |
| G-02 | 7.3 | No absolute lifetime or idle timeout | 24 h / 60 min (prod), 4 h / 60 min (demo) | 7.1.1, 7.3.1, 7.3.2 |
| G-03 | 7.4 | Access JWT valid after logout | `sid` claim + Redis revocation set, fail closed | 7.4.1, 7.4.2 |
| G-04 | 12.3 | Internal connections unencrypted | Documented deviation EX-03 | 12.3.1–12.3.4 |
| G-05 | 6.2 | Breached-password check optional, egress not allowed | Mandatory check (offline list; optional HIBP via the egress proxy) | 6.2.4, 6.2.12 |
| G-06 | 3.4 | CSP lacked `object-src 'none'` | Added (A-24); `style-src-attr 'unsafe-inline'` accepted (RR-07) | 3.4.3 |
| G-07 | 13.2 / 1.5 | Redis auth and job serialisation unspecified | Redis ACL + password; msgpack serializer (A-25(c)) | 1.5.2, 13.2.1 |
| G-08 | 8.1 / 8.2 | No queue-membership model | `user_queue_memberships` (A-25(b)) | 8.1.1, 8.2.2 |
| G-09 | 13.2 | Egress allow-list not enforced | Egress proxy, no internet route (A-25(d), ADR-0036) | 13.2.4, 13.2.5 |
| G-10 | 4.1 | No 415 code | `UNSUPPORTED_MEDIA_TYPE` 415 (**built in P0**) | 3.5.2 |
| G-11 | 7.5 | No session list/revoke | `GET /auth/sessions` + revoke with re-authentication | 7.5.2 |
| G-12 | 16.4 | Audit chain across partitions unspecified | `audit_chain_checkpoints` + off-host exports (A-25(b)) | 16.4.2 |

## Open gaps (v1.1)

| Gap | Rows | Description | Proposed resolution | Owner / by |
|---|---|---|---|---|
| G-13 | 6.4.3 | No defined forgotten-password flow (no outbound e-mail) | Admin re-issues an activation secret; sessions revoked; audited | Owner, P7 (spec addition) |
| G-14 | 4.1.2 | Caddy's automatic HTTP→HTTPS redirect also applies to `/api/*` | Answer plain-HTTP API requests with an error instead of redirecting | Owner, P9 |
| G-15 | 16.4.1 | `X-Request-ID` validation not specified | Validate format or generate server-side | Owner, P4 |
| G-16 | 2.4.1 | No per-user total SSE cap | Add a per-user stream cap and maximum duration | Owner, P4 |
| G-17 | 11.4.4 | restic's key derivation not recorded | Record it in the crypto inventory (verify) | Owner, P9 |

## Sign-off

| Review point | Date | Reviewer | Met / Partial / Deferred / N/A | Notes |
|---|---|---|---|---|
| P4 exit | — | — | — | — |
| P7 exit | — | — | — | — |
| P9 exit (generated checklist) | — | — | — | `asvs-checklist` CI job green |
| P11 (release) | — | — | — | DoD-9 |
