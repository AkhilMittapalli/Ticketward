"""Model training (planned in P3, spec §9.5).

Planned modules: ``sft`` (QLoRA SFT with TRL, assistant-only loss), ``encoder``
(ModernBERT multi-head baseline, E2) and ``config`` (pydantic-validated YAML configs from
``ml/configs/``; ``config_sha`` logged to MLflow). Runs on Kaggle/Colab T4 with the
platform's preinstalled CUDA torch.
"""
