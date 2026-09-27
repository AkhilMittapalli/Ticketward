# ticketward (backend)

FastAPI service for Ticketward. Python 3.12, `uv`, src layout (`src/ticketward/`).
The repository [README](../README.md) is the entry point; this file covers backend-only workflows.

## Environment (OneDrive / risk R-13)

The repository may live inside OneDrive. **Never create the virtualenv inside the repo.**
Point `uv` at a directory outside OneDrive before running any `uv` command:

```powershell
# PowerShell
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\.venvs\ticketward-backend"
```

```bash
# bash / zsh (Linux, macOS, Git Bash)
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ticketward-backend"
```

## Common commands (run from `backend/`)

| Task | Command |
|---|---|
| Install (locked) | `uv sync --locked` |
| Lint | `uv run ruff check .` and `uv run ruff format --check .` |
| Type check (strict) | `uv run mypy src` (or `uv run mypy` for src + tests + alembic) |
| Tests + coverage gate | `uv run pytest --cov` |
| Run API locally | `uv run --env-file ../.env uvicorn --factory ticketward.main:create_app --reload` |
| Migrations | `uv run alembic upgrade head` (needs a reachable Postgres) |
| New migration | `uv run alembic revision --rev-id 0002 -m "short description"` |
| Export JSON Schemas | `uv run python ../scripts/export_schemas.py` (`--check` in CI) |

Settings are read from `TW_*` environment variables and from secret files in
`TW_SECRETS_DIR` (default `/run/secrets`); see `src/ticketward/core/config.py` and
`../.env.example`.

## Layout

```
src/ticketward/
  main.py          app factory (create_app), lifespan, middleware + router wiring
  api/             errors (RFC 9457), middleware, routers, dependencies
  core/            settings, logging (redaction)
  domain/          frozen taxonomy, ports (protocols), domain errors - no infrastructure imports
  schemas/         Pydantic v2 contracts + JSON Schema export
  services/        application services (health checks in P0)
  db/              SQLAlchemy base + async session factory
alembic/           async migrations (0001_extensions)
tests/             unit/ security/ property/ contract/ integration/
```
