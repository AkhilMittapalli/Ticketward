# OWASP ASVS 5.0 Level 2 - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Resolved (version, structure, what changed, applicability and evidence plan are all answered). Spec v1.1 adjudicated the L2 gaps (A-21). MFA is a documented exception by owner decision D-01.
**Category**: Security / Compliance baseline
**Linked ADR(s)**: ADR-0027 (target ASVS L2); related ADR-0020, ADR-0023, ADR-0024, ADR-0026
**Spec sections**: §4 PR-002, §12 (all subsections), §14.3 (security tests), §14.5 (CI), §15, §16 P9, §19 DoD-9, §21, §22, §23

---

## EXECUTIVE SUMMARY

- **Version.** The current stable version is **OWASP ASVS 5.0.0**, dated May 2025 and released live at Global AppSec EU Barcelona (2025-05-30). No later stable release exists as of 2026-09-26. The repository names the **5.0.1 patch** as the next target, and `master` is the "bleeding edge". Cite requirements as `v5.0.0-<chapter>.<section>.<req>`.
- **Size and structure.** 17 chapters (V1-V17) and **345 requirements**: 70 at L1, 183 at L2, 92 at L3. These counts come from the official 5.0.0 CSV. Levels are cumulative, so an **L2 claim covers 253 requirements** (L1 + L2).
- **What changed from 4.0.3.**
  - Only 11 of 286 v4 requirements are unchanged, and every ID is renumbered.
  - The standard now states security goals rather than prescribing mechanisms.
  - Documentation requirements are explicit and appear first in each chapter.
  - New chapters: Web Frontend Security, Self-contained Tokens, OAuth/OIDC, WebRTC, Secure Coding and Architecture. The v4 Architecture chapter is gone.
  - L1 shrank from 128 to 70 requirements.
  - CWE/NIST mappings are removed from the main text.
- **Applicability to Ticketward.** About **176 of the 253** L1+L2 requirements apply (181 if MFA is built). V10 OAuth/OIDC, V17 WebRTC, GraphQL, WebSocket, IdP/federation, file upload and legacy-injection items are N/A, each with a rationale. **15 of the 17 chapters apply at least partially.**
- **Material L2 gaps in the spec as written** (details in "SPEC IMPACT"):
  - MFA (6.3.3);
  - mandatory breached-password check (6.2.12);
  - documented and enforced session timeouts (7.1.1, 7.3.x);
  - immediate revocation and session self-service (7.4.x, 7.5.2);
  - the `__Host-` rule for the refresh cookie (3.3.3);
  - `object-src 'none'` missing from the CSP (3.4.3);
  - internal service-to-service TLS (12.3.1-12.3.4);
  - a real secrets manager (13.3.1);
  - off-host log shipping (16.4.3);
  - arq's default pickle serialisation (1.5.2);
  - several missing documentation artefacts (crypto inventory, comms inventory, logging inventory, data classification, remediation SLA).
- **Evidence plan.** Generate `docs/security/asvs-l2-checklist.md` from the official CSV, so IDs and text are never retyped. Every applicable row needs at least one evidence item from five types: an automated test, a scanner or CI report, a config file, a documentation section, or a dated manual verification record. "Deferred" requires a written risk acceptance with compensating controls. The README's L2 claim must quote the met, N/A and deferred counts.

---

## QUESTIONS

1. Which ASVS version is current, and how should we cite it?
2. What is its chapter structure, and how many requirements are there per level?
3. What changed in 5.0 compared with 4.0.3?
4. Which chapters and requirements apply at L2 to this system (FastAPI + Next.js + Postgres/Redis + LLM workers, single VM)?
5. What evidence will prove each requirement, and who produces it in which phase?
6. (Derived) Where does the spec, as written, fall short of L2?
7. (Related, spec §12.3) Is there an OWASP Top 10 2025 edition to map to?

---

## FINDINGS

### F1. Version and release (accessed 2026-09-26)

