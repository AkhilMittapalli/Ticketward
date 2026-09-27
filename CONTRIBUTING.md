# Contributing to Ticketward

Thanks for your interest. The specification (`TICKETWARD_SPEC.md`, kept in the project
knowledge base) is the source of truth; changes to its decisions go through an ADR in
`docs/adr/`.

## Ground rules

- **Data:** only synthetic, public or authorized de-identified data (S-12). Never commit
  real tickets, emails, names or credentials. Every dataset record carries provenance
  fields (`data/README.md`).
- **Secrets:** never in code, examples or docs; placeholders only. Local secrets live in
  `secrets/` (gitignored); gitleaks runs in pre-commit and CI.
- **Safety rules S-01 to S-12** are enforced in code and tests. A change that weakens one
  (for example auto-sending, or skipping forced review) will not be merged.
- **Taxonomy changes** (any enum in `backend/src/ticketward/domain/taxonomy.py`) need an
  ADR, a new `TAXONOMY_VERSION`, relabeling, retraining and a migration. The taxonomy
  fingerprint test fails otherwise.
- **Logging:** never log ticket text or PII; log ids and lengths. The redaction processor
  is a safety net, not a license.

## Development setup

See the README "Quick start" and "Local development". Key points:

- Python 3.12 via uv; set `UV_PROJECT_ENVIRONMENT` to a directory **outside OneDrive**
  (risk R-13) before any `uv` command. The Makefile does this for you (`BACKEND_VENV`).
- Node 22 + pnpm 10 (`corepack pnpm` or `npx pnpm@10.34.5`).
- Optional git hooks: `uvx pre-commit install` (hooks: ruff, ruff-format, mypy, gitleaks,
  file hygiene, lockfile check, frontend lint/format).

## Quality gates (run before opening a PR)

```bash
make lint typecheck test-cov      # backend: ruff, ruff format --check, mypy --strict, pytest (coverage >= 85%)
make frontend-check               # eslint, tsc, prettier --check, next build
make export-schemas               # regenerate schemas/json and docs/openapi.json if contracts changed
make compose-config               # validate compose files
```

Standards (spec §14.2): type hints everywhere, Google-style docstrings on public functions,
no bare `except`, no `detail=str(e)` (errors are RFC 9457 problem+json with safe messages),
async all the way, dependency injection through FastAPI `Depends` and the ports in
`domain/ports.py`. Every new route needs an auth dependency or an explicit entry in
`PUBLIC_ROUTES` with a justification (the route-auth test enforces this).

## Branches, commits and pull requests

- Trunk-based on `main`; short-lived `feat/...`, `fix/...`, `chore/...` branches; squash merge.
  Branch protection requires the status checks but no approvals (solo owner); review is a
  documented self-review against the PR checklist.
- [Conventional Commits](https://www.conventionalcommits.org/) **on the PR title**, e.g.
  `feat(policy): add legal-threat lexicon`: with squash merges the PR title becomes the
  commit message, and the CI `pr-title` job checks it.
- Fill in the pull request template: linked BR-IDs/ADR, tests, eval impact, security
  checklist, docs updated, breaking changes, self-review.
- Releases use SemVer (`0.x` until the Definition of Done); models are versioned separately.

## Dependency notes

- Lock files are authoritative: `backend/uv.lock` (`uv sync --locked` in CI,
  `--frozen` in Docker) and `frontend/pnpm-lock.yaml` (`--frozen-lockfile`). `ml/uv.lock`
  is created in P2/P3 and never contains torch/CUDA wheels.
- Starlette 1.7 prefers the newer `httpx2` package for its test client; the backend keeps
  the established `httpx` until `httpx2` has been reviewed, and silences only that
  specific deprecation warning in `backend/pyproject.toml`.
- Pin new GitHub Actions by full commit SHA and container images by digest.

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
