"""Ticketward offline ML package (``tw_ml``).

Code lives here, notebooks stay thin wrappers (``python -m tw_ml.train --config ...``,
spec §9.5). Subpackages:

* ``datagen`` - synthetic dataset generation, labeling QA, leakage checks (P1)
* ``eval`` - metrics, statistics, holdout guard and reports (P2, P10)
* ``baselines`` - the E1 rules baseline and the policy-lexicon reference parser (P2)
* ``train`` - QLoRA SFT and the encoder baseline (P3)
* ``export`` - adapter merge, GGUF conversion, Ollama Modelfile, HF Hub (P3)

All data is synthetic, public or authorized de-identified (S-12, ``data/README.md``).
"""

__version__ = "0.1.0.dev0"
