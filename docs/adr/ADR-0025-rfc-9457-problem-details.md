---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §0 (reference patterns), §11 (error envelope, codes), §12.2, §12.3 (A02, A10:2025), §15 (request id), §24.3
informed: frontend and API client authors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0025: RFC 9457 problem details for all API errors

> **Amended in spec v1.1 (2026-09-27; change record A-25(j), W-m17, A-20, A-23).**
> * **Problem-type URIs are relative** (`/problems/<slug>`, **built in P0**), so no owned domain is needed. This
>   resolves the v1.0 concern this ADR flagged: absolute type URIs under a domain the project did not own.
> * **Codes added:**
>   * `BAD_REQUEST` 400, `METHOD_NOT_ALLOWED` 405, `UNSUPPORTED_MEDIA_TYPE` 415 (JSON-only API);
>   * `DEMO_LOCKED` 403 (privileged action in demo mode);
>   * `REFRESH_SUPERSEDED` 409 (refresh race grace; the client retries once);
>   * `MAINTENANCE` 503 (demo reset window).
> * Missing queue ownership on approve is `FORBIDDEN` 403, not `CONFLICT` 409 (A-25(k)).

## Context and Problem Statement

The owner's reference project sent `detail=str(e)` to clients, leaking exception text (spec §0). The spec replaces
that with **RFC 9457 problem+json**: safe messages, a `request_id`, and stack traces only in redacted server logs.

The envelope (§11) has `type`, `title`, `status`, `detail`, `instance`, plus the extension members `code`,
`request_id` and `errors[]`.

| Code | Status |
|---|---|
| `BAD_REQUEST` | 400 |
| `VALIDATION_ERROR` | 422 |
| `UNAUTHENTICATED` | 401 |
| `FORBIDDEN` | 403 |
| `CSRF_FAILED` | 403 |
| `DEMO_LOCKED` | 403 |
| `NOT_FOUND` | 404 |
| `METHOD_NOT_ALLOWED` | 405 |
| `CONFLICT` | 409 |
| `REFRESH_SUPERSEDED` | 409 |
| `IDEMPOTENCY_MISMATCH` | 422 |
| `PAYLOAD_TOO_LARGE` | 413 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 |
| `RATE_LIMITED` | 429 (+ `Retry-After`) |
| `UPSTREAM_UNAVAILABLE` | 503 |
| `MAINTENANCE` | 503 |
| `INTERNAL` | 500 (generic detail, never exception text) |

RFC 9457 (July 2023) obsoletes RFC 7807. A10:2025 (Mishandling of Exceptional Conditions) makes safe, consistent
error handling an explicit Top 10 concern.

What error format should every API response use?

## Decision Drivers

* No information leakage through errors (A02/A10:2025; ASVS V13.4, V16.5).
* A stable, machine-readable contract for the generated TypeScript client (`code`, not message parsing).
* Correlation: every error carries `request_id`, which matches logs and traces (§15).
* No dependency on an externally owned domain for `type` identifiers.

## Considered Options

1. RFC 9457 `application/problem+json` with relative `type` URIs and fixed extension members (chosen)
2. Ad hoc `{"detail": ...}` (the FastAPI default)

## Decision Outcome

Chosen option: "RFC 9457 with relative type URIs", because it is the IETF standard for HTTP API errors and separates
the stable contract (`type`, `code`) from human text. Relative `type` references such as `/problems/validation-error`
resolve against the API origin, so no third-party domain can ever serve content at a problem-type URL.

Rules:

* **Every** error path returns problem+json: `HTTPException`, `RequestValidationError`, Starlette 404/405, body-limit
  413, 415, rate-limit 429, CSRF 403, `DEMO_LOCKED` 403, idempotency 422, maintenance 503, and a last-resort 500
  handler.
* **Validation errors never echo input values.** Only `loc`, `msg` and `type` are returned. Pydantic's `input` and
  `ctx` are dropped, because they could contain a customer message or a password.
* `detail` strings come from an allow-listed catalogue. Exception messages are never interpolated. The 500 handler
  logs the redacted exception with `request_id`, and returns only generic text.
* `/problems/<slug>` pages may later carry short human-readable docs (`docs/api.md` anchors).
* Out of scope → 404; in scope but not allowed → 403 (ADR-0021).

### Consequences

* Good, because clients branch on `code`, and the generated TS client exposes a typed `Problem` shape, including
  `DEMO_LOCKED` and `REFRESH_SUPERSEDED` handling (single retry).
* Good, because support and debugging go through `request_id`, with no internal detail reaching the client.
* Good, because relative URIs remove the domain-ownership dependency entirely.
* Bad, because every framework default handler must be overridden, and missing one leaks the default shape. The tests
  below catch that.
* Neutral, because responses are more verbose than `{detail}`.

### Confirmation

* Semgrep custom rule: no `detail=str(e)` or exception objects in problem construction (§12.8).
* schemathesis (contract stage): every 4xx/5xx response has `Content-Type: application/problem+json`, a relative
  `type`, and `request_id` (custom check, proposed).
* `T-SEC-ERRORS`: one unit test per code, including Starlette 404/405, 413, 415, `DEMO_LOCKED` and `MAINTENANCE`. An
  injected failing dependency returns the generic `INTERNAL` body without exception text. Invalid `TicketCreate`
  bodies return errors without `input`.
* The OpenAPI document declares the problem schema for error responses, and the frontend client parses it (vitest),
  including the `REFRESH_SUPERSEDED` retry.

## Pros and Cons of the Options

### RFC 9457 with relative type URIs

* Good, because it is standard, extensible and leak-resistant, with correlation built in and no domain dependency.
* Bad, because it is more verbose, and every default handler must be customised.

### Ad hoc `{"detail": ...}`

* Good, because it is the framework default.
* Bad, because shapes are inconsistent, there are no stable codes, and it invites the `detail=str(e)` leakage the spec
  removes.

## More Information

* Spec (private): §0 (reference patterns), §11 (envelope, codes, 404/403 rule, 415, relative URIs), §12.2, §12.3,
  §12.8 (Semgrep rule), §14.2, §15, §24.3 (`DEMO_LOCKED`), §24.4 (`MAINTENANCE`). Change record A-25 (j)(k), W-m17,
  A-20, A-23.
* Standard: RFC 9457, "Problem Details for HTTP APIs" (obsoletes RFC 7807).
* Research: no dedicated topic.
* Related ADRs: ADR-0004, ADR-0020 (`REFRESH_SUPERSEDED`), ADR-0021 (404/403), ADR-0024, ADR-0035 (`DEMO_LOCKED`,
  `MAINTENANCE`).
* Revisit when: the API gains a v2.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (relative problem URIs, 400/405/415,
  `DEMO_LOCKED`, `REFRESH_SUPERSEDED`, `MAINTENANCE`).
