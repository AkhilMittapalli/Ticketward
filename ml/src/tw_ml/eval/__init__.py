"""Evaluation harness (planned in P2, extended in P10, spec §9.7-§9.10).

Planned modules: ``classify`` (M-01..M-04), ``e2e`` (E5 against the Compose stack),
``retrieval`` (Recall@k, MRR, nDCG), ``latency`` (M-08), ``bootstrap`` (95% CIs) and
``report`` (``evals/reports/<date>/``). Every run writes an ``eval_runs`` record.
"""