- The GitHub README (`OWASP/ASVS`, master) and the OWASP project page both state the latest stable version is **5.0.0, dated May 2025**, "released live on stage at Global AppSec EU Barcelona 2025". The GitHub release `v5.0.0_release` was published **2025-05-30** (GitHub API). The Frontispiece reads "Version 5.0.0, May 2025". The licence is CC BY-SA 4.0.
- The README names the next release target as a patch, **5.0.1**. The `master` branch holds in-progress changes, and the GitHub "latest" pre-release is rebuilt automatically from it (last recreated 2026-09-03). **Pin to the `v5.0.0` tag, not `master`.**
- **Citation format:** `v<version>-<chapter>.<section>.<requirement>`, e.g. `v5.0.0-3.3.3`.
- **Machine-readable exports** in `5.0/docs_en/`: CSV (columns `chapter_id, chapter_name, section_id, section_name, req_id, req_description, L`), JSON, flat JSON, XML, CycloneDX JSON, DOCX, plus "legacy" (tick-mark) variants.

### F2. Structure and counts (computed from the official v5.0.0 CSV)

| Ch | Name | Sections | L1 | L2 | L3 | L1+L2 |
|---|---|---|---|---|---|---|
| V1 | Encoding and Sanitization | Architecture; Injection Prevention; Sanitization; Memory/String/Unmanaged Code; Safe Deserialization | 8 | 19 | 3 | 27 |
| V2 | Validation and Business Logic | Documentation; Input Validation; Business Logic Security; Anti-automation | 4 | 7 | 2 | 11 |
| V3 | Web Frontend Security | Documentation; Unintended Content Interpretation; Cookie Setup; Browser Security Mechanism Headers; Browser Origin Separation; External Resource Integrity; Other | 8 | 11 | 12 | 19 |
| V4 | API and Web Service | Generic Web Service; HTTP Message Structure; GraphQL; WebSocket | 2 | 8 | 6 | 10 |
| V5 | File Handling | Documentation; Upload and Content; Storage; Download | 4 | 5 | 4 | 9 |
| V6 | Authentication | Documentation; Password Security; General; Factor Lifecycle and Recovery; General MFA; Out-of-Band; Cryptographic; Identity Provider | 13 | 22 | 12 | 35 |
| V7 | Session Management | Documentation; Fundamentals; Timeout; Termination; Defenses Against Session Abuse; Federated Re-authentication | 6 | 12 | 1 | 18 |
| V8 | Authorization | Documentation; General Design; Operation Level; Other | 4 | 3 | 6 | 7 |
| V9 | Self-contained Tokens | Token source and integrity; Token content | 4 | 3 | 0 | 7 |
| V10 | OAuth and OIDC | Generic; Client; Resource Server; Authorization Server; OIDC Client; OpenID Provider; Consent | 5 | 24 | 7 | 29 |
| V11 | Cryptography | Inventory and Documentation; Implementation; Encryption Algorithms; Hashing; Random Values; Public Key; In-Use Data | 3 | 11 | 10 | 14 |
| V12 | Secure Communication | General TLS; HTTPS to External Services; Service-to-Service | 3 | 6 | 3 | 9 |
| V13 | Configuration | Documentation; Backend Communication; Secret Management; Unintended Information Leakage | 1 | 12 | 8 | 13 |
| V14 | Data Protection | Documentation; General; Client-side | 2 | 7 | 4 | 9 |
| V15 | Secure Coding and Architecture | Documentation; Architecture and Dependencies; Defensive Coding; Safe Concurrency | 3 | 10 | 8 | 13 |
| V16 | Security Logging and Error Handling | Documentation; General Logging; Security Events; Log Protection; Error Handling | 0 | 16 | 1 | 16 |
| V17 | WebRTC | TURN Server; Media; Signaling | 0 | 7 | 5 | 7 |
| **Total** | | | **70** | **183** | **92** | **253** |

The "What is the ASVS" chapter describes the levels this way:

- **L1** is the minimum starting point, about 20% of the requirements.
- **L2** is the target for most applications. Complying with it means implementing roughly 70% of all requirements (all of L1 plus L2).
- **L3** adds defence in depth.
- Documentation requirements sit in the first section of each chapter.

### F3. What changed from 4.0.3 to 5.0 ("For Users of 4.0" chapter, paraphrased)

