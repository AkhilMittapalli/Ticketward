# Next.js (App Router) Security: CSP Nonces, Cookies via Same-Origin Proxy, Server Actions, Advisories - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Resolved. CSP design, style handling, cookie/SSR model, the Server Actions decision and the version floor are all defined. Re-check the advisory list at P8 start and before every release.
**Category**: Security / Frontend
**Linked ADR(s)**: ADR-0023 (Next.js App Router + TS strict + Tailwind + shadcn/ui; same-origin via Caddy); related ADR-0020 (auth cookies/CSRF), ADR-0026 (Caddy), ADR-0027 (ASVS)
**Spec sections**: §7.1 (frontend ↔ API), §12.7 (CSRF/CORS/CSP/headers), §14.1 (frontend layout), §14.2 (frontend standards), §16 P8, §23

---

## EXECUTIVE SUMMARY

- **Versions (npm registry, 2026-09-26).** `next` **16.3.6** (latest, 2026-09-22), backport line 15.5.26; `react`/`react-dom` **19.3.0**; `tailwindcss` 4.3.3.
- **Minimum safe floor.** According to the GitHub Advisory Database, the floor is **next >= 16.3.3** (or >= 15.5.24 on the backport line). The 2026-09-08 critical fixes cover:
  - unauthenticated RCE in the Image Optimization API with AVIF files;
  - unauthenticated RCE on Windows-hosted servers. This one is relevant to the owner's Windows dev machine.
  **Pin 16.3.6.**
- **CSP.** In Next.js 16, `middleware.ts` is **deprecated and renamed `proxy.ts`**, and it runs on the Node.js runtime by default. The proxy creates a per-request nonce, sets it on the *request* `Content-Security-Policy` header, and Next.js stamps it onto its own scripts and inline styles.
  - **Cost:** every page must render dynamically. Static optimisation and ISR are disabled, pages can't be CDN-cached, and Partial Prerendering is incompatible. That is acceptable here, because every page is authenticated and per-user.
  - The experimental hash-based SRI alternative (`experimental.sri`) exists but only covers build-time scripts.
- **Styles.**
  - Tailwind compiles to a static CSS file (allowed by `'self'`).
  - React `style={{…}}` attributes, which Radix/shadcn use, are *attributes*, and CSP nonces cannot apply to attributes. So use `style-src 'self' 'nonce-…'` plus **`style-src-attr 'unsafe-inline'`** (Chrome 75+, Firefox 103+, Safari 15.1+). Styles set through the CSSOM (`el.style.x = …`) are not blocked at all.
  - shadcn's chart `ChartStyle` injects a `<style>` element. Give it the nonce, or move its variables into CSS.
- **Required CSP additions** (ASVS 3.4.3): `object-src 'none'` and `base-uri 'none'`; `frame-ancestors 'none'` on every response (3.4.6). Nonces must come from 16 random bytes; the docs' `crypto.randomUUID()` example has only 122 random bits, and ASVS 11.5.1 says UUIDs don't qualify.
- **Cookies.** Caddy serves `/api/*` (FastAPI) and the pages (Next.js) from one origin.
  - FastAPI alone sets and reads auth cookies.
  - Server Components forward **only** the access cookie to `http://api:8000` over the internal network, with `no-store`.
  - The refresh cookie never reaches Next.js (it is path-scoped to `/api/v1/auth`), so refresh happens client-side (single-flight). Next.js `proxy.ts` does **no** authorisation (CVE-2025-29927 plus several 2026 proxy-bypass CVEs).
- **Server Actions.** They are enabled by default, and **there is no config switch to disable them.** Next.js's built-in CSRF check compares `Origin` with `Host`/`X-Forwarded-Host`, but a request with **no `Origin` is let through with a warning**. `Origin: null` was a bypass until 16.1.7. Decision:
  - Ticketward uses **no Server Actions** (`'use server'` banned by ESLint and CI).
  - Caddy returns **405 for any non-GET/HEAD request to Next.js**.
  - All mutations go to FastAPI with the CSRF header.
  - Patching still matters, because the Dec-2025 RSC RCE (CVE-2025-55182) affected App Router apps even without Server Functions.
- **11 spec-impact items** (see SPEC IMPACT).

---

## QUESTIONS

