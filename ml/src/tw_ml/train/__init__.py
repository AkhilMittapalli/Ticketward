"""Model training on Kaggle/Colab T4 (spec v1.1 §9.4-§9.6; P2.9-P2.11, P2.21, P3.4-P3.7).

* ``config`` - pydantic ``SFTRunConfig`` / ``EncoderRunConfig`` for ``ml/configs/*.yaml``, the
  §9.5 rules as validators, ``config_sha``;
* ``data`` - guarded train/val loading (holdout guard, no Anthropic/Claude provenance) and the
  Option A SFT rows (pre-tokenized, prompt masked, train/serve parity checked);
* ``sft`` - E4 LoRA (<= 2B) / QLoRA (3-4B) SFT with TRL, the epoch-end generation eval, Hub
  resume;
* ``encoder`` - E2 ModernBERT multi-head baseline with per-head temperature scaling;
* ``smoke`` - the R-21 T4 smoke test; ``hub`` - dataset fetch, resume state and uploads;
  ``runtime`` - platform asserts, library versions, MLflow environment.

``python -m tw_ml.train --config <yaml> --seed N [--dry-run]`` is the entry point; notebooks are
thin wrappers. torch comes from the platform and is imported only inside functions, so the
package imports (and ``--dry-run`` runs) without it.
"""
