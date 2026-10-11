# E1 on hard_dev: tw-rules-baseline@rules_baseline.v1+2b18a02d5f8f

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | bd1ef683-7be8-4368-96cf-80c91f0ced75 |
| Created | 2026-10-11T23:54:26+00:00 |
| Experiment / split | E1 / hard_dev (open) |
| System | tw-rules-baseline@rules_baseline.v1+2b18a02d5f8f |
| Git SHA | fc26ebebe3f1089aec260b10bca8103bcbe9e0ca |
| Gold | hard_dev.v1.jsonl (a1e453f41e60) |
| Predictions | e1_hard_dev (3e40125d6d52) |
| Data manifests | data/manifests/test_hard.json (4f3f8a4151ac) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 30, scored 30, missing 0, extra 0, with decision 30 |
| Holdout | phase P2; origins hard_dev 30 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.845 [0.729, 0.933] | stratified-percentile-bootstrap | 30 |  |  |
| M-01.intent_accuracy | 0.800 [0.627, 0.905] | wilson | 30 | 24 |  |
| M-01.other_unclear_f1 | 0.500 [0.000, 1.000] | stratified-percentile-bootstrap | 30 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.500 [0.095, 0.905] | wilson | 2 | 1 |  |
| M-01.other_unclear_precision | 0.500 [0.095, 0.905] | wilson | 2 | 1 |  |
| M-02.routing_accuracy | 0.800 [0.627, 0.905] | wilson | 30 | 24 | policy final queue for 30, model queue for 0, none for 0 |
| M-03.priority_accuracy | 0.333 [0.192, 0.512] | wilson | 30 | 10 |  |
| M-03.priority_within_one | 0.800 [0.627, 0.905] | wilson | 30 | 24 |  |
| M-03.product_area_accuracy | 0.633 [0.455, 0.781] | wilson | 30 | 19 |  |
| M-03.sentiment_macro_f1 | 0.156 [0.103, 0.226] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.churn_macro_f1 | 0.472 [0.394, 0.545] | stratified-percentile-bootstrap | 30 |  |  |
| M-03.entity_f1 | 0.781 [0.716, 0.842] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 69, matched 59; ticket-cluster bootstrap |
| M-03.entity_precision | 0.855 [0.778, 0.928] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 69, matched 59; ticket-cluster bootstrap |
| M-03.entity_recall | 0.720 [0.640, 0.803] | ticket-cluster-percentile-bootstrap | 30 |  | gold entities 82, predicted 69, matched 59; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 0.667 [0.208, 0.939] | wilson | 3 | 2 |  |
| M-03c.model.billing_payment_failure_recall | 0.667 [0.208, 0.939] | wilson | 3 | 2 |  |
| M-03c.model.cancellation_request_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.model.service_outage_recall | 0.667 [0.208, 0.939] | wilson | 3 | 2 |  |
| M-03c.model.security_report_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.model.pooled_recall | 0.769 [0.497, 0.918] | wilson | 13 | 10 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-03c.system.billing_duplicate_charge_recall | 0.667 [0.208, 0.939] | wilson | 3 | 2 |  |
| M-03c.system.billing_payment_failure_recall | 1.000 [0.292, 1.000] | clopper-pearson | 3 | 3 |  |
| M-03c.system.cancellation_request_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.system.service_outage_recall | 0.667 [0.208, 0.939] | wilson | 3 | 2 |  |
| M-03c.system.security_report_recall | 1.000 [0.158, 1.000] | clopper-pearson | 2 | 2 |  |
| M-03c.system.pooled_recall | 0.846 [0.578, 0.957] | wilson | 13 | 11 | model primary/secondary intent, the class's forced reason or N6, pooled |
| M-04.json_validity | 1.000 [0.884, 1.000] | clopper-pearson | 30 | 30 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 1.000 [0.884, 1.000] | clopper-pearson | 30 | 30 |  |
| M-04.schema_repair | 0.000 [0.000, 0.116] | clopper-pearson | 30 | 0 |  |
| M-04.failed | 0.000 [0.000, 0.116] | clopper-pearson | 30 | 0 | failed_fallback plus missing predictions |
| M-07a.forced_escalation | 0.882 [0.657, 0.967]; one-sided 95% lower bound 0.6738 | wilson | 17 | 15 | gate 1.00; published with n and the one-sided exact 95% lower bound |
| M-07b.correct_abstention | 0.750 [0.301, 0.954] | wilson | 4 | 3 |  |
| M-07c.over_escalation | 0.111 [0.020, 0.435] | wilson | 9 | 1 | lower is better |
| M-07d.human_request_recall_explicit | 0.500 [0.095, 0.905] | wilson | 2 | 1 |  |
| M-07d.human_request_recall_indirect | 0.000 [0.000, 0.975] | clopper-pearson | 1 | 0 |  |
| M-07d.human_request_recall | 0.333 [0.061, 0.792] | wilson | 3 | 1 |  |
| M-07d.false_positive_rate | 0.000 [0.000, 0.128] | clopper-pearson | 27 | 0 | customer_requested_human reason on tickets without a request; lower is better |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| account_access_issue | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| billing_duplicate_charge | 3 | 2 | 2 | 1.000 | 0.667 [0.208, 0.939] | 0.800 |
| billing_payment_failure | 3 | 2 | 2 | 1.000 | 0.667 [0.208, 0.939] | 0.800 |
| refund_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| plan_pricing_inquiry | 2 | 4 | 2 | 0.500 | 1.000 [0.158, 1.000] | 0.667 |
| service_outage | 3 | 4 | 2 | 0.500 | 0.667 [0.208, 0.939] | 0.571 |
| bug_report | 3 | 1 | 1 | 1.000 | 0.333 [0.061, 0.792] | 0.500 |
| how_to_question | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| security_report | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |
| privacy_legal_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| other_unclear | 2 | 2 | 1 | 0.500 | 0.500 [0.095, 0.905] | 0.500 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 3 | 2 | 2 | 1.000 | 0.667 [0.208, 0.939] | 0.800 |
| billing_payment_failure | 3 | 2 | 2 | 1.000 | 0.667 [0.208, 0.939] | 0.800 |
| cancellation_request | 2 | 2 | 2 | 1.000 | 1.000 [0.158, 1.000] | 1.000 |
| service_outage | 3 | 4 | 2 | 0.500 | 0.667 [0.208, 0.939] | 0.571 |
| security_report | 2 | 3 | 2 | 0.667 | 1.000 [0.158, 1.000] | 0.800 |

## Per class: critical_system

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 3 |  | 2 | n/a | 0.667 [0.208, 0.939] | n/a |
| billing_payment_failure | 3 |  | 3 | n/a | 1.000 [0.292, 1.000] | n/a |
| cancellation_request | 2 |  | 2 | n/a | 1.000 [0.158, 1.000] | n/a |
| service_outage | 3 |  | 2 | n/a | 0.667 [0.208, 0.939] | n/a |
| security_report | 2 |  | 2 | n/a | 1.000 [0.158, 1.000] | n/a |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 billing_payment_failure | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| 5 refund_request | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 1 |
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
