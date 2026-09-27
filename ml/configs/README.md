# ml/configs/ (placeholder)

Versioned YAML configs, validated by pydantic models in `tw_ml.train.config`; the
`config_sha` of each run is logged to MLflow (spec §9.5-§9.6).

| Planned file | Purpose | Phase |
|---|---|---|
| `bakeoff.yaml` | zero-shot candidate models, constrained decoding settings | P2 |
| `sft_qwen_1p5b.yaml` | QLoRA SFT, default candidate (NF4, r=16, alpha=32, lr 2e-4) | P3 |
| `sft_qwen_3b.yaml` | QLoRA SFT, larger candidate | P3 |
| `encoder_modernbert.yaml` | ModernBERT multi-head baseline (E2) | P2 |

Base model names and revisions are chosen by the P2 bake-off (ADR-0011) and pinned by
HF revision SHA.
