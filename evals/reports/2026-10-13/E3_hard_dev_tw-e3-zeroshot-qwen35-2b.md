# E3 on hard_dev: tw-e3-zeroshot-qwen35-2b

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | 978b4138-919b-4d6c-8dff-3860504c1e2c |
| Created | 2026-10-13T01:58:25+00:00 |
| Experiment / split | E3 / hard_dev (open) |
| System | tw-e3-zeroshot-qwen35-2b |
| Git SHA | 286ba022a8c38b13d26af683bf9ee8fe2cb4988f |
| Gold | hard_dev.v1.jsonl (a1e453f41e60) |
| Predictions | qwen35-2b_hard_dev (7876113d1703) |
| Data manifests | data/manifests/test_hard.json (4f3f8a4151ac) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 30, scored 30, missing 0, extra 0, with decision 0 |
| Holdout | phase P2; origins hard_dev 30 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.901 [0.784, 0.972] | stratified-percentile-bootstrap | 30 |  |  |
| M-01.intent_accuracy | 0.833 [0.664, 0.927] | wilson | 30 | 25 |  |
| M-01.other_unclear_f1 | 0.000 [0.000, 0.000] | stratified-percentile-bootstrap | 30 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.000 [0.000, 0.842] | clopper-pearson | 2 | 0 |  |
| M-01.other_unclear_precision | n/a | undefined (n = 0) | 0 |  |  |
| M-02.routing_accuracy | 0.833 [0.664, 0.927] | wilson | 30 | 25 | policy final queue for 0, model queue for 28, none for 2 |
| M-03.priority_accuracy | 0.367 [0.219, 0.545] | wilson | 30 | 11 |  |
| M-03.priority_within_one | 0.933 [0.787, 0.982] | wilson | 30 | 28 |  |
| M-03.product_area_accuracy | 0.733 [0.556, 0.858] | wilson | 30 | 22 |  |
| M-03.sentiment_macro_f1 | 0.270 [0.209, 0.320] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.churn_macro_f1 | 0.567 [0.438, 0.714] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.entity_f1 | 0.479 [0.375, 0.589] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 131, matched 51; ticket-cluster bootstrap |
| M-03.entity_precision | 0.389 [0.288, 0.511] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 131, matched 51; ticket-cluster bootstrap |
| M-03.entity_recall | 0.622 [0.505, 0.735] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 131, matched 51; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 0.667 [0.208, 0.939] | wilson | 3 | 2 |  |
| M-03c.model.billing_payment_failure_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.cancellation_request_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.model.service_outage_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.security_report_recall | 0.500 [0.095, 0.905] | wilson | 2 | 1 |  |
| M-03c.model.pooled_recall | 0.846 [0.578, 0.957] | wilson | 13 | 11 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-04.json_validity | 0.933 [0.787, 0.982] | wilson | 30 | 28 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 0.933 [0.787, 0.982] | wilson | 30 | 28 |  |
| M-04.schema_repair | 0.000 [0.000, 0.116] | clopper-pearson | 30 | 0 |  |
| M-04.failed | 0.067 [0.018, 0.213] | wilson | 30 | 2 | failed_fallback plus missing predictions |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| account_access_issue | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| billing_duplicate_charge | 3 | 2 | 2 | 1.000 | 0.667 [0.208, 0.939] | 0.800 |
| billing_payment_failure | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| refund_request | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| plan_pricing_inquiry | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| service_outage | 3 | 5 | 3 | 0.600 | 1.000 [0.292, 1.000] | 0.750 |
| bug_report | 3 | 2 | 2 | 1.000 | 0.667 [0.208, 0.939] | 0.800 |
| how_to_question | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| security_report | 2 | 1 | 1 | 1.000 | 0.500 [0.095, 0.905] | 0.667 |
| privacy_legal_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| other_unclear | 2 | 0 | 0 | n/a | 0.000 [0.000, 0.842] | 0.000 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 3 | 2 | 2 | 1.000 | 0.667 [0.208, 0.939] | 0.800 |
| billing_payment_failure | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| service_outage | 3 | 5 | 3 | 0.600 | 1.000 [0.292, 1.000] | 0.750 |
| security_report | 2 | 1 | 1 | 1.000 | 0.500 [0.095, 0.905] | 0.667 |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | inv |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 billing_payment_failure | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 refund_request | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |
| 10 how_to_question | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| 11 security_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 1 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| 13 other_unclear | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 28 |
| repaired_l1 | 0 |
| repaired_l2 | 0 |
| failed_fallback | 2 |
| missing | 0 |

## Notes

- M-07a..d not computed: no prediction carries a policy decision
