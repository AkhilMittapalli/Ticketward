---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §8; spec §6, §11, §12.2, §12.3, §14.2; research auth-cookie-jwt-csrf
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1 alignment; decision unchanged)
---

# ADR-0004: FastAPI with Pydantic v2 for the API and data contracts

> **Amended in spec v1.1 (2026-09-27): alignment only; the decision is unchanged.**
> * FastAPI ≥ 0.141 no longer flattens included routers. Every router therefore declares its **full `/api/v1/...`
>   prefix**, and the route-auth test iterates routes through FastAPI's route-iteration API (A-29).
> * The app runs **two listeners**: the public API (through Caddy), and an **internal-only service-token listener** on
>   a port Caddy does not route (A-25(l), ADR-0020).
> * The API is JSON-only. Other media types get **415** (ADR-0025). Body limits are per route (A-25(g)): 256 KB for
>   tickets, 2 MB for batch, 1 MB for KB bodies, 64 KB for every other route. Both are **built in P0**
>   (`JsonBodyMiddleware` and the per-route limits with the 64 KB default).
> * Constrained decoding uses a derived **decoding schema** (refs inlined, every field required), exported by
>   `scripts/export_schemas.py`, not the raw `model_json_schema()` (§6).
> * `docs/openapi.json` is exported by a script and diffed in CI (drift check + `oasdiff`). Swagger UI is non-prod
>   only, never in the public demo.

## Context and Problem Statement

The brief's stack table recommends "Python, FastAPI, Pydantic" for the backend (brief §8, BR-036). The spec leans on
one schema pipeline (§6). Pydantic v2 models in `backend/src/ticketward/schemas/` are:

1. the API request/response contracts (`TicketCreate` with `extra="forbid"`, `TriageResult`, `DraftResponse`, …);
2. exported to JSON Schema (draft 2020-12) in `schemas/json/`, plus a derived decoding schema for constrained
   decoding (ADR-0014);
3. the input for the frontend TypeScript types (`openapi-typescript`, ADR-0023);
4. the validity gate: nothing unvalidated reaches the UI, and response validation stays on (§6.6 step 7).

The API is I/O-bound and async: asyncpg, httpx to Ollama and (through the egress proxy) Anthropic, Redis, and SSE
streams. It needs dependency injection for ports (`domain/ports.py`), and an OpenAPI 3.1 document that CI can diff.

Which web framework and validation library should carry these responsibilities?

## Decision Drivers

* One source of truth for contracts: Pydantic → JSON Schema / decoding schema → TS types (BR-027, M-04).
* Async-native I/O for a pipeline that waits on models, the database and Redis.
* Accurate OpenAPI 3.1 for contract tests (schemathesis) and breaking-change checks (`oasdiff`).
* Security posture: strict validation, mass-assignment prevention (`extra="forbid"`), response filtering, and an
  enumerable route table for deny-by-default tests.
* Typing: `mypy --strict` with the pydantic plugin (§14.2).
* Brief alignment (BR-036).

## Considered Options

1. FastAPI + Pydantic v2 (chosen)
2. Django + Django REST Framework
3. Litestar

## Decision Outcome

Chosen option: "FastAPI + Pydantic v2", because it is the brief's recommendation, and the same Pydantic models serve
as API contracts, the source of the constrained-decoding schema, and the OpenAPI input for type generation, with no
translation layer.

Hardening implied (the framework gives none of this for free):

* RFC 9457 handlers for every error path, including Starlette's 404/405, body-limit 413 and 415 (ADR-0025).
* Docs endpoints disabled in `prod` and in the demo. Prod startup validation refuses docs, debug, CORS and non-JSON
  logs (§12.3 A02:2025, §14.2).
* JSON-only (415 otherwise). No form/multipart extras installed, since no route needs them.
* Explicit `response_model` on every route, so internal columns (`message_enc`, `password_hash`, …) cannot leak.
* Full `/api/v1` prefix declared on every router. A test enforces it (A-29).
* In-house security middleware (`api/middleware/{request_id,security_headers,csrf,body_limit,client_ip,demo_mode}.py`,
  §14.1), following ADR-0020 and ADR-0035.

