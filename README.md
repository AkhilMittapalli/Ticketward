# Ticketward

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
<!-- TBD (P9): CI, CodeQL and OpenSSF Scorecard badges once the GitHub path is final; HF model link (P10). -->

Ticketward is a human-in-the-loop customer-support resolution copilot. It fine-tunes a compact language model for ticket triage, retrieves approved knowledge with citations, drafts agent-reviewed replies, and produces context-preserving escalation briefs.

> **Status: Phase 0 (foundation), aligned with spec v1.1.** Repository, tooling, CI,
> Compose stack, API skeleton (health, RFC 9457 errors with relative `/problems/<slug>`
> types, security headers, per-route body limits, JSON-only bodies), frozen taxonomy and
> data contracts. Nothing below marked *TBD* exists yet, and no result is claimed until it
> is measured.

## Central claim

"Use the smallest reliable model for routine support work; use retrieval and policy controls to keep answers grounded; and stop automation when a human should decide."

Why this is not "chat with docs":

- **Resolution quality, not answers:** the product is measured on routing accuracy,
  critical-category recall, citation support and correct escalation, not on fluency.
- **Deterministic safety:** a versioned policy engine (not the model) decides when a human
  must decide; refunds, cancellations, disputes, security, legal/privacy and active
  incidents always go to a person, and nothing is ever auto-sent.
- **Evidence-first:** every factual sentence must cite an approved, current knowledge-base
  source; with weak evidence the system asks or escalates instead of guessing.

## Demo

*TBD (P11):* two-minute walkthrough video and a public demo on synthetic data (host chosen
at P9 after the latency benchmark, D-06).

## Results

*TBD (P10):* headline table for experiments E1-E6 (spec §9.7): every number as point [CI]
with n, plus the date, commit, `analysis_plan_sha` and links to the committed reports,
followed immediately by the limitations. The OOD table will carry its caveat (Bitext covers
only 5 of 12 intents and 2 of 5 critical classes). No numbers are published before they are
reproducible with one command.

## Architecture

*TBD (P9):* architecture diagram and request lifecycle. In short (spec §7): Next.js UI ->
FastAPI (`/api/v1`) -> async pipeline (PII masking -> SLM triage in parallel with hybrid
retrieval -> deterministic policy engine -> local SLM draft, gated frontier draft, or human
escalation -> citation verification) on PostgreSQL 16 + pgvector and Redis.

## Quick start (P0)

