"""Model export and publishing (planned in P3, spec §9.5-§9.6).

Planned modules: ``merge`` (adapter merge), ``gguf`` (llama.cpp conversion, Q4_K_M and
Q8_0, quantization-drift check), ``modelfile`` (Ollama Modelfile, temperature 0) and
``hub`` (HF Hub publishing of safetensors + GGUF + model card, sha256 recorded).
"""