1. How do we add a nonce-based CSP in the App Router, and what does it do to static rendering?
2. How do Tailwind, shadcn/Radix and inline styles fit under a strict CSP?
3. How should cookies and auth work across the same-origin proxy (SSR data fetching, refresh, CSRF)?
4. How do Server Actions defend against CSRF, and should we disable them?
5. Which recent Next.js/React security advisories matter, and what is the minimum safe version?
6. (Derived) What dev-environment settings keep dev behaviour equal to prod (cookies, CSP)?

---

## FINDINGS

### F1. Versions (npm registry dist-tags, accessed 2026-09-26)

| Package | latest | Other tags |
|---|---|---|
| `next` | **16.3.6** (2026-09-22) | backport 15.5.26 (2026-09-22); canary 16.4.0-canary.50; next-14 14.2.35 |
| `react`, `react-dom`, `react-server-dom-webpack` | **19.3.0** (2026-09-09) | backport 19.0.8 |
| `eslint-config-next` / `@next/eslint-plugin-next` | 16.3.6 | |
| `tailwindcss` | 4.3.3 (2026-07-16) | |
| `jose` (only if the frontend ever verifies JWTs) | 6.2.12 | |

### F2. CSP in the App Router (Next.js docs v16.3.6, accessed 2026-09-26)

- **Proxy.** "How to set a CSP" now uses `proxy.ts`. The `proxy.js` reference says the `middleware` convention is deprecated and renamed to `proxy` (v16.0.0), and that proxy defaults to the Node.js runtime. The `runtime` option is not allowed in proxy files, and a codemod `middleware-to-proxy` exists.
- **Mechanism:**
  1. The proxy generates a nonce.
  2. It sets `Content-Security-Policy` (containing `'nonce-…'`) and `x-nonce` on the **request** headers, and the CSP on the response.
  3. During SSR, Next.js parses the request CSP, extracts the nonce and attaches it to framework scripts, page bundles, the inline styles and scripts it generates, and `<Script nonce>`.
  4. The nonce is readable in Server Components through `(await headers()).get('x-nonce')`.
- **Rendering impact:**
  - Nonces **require dynamic rendering for all pages**.
  - Static optimisation and ISR are disabled, and pages can't be CDN-cached without extra configuration.
  - **PPR is incompatible.**
  - Pages may need `await connection()` to force dynamic rendering.
  - Consequences listed by the docs: slower initial loads and more server load.
- **Matcher.** The recommended matcher excludes `api`, `_next/static`, `_next/image`, `favicon.ico` and prefetch requests (`next-router-prefetch`, `purpose: prefetch`).
- **Dev mode.** `'unsafe-eval'` is needed only in development (React debugging). The docs' dev variant also uses `style-src 'unsafe-inline'`.
- **SRI alternative.** `experimental: { sri: { algorithm: 'sha256' } }` adds hashes at build time and keeps static generation. It is experimental, App Router only, and cannot handle dynamically generated scripts (added in v14.0.0).
- The docs' nonce example is `Buffer.from(crypto.randomUUID()).toString('base64')`.

### F3. Inline styles vs CSP (MDN, accessed 2026-09-26)

- **`style-src` without `'unsafe-inline'`** blocks:
  - inline `<style>` elements and `<link>`ed styles not in the allowlist;
  - inline `style="…"` attributes;
  - styles applied by setting the `style` attribute or `cssText` from JS.
- It does **not** block direct CSSOM property assignment (`el.style.display = 'none'`).
- **`style-src-attr`** governs inline `style` attributes, including `setAttribute('style', …)` and `cssText`. **Nonces don't apply to it**; its values are `'unsafe-inline'`, `'unsafe-hashes'` and `'none'`. Support: Chrome 75+, Firefox 103+, Safari 15.1+ (Baseline since Dec 2022).
- **shadcn/ui** `chart.tsx` (registry new-york-v4, main branch, checked 2026-09-26) defines `ChartStyle`, which renders `<style dangerouslySetInnerHTML=…>` with no nonce. It would be blocked under a nonce-only `style-src`.

### F4. Server Actions security (Next.js docs v16.3.6, accessed 2026-09-26)