- **Requirements.** v4.0.3 had 286.
  - Only **11** survive unchanged, and **15** received only grammatical edits.
  - **109 (38%)** are no longer separate requirements: 50 deleted, 28 removed as duplicates, 31 merged.
  - The rest were substantively rewritten.
  - **All IDs changed**, even for unmodified text, because the chapters were reordered. v5 uses plain numbers, and a "legacy" tick-mark export is kept for compatibility.
- **Philosophy.** Requirements now state security goals and name a mechanism only when it is the sole practical solution. Implicit "analysis" expectations became explicit **documentation requirements**.
- **Structure.** New chapters: OAuth and OIDC, WebRTC, Self-contained Tokens (split out of session management), Web Frontend Security, Secure Coding and Architecture. The **V1 Architecture chapter was removed**, and input validation moved next to business logic (V2).
- **Mappings.** Direct CWE/NIST mappings are gone from the main body. Future alignment is planned through OWASP CRE. A two-way v4↔v5 mapping is published separately and may change independently of releases.
- **Levels.** L1 shrank from 128 (46%) to **70 (20%)**. Level placement is now based on risk reduction and implementation effort rather than on black-box testability.

**Consequence for this project.** Any 4.0.3-based checklist, blog template or scanner rule set is not reusable as-is. Build the checklist from the v5.0.0 CSV (D2).

### F4. L2 items that most affect this architecture (paraphrased, with levels)

- **V3 frontend:**
  - 3.3.1-3.3.4: cookie `Secure`, prefixes, SameSite, HttpOnly.
  - 3.4.1: HSTS >= 1 year, with subdomains at L2.
  - 3.4.3: a global CSP that **must include `object-src 'none'` and `base-uri 'none'`**, plus an allowlist or nonces/hashes (per-response nonces are only mandatory at L3).
  - 3.4.4: nosniff. 3.4.5: Referrer-Policy. 3.4.6: `frame-ancestors` on **every** response.
  - 3.5.1-3.5.3: CSRF / origin separation. 3.5.4: separate apps on separate hostnames.
- **V6 authentication:**
  - 6.2.12: breached passwords.
  - **6.3.3 (L2): MFA or a combination of single-factor mechanisms is required.**
  - 6.4.1: initial secrets. 6.1.1/6.3.1: anti-automation.
- **V7 sessions:**
  - 7.1.1/7.1.2: documented timeouts and concurrency.
  - 7.3.1/7.3.2: enforced timeouts.
  - 7.4.1/7.4.2/7.4.5: termination, including admin kill.
  - 7.5.2: users can view and kill their sessions after re-authenticating.
- **V9 tokens:**
  - 9.1.2: algorithm allow-list, with key-confusion controls when symmetric and asymmetric algorithms are mixed.
  - 9.2.2/9.2.3: token type and audience.
- **V11 crypto:**
  - 11.1.1/11.1.2: key-management policy (NIST SP 800-57) and a crypto inventory.
  - 11.4.2: a password KDF with current parameters.
  - 11.5.1: >= 128-bit CSPRNG values. The standard notes that **UUIDs do not qualify**.
- **V12 comms:**
  - **12.3.1/12.3.3/12.3.4 (L2): TLS (or equivalent) for *all* inbound and outbound connections, including databases and internal HTTP services, with trusted or pinned internal certificates.**
- **V13 config:**
  - 13.2.1: backend components authenticate with individual accounts, short-lived tokens or certificates.
  - 13.2.4/13.2.5: egress allowlist.
  - **13.3.1 (L2): a secrets-management solution (e.g., a key vault); no secrets in source or artefacts.**
  - 13.4.5: no exposed internal docs or monitoring endpoints.
- **V14 data:**
  - 14.2.1: no sensitive data in URLs.
  - 14.2.3: no sensitive data to untrusted third parties.
  - 14.3.1-14.3.3: client-side clearing, `no-store`, no sensitive browser storage.
- **V15 coding:**
  - 15.1.1: documented remediation timeframes for vulnerable components. 15.1.2: SBOM.
  - 15.1.3/15.2.2: resource-demanding functions are documented and protected.
  - 15.3.2: no automatic redirect following. 15.3.3: mass assignment. 15.3.4: trusted client-IP propagation.
