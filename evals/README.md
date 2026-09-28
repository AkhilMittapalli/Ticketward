# evals/ - evaluation data and published results

Nothing is published here until it is measured and reproducible with one command (spec
§9.8-§9.10). Layout:

| Path | Contents | Status | Phase |
|---|---|---|---|
| `ANALYSIS_PLAN.md` | pre-registration (hypotheses H1-H3, metrics, splits, CI methods, gates, failed-gate procedure); hashed into every report as `analysis_plan_sha`, frozen before P10 | draft | P2, frozen P10 |
| `sealed_access.jsonl` | append-only log of every sealed-split evaluation (`tw_ml.eval.holdout`), committed | open log | P10 |
| `hard_set.v1.jsonl` | 100 hand-written hard cases; `hard_dev` (30) / `hard_final` (70) in `data/manifests/test_hard.json` | sealed part | P1 |
| `smoke/` | 60-ticket stratified fixture + recorded model outputs (golden cassettes) for CI | planned | P6 |
| `retrieval/qrels_dev.v1.jsonl`, `qrels_test.v1.jsonl` | 150 + 20 queries each, dev from val tickets, test sealed | planned | P5 |
| `e2e_scenarios.v1.jsonl` | 120 scenarios with gold policy path, queue and must-cite docs | sealed | P6/P10 |
| `ood/test_ood.v1.pointers.jsonl` | Bitext row pointers only (CDLA-Sharing-1.0 text never committed) | sealed | P1/P10 |
| `baselines/` | `production.json`, the metric baseline of the nightly regression gate | planned | P3 |
| `reports/<date>/` | `<experiment>_<split>_<system>.json` (`eval_report.v1`) + `.md`, `compare_*.json`, `baselines.md`, `bakeoff.md`, leakage reports | per run | P1-P10 |

## Sealed splits

`test_synth`, `hard_final` (and so all of `test_hard`), `test_ood`, `e2e_scenarios` and
`qrels_test` stay **sealed until P10** (spec §9.3, §16; A-10). Before P10, thresholds, prompts,
calibration, seed choice and error analysis use `val`, `val_dev`, `hard_dev` and `qrels_dev`
only; nightly regressions run on a val sample + `hard_dev`.

- `python -m tw_ml.eval` and `python -m tw_ml.baselines.rules` pass the holdout guard first. It
  places every gold record by `provenance.split` or its record-id prefix (`ts_`, `th_`, `to_`,
  `te_`...), not by the `--split` name. `test_hard` records count as `hard_final` unless the
  frozen `data/manifests/test_hard.json` lists them in `hard_dev`, and records with no
  recognizable origin are refused (fail closed).
- A sealed evaluation needs `--phase P10 --i-understand-sealed`. Each one is appended to
  `sealed_access.jsonl` (time, action, split, system, git SHA, file hashes) and its running
  `eval_count_on_split` is published in the report: protected splits are evaluated once per
  registered model version.

## Metrics and gates

M-01 to M-13 are defined in spec §9.8; the estimators are in `tw_ml.eval.metrics` and the gates
in `tw_ml.eval.gates`. Proportions carry Wilson 95% CIs (Clopper-Pearson at 0/n and n/n);
macro-F1 and entity F1 carry percentile bootstrap CIs (B = 10,000, `default_rng(2026)`,
stratified by gold class or resampled by ticket). **M-07a (forced escalation) must be 1.00: any
miss blocks a release**, and it is published with n and the one-sided exact 95% lower bound
0.05^(1/n). Critical-category recall is gated **pooled** (>= 0.95 on test_synth) with each class
>= 0.90, all with n and Wilson CIs. Gates are decisions published with their CIs; a miss is
reported as a miss (`ANALYSIS_PLAN.md` §13).

## Commands

Run from `ml/` with the ml venv (`UV_PROJECT_ENVIRONMENT`, see `ml/README.md`):

```bash
# E1 rules baseline -> prediction.v1 JSONL (reads only the tickets, never the labels)
uv run python -m tw_ml.baselines.rules --input ../data/generated/val/records.jsonl \
    --out ../evals/runs/e1_val.jsonl

# Score one system on one split -> evals/reports/<date>/E1_val_<system>.{json,md}
uv run python -m tw_ml.eval score --pred ../evals/runs/e1_val.jsonl \
    --gold ../data/generated/val/records.jsonl --split val --experiment E1

# Several seeds of one system (E2/E4): per-seed values, mean, SD CI, two-level bootstrap
uv run python -m tw_ml.eval score --pred s42=a.jsonl --pred s1337=b.jsonl --pred s2026=c.jsonl \
    --deployed-seed s1337 --gold ../data/generated/val/records.jsonl --split val --experiment E4

# Paired comparison (P10 confirmatory family: E4 against E3, E1, E2 in this order)
uv run python -m tw_ml.eval compare --gold G --split val --pred-a e4.jsonl \
    --pred-b e3.jsonl --pred-b e1.jsonl --pred-b e2.jsonl --family confirmatory

# Combine reports into one page
uv run python -m tw_ml.eval render --report R1.json --report R2.json \
    --out ../evals/reports/<date>/baselines.md --title "P2 baselines (val + hard_dev)"
```

Exit codes: 0 success, 1 a gate failed with `--fail-on-gate`, 2 usage, data or holdout error
(including every refused sealed split). Make targets: `make eval-baselines` (E1/E2, P2),
`make eval-bakeoff` (E3, P2), `make eval-slm MODEL=<registry-id> SPLIT=<split>` (P3),
`make eval-retrieval` (P5), `make eval-e2e` (P10), `make bench-latency N=200` (P10),
`make report` (P10). During P2 the baseline and bake-off targets run on val and `hard_dev` only.