**Verify at build (R-14):** pin FastAPI, Starlette and Pydantic at P0. Confirm the route-iteration API and OpenAPI
3.1 output for the pinned FastAPI.

### Consequences

* Good, because contract drift is structurally impossible. A schema change moves JSON Schema, the decoding schema,
  OpenAPI and TS types together, and CI diffs them.
* Good, because Pydantic v2's compiled core keeps strict validation cheap, including on model outputs (§6.6).
* Good, because `Depends` gives clean injection of ports and role checks (`require_roles(...)`, ADR-0021).
* Bad, because FastAPI ships no authentication, CSRF, sessions or admin, which leaves more security-critical code to
  own. Mitigation: ≥ 95% branch coverage on `core/security` (§14.3), the security suite, and ASVS tracking
  (ADR-0027).
* Bad, because the default `{detail: ...}` error shape is the reference-project weakness (§0), so it is overridden
  everywhere (ADR-0025).
* Neutral, because FastAPI/Starlette release often, so Dependabot and pip-audit are mandatory. The repo keeps `httpx`
  rather than Starlette's `httpx2` preference (owner decision pending, L-7).

### Confirmation

* Contract stage (§14.5 step 5): schemathesis finds no 500s on fuzzed input; OpenAPI drift check against
  `docs/openapi.json`; `oasdiff` breaking-change check.
* JSON Schema and decoding-schema snapshot tests. CI asserts the decoding-schema key order equals the training-target
  key order (§6). Frontend type-gen diff.
* `T-SCHEMA-gate` (BR-027): an invalid model output never reaches a response.
* `T-SEC-CONFIG-prod`: with `TW_ENV=prod`, docs return 404, and the app refuses to boot with debug, CORS, non-JSON
  logs, or a missing, short or placeholder secret.
* `T-SEC-ROUTE-AUTH`: FastAPI route iteration finds every route, asserts an explicit auth dependency, and asserts
  the full `/api/v1` prefix (A-29).
* `T-SEC-SVC-listener` (proposed name): service tokens are accepted only on the internal listener. The public app
  rejects them.
* Lint stage: `mypy --strict` with the pydantic plugin.

## Pros and Cons of the Options

### FastAPI + Pydantic v2

* Good, because it is the brief's recommendation, async-first on ASGI, and generates OpenAPI and JSON Schema from the
  same models.
* Bad, because it has few built-in security features, and returning ORM objects without a `response_model` can leak
  data (handled by review and tests).

### Django + DRF

* Good, because it includes authentication, sessions, CSRF, admin, ORM and migrations, with mature defaults.
* Bad, because DRF is sync-first, and its serializers would duplicate the Pydantic contracts still needed for
  decoding schemas and TS types. It also departs from the brief.

### Litestar

* Good, because it is fast and well designed, with DI, CSRF middleware and OpenAPI built in.
* Bad, because its community is smaller and reviewers know it less. It departs from the brief with no decisive
  benefit.

## More Information

* Spec (private): §6 (contracts, decoding schema), §6.6 (validity gate), §7.1 (layering), §11 (API, OpenAPI, 415,
  service-token listener), §12.2 (Elevation: route iteration), §12.3, §14.1, §14.2, §14.3. Change record A-25 (g)(l),
  A-29 (f), L-7.
* Brief (private): §5 (JSON schema before UI), §8 (stack). BR-027, BR-036.
* Research: [auth-cookie-jwt-csrf](../research/auth-cookie-jwt-csrf.md) (the security middleware we build). No
  dedicated framework-selection topic.
* Related ADRs: ADR-0006, ADR-0014, ADR-0020, ADR-0021, ADR-0023, ADR-0025, ADR-0035.
* Revisit when: a need arises that FastAPI/Starlette cannot meet, or on a FastAPI major-version change.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 updated for spec v1.1 (router prefixes, internal listener,
  415, decoding schema; decision unchanged).
