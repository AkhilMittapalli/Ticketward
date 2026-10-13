# E3 on val: tw-e3-zeroshot-qwen3-1.7b

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | cd1871a6-345d-4e8f-8fb9-a0acc30e8036 |
| Created | 2026-10-13T01:57:58+00:00 |
| Experiment / split | E3 / val (open) |
| System | tw-e3-zeroshot-qwen3-1.7b |
| Git SHA | 286ba022a8c38b13d26af683bf9ee8fe2cb4988f |
| Gold | records.jsonl (54a09e69ecfc) |
| Predictions | qwen3-1.7b_val (952c7ddf6282) |
| Data manifests | data/manifests/val.json (a9ea2dcc4829) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 230, scored 230, missing 0, extra 0, with decision 0 |
| Holdout | phase P2; origins val 230 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.789 [0.745, 0.831] | stratified-percentile-bootstrap | 230 |  |  |
| M-01.intent_accuracy | 0.778 [0.720, 0.827] | wilson | 230 | 179 |  |
| M-01.other_unclear_f1 | 0.000 [0.000, 0.000] | stratified-percentile-bootstrap | 230 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.000 [0.000, 0.176] | clopper-pearson | 19 | 0 |  |
| M-01.other_unclear_precision | n/a | undefined (n = 0) | 0 |  |  |
| M-02.routing_accuracy | 0.665 [0.602, 0.723] | wilson | 230 | 153 | policy final queue for 0, model queue for 223, none for 7 |
| M-03.priority_accuracy | 0.448 [0.385, 0.512] | wilson | 230 | 103 |  |
| M-03.priority_within_one | 0.896 [0.849, 0.929] | wilson | 230 | 206 |  |
| M-03.product_area_accuracy | 0.496 [0.432, 0.560] | wilson | 230 | 114 |  |
| M-03.sentiment_macro_f1 | 0.190 [0.150, 0.232] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.churn_macro_f1 | 0.269 [0.215, 0.323] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.entity_f1 | 0.373 [0.331, 0.415] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 1090, matched 293; ticket-cluster bootstrap |
| M-03.entity_precision | 0.269 [0.232, 0.309] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 1090, matched 293; ticket-cluster bootstrap |
| M-03.entity_recall | 0.607 [0.561, 0.653] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 1090, matched 293; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 0.957 [0.790, 0.992] | wilson | 23 | 22 |  |
| M-03c.model.billing_payment_failure_recall | 0.792 [0.595, 0.908] | wilson | 24 | 19 |  |
| M-03c.model.cancellation_request_recall | 1.000 [0.824, 1.000] | clopper-pearson | 19 | 19 |  |
| M-03c.model.service_outage_recall | 1.000 [0.877, 1.000] | clopper-pearson | 28 | 28 |  |
| M-03c.model.security_report_recall | 0.955 [0.782, 0.992] | wilson | 22 | 21 |  |
| M-03c.model.pooled_recall | 0.940 [0.881, 0.970] | wilson | 116 | 109 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-04.json_validity | 0.970 [0.939, 0.985] | wilson | 230 | 223 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 0.917 [0.875, 0.946] | wilson | 230 | 211 |  |
| M-04.schema_repair | 0.052 [0.030, 0.089] | wilson | 230 | 12 |  |
| M-04.failed | 0.030 [0.015, 0.061] | wilson | 230 | 7 | failed_fallback plus missing predictions |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 13 | 10 | 9 | 0.900 | 0.692 [0.424, 0.873] | 0.783 |
| account_access_issue | 12 | 16 | 10 | 0.625 | 0.833 [0.552, 0.953] | 0.714 |
| billing_duplicate_charge | 23 | 24 | 22 | 0.917 | 0.957 [0.790, 0.992] | 0.936 |
| billing_payment_failure | 24 | 20 | 19 | 0.950 | 0.792 [0.595, 0.908] | 0.864 |
| refund_request | 15 | 14 | 14 | 1.000 | 0.933 [0.702, 0.988] | 0.966 |
| cancellation_request | 19 | 20 | 19 | 0.950 | 1.000 [0.824, 1.000] | 0.974 |
| plan_pricing_inquiry | 6 | 7 | 5 | 0.714 | 0.833 [0.436, 0.970] | 0.769 |
| service_outage | 28 | 49 | 28 | 0.571 | 1.000 [0.877, 1.000] | 0.727 |
| bug_report | 14 | 1 | 1 | 1.000 | 0.071 [0.013, 0.315] | 0.133 |
| how_to_question | 16 | 20 | 12 | 0.600 | 0.750 [0.505, 0.898] | 0.667 |
| security_report | 22 | 23 | 21 | 0.913 | 0.955 [0.782, 0.992] | 0.933 |
| privacy_legal_request | 19 | 19 | 19 | 1.000 | 1.000 [0.824, 1.000] | 1.000 |
| other_unclear | 19 | 0 | 0 | n/a | 0.000 [0.000, 0.176] | 0.000 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 23 | 24 | 22 | 0.917 | 0.957 [0.790, 0.992] | 0.936 |
| billing_payment_failure | 24 | 20 | 19 | 0.950 | 0.792 [0.595, 0.908] | 0.864 |
| cancellation_request | 19 | 20 | 19 | 0.950 | 1.000 [0.824, 1.000] | 0.974 |
| service_outage | 28 | 49 | 28 | 0.571 | 1.000 [0.877, 1.000] | 0.727 |
| security_report | 22 | 23 | 21 | 0.913 | 0.955 [0.782, 0.992] | 0.933 |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | inv |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| 2 account_access_issue | 1 | 10 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 22 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| 4 billing_payment_failure | 0 | 0 | 1 | 19 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 2 |
| 5 refund_request | 0 | 0 | 0 | 1 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 8 | 1 | 1 | 0 | 0 | 0 | 1 |
| 10 how_to_question | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 0 | 0 | 1 |
| 11 security_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 21 | 0 | 0 | 0 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 0 | 0 |
| 13 other_unclear | 0 | 1 | 0 | 0 | 0 | 0 | 2 | 8 | 0 | 7 | 0 | 0 | 0 | 1 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 211 |
| repaired_l1 | 12 |
| repaired_l2 | 0 |
| failed_fallback | 7 |
| missing | 0 |

## Notes

- M-07a..d not computed: no prediction carries a policy decision
