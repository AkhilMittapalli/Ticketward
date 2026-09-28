# Ticketward developer entry points. Requires GNU make and a POSIX shell (Linux,
# macOS, WSL, Git Bash). Windows PowerShell users: the README lists the raw commands.
#
# Risk R-13: virtualenvs must live OUTSIDE the (OneDrive-synced) repository. Each uv
# command below gets its own UV_PROJECT_ENVIRONMENT; override per machine, e.g.
#   make install BACKEND_VENV=/c/Users/me/.venvs/ticketward-backend

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

BACKEND_VENV ?= $(HOME)/.venvs/ticketward-backend
ML_VENV ?= $(HOME)/.venvs/ticketward-ml
UV_BACKEND := cd backend && UV_PROJECT_ENVIRONMENT="$(BACKEND_VENV)" uv
UV_ML := cd ml && UV_PROJECT_ENVIRONMENT="$(ML_VENV)" uv
DATAGEN := $(UV_ML) run python -m tw_ml.datagen
PNPM ?= corepack pnpm
FRONTEND := cd frontend && $(PNPM)
COMPOSE ?= docker compose
COMPOSE_PROD := $(COMPOSE) -f compose.yaml -f compose.prod.yaml
PYTHON ?= python3

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ setup
.PHONY: install install-backend install-ml install-frontend secrets
install: install-backend install-ml install-frontend ## Install backend + ml (uv, locked) and frontend (pnpm, frozen)

install-backend: ## uv sync --locked into $(BACKEND_VENV)
	$(UV_BACKEND) sync --locked

install-ml: ## uv sync --locked into $(ML_VENV) (datagen, eval, dev groups; no torch)
	$(UV_ML) sync --locked

install-frontend: ## pnpm install --frozen-lockfile
	$(FRONTEND) install --frozen-lockfile

secrets: ## Create local Docker secret files in ./secrets (never committed)
	$(PYTHON) scripts/gen_dev_secrets.py

# ------------------------------------------------------------------ quality
.PHONY: lint format typecheck test test-cov frontend-check precommit
lint: ## Ruff (check + format --check) for backend/scripts/ml, ESLint + Prettier for frontend
	$(UV_BACKEND) run ruff check .
	$(UV_BACKEND) run ruff format --check .
	$(UV_BACKEND) run ruff check ../scripts
	$(UV_BACKEND) run ruff format --check ../scripts
	$(UV_BACKEND) run ruff check ../ml
	$(UV_BACKEND) run ruff format --check ../ml
	$(FRONTEND) lint
	$(FRONTEND) format:check

format: ## Auto-format and auto-fix (ruff, prettier)
	$(UV_BACKEND) run ruff check --fix .
	$(UV_BACKEND) run ruff format .
	$(UV_BACKEND) run ruff format ../scripts
	$(UV_BACKEND) run ruff format ../ml
	$(FRONTEND) format

typecheck: ## mypy --strict (backend src/tests/alembic, ml src/tests) and tsc --noEmit
	$(UV_BACKEND) run mypy src
	$(UV_BACKEND) run mypy
	$(UV_ML) run mypy src tests
	$(FRONTEND) typecheck

test: ## Backend + ml tests (backend integration tests skip unless TW_TEST_* is set)
	$(UV_BACKEND) run pytest
	$(UV_ML) run pytest

test-cov: ## Backend + ml tests with coverage gates (fail_under = 85)
	$(UV_BACKEND) run pytest --cov --cov-report=term-missing
	$(UV_ML) run pytest --cov

frontend-check: ## Frontend lint, typecheck, format check and production build
	$(FRONTEND) lint
	$(FRONTEND) typecheck
	$(FRONTEND) format:check
	$(FRONTEND) build

precommit: ## Run all pre-commit hooks on all files
	uvx pre-commit run --all-files

# ------------------------------------------------------------------ data (P1, tw_ml.datagen)
.PHONY: data-check datagen-dry-run leakage hardset-validate manifests-verify
data-check: ## Pools up to date + split plans (train, val, test_synth) are feasible
	$(DATAGEN) pools --check
	$(DATAGEN) plan --split train
	$(DATAGEN) plan --split val
	$(DATAGEN) plan --split test_synth

datagen-dry-run: ## Render 5 Family-A train prompts without calling any provider
	$(DATAGEN) generate --split train --family A --n 5 --dry-run

leakage: ## Leakage checks C1-C7 over the generated splits (local; data/generated is gitignored)
	$(DATAGEN) leakage

