# tw-ml - offline ML (datagen, training, evaluation, export)

Separate uv project from the backend (ADR-0003: separate locks). It never imports the backend
package: the only shared contract is the exported JSON Schemas in `schemas/json/`, from which
`tw_ml.datagen.taxonomy` loads every enum (a test fails when the two drift). See spec §9.

| Path | Contents | Phase |
|---|---|---|
| `src/tw_ml/datagen/` | generation matrix and sampler, prompts, providers, generation loop, rule-checker, leakage C1-C7, label QA, manifests, hard set, Bitext OOD | P1 (built) |
| `src/tw_ml/eval/` | metrics, bootstrap CIs, E1-E6 reports | P2, P10 |
| `src/tw_ml/train/` | LoRA/QLoRA SFT (TRL), ModernBERT baseline | P3 |
| `src/tw_ml/export/` | adapter merge, GGUF, Ollama Modelfile, HF Hub publishing | P3 |
| `configs/` | `datagen.yaml`, `datagen_prices.v1.yaml`, `leakage.yaml` (training configs from P2) | P1+ |
| `prompts/datagen/` | generator prompt families `pa_persona.v1`, `pb_scenario.v1` | P1 |
| `tests/` | offline test suite (FakeProvider, tiny fixtures; no network) | P1+ |

## Environment (OneDrive / risk R-13)

Never create the virtualenv inside the repo, and never use the global Python 3.14:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\.venvs\ticketward-ml"   # PowerShell
$env:UV_PYTHON_PREFERENCE = "only-managed"                               # uv-managed 3.12
```

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ticketward-ml"              # bash
export UV_PYTHON_PREFERENCE=only-managed
```

`requires-python = ">=3.12,<3.14"`: 3.12 locally and on Kaggle, 3.13 on Colab; `.python-version`
selects 3.12.

## Dependency groups and the lock

`ml/uv.lock` is committed; CI and local installs use `uv sync --locked`.

| Group | Contents | Default |
|---|---|---|
| (project) | pydantic, pyyaml | always |
| `datagen` | httpx, numpy, scipy (exact sparse Jaccard), `datasketch==2.0.0` (exact pin, ERPROT), pydantic, pyyaml | yes |
| `eval` | numpy, scipy, scikit-learn | yes |
| `dev` | pytest, pytest-cov, hypothesis, ruff, mypy, scipy-stubs, types-PyYAML | yes |
| `bitext` | datasets, huggingface-hub<2 (only for the owner-run OOD build) | no |
| `train` | accelerate, bitsandbytes, datasets, huggingface-hub<2, peft, transformers, trl (planned, P3) | no |
| `export` | huggingface-hub<2, jinja2, safetensors (planned, P3) | no |

```bash
cd ml
uv lock                                               # after any pyproject change
uv sync --locked                                      # datagen + eval + dev
uv run ruff check && uv run ruff format --check
uv run mypy src tests
uv run pytest --cov                                   # coverage gate 85%
```

**torch and CUDA wheels never enter the lock** (A-03). `[tool.uv] override-dependencies` replaces
torch with a never-true marker, so the lock resolves `peft`, `accelerate` and `bitsandbytes`
without torch or any `nvidia-*`/`triton` wheel; on Kaggle/Colab the platform's CUDA torch
satisfies them. Install the training group into the platform interpreter, e.g.
`uv pip install --system -e . --group train`, after checking
`python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`.

`sentence-transformers` (optional leakage check C3) is not in the lock either, because it would
pull torch. Install `sentence-transformers==6.1.0` into the environment that runs the check and pin
the bge-small revision in `configs/leakage.yaml`; otherwise C3 is skipped and the report says so.

## P1 data commands

```bash
uv run python -m tw_ml.datagen plan --split train                 # quotas, strata, coverage
uv run python -m tw_ml.datagen generate --split train --family A --n 50 --dry-run
uv run python -m tw_ml.datagen generate --split train --family A --n 50 --budget-usd 1
uv run python -m tw_ml.datagen validate --split train
uv run python -m tw_ml.datagen leakage                            # evals/reports/leakage_<date>.json
uv run python -m tw_ml.datagen qa sample --out-dir <folder>       # 540-record blind audit
uv run python -m tw_ml.datagen manifest freeze --split test_synth --file data/generated/test_synth/records.jsonl
uv run python -m tw_ml.datagen hardset validate
uv run python -m tw_ml.datagen pools --check
```

A real `generate` needs `TW_DATAGEN_A_API_KEY` (or `_B_`), refuses Anthropic endpoints and models,
checks that the vendor-terms snapshot is at most 30 days old (`--terms-reviewed` after a
re-review), prices every call before making it, and stops at `--budget-usd` or the $15 total.
Output goes to `data/generated/<split>/` (gitignored) and resumes where it stopped.

## Rules

- Only synthetic, public or authorized de-identified data (S-12, `data/README.md`); never Claude
  outputs in any dataset (A-01).
- Models load `safetensors` only, `trust_remote_code=False`, pinned HF revisions (§12.3 A08).
- Notebooks are thin wrappers around `python -m tw_ml.<module>`; logic lives in `src/`.
