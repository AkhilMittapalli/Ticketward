# syntax=docker/dockerfile:1
# Ticketward web UI (spec §12.9): multi-stage build of the Next.js standalone output,
# non-root runtime (UID 10001), no package manager or build tooling at runtime.
# Base image pinned by digest (resolved 2026-09-26); Dependabot proposes bumps.

ARG NODE_IMAGE=node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402

# ------------------------------------------------------------------------------- deps
FROM ${NODE_IMAGE} AS deps
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable pnpm \
    && pnpm install --frozen-lockfile

# ------------------------------------------------------------------------------ build
FROM ${NODE_IMAGE} AS build
ENV NEXT_TELEMETRY_DISABLED=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN corepack enable pnpm \
    && pnpm build

# ---------------------------------------------------------------------------- runtime
FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup -S -g 10001 rf && adduser -S -D -H -u 10001 -G rf rf \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
        /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack
WORKDIR /app
COPY --from=build --chown=root:root /app/.next/standalone ./
COPY --from=build --chown=root:root /app/.next/static ./.next/static
COPY --from=build --chown=root:root /app/public ./public
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "server.js"]