- Server Actions are stable since v14 and **enabled by default**. The `serverActions` config has only `allowedOrigins` and `bodySizeLimit` (default 1 MB). **No option disables them.**
- **CSRF defence:**
  - Actions are POST-only.
  - Next.js compares the host of `Origin` with `x-forwarded-host` (or `host`) and aborts on mismatch. `allowedOrigins` adds extra hosts, with `*` and `**` wildcards.
  - **A request with no `Origin` header is allowed through with a warning.** The check runs in production.
- **Other hardening:**
  - Action IDs are encrypted and non-deterministic, regenerated per build (cached for at most 14 days).
  - Unused actions are removed.
  - Closure variables are encrypted with a per-build key (`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` for multi-instance setups).
  - The docs insist on authentication and authorisation **inside** every action, and state that page-level checks don't extend to the actions defined in the page.
- **Proxy is not an auth boundary.** Server Functions are POSTs to the route that uses them, so a proxy matcher change can silently drop coverage. Always verify auth inside the function. The data-security guide recommends a `server-only` Data Access Layer returning minimal DTOs, and optional React taint APIs (`experimental.taint`).
- The Server Action request header constant in Next.js 16.3.6 source is `next-action`. Progressive-enhancement form posts carry the action id in the form body instead, so blocking by header alone is incomplete.

### F5. Advisories (GitHub Advisory Database API, `ecosystem=npm&affects=next` and `react-server-dom-webpack`, accessed 2026-09-26)

