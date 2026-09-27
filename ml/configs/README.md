# ml/configs/

Versioned YAML configs. Pydantic models validate every file on load; a changed config is a
new version (a new file or a bumped `version`), never a silent edit of one already used for a
published dataset or run.

| File | Purpose | Phase |
|---|---|---|
| `datagen.yaml` | generator families, hosts (DeepInfra primary / Groq fallback for Family A, Mistral for Family B), request parameters, retry policy, $15 budget, terms snapshot | P1 |
| `datagen_prices.v1.yaml` | dated per-million-token prices (as of 2026-09-27) for token accounting and the budget cap | P1 |
| `leakage.yaml` | leakage checks C1-C7: thresholds, LSH parameters (asserted b=30, r=4), embedding model, KB and protected-string settings | P1 |

Planned (P2/P3): `bakeoff.yaml`, `sft_qwen35_2b.yaml`, `sft_qwen3_1p7b.yaml`,
`sft_qwen3_4b_2507.yaml`, `encoder_modernbert.yaml`. Base model names and revisions are chosen by
the P2 bake-off (ADR-0011) and pinned by HF revision SHA; the `config_sha` of each run is logged
to MLflow (spec §9.5-§9.6).

Secrets never live here: API keys come only from `TW_DATAGEN_{A,B}_API_KEY`.
