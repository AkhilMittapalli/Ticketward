---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §9.5, §12.9, §14.2, R-04/R-14; research python-packaging, qlora-training-on-t4
informed: contributors (via docs/adr/README.md, DEVELOPER_HANDOFF.md)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0002: Pin Python 3.12 for the backend; the ML project allows 3.12–3.13

> **Amended in spec v1.1 (2026-09-27).**
> * The **ml** project now allows `requires-python = ">=3.12,<3.14"`, because Colab runs Python 3.13 and Kaggle runs
>   3.12 (A-03). The **backend stays pinned to 3.12** (`>=3.12,<3.13`).
> * Training notebooks use the **platform's torch** (2.11 on Kaggle and Colab), asserted at runtime, not locked in the
>   notebook export (§9.5).
> * The Docker base image is now **`python:3.12-slim-trixie`**, pinned by digest, because bookworm is Debian oldstable
>   (A-29). The choice and digests are verified at P9 (research `python-packaging`).

## Context and Problem Statement

Ticketward has two Python projects (spec §14.1):

* **backend/**: FastAPI, SQLAlchemy, Presidio/spaCy, sentence-transformers on CPU, bm25s/PyStemmer and argon2-cffi.
  It runs in Docker images, CI and on the owner's laptop.
* **ml/**: the CUDA training and evaluation stack (Transformers, PEFT, TRL, bitsandbytes for QLoRA, datasets,
  MLflow). It runs on Kaggle/Colab T4 notebooks, which dictate their own interpreter and torch builds.

Several of these libraries ship compiled extensions with wheels for a limited set of Python versions. The laptop has a
global Python 3.14, and risk R-04 is picking it up by accident. Risk R-14 is version drift between spec and build.

v1.0 pinned 3.12 everywhere. The ERPROT training research then found that Colab's runtime is **Python 3.13**. A
3.12-only `ml` project cannot install cleanly there without a separate interpreter, and replacing the platform
interpreter would also discard the platform's matched CUDA/torch build.

Which Python versions should each project support, and how is that enforced?

## Decision Drivers

* Binary wheel availability for compiled backend dependencies (spaCy, PyStemmer, argon2-cffi, tokenizers).
* Parity between laptop, CI and Docker for the backend (DoD-1: clean clone to working UI in ≤ 15 min).
* Training on free T4 notebooks without fighting the platform's interpreter or CUDA/torch build (R-03).
* Isolation from the global 3.14 interpreter (R-04).
* An upstream security-fix window covering the project's life.

## Considered Options

1. Backend pinned to 3.12; ml allows 3.12–3.13 and uses the platform's torch (chosen, v1.1)
2. Python 3.13 everywhere
3. Python 3.14 everywhere

v1.0 chose "3.12 everywhere". It is superseded by option 1 because of Colab 3.13.

## Decision Outcome

Chosen option: "backend pinned to 3.12; ml allows 3.12–3.13", because the backend keeps one deterministic,
well-tested interpreter across laptop, CI and images, while the training project runs natively on both Kaggle (3.12)
and Colab (3.13).

Enforcement:

| Where | Setting |
|---|---|
| `backend/` | `.python-version` = `3.12`; `requires-python = ">=3.12,<3.13"`; ruff `target-version = "py312"`; mypy `python_version = "3.12"` |
| `ml/` | `requires-python = ">=3.12,<3.14"`; torch **not** locked for notebooks (the platform build is asserted at runtime); `huggingface-hub<2` |
| Docker | `python:3.12-slim-trixie@sha256:<digest>` (or distroless for the API), multi-stage |
| Interpreters | uv-managed (ADR-0003), never the global 3.14 |

**Verify at build (R-14; research `python-packaging`):**
* at P0/P3, that every backend dependency publishes 3.12 wheels, and ml dependencies publish 3.12 and 3.13 wheels
  (bitsandbytes, causal-conv1d, spaCy models installed by URL + sha256);
* the Kaggle/Colab Python and torch versions at P3;
* the trixie image digests at P9.

### Consequences

* Good, because the backend image, CI and laptop share one interpreter, which removes "works on my machine" failures
  for the production code.
* Good, because training uses each platform's matched CUDA/torch build, avoiding custom wheel builds on T4 sessions.
* Good, because the `<3.13` (backend) and `<3.14` (ml) caps stop silent upgrades.
* Bad, because the ml project must be tested on two interpreters. Mitigation: its unit tests run on 3.12 and 3.13 in
  CI (proposed matrix), and the notebook asserts the torch version at start.
* Bad, because 3.12 appears to be in its security-fix-only upstream phase (source-only releases; verify). Mitigation:
  uv-managed builds, and weekly image rebuilds (§12.3 A03:2025).
* Neutral, because the backend needs nothing beyond 3.12 (PEP 695 generics, `asyncio.TaskGroup`).

### Confirmation

* CI runs `uv sync --locked` (ADR-0003), which fails when the interpreter violates `requires-python`. Docker runs
  `uv sync --frozen`.
* (proposed) `backend/tests/unit/test_runtime.py::test_python_version` asserts `sys.version_info[:2] == (3, 12)`.
  `ml/tests/test_runtime.py` asserts `(3, 12) <= sys.version_info[:2] < (3, 14)`.
* The ml smoke test (`python -m tw_ml.train.smoke`, §9.5) logs the Python, torch and CUDA versions to MLflow, and fails
  on unsupported versions.
* Trivy image scan on the digest-pinned `python:3.12-slim-trixie` base (§12.8); weekly Dependabot Docker updates.
* P0/P9 review: `.python-version`, `requires-python` and base-image digests present and matching this ADR.

## Pros and Cons of the Options

### Backend 3.12 pinned; ml 3.12–3.13 (chosen)

* Good, because the production runtime is pinned and mature, and training fits both notebook platforms.
* Bad, because there are two interpreter targets for `ml`, and a small risk of version-specific behaviour in training
  code.

### Python 3.13 everywhere

* Good, because it has a longer upstream support window, and it matches Colab.
* Bad, because the v1.0 spec recorded ML and compiled-dependency wheel gaps, and the backend gains nothing from 3.13.
  Moving the production runtime for a training-platform reason couples two independent projects.
* Neutral, because wheel coverage has improved since, so this is a candidate at the next revisit.

### Python 3.14 everywhere

* Good, because it is the newest release, and already on the laptop.
* Bad, because it is too new for the CUDA and NLP ecosystem, and using the global interpreter is exactly R-04.

## More Information

* Spec (private): §9.5 (hardware plan, platform torch, `huggingface-hub<2`), §12.9 (base images), §14.1, §14.2,
  §21 R-03, R-04, R-13, R-14. Change record A-03, A-29 (e).
* Research: [python-packaging](../research/python-packaging.md) (Python ranges, platform torch, wheels, base images),
  [qlora-training-on-t4](../research/qlora-training-on-t4.md) (Kaggle/Colab runtimes).
* Related ADRs: ADR-0003 (uv, separate locks), ADR-0012 (training stack), ADR-0026 (images).
* Revisit when: all backend dependencies are confirmed on 3.13+ and a release boundary (v1.x) is reached, or before
  3.12's upstream end of life (about Oct 2028; verify).
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (ml 3.12–3.13, platform torch,
  trixie base).
