"""Evaluation harness (spec v1.1 §9.7-§9.10; built in P2, extended in P10).

Modules:

* ``stats`` - Wilson / Clopper-Pearson intervals, the one-sided exact bound (M-07a), stratified
  and ticket-cluster bootstrap (B = 10,000, seed 2026), paired bootstrap, approximate
  randomization, McNemar exact / mid-p, Holm and BH, per-seed aggregation, Cohen's kappa
* ``data`` - gold rows and ``prediction.v1`` records, loaders and the gold/prediction join
* ``metrics`` - M-01..M-04 and M-07a..d, the two-level seed bootstrap, paired system comparison
* ``gates`` - the §9.8 acceptance gates and the phase exits, as data
* ``holdout`` - the sealed-split guard and the ``evals/sealed_access.jsonl`` log
* ``report`` - ``eval_report.v1`` / ``eval_comparison.v1`` schemas and Markdown rendering

Run ``python -m tw_ml.eval --help``. Planned: ``e2e`` (E5 against the Compose stack),
``retrieval`` (Recall@k, MRR, nDCG), ``latency`` (M-08), ``calibration`` (M-12), ``bakeoff``
(the E3 driver) and the OOD scorer (P2-P10).
"""
