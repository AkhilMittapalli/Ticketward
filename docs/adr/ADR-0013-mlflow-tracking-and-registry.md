---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §9.6, §9.9, §9.10, §10 (model_versions, eval_runs), §11 (model activation); research qlora-training-on-t4, evaluation-statistics
informed: contributors; reviewers reproducing benchmarks
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0013: MLflow for experiment tracking and model registry

> **Amended in spec v1.1 (2026-09-27; change record A-26, W-m16).**
> * **MLflow aliases** `@candidate` → `@staging` → `@production` replace the deprecated registry stages (verify
>   against the pinned MLflow version). `model_versions.stage` mirrors the alias.
> * **Storage:** during Kaggle/Colab training, runs go to a local file store (`/kaggle/working/mlruns`), uploaded as an
>   `mlruns/` artifact to the private HF checkpoint repo at every epoch end and at run end. A **Postgres-backed MLflow
>   tracking server** in the Compose `ml` profile imports the synced runs. This replaces the garbled v1.0 sentence.
> * More lineage is logged: torch/transformers/trl/peft/bitsandbytes versions, GPU name and seed.
>   `model_versions` gains `training_method`, `deployed_seed`, `llama_cpp_build`, `quant_type`, `imatrix_sha256`,
>   `chat_template_sha256`, `ollama_version`, `calibrator_version` and `calibration_fit_run_id`.

## Context and Problem Statement

The success claim must be "reproducible with one command", following the pre-registered analysis plan (§1.4,
ADR-0032). Every published number traces to an `eval_runs` row with `git_sha`, `config_sha`, `data_manifest_sha` and
`analysis_plan_sha` (§9.9, §10).

Model promotion requires:
* a full eval run meeting the §9.8 thresholds;
* a recorded `eval_run_id`;
* a passing quantization-drift gate;
* a fitted calibrator;
* an updated model card (§9.10).

Promotion to production is an audited **admin action** (`POST /api/v1/admin/models/{id}/activate`), and it is
`DEMO_LOCKED` in the public demo.

Training runs on ephemeral Kaggle/Colab sessions. Evaluation and serving run in the Compose stack.

Which tool tracks experiments and holds the model registry, and how do ephemeral notebook runs reach it?

## Decision Drivers

* Open source and self-hosted, with no account needed to reproduce the lineage.
* A registry with versions and promotion semantics (aliases).
* Works offline on ephemeral notebooks, with runs synced afterwards.
* The tracking server must not become an exposed, unauthenticated attack surface.
* The app, not the tracker, is authoritative for production.

## Considered Options

1. MLflow: local file store in notebooks, synced via the HF checkpoint repo into a Postgres-backed server in the `ml`
   profile (chosen)
2. Weights & Biases (W&B)
3. Neptune
4. None (log files and git only)

## Decision Outcome

Chosen option: "MLflow with notebook file stores synced into a self-hosted Postgres-backed server", because it is
open source with a built-in registry, runs without a SaaS account, and handles ephemeral sessions through the
checkpoint repo that training already uses (ADR-0012).

Operating rules:

* **Authority:** `model_versions.stage` and the audited activation endpoint decide what is in production. The MLflow
  alias mirrors them for lineage, and never drives serving.
* **Aliases, not stages:** `@candidate` (registered) → `@staging` (passed the gate) → `@production` (admin
  activation). Verify alias support and behaviour for the pinned MLflow version.
* **Exposure:** the MLflow server listens on the internal Compose network only, in the `ml` profile. It is never
  published through Caddy and never runs on the demo VM (it ships without strong authentication).
* **No model loading from MLflow into the app.** The app loads only GGUFs downloaded by HF revision and verified by
  sha256 against `model_versions.gguf_sha256` before `ollama create` (ADR-0014). MLflow artifacts are never
  deserialised by the backend.
* **Registry naming:** `tw-triage-<base>-<method>`, where `<method>` is the method actually used (`lora`/`qlora`).
  A Llama base takes the `Llama-` prefix (ADR-0011). Semver: MAJOR = taxonomy/schema, MINOR = retrain or new data,
  PATCH = quantization or prompt fix.

### Consequences

* Good, because every metric links back to a run with code, config, data, library and hardware lineage.
* Good, because the synced `mlruns/` artifact survives notebook preemption, since it rides along with the checkpoint
  pushes.
* Bad, because the UI and Colab experience are weaker than W&B, and importing runs is a documented manual step.
* Bad, because it is one more service to patch and keep internal. Mitigations: the optional profile, no published
  port, and Dependabot/pip-audit on the ml lock.
* Neutral, because alias semantics depend on the pinned MLflow version. The app-side gate makes this invisible to
  serving.

### Confirmation

* Every `make eval-*` run writes an `eval_runs` row with `git_sha`, `config_sha`, `data_manifest_sha`, and (for P10
  reports) `analysis_plan_sha`. A contract test asserts they are non-null (§9.9).
* `T-MODEL-activate-gate`: activation fails unless the linked eval run meets §9.8, the drift gate passed, a
  calibrator is fitted, and the GGUF sha256 matches (`T-SEC-MODEL-sha-mismatch`). Success writes `model.activate`; in
  demo mode the call returns `403 DEMO_LOCKED`.
* An alias-sync check: `model_versions.stage` equals the MLflow alias for the registered version (proposed).
* (proposed) compose-smoke asserts the MLflow service has no published ports, and is absent from
  `compose.prod.yaml`.

## Pros and Cons of the Options

### MLflow (self-hosted, synced)

* Good, because it is OSS with a registry, offline-capable and widely known.
* Bad, because hardening is our job, the UX is weaker, and its API history (stages → aliases) must be tracked.

### Weights & Biases

* Good, because it has excellent UX and Colab integration.
* Bad, because it is SaaS: an account, data leaving the machine, free-tier limits, lock-in, and reviewers need
  accounts to see the lineage.

### Neptune

* Good, because it is a capable metadata store.
* Bad, because it is SaaS with a smaller ecosystem, and its service continuity would need checking before any
  long-term dependency.

### None

* Good, because it has zero overhead.
* Bad, because numbers lose their lineage to code, config and data, which breaks reproducibility and the promotion
  gate's `eval_run_id` linkage.

## More Information

* Spec (private): §1.4, §9.6 (storage, aliases, registry naming, `model_versions` fields), §9.9, §9.10 (promotion),
  §10, §11 (`/admin/models`, `GET /models`, `DEMO_LOCKED`), §15 (model-rollback runbook). Change record A-26, W-m16.
* Research: [qlora-training-on-t4](../research/qlora-training-on-t4.md) (checkpoint/Hub sync),
  [evaluation-statistics](../research/evaluation-statistics.md) (reporting lineage).
* Related ADRs: ADR-0012, ADR-0014, ADR-0021, ADR-0032, ADR-0035.
* Revisit when: multiple contributors need a hosted UI, or the MLflow registry API changes again.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (aliases, storage and sync design,
  extended lineage fields).
