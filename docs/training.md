# Training runbook: Kaggle T4 x2 (primary) and Colab T4

How the owner runs E2 (encoder baseline, P2.11), the R-21 smoke test (P2.21) and E4 (LoRA/QLoRA
SFT, P3.8) on free GPUs. The notebooks in `ml/notebooks/` are thin wrappers: every step is a
`python -m tw_ml.train...` command from the repository at a pinned commit, so what ran is always
reproducible from the commit SHA, the config and the dataset revision.

Items marked **UNVERIFIED** come from secondary sources or could not be read (Kaggle's docs are
JS-rendered). Check them in the UI and correct this page.

## 1. What runs where

| Step | Command (from the repository root) | Where |
|---|---|---|
| Validate a config and the data | `python -m tw_ml.train --config <yaml> --seed 42 --dry-run [--allow-unverified]` | any machine (no torch) |
| Fetch train/val | `python -m tw_ml.train.hub fetch-data --repo <hf_user>/<dataset> --revision <sha>` | notebook |
| R-21 smoke test | `python -m tw_ml.train.smoke --config ml/configs/sft_<base>.yaml --steps 20` | notebook, GPU 0 |
| Train one seed | `CUDA_VISIBLE_DEVICES=<gpu> python -m tw_ml.train --config <yaml> --seed <seed>` | notebook |
| Push a seed's run files | `python -m tw_ml.train.hub push-run --config <yaml> --seed <seed>` | notebook |
| Score E2 | `python -m tw_ml.eval score --experiment E2 ...` (section 7) | dev laptop |

