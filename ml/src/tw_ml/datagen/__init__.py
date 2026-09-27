"""P1 dataset tooling (spec v1.1 §9.1-§9.3): generation, label QA, leakage checks, manifests.

Run ``python -m tw_ml.datagen --help``. Modules:

* ``taxonomy`` - enums loaded from the exported ``schemas/json`` contracts (never the backend)
* ``records`` - ticket, label, cell and provenance models (T-DATA-provenance)
* ``labelrules`` / ``factsheet`` / ``pools`` / ``matrix`` / ``entities`` - the generation spec and
  the seeded pairwise-coverage sampler
* ``prompts`` / ``providers`` / ``generate`` / ``pii`` / ``noise`` - prompt families P-A and
  P-B, the OpenAI-compatible client and the resumable, budget-capped generation loop
* ``validate`` - schema validation and the rule-checker (R1-R10, fact-sheet plausibility)
* ``leakage`` - checks C1-C7 and the JSON report
* ``qa`` - 540-record audit, Wilson pass rule, Cohen's kappa
* ``manifest`` - content-hash manifests, freeze and verify
* ``hardset`` - owner-written hard set validation and the 30/70 split
* ``bitext`` - Bitext OOD pointers (downloads only when the owner runs it)
"""
