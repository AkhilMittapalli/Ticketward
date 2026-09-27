# Ticketward - frontend

Next.js (App Router, 16.3.6), React 19.3.0, TypeScript strict (+ `noUncheckedIndexedAccess`),
Tailwind CSS 4, ESLint 9 (next/core-web-vitals + typescript-eslint strict-type-checked +
jsx-a11y), Prettier, pnpm 10. P0 ships a placeholder page; the agent workspace is P8.

## Commands

pnpm is pinned through `packageManager` (`pnpm@10.34.5`). Use `corepack pnpm ...` or, if
corepack is unavailable, `npx pnpm@10.34.5 ...`.

```bash
pnpm install --frozen-lockfile
pnpm dev            # http://localhost:3000
pnpm lint           # eslint, zero warnings allowed
pnpm typecheck      # next typegen + tsc --noEmit
pnpm format:check   # prettier
pnpm build          # production build (output: standalone)
```

`node_modules/` and `.next/` are gitignored. If the repository lives inside OneDrive
(risk R-13), expect sync churn from those folders: pause syncing during installs or keep a
clone outside OneDrive; the git remote is the source of truth.

## Security rules (ERPROT `nextjs-security`)

- **Versions**: `next`, `react` and `react-dom` are pinned to exact versions. Next.js
  releases below 16.3.3 carry critical advisories (including RCE on Windows-hosted
  servers); never downgrade and review every bump.
- **No Server Actions and no `"use cache"`.** ESLint (`no-restricted-syntax`) fails on either
  directive and a CI grep backs it up. All mutations go through the FastAPI API with cookie
  auth, a CSRF header and idempotency keys (see `src/lib/api/README.md`); pages are
  per-user and dynamically rendered.
- **No `middleware.ts` / `proxy.ts` for auth.** Next 16 renames `middleware.ts` to `proxy.ts`;
  neither exists yet. The nonce-based CSP lands in P8/P9 together with same-origin `/api`
  routing through Caddy.
- `next.config.ts`: `output: "standalone"`, `poweredByHeader: false`,
  `images.unoptimized: true` (no image-optimizer endpoint), baseline security headers.
- No third-party runtime requests: system fonts only (no `next/font/google`).

## Docker

`Dockerfile` builds the standalone output on `node:22-alpine` (pinned by digest) and runs it
as UID 10001. The Compose service (with Caddy in front) is added in P8/P9.
