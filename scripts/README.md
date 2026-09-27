# scripts/

| Script | Status | Purpose |
|---|---|---|
| `export_schemas.py` | **P0** | Export JSON Schemas to `schemas/json/` and OpenAPI to `docs/openapi.json`; `--check` fails on drift (CI) |
| `gen_dev_secrets.py` | **P0** | Create `secrets/tw_db_password` and `secrets/tw_redis_password` (64 hex chars); `--force` rotates |
| `uv_backend.py` | **P0** | Run `uv` for `backend/` with the venv outside the repo (pre-commit hooks, risk R-13) |
| `sync_research.py` | **P0** | Publish the private `Core files/ERPROT` notes to `docs/research/` (owner decision D-04). Refuses local paths, links leaving the folder, real e-mails and secret-like strings; `--check` fails on drift, `--scan-only` is the CI privacy scan, `--prune` deletes orphaned generated notes |
| `seed.py` | stub, P1/P9 | Idempotent seed: KB sources, synthetic accounts, demo users per role |
| `reindex.py` | stub, P5 | Rebuild chunks, embeddings and the BM25 index after a model/KB change |
| `demo_reset.py` | stub, P11 | Nightly reset of the public demo |
| `gen_ts_types.sh` | planned, P8 | `openapi-typescript` from `docs/openapi.json` |
| `backup.sh` / `restore.sh` | planned, P9 | `pg_dump -Fc` to encrypted storage and the restore drill (RPO 24 h, RTO 1 h) |

Stubs exit with status 1 and name their phase, so nothing silently pretends to work.
Python scripts share the backend lint configuration (`scripts/ruff.toml`) and are
type-checked by the backend's `mypy` run. Scripts that import `ticketward` run in the
backend environment: `uv run --project backend python scripts/<name>.py`.