| Published | ID | Sev | Summary | Fixed in | Ticketward response |
|---|---|---|---|---|---|
| 2026-09-08 | GHSA-2xp9-vwfh-vxw4 | **critical** | Unauthenticated RCE in the Image Optimization API when AVIF files are used (libheif via sharp) | 15.5.24 / **16.3.3** | Upgrade; `images.unoptimized`; 404 on `/_next/image` at the edge |
| 2026-09-08 | CVE-2026-75604 (GHSA-p293-qw3h-jr36) | **critical** | Unauthenticated RCE on Windows-hosted servers (Pages and App Router without Cache Components) | 15.5.24 / **16.3.3** | Upgrade, **especially for `next dev`/`next start` on the Windows workstation**; prod runs Linux containers |
| 2026-07-22 | CVE-2026-64649 | high | SSRF in Server Actions on custom servers (Host headers not pinned) | 15.5.21 / 16.2.11 | No Server Actions; Caddy pins the host |
| 2026-07-22 | CVE-2026-64645 | high | SSRF in rewrites via attacker-controlled destination hostname | 15.5.21 / 16.2.11 | No Next rewrites; Caddy routes `/api` |
| 2026-07-22 | CVE-2026-64642 | high | Proxy bypass (Turbopack + single i18n locale) | 16.2.11 | No i18n; no auth in proxy |
| 2026-07-22 | CVE-2026-64641 | high | DoS in App Router via Server Actions | 15.5.21 / 16.2.11 | Upgrade; edge 405 on non-GET |
| 2026-07-22 | CVE-2026-64643, -64644, -64646, -64647, -64648 | medium | Server Function endpoint disclosure; image optimizer SVG DoS; unbounded edge Server Action payload; response-cache confusion (2) | 15.5.21 / 16.2.11 | Upgrade |
| 2026-05-11 | CVE-2026-44581 | medium | **XSS in App Router apps using CSP nonces** behind shared caches (malformed request-derived nonce reflected) | 15.5.16 / 16.2.5 | Upgrade; **strip inbound `Content-Security-Policy` request headers at Caddy** (the advisory's workaround) |
| 2026-05-11 | CVE-2026-44575, CVE-2026-45109 (incomplete-fix follow-up), CVE-2026-44574, CVE-2026-44573 | high | Proxy bypasses (segment-prefetch routes, dynamic param injection, Pages i18n) | 16.2.5 / 16.2.6 | Auth enforced by FastAPI and the DAL, never in proxy |
| 2026-05-11 | CVE-2026-44578, CVE-2026-44579, GHSA-8h8q-6873-q5fj, CVE-2026-44576/-44582/-44572/-44577/-44580 | high/med/low | WebSocket-upgrade SSRF, Cache Components DoS, Server Components DoS, RSC cache poisoning, redirect cache poisoning, image DoS, `beforeInteractive` XSS | 15.5.16 / 16.2.5 | Upgrade |
| 2026-03-17 | CVE-2026-27978 | medium | `Origin: null` bypassed the Server Actions CSRF check | 16.1.7 | No Server Actions |
| 2026-03-17 | CVE-2026-29057, -27979, -27980, -27977 | medium/low | Request smuggling in rewrites, PPR resume DoS, image cache disk growth, dev HMR null-origin | 16.1.7 / 15.5.13-14 | Upgrade |
| 2026-01-28 | GHSA-h25m-26qc-wcjf; CVE-2025-59472, CVE-2025-59471 | high/medium | RSC request-deserialization DoS; PPR memory; image remotePatterns DoS | 16.0.11 / 16.1.5 / 15.5.10 | Upgrade |
| 2025-12-11/12 | GHSA-mwv6-3258-q52c, GHSA-w37m-7fhw-fmv9, GHSA-5j59-xgg2-r9c4 | high/medium | RSC DoS, Server Actions source-code exposure, incomplete-fix follow-up | 16.0.9 / 16.0.10 | Upgrade |
| 2025-12-03 | GHSA-9qr9-h5gf-34mp (upstream **CVE-2025-55182**, CVSS 10.0) | **critical** | RCE in the React Flight protocol (App Router, Next 15.x/16.x). React states apps can be vulnerable **even without Server Function endpoints** | 15.0.5-15.5.7, **16.0.7** | Upgrade; defence in depth via the edge 405 |
| 2025-03-21 | **CVE-2025-29927** (GHSA-f82v-jwr5-mffw) | **critical** | Authorisation bypass in middleware via the internal `x-middleware-subrequest` header | 15.2.3 / 14.2.25 / 13.5.9 / 12.3.5 | Never authorise in middleware/proxy; strip `x-middleware-subrequest` at the edge (the advisory's workaround) |

React (`react-server-dom-webpack`) 2026 advisories CVE-2026-44907, CVE-2026-23870, CVE-2026-23869 and CVE-2026-23864 (DoS) are fixed in 19.0.8, 19.1.9 and 19.2.8. The App Router uses the React build that Next bundles, so **upgrading `next` is what applies the fix**. Keep `react`/`react-dom` at 19.3.0 as well.

### F6. Self-hosting guidance (Next.js docs v16.3.6, accessed 2026-09-26)

- Put a reverse proxy in front of `next start`. It handles malformed requests, slow-connection attacks, payload limits and rate limiting.
- Dynamic pages are served with `Cache-Control: private, no-cache, no-store, max-age=0, must-revalidate`, which satisfies ASVS 14.3.2 for SSR pages.
- Streaming requires proxies that don't buffer. Caddy flushes SSE automatically; HTML streaming works through `reverse_proxy`.
- `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` and `deploymentId` matter only for multi-instance deployments, which does not apply here.

---

## DECISION / RECOMMENDATION

### D1. Versions and update policy

- Pin `next@16.3.6`, `react@19.3.0`, `react-dom@19.3.0`, `eslint-config-next@16.3.6`, `tailwindcss@4.3.3` in `pnpm-lock.yaml`. Use Node.js LTS in the image (check the LTS line at build).
- Dependabot/Renovate group for `next` + `react*`. `pnpm audit --prod` fails CI on high/critical (spec §12.8).
- Subscribe to the vercel/next.js GitHub security advisories. **Target: upgrade within 72 h of a critical/high Next.js advisory.** That turnaround is our own SLA proposal; record it in SECURITY.md (ASVS 15.1.1).

### D2. `proxy.ts`: nonce CSP (Next.js 16)

```ts
// frontend/src/proxy.ts
import { NextResponse, type NextRequest } from 'next/server'

function newNonce(): string {
  const bytes = new Uint8Array(16)                 // 128-bit CSPRNG (ASVS 11.5.1); not crypto.randomUUID()
  crypto.getRandomValues(bytes)
  return Buffer.from(bytes).toString('base64')     // proxy runs on the Node.js runtime in Next 16
}

export function proxy(request: NextRequest) {
  const nonce = newNonce()
  const dev = process.env.NODE_ENV === 'development'
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ''}`,
    dev ? "style-src 'self' 'unsafe-inline'" : `style-src 'self' 'nonce-${nonce}'`,
    "style-src-attr 'unsafe-inline'",              // React style={} attributes (Radix/shadcn); nonces cannot cover attributes
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",                          // fetch + SSE are same-origin
    "object-src 'none'",                           // ASVS v5.0.0-3.4.3
    "base-uri 'none'",                             // ASVS v5.0.0-3.4.3
    "form-action 'self'",
    "frame-ancestors 'none'",                      // ASVS v5.0.0-3.4.6
    'upgrade-insecure-requests',
  ].join('; ')

  const requestHeaders = new Headers(request.headers)   // Caddy has already stripped client-supplied CSP/x-nonce
  requestHeaders.set('x-nonce', nonce)
  requestHeaders.set('Content-Security-Policy', csp)     // Next.js extracts the nonce from this request header
  const response = NextResponse.next({ request: { headers: requestHeaders } })
  response.headers.set('Content-Security-Policy', csp)
  return response                                        // NO authentication/authorisation logic here
}