hardset-validate: ## Validate the owner-written hard set (quotas, attestation, 30/70 split)
	$(DATAGEN) hardset validate

manifests-verify: ## Verify content-hash manifests of frozen splits
	$(DATAGEN) manifest verify

# ------------------------------------------------------------------ contracts
.PHONY: export-schemas check-schemas
export-schemas: ## Export JSON Schemas (schemas/json) and OpenAPI (docs/openapi.json)
	$(UV_BACKEND) run python ../scripts/export_schemas.py

check-schemas: ## Fail if exported contracts are stale (CI)
	$(UV_BACKEND) run python ../scripts/export_schemas.py --check

# ------------------------------------------------------------------ research (D-04)
.PHONY: sync-research check-research scan-research
sync-research: ## Publish ../Core files/ERPROT to docs/research (refuses private content)
	$(UV_BACKEND) run python ../scripts/sync_research.py --prune

check-research: ## Fail if docs/research is stale versus the private working notes
	$(UV_BACKEND) run python ../scripts/sync_research.py --check

scan-research: ## Privacy scan of the published docs/research (CI)
	$(UV_BACKEND) run python ../scripts/sync_research.py --scan-only

# ------------------------------------------------------------------ compose
.PHONY: up up-prod down logs ps migrate compose-config run
up: ## Start the dev stack: docker compose up -d --build (auto-loads compose.override.yaml)
	$(COMPOSE) up -d --build

up-prod: ## Start prod-like: docker compose -f compose.yaml -f compose.prod.yaml up -d --build
	$(COMPOSE_PROD) up -d --build

down: ## Stop the stack (data volumes kept; use `docker compose down -v` to delete them)
	$(COMPOSE) down

logs: ## Follow logs of all services
	$(COMPOSE) logs -f --tail=200

ps: ## Show service status and health
	$(COMPOSE) ps -a

migrate: ## Run Alembic migrations in the one-shot migrate container
	$(COMPOSE) run --rm migrate

compose-config: ## Validate compose files (dev and prod)
	$(COMPOSE) config --quiet
	$(COMPOSE_PROD) config --quiet

run: ## Run the API locally with reload against the dev stack (reads ../.env)
	$(UV_BACKEND) run --env-file ../.env uvicorn --factory ticketward.main:create_app --reload --port 8000

# ------------------------------------------------------------------ security
.PHONY: security
security: ## bandit + pip-audit locally (gitleaks, Trivy, Semgrep run in CI; see security.yml)
	uvx --from "bandit[toml]==1.9.4" bandit -c backend/pyproject.toml -r backend/src scripts ml/src
	$(UV_BACKEND) export --frozen --no-emit-project --all-extras --format requirements-txt -o "$${TMPDIR:-/tmp}/tw-requirements.txt"
	uvx pip-audit==2.10.1 --requirement "$${TMPDIR:-/tmp}/tw-requirements.txt" --require-hashes --disable-pip --strict
	$(UV_ML) export --frozen --no-emit-project --all-extras --format requirements-txt -o "$${TMPDIR:-/tmp}/tw-ml-requirements.txt"
	uvx pip-audit==2.10.1 --requirement "$${TMPDIR:-/tmp}/tw-ml-requirements.txt" --require-hashes --disable-pip --strict
	@command -v gitleaks >/dev/null && gitleaks git --redact --no-banner . || echo "gitleaks not installed; runs in pre-commit and CI"

# ------------------------------------------------------------------ planned (later phases)
EVAL := $(UV_ML) run python -m tw_ml.eval
E1 := $(UV_ML) run python -m tw_ml.baselines.rules
BAKEOFF := $(UV_ML) run python -m tw_ml.eval.bakeoff
EVAL_DATE ?= $(shell date -u +%Y-%m-%d)
VAL_GOLD ?= ../data/generated/val/records.jsonl
HARD_DEV_GOLD ?= ../evals/hard_dev.v1.jsonl

.PHONY: seed eval-baselines bakeoff-dry-run eval-bakeoff-run eval-bakeoff eval-smoke eval-slm eval-e2e eval-retrieval bench-latency report demo-reset
seed: ## Seed synthetic demo data (planned in P1/P9)
	@echo "seed: planned in P1 (synthetic KB + accounts) and P9 (demo seed)"