- **V16 logging (all L2):**
  - 16.1.1: logging inventory.
  - 16.2.2: UTC.
  - 16.2.5: sensitivity-based redaction.
  - 16.3.1-16.3.4: authentication, authorisation-failure, security and error events.
  - 16.4.2: tamper protection.
  - **16.4.3: logs shipped to a logically separate system.**
  - 16.5.1-16.5.3: generic errors, graceful degradation, fail secure.
- **V1:**
  - 1.2.4: parameterised queries. 1.3.5: sanitise Markdown. 1.3.6: SSRF allowlists.
  - **1.5.2: no unsafe deserialisation**, which is relevant because arq defaults to `pickle` (see `observability-otel.md` F6).

### F5. OWASP Top 10 status (spec §12.3 asks for this check)

`https://top10.owasp.org/` now redirects to the **OWASP Top 10:2025** (accessed 2026-09-26):

- A01 Broken Access Control
- A02 Security Misconfiguration
- A03 Software Supply Chain Failures
- A04 Cryptographic Failures
- A05 Injection
- A06 Insecure Design
- A07 Authentication Failures
- A08 Software or Data Integrity Failures
- A09 Security Logging and Alerting Failures
- A10 Mishandling of Exceptional Conditions

The page shows no explicit publication date. Spec §12.3 still uses the 2021 list, including A10 SSRF, which is not a top-level 2025 category. Where SSRF sits in 2025 is **UNVERIFIED — check the category pages at build**.

---

## DECISION / RECOMMENDATION

### D1. Target and claim wording

- Target **ASVS v5.0.0 Level 2** (ADR-0027), pinned to tag `v5.0.0`. Re-check for 5.0.1 at P9. If 5.0.1 is released, adopt it: a patch release should not change levels, but verify.
- **README claim template:** "Verified against OWASP ASVS v5.0.0 Level 2: N Met, M N/A (with rationale), K Deferred (listed with compensating controls). Self-assessed, not third-party certified; checklist at `docs/security/asvs-l2-checklist.md`, last verified YYYY-MM-DD at commit abc123."

### D2. Chapter-by-chapter applicability (Ticketward v1)

Counts are L1+L2 from the official CSV. "Applicable" subtracts the N/A items named in the table.