Every run first checks the platform (the platform's torch **2.11**, CUDA, a T4), refuses a
`<verify>` base revision unless `--allow-unverified` is passed, and refuses a `<hf_user>`
checkpoint repo. Training data goes through the holdout guard (train and val only) and the
S-12 check (no record whose provenance mentions Anthropic or Claude).

## 2. One-time setup

**Configs (commit before a run).**

1. Pin each base model's commit SHA in `ml/configs/bakeoff.yaml` (`hf_revision`) and in the
   matching `ml/configs/sft_*.yaml` (`base.revision`); a test requires the two to agree. Pin
   `answerdotai/ModernBERT-base` in `encoder_modernbert.yaml`.
2. Replace `<hf_user>` in every `hub.checkpoint_repo` with your Hugging Face user name. The trainer
   creates one **private** repo per seed on the first push.
3. Generate `ml/configs/prompt_formats/<id>.json` for every SFT base (bake-off step 4 in
   `ml/configs/README.md`). The training run and the dry run refuse a missing file, and training
   asserts that the chat template renders every prompt byte-identical to `render_raw` of it.
4. Run the dry run for each config you will train, commit, push, and note the commit SHA.

**Hugging Face.** Create a fine-grained token with write access to your own repos. It is only ever
typed into the platform's secret store, never into a file, a chat or a command line.

**Dataset upload (dev laptop).** Create a private dataset repo that holds **only**
`train/records.jsonl` and `val/records.jsonl`; keep the sealed splits in a separate private repo.
The fetch step downloads only those two files at a pinned revision anyway. With the pinned Hub
client (CLI flags **UNVERIFIED**, check `hf upload --help`):

```bash
uvx --from huggingface-hub==1.33.0 hf repo create <hf_user>/ticketward-data --repo-type dataset --private
uvx --from huggingface-hub==1.33.0 hf upload <hf_user>/ticketward-data data/generated/train/records.jsonl train/records.jsonl --repo-type dataset
uvx --from huggingface-hub==1.33.0 hf upload <hf_user>/ticketward-data data/generated/val/records.jsonl val/records.jsonl --repo-type dataset
```

Note the dataset commit SHA shown after the last upload (or in the repo's history): it is the
notebook's `HF_DATASET_REVISION`. If `data/manifests/train.json` or `val.json` is committed, the
run also checks that the downloaded content matches it.

**Kaggle account.** Phone verification is required for GPUs and for Internet access
(**UNVERIFIED** wording). Import `ml/notebooks/train_kaggle.ipynb` (File, Import notebook), then:

- Settings: Accelerator **GPU T4 x2**; Internet **on**.
- Add-ons, Secrets: add `HF_TOKEN` and attach it to this notebook.

## 3. Run on Kaggle

1. Edit the parameters cell: `GIT_SHA`, `CONFIG`, `HF_DATASET_ID`, `HF_DATASET_REVISION` (keep
   `ALLOW_UNVERIFIED = False` once the revisions are pinned).
2. **Save Version, Save & Run All (Commit).** The run continues in the background, up to about 12 h
   per session (**UNVERIFIED**).
3. The notebook clones the commit and checks it, asserts Python 3.12/3.13, torch 2.11 and two T4s,
   installs `ml/requirements/train.txt` (hashed, `--no-deps`, no torch/triton/CUDA wheels) and the
   package, copies `HF_TOKEN` into the environment, fetches train/val, runs the smoke test (SFT
   configs), trains seeds 42 and 1337 in parallel (one per T4, no DDP), then seed 2026, and pushes
   each seed's run files again.
4. Outputs stay in `/kaggle/working/tw-runs/` (the notebook's output) and in each seed's private
   repo: checkpoints every 25 steps with `last-checkpoint/`, `epoch_adapters/`,
   `selected_adapter/`, `selection.json`, `epoch_eval.jsonl`, `confusion/` (val intent confusion
   matrix per epoch), `data_manifest.json`, `run_summary.json` and the MLflow store `mlruns/`
   (tags: `config_sha`, git SHA, manifest hashes, library versions, GPU, seed). Logs:
   `tw-runs/train-s<seed>.log`. If the pinned MLflow no longer accepts a file store, switch
   `tracking.store` to `sqlite` in a new config version (**UNVERIFIED** for MLflow 3.16).

**Read the smoke report first** (`tw-runs/smoke/<name>-s42/smoke_report.json`; the cell fails when
a check fails):

| Check | If it fails |
|---|---|
| 1 fp16 forward/backward | Inf/NaN on the base: record it, fall back to Qwen3-1.7B (§9.5 decision rule) |
| 2 trainable fp32 | The fp32 re-cast guard did not apply: stop, fix the code |
| 3 loss type | `nll` fallback used (it is reported): make `loss_type: nll` explicit in a new config version |
| 4 peak memory < 13 GiB | Use the `nll` fallback batch, or QLoRA for 3-4B |
| 5 time per seed | Over 2 h (2B) / 4 h (4B): note it for the bake-off decision |
| 6 Qwen3.5 fast path | Informational: run once with `fla`/`causal-conv1d` installed and once without, and compare s/step |
| 7 resume | Loss differs after resume: stop, do not rely on resume |

**Final checkpoint.** Early stopping and `load_best_model_at_end` use `eval_loss`; the adapter to
export (P3.11) is `selected_adapter/`, the epoch-end adapter with the best val macro-F1 (ties go
to the lower `eval_loss`), recorded in `selection.json`.

## 4. Resume after a lost session

Rerun the same notebook version (same `GIT_SHA`, `CONFIG` and dataset revision). Each seed
downloads its repo's `last-checkpoint/` (plus the epoch records, adapters and MLflow store) and
continues; the log says `resuming from Hub last-checkpoint (step N)`. A seed starts fresh only
when its repo or `last-checkpoint/` does not exist yet; any other Hub error stops the run instead
of silently overwriting a pushed checkpoint. To restart a seed from zero, delete its checkpoint
repo yourself first.

## 5. Colab differences

- `ml/notebooks/train_colab.ipynb`; Runtime, Change runtime type: **T4 GPU**. Colab runs Python 3.13.
- Secrets (key icon): add `HF_TOKEN` and allow notebook access.
- Interactive only: no background execution on the free tier, and the tab must stay open. One T4
  means the three seeds run one after another.
- `/content` is lost on disconnect. Run all cells again in a new runtime; every seed resumes from
  its Hub repo (section 4).

## 6. Costs and limits

| Item | Value | Status |
|---|---|---|
| Kaggle GPU quota | about 30 h per week | **UNVERIFIED** (secondary sources; check the quota widget) |
| T4 x2 billing | may count 2 quota hours per hour | **UNVERIFIED** |
| Kaggle session | at most 12 h (Save & Run All) | **UNVERIFIED** |
| `/kaggle/working` size | about 20 GB | **UNVERIFIED** |
| SIGTERM grace on shutdown | unknown: never relied on (checkpoints every 25 steps instead) | **UNVERIFIED** |
| Colab free runtime | at most 12 h, idle timeouts, GPUs not guaranteed | Colab FAQ |
| Time per SFT seed | estimate 0.9-1.5 h (2B class) and 2.3-3.9 h (4B class) for 3 epochs, plus about 5 min of generation eval per epoch | estimate: the smoke test measures s/step |
| E2 per seed | 5 epochs of ModernBERT-base at 512 tokens | not measured yet |
| Money | $0 on Kaggle/Colab free tiers; a rented A10/L4 is about $0.5-1/h but needs a bf16 config (not written yet) | spec §9.5 |

## 7. E2: scoring the encoder baseline

Set `CONFIG = "ml/configs/encoder_modernbert.yaml"` (no smoke test runs for it). Each seed writes
`predictions/val.jsonl` (`prediction.v1`), `predictions/val.confidence.jsonl` (calibrated
`FieldConfidence` plus `p_critical`), the same for `hard_dev` once `evals/hard_dev.v1.jsonl`
exists, `calibrator.json` (one temperature per head, fitted on val) and `final/` (weights, heads,
tokenizer) for the P10 prediction on sealed splits. Download each seed's `predictions/val.jsonl`
from its repo into `evals/runs/<date>/` (gitignored), for example
`uvx --from huggingface-hub==1.33.0 hf download <hf_user>/tw-e2-modernbert-base-s42 predictions/val.jsonl --local-dir <folder>`
(flags **UNVERIFIED**), rename them per seed, and score all seeds together:

```bash
cd ml && uv run python -m tw_ml.eval score --experiment E2 --split val \
  --gold ../data/generated/val/records.jsonl \
  --pred s42=../evals/runs/<date>/e2_s42_val.jsonl --pred s1337=../evals/runs/<date>/e2_s1337_val.jsonl \
  --pred s2026=../evals/runs/<date>/e2_s2026_val.jsonl --deployed-seed <seed with the best val macro-F1>
```

The encoder has no heads for entities, secondary intents, churn signals or the human-request
flag: its outputs leave them empty or false, so compare E2 with E4 on the classification metrics
(honesty rule, spec §9.7). Val ECE of the calibrated encoder is in-sample: the temperatures are
fitted on the same val set.

## 8. Rules that never bend

- `HF_TOKEN` lives only in the platform's secret store and the process environment; the notebooks
  never print it, and tests fail if a notebook would.
- Training machines only ever download train and val. Sealed splits stay sealed until P10.
- No Claude or Anthropic output is ever trained on: the loader refuses such a record.
- Checkpoint and model repos stay private until the sanitization review (spec §9.5).
