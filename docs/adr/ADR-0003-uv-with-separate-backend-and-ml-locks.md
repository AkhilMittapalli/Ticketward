---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §9.5, §12.3, §12.8, §14.2, R-13; research python-packaging, qlora-training-on-t4
informed: contributors (via DEVELOPER_HANDOFF.md)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0003: Use uv with two independent projects and separate lockfiles

> **Amended in spec v1.1 (2026-09-27).**
> * **uv is pinned to 0.9.6.** A uv bump requires a re-lock of both projects (§14.2).
> * **CI uses `uv sync --locked`**, which fails if a lockfile is stale. **Docker uses `uv sync --frozen`** (install
>   exactly what is locked, no resolution).
> * The spec now says "two independent uv projects, never one shared workspace" (W-4). The v1.0 P0 wording
>   ("uv workspace") that this ADR flagged is fixed. "One shared workspace" is recorded as a rejected option.
> * The ml notebook export does not lock torch. The platform's torch is used and asserted (ADR-0002).
>   `huggingface-hub<2` is pinned, because transformers 5.17 requires < 2.0 (§9.5).
> * `scripts/uv_backend.py` wraps backend commands for repo-root invocation (§14.2).

## Context and Problem Statement

The repo holds two Python projects whose dependency graphs barely overlap and sometimes conflict (spec §14.1):

* `backend/`: the FastAPI service and the worker. It runs on CPU in Docker, so PyTorch must be the CPU build used by
  sentence-transformers, the reranker, the NLI verifier and the injection detector.
* `ml/`: data generation, training and evaluation on Kaggle/Colab T4. It uses the platform's CUDA torch, plus
  Transformers, PEFT, TRL, bitsandbytes (QLoRA only), datasets and MLflow.

Both projects must install reproducibly in CI, Docker and on the owner's laptop. The repo sits under OneDrive, where a
synced `.venv` can be corrupted (R-13).

How should dependencies be resolved, locked and installed so both projects are reproducible, auditable and isolated
from each other?

## Decision Drivers

* Reproducibility: hash-locked installs that fail on a stale lock in CI (DoD-1, DoD-4).
* Isolation: the CUDA/HF training stack never leaks into the CPU backend image (size, attack surface; A03:2025).
* Supply-chain auditability: locks feed pip-audit, Trivy and Dependabot (§12.8).
* Interpreter management without the global 3.14 (ADR-0002, R-04).
* Speed and ergonomics for a solo developer on Windows plus Linux containers.

## Considered Options

1. uv with **two independent projects and lockfiles** (`backend/uv.lock`, `ml/uv.lock`) (chosen)
2. uv with **one shared workspace** for both projects (one lockfile)
3. Poetry
4. pip-tools (`pip-compile` + `pip-sync`)
5. conda / mamba

## Decision Outcome

Chosen option: "uv with two independent projects and lockfiles", because it meets every driver with one fast tool.
It gives universal hash-locked resolution, `--locked`/`--frozen` installs and interpreter management, while keeping
the CUDA/HF graph completely separate from the production image.

Specifics:

* Two uv projects, each with its own `pyproject.toml` and `uv.lock`. **Never** a workspace, because a workspace
  shares one lockfile.
* `uv` pinned to **0.9.6** in CI (setup action pinned by SHA) and in the Dockerfiles. Bumping it is a deliberate PR
  that re-locks both projects.
* CI: `uv sync --locked`. Docker: `uv sync --frozen` (`--no-dev` in runtime images). Pre-commit: `uv lock --check`.
* The backend selects the **CPU** PyTorch build via an explicit index in `[tool.uv.sources]`. The ml project leaves
  torch to the platform in notebooks (asserted at runtime), and pins the rest of its stack (versions to re-verify at
  P3 are listed in spec §9.5).
* The only contract between the projects is the exported JSON Schemas in `schemas/json/` (spec §6). `ml/` never
  imports `ticketward` runtime code.