| Ch | L1+L2 | Applicable | Applicability and rationale | Key requirements for us | Primary evidence (and phase) |
|---|---|---|---|---|---|
| V1 | 27 | 16 | Partial. N/A: LDAP (1.2.6), XPath (1.2.7), LaTeX (1.2.8), SVG upload (1.3.4), JNDI (1.3.8), memcache (1.3.9), mail (1.3.11; S-01 means nothing is ever sent), unmanaged-memory items (1.4.x; Python/TS only, native deps covered by V15), XML parsing (1.5.1) | 1.2.4 SQLAlchemy bound params; 1.3.1/1.3.5 `nh3` + react-markdown without raw HTML; 1.3.6 egress allowlist; 1.3.7 no user-controlled templates; 1.5.2 msgpack not pickle for arq | Semgrep custom rules (no f-string SQL, no `pickle`, no `detail=str(e)`); injection unit tests (P4-P6) |
| V2 | 11 | 11 | Full | 2.1.3 documented business limits (quotas, frontier budget, job caps); 2.3.3 transactions; 2.3.4 locking (draft approve, refresh rotation); 2.4.1 anti-automation | `docs/security/business-limits.md`; rate-limit and quota tests; idempotency tests (P4, P7, P11) |
| V3 | 19 | 19 | Full (browser app) | 3.3.x cookies (see `auth-cookie-jwt-csrf.md`); 3.4.1 HSTS; 3.4.3 CSP incl. `object-src 'none'`; 3.4.6 `frame-ancestors` on every response; 3.5.x CSRF/Fetch Metadata; 3.5.4 app on its own hostname; 3.7.2 redirect allowlist | Playwright + pytest header assertions on HTML, API, static and error responses; CSRF suite; Caddyfile + `proxy.ts` (P8, P9) |
| V4 | 10 | 4 | Partial. N/A: GraphQL (4.3.x), WebSocket (4.4.x; SSE is used) | 4.1.1 correct Content-Type; 4.1.2 HTTPS redirect only for user-facing endpoints; 4.1.3 proxy headers not client-overridable (Caddy overwrites `X-Real-IP`, strips spoofable headers); 4.2.1 no request smuggling (single parser path; Caddy HTTP/1.1+2) | Header-spoofing test through Caddy; compose-smoke (P9) |
| V5 | 9 | 2 | Mostly N/A: no file uploads (KB content arrives as JSON text <= 1 MB). Applicable: 5.4.1/5.4.2 if any export/download endpoint exists (feedback export, eval report) | Content-Disposition + RFC 6266 filename sanitisation on downloads | Download endpoint tests (P7/P10) |
| V6 | 35 | 23 (+5 if MFA) | Partial. N/A: out-of-band OTP (6.6.x), IdP/federation (6.8.x). MFA section 6.5.x applies if TOTP is built | 6.1.1 anti-automation doc; 6.2.x password policy (15/128, blocklist, breached set); **6.3.3 MFA**; 6.3.2 no default accounts (demo users are deliberately non-default and demo-only); 6.4.1 activation secrets; 6.4.3 no reset flow that bypasses MFA | Auth test suite; `docs/security/authentication.md` (P4) |
| V7 | 18 | 15 | Partial. N/A: federated items (7.1.3, 7.6.x) | 7.1.1/7.1.2 lifetimes and concurrency documented; 7.3.1/7.3.2 idle + absolute enforced; 7.4.1 revocation within one request; 7.4.5 admin kill; 7.5.2 self-service list/kill | Session test suite (P4) |
| V8 | 7 | 6 | Partial. N/A: 8.4.1 multi-tenant (single tenant, `org_id` reserved). Keep `org_id` scoping anyway | 8.1.1/8.1.2 RBAC matrix + field-level rules (e.g., unmasked text only via reveal endpoint); 8.2.1 deny-by-default route enumeration; 8.2.2 IDOR; 8.2.3 field-level; 8.3.1 server-side only | Route-auth enumeration test, IDOR tests, `docs/security/authorization.md` (P4, P8) |
| V9 | 7 | 7 | Full (JWT access + service tokens) | 9.1.1-9.1.3 signature, allow-list, local keys; 9.2.1-9.2.3 exp/nbf, `typ`, `aud` | JWT negative tests (P4) |
| V10 | 29 | 0 | N/A: no OAuth/OIDC client, resource server or provider. Taskmoor "SSO" is fictional product data, not our auth | - | Rationale row |
| V11 | 14 | 14 | Full | 11.1.1/11.1.2 key policy + crypto inventory (JWT ES256 keys, CSRF HMAC keys, AES-GCM row keys, TLS, restic); 11.2.2 crypto agility (`kid`, key id per row); 11.3.2/11.3.3 AES-GCM; 11.4.2 argon2id; 11.5.1 CSPRNG >= 128 bits (no UUIDs as secrets) | `docs/security/crypto-inventory.md`; unit tests; Semgrep rule banning `random`/`uuid4` for secrets (P4, P9) |
| V12 | 9 | 8 | Partial. N/A: 12.1.3 mTLS client certs | 12.1.1 TLS 1.2+ (Caddy default); 12.2.x public certs; **12.3.1-12.3.4 internal TLS** (gap) | testssl.sh or equivalent report (tool UNVERIFIED); compose config (P9) |
| V13 | 13 | 13 | Full | 13.1.1 comms inventory; 13.2.1 individual service accounts (`tw_app`, `tw_migrator`, `tw_readonly`, Redis ACL users); 13.2.3 no default credentials; 13.2.4/13.2.5 egress allowlist; **13.3.1 secrets manager**; 13.4.2 no debug; 13.4.5 `/metrics` and Swagger not public | pydantic-settings prod validation test; Caddy blocks; `docs/security/communications.md` (P9) |
| V14 | 9 | 9 | Full | 14.1.1/14.1.2 data classification (ticket raw text, masked text, PII map, credentials); 14.2.1 no PII in URLs (review `GET /tickets?q=`, redact the query in access logs); 14.2.3 third parties (Anthropic masked; Cloudflare if proxied; Langfuse masked) ; 14.3.1-14.3.3 client clearing, `no-store`, no browser storage of ticket data | `docs/security/data-classification.md`; header tests; Playwright storage assertion (P8, P9) |
| V15 | 13 | 13 | Full | 15.1.1 remediation SLA (e.g., critical 7 d, high 30 d — owner to set); 15.1.2 SBOM (syft); 15.1.3/15.2.2 pipeline resource limits; 15.2.3 stub LLM provider disabled in prod; 15.3.3 Pydantic `extra="forbid"`; 15.3.4 client IP; 15.3.6 no prototype-pollution-prone merges | SECURITY.md SLA; CI scans; SBOM artefact (P9) |
| V16 | 16 | 16 | Full | 16.1.1 logging inventory; 16.2.x structlog JSON, UTC, redaction; 16.3.1-16.3.4 security events; 16.4.1 JSON encoding (log-injection safe); 16.4.2 audit hash chain + DB grants; **16.4.3 off-host shipping** (gap); 16.5.x problem+json | Redaction tests, audit-chain test, `docs/security/audit-events.md`, `docs/security/logging-inventory.md` (P4, P7, P9) |
| V17 | 7 | 0 | N/A: no WebRTC | - | Rationale row |
| **Sum** | **253** | **176 (181 with MFA)** | | | |

