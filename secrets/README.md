# secrets/ (local Docker secrets, never committed)

Compose mounts these files at `/run/secrets/<name>` (spec §12.6). pydantic-settings reads
them through `TW_SECRETS_DIR`; the file name is the setting's variable name in lower case.

| File | Used by | Setting |
|---|---|---|
| `tw_db_password` | postgres (`POSTGRES_PASSWORD_FILE`), migrate, api | `TW_DB_PASSWORD` |
| `tw_redis_password` | redis (`requirepass`), migrate, api | `TW_REDIS_PASSWORD` |

Create them with strong random values (64 hex chars) from the repository root:

```bash
python scripts/gen_dev_secrets.py            # or: make secrets
python scripts/gen_dev_secrets.py --force    # rotate (then: docker compose down -v; the
                                             # Postgres password is fixed at first init)
```

- Only `*.example` placeholders and this README are tracked (see `.gitignore`); gitleaks
  runs in pre-commit and CI.
- The files are created world-readable (0644) because the containers run as non-root
  UIDs (postgres 999, redis 999, api 10001) and Compose cannot chown file-based secrets.
  That is acceptable for a single-user dev machine only. Deployments use the host's
  secret store instead (spec §12.6, P11).
- The API refuses to start in `prod` if a secret is missing, shorter than 16 characters
  or looks like a placeholder.
