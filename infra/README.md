# infra/

| Path | Status | Purpose |
|---|---|---|
| `postgres/init.sql` | **P0, active** | First-init script (superuser): pgcrypto, vector, citext, pg_trgm |
| `caddy/Caddyfile` | placeholder, P9 | TLS reverse proxy, security headers, same-origin `/api` routing |
| `otel/` | planned, P7 | OpenTelemetry Collector config (`collector.yaml`) |
| `prometheus/` | planned, P7 | Scrape config for `/metrics` (internal network only) |
| `grafana/` | planned, P7 | Provisioned dashboards (service health, pipeline, quality, KB, security) |
| `ollama/` | planned, P3/P4 | `Modelfile` for the fine-tuned GGUF (temperature 0) |

The observability services and Ollama join `compose.yaml` under the opt-in `observability`
and `ml` profiles; core services never sit behind a profile.
