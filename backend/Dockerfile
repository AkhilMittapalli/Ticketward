# syntax=docker/dockerfile:1
# Ticketward API image (spec §12.9): multi-stage, non-root (UID 10001), no build
# tools or pip at runtime, read-only-root friendly. Base images are pinned by digest;
# Dependabot's docker ecosystem proposes digest bumps.
# Base: python:3.12-slim-trixie (spec v1.1 §12.9, A-29; bookworm is now Debian oldstable).
# Digest resolved 2026-09-27; the base choice and digests are verified again at P9
# (ERPROT python-packaging), where distroless remains the alternative.
# The same image runs the API (default CMD) and the one-shot `alembic upgrade head`.

ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.9.6@sha256:4b96ee9429583983fd172c33a02ecac5242d63fb46bc27804748e38c1cc9ad0d

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------- builder
FROM ${PYTHON_IMAGE} AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build

# Dependencies first (cached layer); uv.lock is authoritative (--frozen: no resolution).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# The project itself, installed as a regular (non-editable) package into /opt/venv.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="ticketward-api" \
      org.opencontainers.image.description="Ticketward API (FastAPI)" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    TW_SECRETS_DIR=/run/secrets \
    FORWARDED_ALLOW_IPS=127.0.0.1

# Unprivileged user; drop pip (not needed at runtime, avoids scanner noise).
RUN groupadd --system --gid 10001 rf \
    && useradd --system --uid 10001 --gid rf --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin rf \
    && python -m pip uninstall --yes --quiet pip \
    && rm -rf /root/.cache

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "ticketward.healthcheck"]

# FORWARDED_ALLOW_IPS (env) lists the reverse-proxy addresses whose X-Forwarded-* headers
# are trusted; keep it at loopback until the P9 proxy exists.
CMD ["uvicorn", "--factory", "ticketward.main:create_app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--no-server-header", "--no-access-log", \
     "--timeout-graceful-shutdown", "20"]
