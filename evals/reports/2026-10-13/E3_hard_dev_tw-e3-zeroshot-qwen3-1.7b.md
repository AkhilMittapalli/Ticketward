# E3 on hard_dev: tw-e3-zeroshot-qwen3-1.7b

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | e21eec5a-c85d-4ef0-a2ce-d40ff934ddc8 |
| Created | 2026-10-13T01:58:07+00:00 |
| Experiment / split | E3 / hard_dev (open) |
| System | tw-e3-zeroshot-qwen3-1.7b |
| Git SHA | 286ba022a8c38b13d26af683bf9ee8fe2cb4988f |
| Gold | hard_dev.v1.jsonl (a1e453f41e60) |
| Predictions | qwen3-1.7b_hard_dev (b504e75455d3) |
| Data manifests | data/manifests/test_hard.json (4f3f8a4151ac) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 30, scored 30, missing 0, extra 0, with decision 0 |
| Holdout | phase P2; origins hard_dev 30 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.722 [0.644, 0.783] | stratified-percentile-bootstrap | 30 |  |  |
| M-01.intent_accuracy | 0.733 [0.556, 0.858] | wilson | 30 | 22 |  |
| M-01.other_unclear_f1 | 0.000 [0.000, 0.000] | stratified-percentile-bootstrap | 30 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.000 [0.000, 0.842] | clopper-pearson | 2 | 0 |  |
| M-01.other_unclear_precision | n/a | undefined (n = 0) | 0 |  |  |
| M-02.routing_accuracy | 0.567 [0.392, 0.726] | wilson | 30 | 17 | policy final queue for 0, model queue for 29, none for 1 |
| M-03.priority_accuracy | 0.533 [0.361, 0.698] | wilson | 30 | 16 |  |
| M-03.priority_within_one | 0.967 [0.833, 0.994] | wilson | 30 | 29 |  |
| M-03.product_area_accuracy | 0.500 [0.332, 0.668] | wilson | 30 | 15 |  |
| M-03.sentiment_macro_f1 | 0.393 [0.288, 0.479] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.churn_macro_f1 | 0.352 [0.214, 0.462] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.entity_f1 | 0.453 [0.358, 0.554] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 143, matched 51; ticket-cluster bootstrap |
| M-03.entity_precision | 0.357 [0.257, 0.477] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 143, matched 51; ticket-cluster bootstrap |
| M-03.entity_recall | 0.622 [0.527, 0.721] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 143, matched 51; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.billing_payment_failure_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.cancellation_request_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.model.service_outage_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.security_report_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.model.pooled_recall | 1.000 [0.753, 1.000] | clopper-pearson | 13 | 13 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-04.json_validity | 0.967 [0.833, 0.994] | wilson | 30 | 29 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 0.933 [0.787, 0.982] | wilson | 30 | 28 |  |
| M-04.schema_repair | 0.033 [0.006, 0.167] | wilson | 30 | 1 |  |
| M-04.failed | 0.033 [0.006, 0.167] | wilson | 30 | 1 | failed_fallback plus missing predictions |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 2 | 0 | 0 | n/a | 0.000 [0.000, 0.842] | 0.000 |
| account_access_issue | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |
| billing_duplicate_charge | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| billing_payment_failure | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| refund_request | 2 | 1 | 1 | 1.000 | 0.500 [0.095, 0.905] | 0.667 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| plan_pricing_inquiry | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| service_outage | 3 | 7 | 3 | 0.429 | 1.000 [0.292, 1.000] | 0.600 |
| bug_report | 3 | 0 | 0 | n/a | 0.000 [0.000, 0.708] | 0.000 |
| how_to_question | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |
| security_report | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| privacy_legal_request | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |
| other_unclear | 2 | 0 | 0 | n/a | 0.000 [0.000, 0.842] | 0.000 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| billing_payment_failure | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| service_outage | 3 | 7 | 3 | 0.429 | 1.000 [0.292, 1.000] | 0.600 |
| security_report | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | inv |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 billing_payment_failure | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 refund_request | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 10 how_to_question | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| 11 security_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| 13 other_unclear | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 28 |
| repaired_l1 | 1 |
| repaired_l2 | 0 |
| failed_fallback | 1 |
| missing | 0 |

## Notes

- M-07a..d not computed: no prediction carries a policy decision
