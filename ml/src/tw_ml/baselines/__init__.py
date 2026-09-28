"""Non-LLM baselines (spec v1.1 §9.7).

* ``lexicon`` - the policy lexicon format (``backend/policy/lexicons/*.txt``): parser,
  normalization and matching, the ml-side reference implementation the P6 engine mirrors
* ``entities`` - literal entity extraction from the fact-sheet vocabularies (spec §5.6, R7)
* ``rules`` - the E1 rules baseline: keyword/regex/lexicon triage producing
  ``TriageModelOutput``-shaped predictions (``python -m tw_ml.baselines.rules``)

The E2 encoder baseline lives in ``tw_ml.train`` (P2, Kaggle).
"""
