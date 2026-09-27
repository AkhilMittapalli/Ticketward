# infra/ollama/ (planned in P3/P4)

`Modelfile` for the fine-tuned triage model (spec §9.5 "Export/serving"): the Q4_K_M GGUF
exported by `tw_ml.export` (sha256 verified before load), the base model's chat template,
and `PARAMETER temperature 0`. Ollama runs under the `ml` Compose profile on the internal
network only; its model list is part of the readiness check once triage lands (P4).