Prerequisites: Docker (Compose v2), Python 3.12+ (only to generate secrets),
[uv](https://docs.astral.sh/uv/) 0.9.6+, Node 22 + pnpm 10 (via corepack or `npx pnpm@10.34.5`).

```bash
git clone <repository-url> ticketward && cd ticketward
cp .env.example .env                  # placeholders only; sets TW_ENV=dev (unset means prod)
python scripts/gen_dev_secrets.py     # creates secrets/tw_db_password, secrets/tw_redis_password
docker compose up -d --build          # dev: also loads compose.override.yaml (127.0.0.1 ports)
curl -fsS http://127.0.0.1:8000/api/v1/health/live    # {"status":"ok"}
curl -fsS http://127.0.0.1:8000/api/v1/health/ready   # {"status":"ok","checks":{"db":"ok","redis":"ok"}}
docker compose down                   # add -v to delete the local database volume
```

Production-like run (compose.prod.yaml is never auto-loaded; nothing is published until the
P9 reverse proxy exists):

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

Services: `postgres` (pgvector 0.8.6 on Postgres 16; extensions pgcrypto, vector, citext,
pg_trgm), `redis` (password via secret file), `migrate` (one-shot `alembic upgrade head`)
and `api`. All run with a read-only root filesystem, `cap_drop: [ALL]`,
`no-new-privileges`, resource limits and health checks. The API docs are at
http://127.0.0.1:8000/api/docs in dev only.

*TBD:* `make seed` with synthetic demo data (P1/P9); the same-origin dev entry point
`https://localhost` through Caddy with `tls internal` (target per spec §12.7; the Caddy dev
config is not written yet); stub-LLM vs Ollama modes (P4), where the GGUF is downloaded by
revision SHA and verified by sha256.

### Local development (OneDrive-safe, risk R-13)

This repository may live inside OneDrive. **Never create virtualenvs inside it**; point uv
at a folder outside OneDrive before any `uv` command. Optional cache redirects keep
thousands of small files out of sync too.

```powershell
# PowerShell (Windows)
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\.venvs\ticketward-backend"
$env:PYTHONPYCACHEPREFIX    = "$env:LOCALAPPDATA\ticketward\pycache"   # optional
$env:MYPY_CACHE_DIR         = "$env:LOCALAPPDATA\ticketward\mypy"      # optional
$env:RUFF_CACHE_DIR         = "$env:LOCALAPPDATA\ticketward\ruff"      # optional
cd backend
uv sync --locked
uv run ruff check . ; uv run ruff format --check . ; uv run mypy src ; uv run pytest --cov
```

```bash
# bash (Linux, macOS, Git Bash): the Makefile sets UV_PROJECT_ENVIRONMENT per project
make install lint typecheck test-cov      # override with BACKEND_VENV=/path/outside/onedrive
```

Frontend: `cd frontend && corepack pnpm install --frozen-lockfile && corepack pnpm dev`
(or `npx pnpm@10.34.5 ...`). `node_modules/` and `.next/` are gitignored; OneDrive still
syncs them, so pause syncing during installs or keep a clone outside OneDrive (the git
remote is the source of truth).

## Reproduce benchmarks

*TBD (P2, P10):* `make eval-baselines`, `make eval-bakeoff`, `make eval-slm MODEL=<registry-id> SPLIT=test_synth`,
`make eval-e2e`, `make eval-retrieval`, `make bench-latency N=200`, `make report`
(spec §9.9). The targets exist today and print the phase in which they land.

## Train the model

*TBD (P3):* fine-tune on Kaggle/Colab T4 (`ml/`, spec §9.5): LoRA on an fp16 base for
models up to 2B, QLoRA for 3-4B, and every claim names the method actually used. The
section will give the config, the **measured** time and cost from the smoke test, and the
published adapter, merged model, GGUF and model card on the HF Hub.

## Safety model and security

| Rule | Summary |
|---|---|
| S-01 | No auto-send: an agent approves every outgoing message. |
| S-02 | A request for a person triggers immediate escalation. |
| S-03 | Forced human review: refunds, cancellations, payment disputes, security reports, legal threats, privacy requests, active incidents. |
| S-04-S-06 | Never invent account status, pricing, capabilities, refund eligibility or incident status. |
| S-07 | Factual statements need approved-source citations; a frontier model never compensates for missing evidence. |
| S-08 | Security and privacy/legal cases never go to a frontier model. |
| S-09 | Only approved knowledge is retrievable. |
| S-10 | Handoffs preserve context, entities, attempted steps and rationale. |
| S-11 | Sentiment and churn are labelled "Assistive signal". |
| S-12 | Synthetic, public or authorized de-identified data only. |

**Security:** Ticketward **targets OWASP ASVS 5.0 L2 with documented exceptions**
(self-assessed). The Met / N/A / Deferred counts, the last verification date and commit
are *TBD (P9)*: they come from the generated checklist and its CI completeness job. Known
gaps, stated plainly:

- **MFA is deferred** to after v1.0 (owner decision D-01; limitation L-17). Compensating
  controls: short sessions, login throttling and backoff, breached-password check, a
  15-character minimum, no public sign-up, synthetic data only.
- **Refresh-cookie prefix deviation:** the refresh cookie is `__Secure-tw_refresh` with
  `Path=/api/v1/auth` rather than `__Host-` (ASVS 3.3.3), to keep it off all non-auth
  traffic.
- **Single-host internal TLS deviation:** internal hops on the demo host run in plaintext
  on isolated networks (L-18); any multi-host deployment must enable TLS.
- **Demo-login pathway** and shared demo accounts in the public demo (P11).

Threat model: [docs/security/threat-model.md](docs/security/threat-model.md). Report
vulnerabilities privately as described in [SECURITY.md](SECURITY.md), which also states
the patch SLA.

## Repository tour

| Path | Contents |
|---|---|
| `backend/` | FastAPI service (`src/ticketward/`), Alembic migrations, tests, Dockerfile |
| `frontend/` | Next.js App Router UI (placeholder in P0) |
| `ml/` | offline ML package `tw_ml` (datagen, train, eval, export; P1-P3) |
| `schemas/json/` | exported JSON Schemas (draft 2020-12) of the data contracts |
| `docs/` | `openapi.json`, ADRs (`docs/adr/`), security docs (`docs/security/`), published research (`docs/research/`) |
| `infra/` | Postgres init, Caddy (P9), observability (P7), Ollama (P3/P4) |
| `data/`, `evals/` | provenance policy and evaluation layout (P1/P2) |
| `scripts/` | contract export, dev secrets, planned seed/reindex/backup tooling |

Architecture decisions: [docs/adr/](docs/adr/). Research behind them (published ERPROT
notes, D-04): `docs/research/`, published only through `make sync-research`, which refuses
private content. Tech stack: Python 3.12, FastAPI,
Pydantic v2, SQLAlchemy 2 (async) + asyncpg, Alembic, structlog, PostgreSQL 16 + pgvector,
Redis 7, Next.js 16 + React 19 + TypeScript (strict) + Tailwind 4, uv, pnpm, Docker Compose.

## Known limitations

Synthetic data cannot prove production performance; results are a technical
demonstration, not a deployment claim (L-01). Sentiment and churn risk are assistive
signals, not judgments about customers (L-02). A frontier fallback must comply with the
organization's privacy, security and vendor-review policies; it is off by default (L-03).
Retrieval quality limits generation quality; coverage and stale articles are monitored
(L-04). Human review remains essential for sensitive, financial, legal, privacy and
security matters (L-05). MFA is deferred to after v1.0 (L-17), and internal TLS is a
documented deviation on the single-host demo (L-18). The full list (L-01 to L-19) is
maintained in the specification.

## License, data provenance and disclaimer

- Code: [Apache License 2.0](LICENSE); see also [NOTICE](NOTICE).
- Data: synthetic, public or authorized de-identified only; every record carries
  provenance fields ([data/README.md](data/README.md)). Training and validation data come
  from generator Family A (`openai/gpt-oss-120b`), the synthetic test set from Family B
  (`mistralai/Mistral-Large-3-675B-Instruct-2512`), and **no Claude/Anthropic outputs are
  used in any training data**. The Bitext OOD set is referenced only by pointers, under
  CDLA-Sharing-1.0 with attribution (P1).
- **Taskmoor is fictional and not affiliated with any real company.** It is a B2B
  project-management SaaS invented for this project; all company names, customers,
  accounts, tickets, prices and knowledge-base content are synthetic.
- *TODO (P6, D-05):* add the **"Built with Llama"** attribution here, in the UI footer and
  in NOTICE when Llama Prompt Guard 2 lands (and for the base model if a Llama base wins).
- Acknowledgments: *TBD (P11)*.

## Resume bullet

*TBD (P11):* the brief's bullet is kept as historical input only. The published bullet
must be true when it is added: it names the fine-tuning method actually used (LoRA or
QLoRA) and pgvector (v1 does not use Qdrant, ADR-0005).
