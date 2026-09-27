# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`0.x` until the Definition of
Done). Model versions are tracked separately in the model registry (spec §9.6).

## [Unreleased]

### Changed (spec v1.1 alignment)

- Taxonomy: escalation reasons gain `critical_category_suspected`, `queue_overridden_by_rule`
  and `pii_masking_failed` (system-emitted; `taxonomy_version` stays `2026-09-v1`,
  ADR-0029 amendment); the pinned fingerprint was updated deliberately.
- Contracts (`triage.v1`): `FieldConfidence.p_critical`; every confidence bounded 0..1;
  server-computed entity spans (`ResolvedEntity.source_span`) on `TriageResult` only;
  `ModelMeta.calibrator_version`, `calibration_fit_run_id`, `decoding_backend`,
  `logprobs_mode`; `TriageResult` rejects unrepaired `secondary_intents`.
- Errors: relative problem-type URIs (`/problems/<slug>`); new codes
  `UNSUPPORTED_MEDIA_TYPE` (415), `DEMO_LOCKED` (403), `REFRESH_SUPERSEDED` (409),
  `MAINTENANCE` (503).
- Per-route body limits (64 KB default; 256 KB tickets, 2 MB batch, 1 MB KB documents)
  replace the single 256 KB cap (`TW_BODY_LIMIT_*` settings); non-JSON bodies on unsafe
  methods get 415.
- Log scrubber also covers phone numbers and IBANs.
- API image on `python:3.12-slim-trixie` (digest-pinned); pgvector pinned as
  `0.8.6-pg16`; Compose network `backend` renamed `internal`.
- Frontend: `react`/`react-dom` 19.3.0; ESLint bans `'use cache'` as well as
  `'use server'`; footer disclaimer wording.
- CI: `pr-title` Conventional Commits check and a Server Actions grep; Semgrep rules for
  span exceptions, exception text in logs/spans and insecure randomness for secrets;
  Dependabot groups for `next`+`react*` and `opentelemetry-*`.
- Docs: README security claim ("targets OWASP ASVS 5.0 L2 with documented exceptions",
  MFA deferred), SECURITY.md patch SLA, PR template, NOTICE.

### Added

- Phase 0 foundation: repository layout, Apache-2.0 license, security policy,
  contributing guide, code of conduct, editor/git/pre-commit configuration.
- Backend (`backend/`, Python 3.12, uv): FastAPI app factory with lifespan; pydantic-settings
  configuration that refuses to boot in `prod` with debug, docs, CORS, non-JSON logs or
  weak/placeholder secrets; structlog JSON logging with key- and regex-based redaction
  (numeric LLM token counts kept); RFC 9457 problem+json errors; request-id,
  security-header and body-limit middleware; `GET /api/v1/health/live` and
  `GET /api/v1/health/ready`.
- Frozen taxonomy `2026-09-v1` (intents, queues, priorities, sentiment, churn, product
  areas, entity types, actions, escalation reasons, plans, channels, doc types) with
  critical/forced-review/frontier-denylist sets and default routing.
- Data contracts `TicketCreate`, `TriageModelOutput`, `TriageResult`, `ProblemDetail` and
  their JSON Schemas (draft 2020-12) in `schemas/json/`; OpenAPI in `docs/openapi.json`.
- Domain ports (LLM provider, keyword/vector retrievers, reranker, embedder, PII masker).
- Async SQLAlchemy session factory, declarative base with naming conventions, Alembic
  revision `0001` guarding pgcrypto, vector, citext and pg_trgm plus the `updated_at`
  trigger function.
- Docker: hardened multi-stage API and web images; Compose stack (postgres/pgvector, redis
  with password, one-shot migrate, api) with `compose.override.yaml` (dev, loopback ports)
  and `compose.prod.yaml`.
- Frontend skeleton: Next.js 16.3.6 App Router, React 19.3.0, TypeScript strict, Tailwind 4,
  ESLint (strict-type-checked, jsx-a11y, no Server Actions), Prettier.
- `ml/` package skeleton (`tw_ml`) with planned dependency groups.
- CI (lint, types, tests, contracts, frontend, compose validation), security scanning
  (gitleaks, pip-audit, bandit, Trivy, Semgrep), CodeQL, Dependabot, PR/issue templates.
