# tw-ml - offline ML (datagen, training, evaluation, export)

Separate uv project from the backend (ADR-0003: separate locks). P0 contains only the
package skeleton; the code lands in P1 (datagen), P2 (eval harness, baselines), P3
(QLoRA fine-tune, GGUF export) and P10 (benchmarks). See spec §9.

| Path | Contents | Phase |
|---|---|---|
| `src/tw_ml/datagen/` | synthetic generation, label QA, leakage checks, Bitext mapping | P1 |
| `src/tw_ml/eval/` | metrics, bootstrap CIs, E1-E6 reports | P2, P10 |
| `src/tw_ml/train/` | QLoRA SFT (TRL), ModernBERT baseline, pydantic configs | P3 |
| `src/tw_ml/export/` | adapter merge, GGUF, Ollama Modelfile, HF Hub publishing | P3 |
| `configs/` | versioned training/bake-off YAML configs | P2-P3 |
| `prompts/` | versioned prompt files (`triage.v1.txt` ...) | P2, P6, P7 |

## Python versions

`requires-python = ">=3.12,<3.14"`: 3.12 locally and on Kaggle, 3.13 on Colab. (The
backend is pinned to 3.12 only.) `.python-version` selects 3.12 for local work.

## Environment (OneDrive / risk R-13)

Never create the virtualenv inside the repo:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\.venvs\ticketward-ml"   # PowerShell
```

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ticketward-ml"               # bash
```

## Dependencies and the lock file

- `pyproject.toml` lists the planned optional groups (`datagen`, `train`, `eval`,
  `export`) with lower bounds only. Versions are verified by ERPROT before use.
- **`ml/uv.lock` does not exist yet.** It is generated in P2/P3 on the training
  environment, after the ERPROT model/library checks.
- **torch and CUDA wheels never go into any lock.** Training uses the platform's
  preinstalled CUDA torch (Colab/Kaggle); `torch` is not declared. Install the training
  group into the platform interpreter so the existing torch satisfies `peft`,
  `bitsandbytes` and `accelerate`, e.g. `uv pip install --system -e ".[train]"`, and verify
  `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"` first.
- `huggingface-hub` is capped below 2 (`<2`) until the 2.x API is reviewed.

## Rules

- Only synthetic, public or authorized de-identified data (S-12, `data/README.md`).
- Models load `safetensors` only, `trust_remote_code=False`, pinned HF revisions (§12.3 A08).
- Notebooks are thin wrappers around `python -m tw_ml.<module>`; logic lives in `src/`.
