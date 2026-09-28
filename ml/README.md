# tw-ml - offline ML (datagen, training, evaluation, export)

Separate uv project from the backend (ADR-0003: separate locks). It never imports the backend
package: the only shared contract is the exported JSON Schemas in `schemas/json/`, from which
`tw_ml.datagen.taxonomy` loads every enum (a test fails when the two drift). See spec §9.

| Path | Contents | Phase |
|---|---|---|
| `src/tw_ml/datagen/` | generation matrix and sampler, prompts, providers, generation loop, rule-checker, leakage C1-C7, label QA, manifests, hard set, Bitext OOD | P1 (built) |
| `src/tw_ml/eval/` | metrics M-01..M-04 and M-07a..d, statistics (Wilson, stratified bootstrap B = 10,000, paired tests, Holm, seeds), gates, the sealed-split guard, `eval_report.v1` + Markdown; `python -m tw_ml.eval score/compare/render` | P2 (built), P10 |
| `src/tw_ml/baselines/` | E1 rules baseline (`python -m tw_ml.baselines.rules`) and the policy-lexicon reference parser for `backend/policy/lexicons/` | P2 (built) |
| `src/tw_ml/train/` | E4 LoRA (<= 2B) / QLoRA (3-4B) SFT with TRL, the E2 ModernBERT baseline, the R-21 smoke test, Hub resume; `python -m tw_ml.train --config ... --seed N [--dry-run]` (runs on Kaggle/Colab, see `docs/training.md`) | P2/P3 (built; not run yet) |
| `src/tw_ml/export/` | adapter merge, GGUF, Ollama Modelfile, HF Hub publishing | P3 |
| `configs/` | datagen, leakage, rules baseline, bake-off and the training configs (`sft_*.yaml`, `encoder_modernbert.yaml`) | P1+ |
| `requirements/train.txt` | hashed export of the lock for the notebooks (no torch) | P3 |
| `notebooks/` | `train_kaggle.ipynb`, `train_colab.ipynb`: thin wrappers, committed without outputs | P2/P3 |
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
| `eval` | httpx (the bake-off's Ollama client), numpy, scipy, scikit-learn | yes |
| `dev` | pytest, pytest-cov, hypothesis, ruff, mypy, nbformat (notebook validation), scipy-stubs, types-PyYAML | yes |
| `bitext` | datasets, huggingface-hub<2 (only for the owner-run OOD build) | no |
| `export` | huggingface-hub<2, jinja2, safetensors (planned, P3) | no |
| **`train` extra** | trl 1.14.0, transformers 5.17.0, peft 0.21.0, accelerate 1.15.0, datasets>=4.7.0, bitsandbytes 0.50.2 (Linux), huggingface-hub<2, mlflow, codecarbon (spec §9.5 pins, P3.7) | no: platform only |

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
satisfies them. The `train` extra is never installed locally (`uv sync` installs no extras). On the
platform the notebooks install its hashed export and then the package without dependencies:

```bash
python -m pip install --no-deps --require-hashes -r ml/requirements/train.txt
python -m pip install --no-deps -e ./ml
```

Regenerate the export after every lock change (the header repeats the command) and commit both:

```bash
cd ml && uv export --frozen --no-emit-project --extra train --no-default-groups --group eval   --format requirements-txt --prune torch --output-file requirements/train.txt
```

`tests/test_train_requirements.py` fails when the export drifts from the lock (package set,
versions, hashes) or would install torch, triton or a CUDA `nvidia-*` wheel. The one `nvidia-*`
package it allows is `nvidia-ml-py`, the pure-Python NVML binding that codecarbon imports.

### Licenses of the new dependencies (P3.7)

Recorded for the pinned versions. The `train` extra is not installed locally, so its licenses
come from the projects' published metadata and were not re-read in this environment: check
them on the platform after the install
(`python -c "import importlib.metadata as m; print(m.metadata('trl')['License'])"`, per package).

| Package | Version | License | Where |
|---|---|---|---|
| trl | 1.14.0 | Apache-2.0 | `train` extra |
| transformers | 5.17.0 | Apache-2.0 | `train` extra |
| peft | 0.21.0 | Apache-2.0 | `train` extra |
| accelerate | 1.15.0 | Apache-2.0 | `train` extra |
| datasets | 5.0.1 | Apache-2.0 | `train` extra |
| bitsandbytes | 0.50.2 | MIT | `train` extra (Linux) |
| huggingface-hub | 1.33.0 | Apache-2.0 | `train` extra |
| mlflow | 3.16.1 | Apache-2.0 | `train` extra |
| codecarbon | 3.3.1 | MIT | `train` extra |
| nvidia-ml-py | 13.615.71 | BSD-3-Clause | via codecarbon |
| pycountry | 26.2.16 | LGPL-2.1 (weak copyleft) | via codecarbon. Accepted (lead, 2026-09-28): it is installed unmodified from PyPI and imported only on the training platform; Ticketward never modifies, bundles or distributes it (no image, wheel or published artifact contains it) |
| httpx | 0.28.1 | BSD-3-Clause (read from the installed metadata) | `eval` group |
| nbformat | 5.11.1 | BSD-3-Clause (read from the installed metadata) | `dev` group |

## Training (P2/P3; runs on Kaggle/Colab)

Owner runbook: [`docs/training.md`](../docs/training.md). Locally only the dry run works (no
torch, no model download, nothing written):

```bash
uv run python -m tw_ml.train --config configs/sft_qwen35_2b.yaml --seed 42 --dry-run --allow-unverified
uv run python -m tw_ml.train --config configs/encoder_modernbert.yaml --seed 42 --dry-run --allow-unverified
```

On the platform (from the repository root, as the notebooks run them):

```bash
python -m tw_ml.train.hub fetch-data --repo <hf_user>/<dataset> --revision <sha>   # train/ + val/ only
python -m tw_ml.train.smoke --config ml/configs/sft_qwen35_2b.yaml --steps 20           # R-21
CUDA_VISIBLE_DEVICES=0 python -m tw_ml.train --config ml/configs/sft_qwen35_2b.yaml --seed 42
python -m tw_ml.train.hub push-run --config ml/configs/sft_qwen35_2b.yaml --seed 42
```

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

## Generator API keys (never in files or command lines)

Real generation needs a key for each generator family. Keys are kept in the operating system's
credential store (Windows Credential Manager on Windows) through `keyring`. They never go in `.env`
or any file inside this OneDrive-synced repository, and never on a command line where shell history
could capture them.

```bash
uv run python -m tw_ml.datagen keys set --family A      # hidden prompt; default host: deepinfra
uv run python -m tw_ml.datagen keys set --family B      # only if B needs its own key (see below)
uv run python -m tw_ml.datagen keys status              # stored / not stored; never prints a key
uv run python -m tw_ml.datagen keys delete --family A   # remove after rotating a key
```

Family B (DeepSeek-V3.2, test_synth) also runs on DeepInfra (D-07), so one key covers both: with
nothing stored for `B:deepinfra`, Family B reuses `A:deepinfra` (`keys status` shows
`stored (shared with A:deepinfra)`). Keys are shared only between families on the same host.
A `TW_DATAGEN_<family>_API_KEY` environment variable, when set, takes precedence (for CI or a
one-off session). Use `--host groq` for the Family A fallback host; each host has its own entry.
Backends that would store keys unencrypted or discard them are refused, and tests always use an
in-memory store.

## Rules

- Only synthetic, public or authorized de-identified data (S-12, `data/README.md`); never Claude
  outputs in any dataset (A-01).
- Models load `safetensors` only, `trust_remote_code=False`, pinned HF revisions (§12.3 A08).
- Notebooks are thin wrappers around `python -m tw_ml.<module>`; logic lives in `src/`.
