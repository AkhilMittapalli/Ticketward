"""Model export and publishing (spec §9.4-§9.6).

Built: ``prompt_format`` (chat templates as string assembly for raw prompts, with golden
renderings; P2). Planned (P3): ``merge`` (adapter merge), ``gguf`` (llama.cpp conversion,
Q4_K_M and Q8_0, quantization-drift check), ``modelfile`` (Ollama Modelfile, temperature 0)
and ``hub`` (HF Hub publishing of safetensors + GGUF + model card, sha256 recorded).
"""