### D3. Evidence plan

**Checklist generation (P0, re-run at P9):**

- `scripts/asvs_checklist.py` downloads the v5.0.0 CSV from the tagged path and verifies a pinned SHA-256.
- It filters `L in {1,2}` and merges a hand-maintained `docs/security/asvs-status.yaml` (req_id → status, evidence, phase, notes).
- It renders `docs/security/asvs-l2-checklist.md`.
- CI fails if any L1/L2 row has no status, or if a "Met" row has no evidence link.

**Columns:** `req_id | L | chapter | requirement (short, from CSV) | status (Met / Partial / Deferred / N/A) | evidence | phase | notes`.

**Evidence types:**

| Code | Evidence | Examples |
|---|---|---|
| T | Automated test that runs in CI (pytest security suite, Playwright) | `tests/security/test_csrf.py::test_rejects_cross_site`, `e2e/headers.spec.ts` |
| S | Scanner / CI report artefact | Semgrep, Bandit, CodeQL, pip-audit, `pnpm audit`, Trivy, gitleaks, syft SBOM, optional ZAP baseline (tool version UNVERIFIED) |
| C | Reviewed configuration in git | `infra/caddy/Caddyfile`, `compose.prod.yaml`, `frontend/src/proxy.ts`, Alembic grants migration |
| D | Documentation section | `docs/security/*.md` (threat model, authentication, authorization, crypto inventory, communications, data classification, logging inventory, business limits) |
| M | Manual verification record (dated, with commit SHA) | restore drill log, browser DevTools cookie screenshot, `testssl` output |

**Status rules:**

- "Met" needs at least one T/S/C evidence item, or D evidence for documentation requirements.
- "N/A" needs a one-line architectural rationale.
- "Partial" and "Deferred" need all three of:
  - a compensating control;
  - a risk owner (the project owner);
  - a target version, recorded in `docs/security/risk-acceptances.md`.

**Phase ownership:**

| Phase | Chapters / items |
|---|---|
| P0 | Generate the checklist; V15.1 SLA text; secrets approach (13.3) |
| P4 | V6, V7, V9, V8 (routes/IDOR), V16.3 auth events, V1.2.4 |
| P5-P6 | V1.3.5 sanitisation, V2 business limits, 1.3.6 egress |
| P7 | V16 logging and redaction, V14.2.3 third-party flows (Anthropic, Langfuse) |
| P8 | V3 headers/CSP/cookies from the browser side, V14.3 |
| P9 | V12, V13, V15 scans/SBOM, the full checklist pass, gap closure or deferrals (DoD-9) |
| P11 | Demo-mode deltas (shared accounts, Cloudflare) re-reviewed |

**Cadence.** Re-verify at every minor release, and whenever a new route, cookie or external integration is added (PR template item).

### D4. Recommended closure for each L2 gap

