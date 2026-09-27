---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §8, §12, §13; spec §7.8, §12.7, §12.8, §14.1, §14.2, §14.3, §21 R-19, §24.2; research nextjs-security
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0023: Next.js App Router, TypeScript strict, Tailwind and shadcn/ui; same-origin via Caddy

> **Amended in spec v1.1 (2026-09-27; change record A-24, A-29(d), A-30).**
> * **`next` exact-pinned at 16.3.6.** The 2026-09 advisory floor is 16.3.3, and critical/high Next.js advisories
>   get a **72 h patch SLA** (R-19: two critical RCEs in 2026-09). Pinned with `react`/`react-dom` 19.3.0, Tailwind 4
>   (CSS-first) and an ESLint flat config.
> * **`src/proxy.ts` sets the CSP only**, never authentication or authorization. The CSP nonce is 128 random bits from
>   a CSPRNG, and a nonce CSP forces dynamic rendering, which is **accepted** because every page is per-user.
> * **CSP:** `object-src 'none'`, a style nonce plus `style-src-attr 'unsafe-inline'` (React style attributes), and
>   `strict-dynamic`. The JSON API gets its own `default-src 'none'` CSP (A-29(d)).
> * **No Server Actions** (`'use server'`/`'use cache'` banned by ESLint and a CI grep; Caddy returns 405 for
>   non-GET/HEAD to Next.js). The **image optimizer is disabled** (`/_next/image*` → 404 at the edge).
> * A **server-only data-access layer** forwards only the access cookie (`__Host-Http-tw_access`) to the API with
>   `no-store`. **Session refresh is client-side** (Web Locks single-flight). The TanStack Query cache is in memory
>   only.
> * **Dev is same-origin through Caddy** at `https://localhost` (no CORS in dev). Caddy strips client-supplied
>   `Content-Security-Policy`, `x-nonce` and `x-middleware-subrequest` headers.

## Context and Problem Statement

The brief names "Next.js / React" (brief §8), and the UI carries much of the safety story (§7.8). The workspace shows
the masked thread with a reveal toggle, calibrated confidence chips, the "Human decision required" banner, a draft
editor with struck-out unsupported sentences, and an evidence panel. It also has escalation views, ops and eval
dashboards, KB admin and user admin. The footer carries the Taskmoor disclaimer and "Built with Llama" (D-05).

The frontend renders untrusted content: masked ticket text, model drafts, KB Markdown and handoff briefs. Next.js
itself has an active advisory stream. CVE-2025-29927-class middleware bypasses via `x-middleware-subrequest` showed
that middleware must never be an authorization boundary, and 2026-09 brought two critical RCE advisories (R-19).

Which frontend framework and delivery topology should be used, and under which rules?

## Decision Drivers

* Brief alignment (BR-036), and productive, accessible components (shadcn/ui on Radix).
* End-to-end typing (generated API types, TS strict, `noUncheckedIndexedAccess`).
* The smallest reasonable server attack surface: no Server Actions, no image optimizer, API-only authorization.
* A strict CSP with nonces and no raw-HTML rendering.
* Fast patching of a fast-moving dependency.

## Considered Options

1. Next.js App Router (16.3.x pinned) + TS strict + Tailwind 4 + shadcn/ui, same-origin behind Caddy (chosen)
2. Vite single-page app (React)
3. Remix (React Router framework mode)

## Decision Outcome

Chosen option: option 1, with the v1.1 hardening rules as part of the decision:

* **The API is the only authorization boundary.** `proxy.ts` sets CSP headers only. Server Components read through a
  `server-only` DAL that forwards **only** the access cookie to `http://api:8000` with `no-store` and
  `redirect: 'error'`. They never see the path-scoped refresh cookie.
* **No Server Actions:** mutations go through `/api/v1` with the CSRF header (ADR-0020). Enforced by ESLint
  `no-restricted-syntax`, a CI grep, and Caddy's 405 for non-GET/HEAD to Next.js.
* **CSP (web UI):**

  ```
  default-src 'self'; script-src 'self' 'nonce-…' 'strict-dynamic'; style-src 'self' 'nonce-…';
  style-src-attr 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self';
  object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests
  ```

  Dev adds `'unsafe-eval'`. Chart colours move to CSS variables.