* On the laptop, `UV_PROJECT_ENVIRONMENT` and `UV_CACHE_DIR` point outside OneDrive (R-13).

**Verify at build (research `python-packaging`):** the uv upgrade policy, `--locked` vs `--frozen` semantics for the
pinned uv, the exact CPU torch index configuration, and Dependabot's uv support.

### Consequences

* Good, because the backend image never pulls CUDA or training wheels, so it stays smaller with fewer CVE-bearing
  components.
* Good, because `--locked` fails fast in CI when someone forgets to re-lock, so drift is caught in PRs.
* Good, because uv installs pinned Python builds, which removes the R-04 failure mode.
* Bad, because two locks must be maintained, and shared libraries (for example pydantic) may differ between them.
  This is acceptable because the projects share no runtime code. Dependabot and pip-audit cover both directories.
* Bad, because uv moves fast. The version pin plus a re-lock on every bump keeps changes deliberate.
* Neutral, because tools that need `requirements.txt` get it from `uv export` (verify flags for 0.9.6).

### Confirmation

* Pre-commit `uv lock --check` for both projects (§12.8).
* CI `setup` stage: `uv sync --locked` for both projects (fails on a stale lock). Docker build: `uv sync --frozen`
  (§14.2, §14.5).
* `security` job: pip-audit against both exported locks. `dependabot.yml` entries for `/backend` and `/ml` (§12.8).
* (proposed) The `build images` stage queries the syft SBOM to assert the backend image has no `nvidia-*`/CUDA
  packages.
* (proposed) A CI assertion that the uv version in the workflow, the Dockerfiles and `DEVELOPER_HANDOFF.md` all read
  0.9.6.

## Pros and Cons of the Options

### uv, two independent projects (chosen)

* Good, because it gives fast resolution and installs, interpreter management, universal hash-locked lockfiles and
  standard PEP 621 metadata.
* Good, because the graphs are fully isolated, including CPU vs CUDA torch.
* Bad, because the tool is young, so pinning and re-verification (R-14) are needed.

### uv, one shared workspace

* Good, because there is one lock and one resolution, and shared dependency versions are guaranteed to match.
* Bad, because a single lockfile forces one resolution across the CPU backend and the CUDA training stack. Torch
  variants and conflicting pins leak between them, and a training-only bump re-locks production.
* Bad, because it contradicts the spec's separate-lock requirement (§9.5, §14.2; W-4).

### Poetry

* Good, because it is mature and widely known, with lockfiles, dependency groups and PEP 621 support in 2.x.
* Bad, because it resolves more slowly, CPU/CUDA index selection is awkward, and interpreter management on Windows is
  external.

### pip-tools

* Good, because it outputs standard hashed `requirements.txt`, which every tool reads.
* Bad, because it has no interpreter or virtualenv management, and needs per-platform compiled files.

### conda / mamba

* Good, because it has first-class CUDA binaries and non-Python dependencies.
* Bad, because environments and images get heavy, mixing pip and conda is fragile, and there is a licence review
  burden on the default channel. The notebook platforms and images are pip-native.

## More Information

* Spec (private): §9.5 (separate ML lock, pins to re-verify, platform torch), §12.8 (pre-commit, Dependabot), §14.1,
  §14.2 (uv 0.9.6, `--locked`/`--frozen`, `scripts/uv_backend.py`), §16 P0, §21 R-04, R-13, R-14. Change record W-4,
  A-03, A-29 (g).
* Research: [python-packaging](../research/python-packaging.md) (uv pin and upgrade policy, projects vs workspace,
  wheels), [qlora-training-on-t4](../research/qlora-training-on-t4.md) (training-stack versions).
* Related ADRs: ADR-0002 (Python versions), ADR-0012 (training stack), ADR-0026 (images).
* Revisit when: the projects start sharing runtime code, or the audit tooling needs a lock format uv cannot export.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (uv 0.9.6, `--locked`/`--frozen`,
  workspace option rejected).