| Gap | Recommended closure | Fallback if deferred |
|---|---|---|
| 6.3.3 MFA | TOTP for admin/ops_lead at P4 (other roles optional) | Deferred + compensating: short sessions, per-IP/global throttles, no public account creation, demo data synthetic |
| 6.2.12 breached passwords | Offline list always on + optional HIBP range API | none needed (cheap) |
| 7.1.1 / 7.3.x timeouts | 24 h absolute / 60 min idle (prod), 4 h (demo); documented | - |
| 7.4.1 / 7.4.2 / 7.4.5 / 7.5.2 | `sid` claim + Redis revoked-sid; session list/revoke endpoints | - |
| 3.3.3 refresh cookie | Documented deviation (`__Secure-` + path scoping + compensating controls) | Switch to `__Host-Http-tw_refresh; Path=/` |
| 3.4.3 CSP | Add `object-src 'none'` (see `nextjs-security.md`) | - |
| 12.3.1-12.3.4 internal TLS | TLS for Postgres (server cert from an internal CA, `verify-full`) and Redis (TLS port + ACL) | Deviation for intra-host HTTP hops (Caddy→web/api, worker→Ollama, app→collector). Compensating: single host, `internal: true` Docker networks, no published ports except Caddy. Revisit if multi-host |
| 13.3.1 secrets manager | SOPS + age-encrypted secrets in a private ops repo, decrypted at deploy to root-only Docker secret files; rotation runbook | Deferred + compensating: Docker secrets with file mode 0400, gitleaks, no secrets in images |
| 16.4.3 off-host logs | Ship security/audit events to an external sink. Service choice and pricing **UNVERIFIED**; decide at P9 | Minimum: nightly encrypted off-host copy of audit partitions via restic (not real-time) |
| 1.5.2 deserialisation | arq `job_serializer=msgpack.packb` / `job_deserializer=lambda b: msgpack.unpackb(b, raw=False)`; jobs carry only primitives | - |
| 11.1.x, 13.1.1, 14.1.x, 16.1.1, 15.1.1, 2.1.3 docs | Write the listed `docs/security/*.md` files (P9) | - |

---

## SPEC IMPACT

Disposition in spec v1.1: every item below was applied (A-21, ADR-0027 amended). The exceptions:
- **SI-S2** follows the MFA deferral (owner decision D-01, documented exception, ADR-0040).
- **SI-S5** was resolved with the documented single-host internal-TLS deviation. Internal TLS stays required for any multi-host production.

| # | Spec location | Finding | Recommendation |
|---|---|---|---|
| SI-S1 | §12 "ASVS 5.0 Level 2 (verify version at build)" | Confirmed current: v5.0.0; the next target is patch 5.0.1 | Pin `v5.0.0`; cite `v5.0.0-x.y.z`; build the checklist from the CSV |
| SI-S2 | §12.2/§10 MFA deferred (v1.1, G-4) | 6.3.3 (L2) requires MFA | See `auth-cookie-jwt-csrf.md` SI-A6: TOTP in P4 or a documented deferral |
| SI-S3 | §11 change-password, §11 login, §12.2 | 6.2.12, 7.1.1, 7.3.x, 7.4.x, 7.5.2, 3.3.3 gaps | See `auth-cookie-jwt-csrf.md` SI-A1..SI-A9 |
| SI-S4 | §12.7 CSP | Missing `object-src 'none'` required by 3.4.3 (`base-uri 'none'` is present) | Add it (see `nextjs-security.md` SI-N1) |
| SI-S5 | §12.9 "separate internal network" | 12.3.1/12.3.3/12.3.4 (L2) require TLS for internal connections, including databases | TLS on Postgres and Redis; documented deviation for intra-host HTTP hops (D4) |
| SI-S6 | §12.6 secrets (Docker secrets / host store) | 13.3.1 (L2) expects a secrets-management solution | SOPS+age (or 1Password/Doppler) with a rotation runbook; else a documented deferral |
| SI-S7 | §15 logs to stdout, single VM | 16.4.3 (L2) requires shipping logs to a logically separate system | External log sink for security events, or a documented deviation with nightly off-host audit copies |
| SI-S8 | §7.1 / ADR-0022 arq | arq's default job serialiser is `pickle` (1.5.2) | msgpack serialiser in both producer and worker settings |
| SI-S9 | §12.3 OWASP Top 10 (2021) | The 2025 edition is live, with renamed and re-ordered categories | Re-map §12.3 to Top 10:2025 at P9 |
| SI-S10 | §19 DoD-9 | No claim-wording rule | Adopt the D1 claim template with met/N/A/deferred counts |
| SI-S11 | §14.5 CI | No automated check that the checklist is complete | Add a `asvs-checklist` CI job (D3) |

