# E3 on hard_dev: tw-e3-zeroshot-phi4-mini

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | 85fd3cb5-e398-4437-99d2-a09102ce452d |
| Created | 2026-10-13T01:59:05+00:00 |
| Experiment / split | E3 / hard_dev (open) |
| System | tw-e3-zeroshot-phi4-mini |
| Git SHA | 286ba022a8c38b13d26af683bf9ee8fe2cb4988f |
| Gold | hard_dev.v1.jsonl (a1e453f41e60) |
| Predictions | phi4-mini_hard_dev (f43f3c85925b) |
| Data manifests | data/manifests/test_hard.json (4f3f8a4151ac) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 30, scored 30, missing 0, extra 0, with decision 0 |
| Holdout | phase P2; origins hard_dev 30 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.983 [0.972, 1.000] | stratified-percentile-bootstrap | 30 |  |  |
| M-01.intent_accuracy | 0.967 [0.833, 0.994] | wilson | 30 | 29 |  |
| M-01.other_unclear_f1 | 0.667 [0.000, 1.000] | stratified-percentile-bootstrap | 30 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.500 [0.095, 0.905] | wilson | 2 | 1 |  |
| M-01.other_unclear_precision | 1.000 [0.025, 1.000] | clopper-pearson | 1 | 1 |  |
| M-02.routing_accuracy | 0.967 [0.833, 0.994] | wilson | 30 | 29 | policy final queue for 0, model queue for 30, none for 0 |
| M-03.priority_accuracy | 0.500 [0.332, 0.668] | wilson | 30 | 15 |  |
| M-03.priority_within_one | 0.967 [0.833, 0.994] | wilson | 30 | 29 |  |
| M-03.product_area_accuracy | 0.633 [0.455, 0.781] | wilson | 30 | 19 |  |
| M-03.sentiment_macro_f1 | 0.260 [0.197, 0.318] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.churn_macro_f1 | 0.373 [0.210, 0.548] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.entity_f1 | 0.537 [0.423, 0.636] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 82, matched 44; ticket-cluster bootstrap |
| M-03.entity_precision | 0.537 [0.421, 0.667] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 82, matched 44; ticket-cluster bootstrap |
| M-03.entity_recall | 0.537 [0.400, 0.670] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 82, matched 44; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.billing_payment_failure_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.cancellation_request_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.model.service_outage_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.model.security_report_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.model.pooled_recall | 1.000 [0.753, 1.000] | clopper-pearson | 13 | 13 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-04.json_validity | 1.000 [0.884, 1.000] | clopper-pearson | 30 | 30 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 1.000 [0.884, 1.000] | clopper-pearson | 30 | 30 |  |
| M-04.schema_repair | 0.000 [0.000, 0.116] | clopper-pearson | 30 | 0 |  |
| M-04.failed | 0.000 [0.000, 0.116] | clopper-pearson | 30 | 0 | failed_fallback plus missing predictions |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| account_access_issue | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| billing_duplicate_charge | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| billing_payment_failure | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| refund_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| plan_pricing_inquiry | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| service_outage | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| bug_report | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| how_to_question | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| security_report | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |
| privacy_legal_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| other_unclear | 2 | 1 | 1 | 1.000 | 0.500 [0.095, 0.905] | 0.667 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| billing_payment_failure | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| service_outage | 3 | 3 | 3 | 1.000 | 1.000 [0.292, 1.000] | 1.000 |
| security_report | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 billing_payment_failure | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 refund_request | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| 10 how_to_question | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| 11 security_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| 13 other_unclear | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 30 |
| repaired_l1 | 0 |
| repaired_l2 | 0 |
| failed_fallback | 0 |
| missing | 0 |

## Notes

- M-07a..d not computed: no prediction carries a policy decision