* **Rendering:** React escaping; `react-markdown` without `rehype-raw`; no `dangerouslySetInnerHTML` (ESLint); links
  limited to KB slugs.
* **Config:** `output: 'standalone'`, `poweredByHeader: false`, `images.unoptimized: true`, no rewrites to other
  hosts, no i18n config, `NEXT_TELEMETRY_DISABLED=1`. No secrets under `NEXT_PUBLIC_*`.
* **State:** TanStack Query in memory only. Logout clears the query cache, and the API sends `Clear-Site-Data`.
* **Patching:** re-check the GitHub Advisory Database at P8 start and before each release. Upgrade within 72 h of a
  critical/high advisory, recorded in SECURITY.md. Dependabot groups `next` + `react*`.

**Verify at build (research `nextjs-security`):** the pinned version against current advisories, and whether
Radix/shadcn still need `style-src-attr 'unsafe-inline'`.

### Consequences

* Good, because server rendering and components suit the dashboards, generated types catch API drift, and the server
  surface is minimised (no Server Actions, no image optimizer, no auth in Next.js).
* Good, because a nonce CSP with `strict-dynamic` and `object-src 'none'` confines script execution.
* Bad, because a Node runtime in production and the advisory stream (R-19) mean a standing 72 h patch obligation.
* Bad, because `style-src-attr 'unsafe-inline'` remains for React style attributes (RR-07 residual). Nonced styles
  cover `<style>` elements.
* Neutral, because every page renders dynamically (nonce CSP). That is accepted: all pages are authenticated and
  per-user, so static optimisation brings nothing.

### Confirmation

* Playwright E2E through Caddy:
  * demo flow, three demo cases, RBAC views, axe (no serious issues);
  * CSP present with `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'` and a fresh nonce per
    navigation, with zero CSP violations;
  * no ticket data in browser storage, and logout clears the query cache;
  * `POST /` → 405 and `/_next/image` → 404 at the edge (§14.3).
* Lint: ESLint (strict-type-checked, jsx-a11y, the Server Actions ban), the `'use server'` CI grep, `tsc`, and
  prettier. The contract stage checks the type-gen diff. vitest coverage ≥ 70%.
* `T-SEC-EDGE-headers`: Caddy strips `x-middleware-subrequest`, `x-nonce` and client CSP headers. `pnpm audit --prod`
  and Trivy run in the security stage.
* The release checklist records the `next` version and advisory check date (72 h SLA evidence in SECURITY.md).

## Pros and Cons of the Options

### Next.js App Router (hardened)

* Good, because it is brief-aligned with SSR/RSC for dashboards, strong TS support and a large ecosystem.
* Bad, because of the server-side attack surface, the advisory stream and caching subtleties, which the v1.1 rules
  contain.

### Vite SPA (React)

* Good, because static files served by Caddy mean no Node runtime and the smallest attack surface. It is still React.
* Bad, because there is no server rendering for dashboards, routing and data-loading conventions must be assembled by
  hand, and the portfolio signal is weaker than the named stack.

### Remix (React Router framework mode)

* Good, because it is web-standards-first, with progressive enhancement.
* Bad, because its ecosystem is smaller, it has seen churn since the merge, and it is not the brief's named option.

## More Information

* Spec (private): §7.8 (UI, footer), §12.7 (cookies, CSP, headers, Next.js rules), §12.8 (pins, 72 h SLA), §14.1,
  §14.2 (frontend standards), §14.3 (E2E assertions), §21 R-19, §24.2 (edge rules). Change record A-24, A-29 (d),
  A-30.
* Brief (private): §8, §12, §13. BR-036, BR-065, BR-069, BR-073.
* Research: [nextjs-security](../research/nextjs-security.md).
* Related ADRs: ADR-0020, ADR-0021, ADR-0026 (edge rules), ADR-0034 ("Built with Llama").
* Revisit when: a Next.js major upgrade changes rendering or security defaults, or the SSR requirement disappears
  (then a Vite SPA would reduce attack surface).
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (16.3.6 pin + 72 h SLA, `proxy.ts` CSP,
  no Server Actions, image optimizer off, server-only DAL, same-origin dev).
