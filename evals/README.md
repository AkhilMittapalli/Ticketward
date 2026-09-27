# evals/ - evaluation data and published results

Nothing is published here until it is measured and reproducible with one command (spec
§9.8-§9.10). Planned layout:

| Path | Contents | Phase |
|---|---|---|
| `smoke/` | 60-ticket stratified fixture + recorded model outputs (golden cassette) for CI | P2/P6 |
| `retrieval/qrels.v1.jsonl` | 300 queries with 1-3 relevant `doc_key`s + 40 no-answer queries | P5 |
| `e2e_scenarios.v1.jsonl` | 120 scenarios with gold policy path, queue and must-cite docs | P6/P10 |
| `hard_set.v1.jsonl` | 100 human-written hard cases | P1 |
| `baselines/` | `production.json`, the metric baseline used by the nightly regression gate | P3 |
| `reports/<date>/` | `results.md`, JSON metrics, plots, leakage reports | P2-P10 |

## Metrics and gates

M-01 to M-13 are defined in spec §9.8 (macro-F1, routing accuracy, critical-category recall,
JSON validity/repair, Recall@k, citation-support precision, escalation/abstention, latency,
cost, human feedback, calibration, injection resilience). **M-07a (forced escalation) must
be 1.00: any miss blocks a release.** All proportions carry bootstrap 95% CIs.

## Commands (targets exist; they print their phase until implemented)

```bash
make eval-baselines                                   # E1/E2 (P2)
make eval-bakeoff                                     # E3 zero-shot bake-off on val + hard_dev (P2)
make eval-slm MODEL=<registry-id> SPLIT=test_synth    # E3/E4 (P3)
make eval-retrieval                                   # A1-A4 (P5)
make eval-e2e                                         # E5 (P10)
make bench-latency N=200                              # M-08 (P10)
make report                                           # evals/reports/<date>/ (P10)
```