eval-baselines: ## E1 (+ E2 seeds) on val + hard_dev -> baselines.md (P2; sealed splits refused)
	$(E1) --input $(VAL_GOLD) --out ../evals/runs/$(EVAL_DATE)/e1_val.jsonl
	$(EVAL) score --experiment E1 --split val --gold $(VAL_GOLD) --pred ../evals/runs/$(EVAL_DATE)/e1_val.jsonl --date $(EVAL_DATE)
	$(E1) --input $(HARD_DEV_GOLD) --out ../evals/runs/$(EVAL_DATE)/e1_hard_dev.jsonl
	$(EVAL) score --experiment E1 --split hard_dev --gold $(HARD_DEV_GOLD) --pred ../evals/runs/$(EVAL_DATE)/e1_hard_dev.jsonl --date $(EVAL_DATE)
	# E2 (Kaggle): $(EVAL) score --experiment E2 --split val --gold $(VAL_GOLD) --pred s42=.. --pred s1337=.. --pred s2026=.. --deployed-seed <val-best>
	$(EVAL) render --title "P2 baselines (val + hard_dev)" --out ../evals/reports/$(EVAL_DATE)/baselines.md $$(for f in ../evals/reports/$(EVAL_DATE)/E[12]_*.json; do printf -- '--report %s ' "$$f"; done)

bakeoff-dry-run: ## E3: check the bake-off config, holdout guard, inputs and prompt formats; calls nothing
	$(BAKEOFF) run --dry-run

eval-bakeoff-run: ## E3 runs on local Ollama: constrained, unconstrained (spec 9.4) and the CPU-latency sample (R-15)
	$(BAKEOFF) run
	$(BAKEOFF) run --unconstrained
	$(BAKEOFF) run --mode cpu-sample

eval-bakeoff: ## E3 bake-off: score each candidate's val (+ hard_dev) predictions -> bakeoff.md + ranking
	for p in ../evals/runs/bakeoff/*_val.jsonl; do [ -e "$$p" ] || continue; $(EVAL) score --experiment E3 --split val --gold $(VAL_GOLD) --pred "$$p" --date $(EVAL_DATE); done
	for p in ../evals/runs/bakeoff/*_hard_dev.jsonl; do [ -e "$$p" ] || continue; $(EVAL) score --experiment E3 --split hard_dev --gold $(HARD_DEV_GOLD) --pred "$$p" --date $(EVAL_DATE); done
	$(EVAL) render --title "P2 bake-off (E3, val + hard_dev)" --out ../evals/reports/$(EVAL_DATE)/bakeoff.md $$(for f in ../evals/reports/$(EVAL_DATE)/E3_*.json; do printf -- '--report %s ' "$$f"; done)
	$(BAKEOFF) rank --date $(EVAL_DATE)

eval-smoke: ## Spec 9.10 smoke eval (deterministic, no model; needs evals/smoke from P6); exits 1 on a gate miss
	$(E1) --input ../evals/smoke/smoke.v1.jsonl --out $${TMPDIR:-/tmp}/tw-e1-smoke.jsonl
	$(EVAL) score --experiment E1 --split smoke --gold ../evals/smoke/smoke.v1.jsonl --pred $${TMPDIR:-/tmp}/tw-e1-smoke.jsonl --out-dir $${TMPDIR:-/tmp}/tw-eval-smoke --fail-on-gate

eval-slm: ## Model-level eval: make eval-slm MODEL=<registry-id> SPLIT=test_synth (planned in P3)
	@echo "eval-slm: planned in P3 (MODEL=$(MODEL) SPLIT=$(SPLIT))"

eval-e2e: ## E5 end-to-end eval against the Compose stack (planned in P10)
	@echo "eval-e2e: planned in P10"

eval-retrieval: ## Retrieval Recall@k / MRR / nDCG + ablations (planned in P5)
	@echo "eval-retrieval: planned in P5"

bench-latency: ## Latency benchmark: make bench-latency N=200 (planned in P10)
	@echo "bench-latency: planned in P10 (N=$(N))"

report: ## Render evals/reports/<date>/ (planned in P10)
	@echo "report: planned in P10"

demo-reset: ## Nightly public-demo reset, then backup (planned in P11; spec §24.4)
	@echo "demo-reset: planned in P11"

# ------------------------------------------------------------------ housekeeping
.PHONY: clean
clean: ## Remove local caches and build output inside the repo
	find . -path ./.git -prune -o -type d \( -name __pycache__ -o -name .pytest_cache \
		-o -name .mypy_cache -o -name .ruff_cache -o -name .hypothesis \) -prune -exec rm -rf {} +
	rm -rf backend/.coverage backend/htmlcov frontend/.next