export const config = {
  matcher: [
    {
      source: '/((?!api|_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
}
```

- The root `app/layout.tsx` reads `(await headers()).get('x-nonce')`. That also makes the whole tree dynamic, which nonces require anyway. It passes the nonce to a small `NonceProvider` context for the rare component that renders its own `<style>`/`<script>`.
- **shadcn `ChartStyle`:**
  - Preferred: delete `ChartStyle` and define the chart colour variables (`--color-<key>`) in `globals.css` / Tailwind v4 `@theme`. That removes the inline `<style>`.
  - Alternative: give it `nonce={useNonce()}`. Check that React emits no hydration warning (**verify at P8**).
- **Rules:**
  - No `dangerouslySetInnerHTML` except that audited case.
  - KB Markdown goes through `react-markdown` **without** `rehype-raw` (spec §12.3 A03; ASVS 1.3.5, 3.2.2).
  - No third-party scripts, so the CSP needs no external hosts.

### D3. `next.config.ts`

```ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'standalone',            // small non-root runtime image (spec §12.9)
  poweredByHeader: false,
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  images: { unoptimized: true },   // no Image Optimization API surface (many 2024-2026 advisories incl. the AVIF RCE)
  // No rewrites/redirects to other hosts: /api routing is Caddy's job (CVE-2026-64645, CVE-2026-29057 classes).
  // No i18n config (several proxy-bypass CVEs involve i18n).
}
export default nextConfig
```

Runtime environment: `NEXT_TELEMETRY_DISABLED=1`, `NODE_ENV=production`. The container runs as non-root with a read-only root filesystem and `tmpfs` for `.next/cache` if needed.

### D4. Cookies and auth across the same-origin proxy

- **Routing.** Caddy (see `public-demo-deployment.md` D3):
  - sends `/api/*` → FastAPI and everything else → Next.js;
  - strips `Content-Security-Policy`, `x-nonce` and `x-middleware-subrequest` from client requests;
  - returns 404 for `/_next/image*` and 405 for non-GET/HEAD requests to Next.js.
- **Cookie ownership.** FastAPI alone sets and clears `__Host-Http-tw_access`, `__Host-tw_csrf` and `__Secure-tw_refresh` (see `auth-cookie-jwt-csrf.md` D1). Next.js never sets auth cookies: no auth Route Handlers, no Server Actions. `__Secure-tw_refresh` (Path `/api/v1/auth`) is never sent to Next.js.
- **SSR reads** go through a `server-only` Data Access Layer:

```ts
// frontend/src/lib/api/server.ts
import 'server-only'
import { cookies } from 'next/headers'

const API = process.env.TW_INTERNAL_API_URL ?? 'http://api:8000'   // internal network, never user-controlled

export async function apiGet<T>(path: `/api/v1/${string}`): Promise<{ status: number; data?: T }> {
  const access = (await cookies()).get('__Host-Http-tw_access')?.value
  if (!access) return { status: 401 }
  const res = await fetch(`${API}${path}`, {
    headers: { cookie: `__Host-Http-tw_access=${access}`, accept: 'application/json' },  // forward ONLY the access cookie
    cache: 'no-store',
    redirect: 'error',                                                                    // ASVS 15.3.2
  })
  if (!res.ok) return { status: res.status }
  return { status: res.status, data: (await res.json()) as T }                           // return DTOs, not raw payloads
}
```

- **Session handling in the app shell:**
  - The `(app)` layout calls `/api/v1/auth/me` through `apiGet`.
  - On **401** it renders a client `<SessionRefresher/>`. That component performs the single-flight refresh (`navigator.locks`) and then calls `router.refresh()`; if the refresh fails it calls `router.replace('/login?next=…')`.
  - On **403** it renders the forbidden page.
  - This is needed because Server Components cannot set cookies and the refresh cookie is invisible to them.
- **Client mutations:**
  - The generated fetch client sends same-origin credentials (the default), `Content-Type: application/json`, and `X-CSRF-Token` read from `document.cookie` (`__Host-tw_csrf`).
  - It sends `Idempotency-Key` where the spec requires it.
  - On 401: refresh, then retry once. On 409 `REFRESH_SUPERSEDED`: retry once.
- **SSE:** `new EventSource('/api/v1/tickets/{id}/events')` is same-origin, so cookies are sent. On error: refresh, then reconnect.
- **IP propagation.** Web copies the incoming `X-Real-IP` (set by Caddy) on SSR calls. The API trusts `X-Real-IP` only from the caddy and web container IPs.
- **Client storage.** TanStack Query cache lives in memory only (never persisted to localStorage or IndexedDB, ASVS 14.3.3) and is cleared on logout (14.3.1).

### D5. Server Actions: not used, and made unreachable

1. **Lint:** `no-restricted-syntax` bans the `'use server'` and `'use cache'` directives:

```js
// frontend/eslint.config.mjs (excerpt)
export default [
  // ...next/core-web-vitals, typescript-eslint strict-type-checked, jsx-a11y
  {
    rules: {
      'no-restricted-syntax': ['error',
        { selector: "ExpressionStatement[directive='use server']", message: 'Server Actions are disabled: call FastAPI /api/v1.' },
        { selector: "ExpressionStatement[directive='use cache']", message: "'use cache' is not used in Ticketward." },
      ],
    },
  },
]
```

2. **CI guard:** `rg -n "^\s*['\"]use server['\"]" frontend/src` must return nothing.
3. **Edge:** Caddy returns 405 for any non-GET/HEAD request that isn't `/api/*`. This covers header-invoked actions (`next-action`) and form-body progressive-enhancement posts. It also removes Server-Function-style POST attack surface from the Internet.
4. **Why not rely on Next.js's built-in Origin check:**
   - it allows requests with no `Origin`;
   - it had a `null`-origin bypass until 16.1.7;
   - our CSRF controls (Fetch Metadata + signed token) live in FastAPI, and Server Actions would bypass them entirely.
5. **If a future feature needs Server Actions,** it requires an ADR. Every action must then re-authenticate through the DAL, enforce authorisation and return minimal DTOs. `serverActions.allowedOrigins` stays unset (same-origin only), and the edge rule is narrowed to that route.

### D6. Dev environment parity

- Develop through **Caddy at `https://localhost`** (`tls internal`), proxying to `next dev` and `uvicorn --reload`. Caddy's `reverse_proxy` handles the HMR WebSocket.
- This keeps prefixed and `Secure` cookies, same-origin CSRF checks and the CSP identical to prod. It avoids the cross-origin `http://localhost:3000` → API path, where cookie prefixes and `Secure` behave inconsistently across browsers.
- Dev CSP differs only by `'unsafe-eval'` and dev `style-src 'unsafe-inline'`, both handled in `proxy.ts`.
- On the Windows workstation, run Next.js >= 16.3.3 (CVE-2026-75604), or run it inside the dev container.

### D7. Tests (P8; each is ASVS evidence)

- **Playwright:**
  - the HTML response has a CSP containing `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'` and a nonce;
  - two navigations yield different nonces;
  - a `securitypolicyviolation` listener records **zero** violations across the §17 demo flow, including the charts page;
  - no ticket data in `localStorage`/`sessionStorage`/IndexedDB after the flow;
  - logout clears the query cache.
- **HTTP (through Caddy):**
  - `POST /` → 405;
  - `GET /_next/image?url=/x.png&w=64&q=75` → 404;
  - a client-supplied `Content-Security-Policy` or `x-middleware-subrequest` request header has no effect;
  - API JSON responses carry the Caddy fallback CSP.
- **Lint test:** a fixture file containing `'use server'` fails ESLint.

---

## SPEC IMPACT

Disposition in spec v1.1: every item below was applied (A-24, ADR-0023 amended; `next` exact-pinned at >= 16.3.6).

| # | Spec location | Finding | Recommendation |
|---|---|---|---|
| SI-N1 | §12.7 CSP | Missing `object-src 'none'` (ASVS v5.0.0-3.4.3 requires it together with `base-uri 'none'`) | Add `object-src 'none'` |
| SI-N2 | §12.7 `style-src 'self' 'unsafe-inline'` ("aim for nonce") | A nonce can't cover `style=""` attributes | `style-src 'self' 'nonce-…'` + `style-src-attr 'unsafe-inline'`; nonce or CSS variables for shadcn `ChartStyle` |
| SI-N3 | §12.7 / ADR-0023 | A nonce CSP forces dynamic rendering everywhere (no static optimisation, ISR or PPR) | Accept it (authenticated per-user app) and state it in ADR-0023 |
| SI-N4 | §14.1 frontend layout | Next.js 16 uses `proxy.ts` (middleware deprecated); proxy/middleware auth has a CVE history (CVE-2025-29927 and 2026 bypasses) | Add `src/proxy.ts` for CSP only; auth lives in FastAPI and the `server-only` DAL |
| SI-N5 | §12.7 "Dev allow-list is `http://localhost:3000` with credentials" | Cross-origin dev diverges from prod cookies/CSRF (prefix and `Secure` behaviour on http://localhost) | Same-origin dev through Caddy `https://localhost`; drop the dev CORS path |
| SI-N6 | §14.2 frontend standards | Server Actions can't be disabled by config; the built-in check allows a missing `Origin` | Ban `'use server'`/`'use cache'` (ESLint + CI); edge 405 for non-GET/HEAD to Next.js |
| SI-N7 | §12.3 A06 / §14.1 | The Image Optimization API has had repeated advisories (incl. the 2026-09 AVIF RCE) | `images.unoptimized: true` + edge 404 on `/_next/image` |
| SI-N8 | §14.1/§14.2 versions | Floor per the advisory DB (2026-09-26): next >= 16.3.3 | Pin next 16.3.6 / react 19.3.0; 72 h patch SLA for critical/high |
| SI-N9 | §12.7 nonce | The Next.js docs example derives the nonce from `crypto.randomUUID()` (122 random bits) | 16-byte CSPRNG nonce (ASVS 11.5.1) |
| SI-N10 | §14.2 "Server Components by default" | SSR can't refresh sessions (the refresh cookie is path-scoped to the API; RSC can't set cookies) | Client `SessionRefresher` + DAL returning 401 → refresh flow (D4) |
| SI-N11 | §12.7 headers | Client-supplied `Content-Security-Policy` / `x-middleware-subrequest` request headers were the vector (or workaround target) in CVE-2026-44581 / CVE-2025-29927 | Caddy strips them (with `x-nonce`) on every request |

---

## IMPLEMENTATION CHECKLIST (P8 unless noted)

- [ ] Pin the versions (D1); Dependabot group; advisory subscription; SECURITY.md patch SLA.
- [ ] `src/proxy.ts` (D2), `next.config.ts` (D3), `NonceProvider`, ChartStyle change.
- [ ] `src/lib/api/server.ts` (DAL, `server-only`) + generated client (CSRF header, Idempotency-Key, single-flight refresh, 409 retry).
- [ ] `(app)` layout session gate + `SessionRefresher`; login page; logout clears caches.
- [ ] ESLint `no-restricted-syntax` rule + CI grep (D5).
- [ ] P9: Caddy edge rules (strip headers, 405 non-GET to Next, 404 `/_next/image`, fallback CSP) in the Caddyfile.
- [ ] P0/P8: dev through Caddy `https://localhost` (D6); update the README quick start accordingly.
- [ ] Playwright/HTTP tests (D7); axe checks continue (spec §14.2).

---

## OPEN RISKS / TO VERIFY

- **The advisory stream is very active** (the Sep 2026 batch had two criticals). Re-query the GitHub Advisory Database at P8 start and before each release. **The floor (16.3.3) will move.**
- **`style-src-attr 'unsafe-inline'`** still allows attribute-level CSS injection (no script execution). The residual risk is UI redress, mitigated by React escaping and no raw HTML.
- **Hydration behaviour** of a `nonce` prop on client-rendered `<style>` (the ChartStyle alternative). **Verify at P8**; prefer the CSS-variable approach.
- **ESLint selector** `ExpressionStatement[directive='use server']` must be validated with a lint fixture (ESTree directive representation). **Verify at P8.**
- **The `experimental.sri` path** is not chosen. If static rendering ever becomes important (e.g., a public marketing page), use SRI for that route only.
- **Next.js 16 proxy behaviour details** (matcher coverage of RSC/prefetch variants) have changed across 2026 patches. We don't depend on proxy for security, so this only affects CSP coverage. **Verify with the D7 tests.**

---

## LINKED ADR

- **ADR-0023**: record Next.js 16.3.x, `proxy.ts` CSP-only, nonce-driven dynamic rendering, no Server Actions (lint + edge), no image optimizer, the DAL pattern, same-origin dev via Caddy.
- Cross-refs: ADR-0020 (cookies/CSRF owned by FastAPI), ADR-0026 (Caddy edge rules), ADR-0027 (V3/V14 evidence).

---

## SOURCES (all accessed 2026-09-26)

- npm registry dist-tags: [next](https://registry.npmjs.org/next), [react](https://registry.npmjs.org/react), [tailwindcss](https://registry.npmjs.org/tailwindcss), [jose](https://registry.npmjs.org/jose)
- Next.js docs (v16.3.6): [Content Security Policy guide](https://nextjs.org/docs/app/guides/content-security-policy), [proxy.js file convention](https://nextjs.org/docs/app/api-reference/file-conventions/proxy), [Data security guide](https://nextjs.org/docs/app/guides/data-security), [serverActions config](https://nextjs.org/docs/app/api-reference/config/next-config-js/serverActions), [Self-hosting guide](https://nextjs.org/docs/app/guides/self-hosting)
- [Next.js source: app-router-headers.ts (v16.3.6)](https://github.com/vercel/next.js/blob/v16.3.6/packages/next/src/client/components/app-router-headers.ts)
- MDN: [CSP style-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src), [CSP style-src-attr](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src-attr)
- [shadcn/ui chart.tsx (new-york-v4)](https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/chart.tsx)
- GitHub Advisory Database API: `https://api.github.com/advisories?ecosystem=npm&affects=next` and `affects=react-server-dom-webpack`; key entries: [GHSA-2xp9-vwfh-vxw4](https://github.com/advisories/GHSA-2xp9-vwfh-vxw4), [GHSA-p293-qw3h-jr36](https://github.com/advisories/GHSA-p293-qw3h-jr36), [GHSA-89xv-2m56-2m9x](https://github.com/advisories/GHSA-89xv-2m56-2m9x), [GHSA-955p-x3mx-jcvp](https://github.com/advisories/GHSA-955p-x3mx-jcvp), [GHSA-6gpp-xcg3-4w24](https://github.com/advisories/GHSA-6gpp-xcg3-4w24), [GHSA-ffhc-5mcf-pf4q](https://github.com/advisories/GHSA-ffhc-5mcf-pf4q), [GHSA-267c-6grr-h53f](https://github.com/advisories/GHSA-267c-6grr-h53f), [GHSA-mq59-m269-xvcx](https://github.com/advisories/GHSA-mq59-m269-xvcx), [GHSA-9qr9-h5gf-34mp](https://github.com/advisories/GHSA-9qr9-h5gf-34mp), [GHSA-fv66-9v8q-g76r](https://github.com/advisories/GHSA-fv66-9v8q-g76r), [GHSA-f82v-jwr5-mffw](https://github.com/advisories/GHSA-f82v-jwr5-mffw)
- [React blog: Critical security vulnerability in React Server Components (2025-12-03, with 2026 updates)](https://react.dev/blog/2025/12/03/critical-security-vulnerability-in-react-server-components)

---

**Change log**: 2026-09-27: spec-impact disposition added (A-24); identifiers renamed for Ticketward.

**Document Version**: 1.1
**Next Update**: P8 start (re-query advisories; validate CSP with zero violations)