---

## IMPLEMENTATION CHECKLIST

- [ ] P0: `scripts/asvs_checklist.py` + `docs/security/asvs-status.yaml` seeded with the N/A rationales from D2.
- [ ] P0: CI job `asvs-checklist` (fails on missing status or evidence).
- [ ] P4: auth/session/token evidence tests (see the auth doc checklist).
- [ ] P7: logging inventory, redaction tests, third-party data-flow table (Anthropic, Langfuse, Cloudflare).
- [ ] P8: header/CSP/cookie assertions in Playwright, across HTML, API, static, error and 404 responses.
- [ ] P9: write `docs/security/{authentication,authorization,crypto-inventory,communications,data-classification,logging-inventory,business-limits,risk-acceptances}.md`.
- [ ] P9: Postgres + Redis TLS (or a recorded deviation); secrets approach; off-host security log decision.
- [ ] P9: full checklist pass; README claim with counts; DoD-9 sign-off.
- [ ] P9: re-map spec §12.3 to OWASP Top 10:2025 (via PR + version bump).

---

## OPEN RISKS / TO VERIFY

- **ASVS 5.0.1** may land before P9. Check the `OWASP/ASVS` releases page and adopt it if it is available (verify the level changes).
- **Applicable count (176/181)** depends on the N/A decisions here. It must be recomputed by the script, not hand-maintained.
- **Self-assessment bias.** The checklist is owner-verified. State that clearly, and consider a peer review of the evidence links.
- **Internal TLS effort** (certificates for Postgres/Redis on one host) is estimated at 0.5-1 day. **UNVERIFIED — measure at P9.**
- **Tools for TLS and DAST evidence** (testssl.sh, ZAP baseline): versions and CI integration are **UNVERIFIED**. Evaluate at P9.
- **OWASP Top 10:2025**: publication date and SSRF placement not confirmed on the page. **Verify at build.**

---

## LINKED ADR

- **ADR-0027** (Target OWASP ASVS L2): add the version pin (v5.0.0), claim wording, evidence rules and the deviation register.
- Cross-refs: ADR-0020 (auth), ADR-0022 (arq serialiser), ADR-0023 (frontend/CSP), ADR-0024 (logging), ADR-0026 (deployment/TLS).

---

## SOURCES (all accessed 2026-09-26)

- [OWASP ASVS GitHub README (latest stable 5.0.0; next target 5.0.1; citation format)](https://github.com/OWASP/ASVS)
- [OWASP ASVS project page](https://owasp.org/www-project-application-security-verification-standard/)
- [ASVS releases page](https://github.com/OWASP/ASVS/releases)
- ASVS v5.0.0 chapters: [Frontispiece](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x01-Frontispiece.md), [Preface](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x02-Preface.md), [What is the ASVS](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x03-What-is-the-ASVS.md), [For Users of 4.0](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x05-For-Users-Of-4.0.md), and V1-V17 files in [5.0/en](https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/en)
- [ASVS v5.0.0 export formats (docs_en)](https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/docs_en), including [the CSV used for all counts](https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv)
- [Global AppSec EU 2025 session: Introducing the 5.0 release of the ASVS](https://owasp2025globalappseceu.sched.com/event/1whCc/introducing-the-50-release-of-the-asvs)
- [OWASP Top 10:2025](https://top10.owasp.org/2025/)
- arq source (default `pickle` serialiser): [arq/jobs.py v0.28.0](https://github.com/python-arq/arq/blob/v0.28.0/arq/jobs.py), [msgpack example](https://github.com/python-arq/arq/blob/v0.28.0/docs/examples/custom_serialization_msgpack.py)

---

**Change log**: 2026-09-27: status and spec-impact disposition updated to spec v1.1 (A-21, D-01); identifiers renamed for Ticketward.

**Document Version**: 1.1
**Next Update**: P9, full checklist pass (or earlier if ASVS 5.0.1 is released)
