# `src/lib/api/` - typed API client (planned, P8)

Nothing here is hand-written against the API. The client is generated from the backend
OpenAPI document so frontend types can never drift from the Pydantic contracts.

## Plan

1. **Types**: `openapi-typescript` generates `schema.d.ts` from `docs/openapi.json`
   (exported by `scripts/export_schemas.py`; CI fails if it is stale). Enum types come
   from the frozen taxonomy (`schemas/json/taxonomy.schema.json`, `taxonomy_version`
   `2026-09-v1`). A CI step diffs the generated file (spec §14.3 "frontend type-gen diff").
2. **Transport**: a thin `openapi-fetch` client:
   - `baseUrl: "/api/v1"` - same origin through the reverse proxy, so CORS stays off in
     production (spec §12.7).
   - `credentials: "same-origin"` - auth uses HttpOnly `__Host-`/`tw_*` cookies; tokens are
     never stored in `localStorage`/`sessionStorage`.
   - **CSRF (double submit)**: on unsafe methods (POST, PUT, PATCH, DELETE) read the
     non-HttpOnly `__Host-tw_csrf` cookie and send it as `X-CSRF-Token`. The server compares
     both in constant time and checks `Origin`/`Sec-Fetch-Site`.
   - `Idempotency-Key` (UUID) on `POST /tickets`, `/tickets/{id}/escalations`,
     `/drafts/{id}/approve`, `/feedback` (spec §11).
   - Propagates `X-Request-ID` and surfaces it in error toasts for support correlation.
3. **Errors**: every non-2xx response is RFC 9457 `application/problem+json`
   (`ProblemDetail`: `type`, `title`, `status`, `detail`, `code`, `request_id`, `errors[]`).
   The client maps `code` to UI behaviour (e.g. `UNAUTHENTICATED` -> refresh then login,
   `RATE_LIMITED` -> honour `Retry-After`) and never renders raw server text as HTML.
4. **State**: TanStack Query for client state; Server Components fetch on the server
   through the same client. Zod only at non-generated boundaries.

## Rules

- No Server Actions (see `frontend/README.md`); mutations always go through the API.
- Do not hand-edit generated files; regenerate with `pnpm gen:api` (added in P8).
