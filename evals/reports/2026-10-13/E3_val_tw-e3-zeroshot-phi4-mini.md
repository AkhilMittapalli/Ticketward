# E3 on val: tw-e3-zeroshot-phi4-mini

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | 39b23239-9139-4a52-b786-4d0386f16444 |
| Created | 2026-10-13T01:58:53+00:00 |
| Experiment / split | E3 / val (open) |
| System | tw-e3-zeroshot-phi4-mini |
| Git SHA | 286ba022a8c38b13d26af683bf9ee8fe2cb4988f |
| Gold | records.jsonl (54a09e69ecfc) |
| Predictions | phi4-mini_val (b7002231f230) |
| Data manifests | data/manifests/val.json (a9ea2dcc4829) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 230, scored 230, missing 0, extra 0, with decision 0 |
| Holdout | phase P2; origins val 230 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.898 [0.865, 0.930] | stratified-percentile-bootstrap | 230 |  |  |
| M-01.intent_accuracy | 0.865 [0.815, 0.903] | wilson | 230 | 199 |  |
| M-01.other_unclear_f1 | 0.000 [0.000, 0.000] | stratified-percentile-bootstrap | 230 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.000 [0.000, 0.176] | clopper-pearson | 19 | 0 |  |
| M-01.other_unclear_precision | n/a | undefined (n = 0) | 0 |  |  |
| M-02.routing_accuracy | 0.904 [0.859, 0.936] | wilson | 230 | 208 | policy final queue for 0, model queue for 230, none for 0 |
| M-03.priority_accuracy | 0.552 [0.488, 0.615] | wilson | 230 | 127 |  |
| M-03.priority_within_one | 0.983 [0.956, 0.993] | wilson | 230 | 226 |  |
| M-03.product_area_accuracy | 0.626 [0.562, 0.686] | wilson | 230 | 144 |  |
| M-03.sentiment_macro_f1 | 0.215 [0.167, 0.264] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.churn_macro_f1 | 0.513 [0.447, 0.583] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.entity_f1 | 0.340 [0.295, 0.386] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 599, matched 184; ticket-cluster bootstrap |
| M-03.entity_precision | 0.307 [0.256, 0.367] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 599, matched 184; ticket-cluster bootstrap |
| M-03.entity_recall | 0.381 [0.326, 0.436] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 599, matched 184; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 1.000 [0.852, 1.000] | clopper-pearson | 23 | 23 |  |
| M-03c.model.billing_payment_failure_recall | 0.875 [0.690, 0.957] | wilson | 24 | 21 |  |
| M-03c.model.cancellation_request_recall | 0.947 [0.754, 0.991] | wilson | 19 | 18 |  |
| M-03c.model.service_outage_recall | 1.000 [0.877, 1.000] | clopper-pearson | 28 | 28 |  |
| M-03c.model.security_report_recall | 0.864 [0.667, 0.953] | wilson | 22 | 19 |  |
| M-03c.model.pooled_recall | 0.940 [0.881, 0.970] | wilson | 116 | 109 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-04.json_validity | 1.000 [0.984, 1.000] | clopper-pearson | 230 | 230 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 1.000 [0.984, 1.000] | clopper-pearson | 230 | 230 |  |
| M-04.schema_repair | 0.000 [0.000, 0.016] | clopper-pearson | 230 | 0 |  |
| M-04.failed | 0.000 [0.000, 0.016] | clopper-pearson | 230 | 0 | failed_fallback plus missing predictions |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 13 | 15 | 13 | 0.867 | 1.000 [0.753, 1.000] | 0.929 |
| account_access_issue | 12 | 11 | 10 | 0.909 | 0.833 [0.552, 0.953] | 0.870 |
| billing_duplicate_charge | 23 | 26 | 23 | 0.885 | 1.000 [0.852, 1.000] | 0.939 |
| billing_payment_failure | 24 | 21 | 21 | 1.000 | 0.875 [0.690, 0.957] | 0.933 |
| refund_request | 15 | 14 | 14 | 1.000 | 0.933 [0.702, 0.988] | 0.966 |
| cancellation_request | 19 | 18 | 18 | 1.000 | 0.947 [0.754, 0.991] | 0.973 |
| plan_pricing_inquiry | 6 | 8 | 6 | 0.750 | 1.000 [0.541, 1.000] | 0.857 |
| service_outage | 28 | 29 | 28 | 0.966 | 1.000 [0.877, 1.000] | 0.982 |
| bug_report | 14 | 25 | 13 | 0.520 | 0.929 [0.685, 0.987] | 0.667 |
| how_to_question | 16 | 25 | 15 | 0.600 | 0.938 [0.717, 0.989] | 0.732 |
| security_report | 22 | 19 | 19 | 1.000 | 0.864 [0.667, 0.953] | 0.927 |
| privacy_legal_request | 19 | 19 | 19 | 1.000 | 1.000 [0.824, 1.000] | 1.000 |
| other_unclear | 19 | 0 | 0 | n/a | 0.000 [0.000, 0.176] | 0.000 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 23 | 26 | 23 | 0.885 | 1.000 [0.852, 1.000] | 0.939 |
| billing_payment_failure | 24 | 21 | 21 | 1.000 | 0.875 [0.690, 0.957] | 0.933 |
| cancellation_request | 19 | 18 | 18 | 1.000 | 0.947 [0.754, 0.991] | 0.973 |
| service_outage | 28 | 29 | 28 | 0.966 | 1.000 [0.877, 1.000] | 0.982 |
| security_report | 22 | 19 | 19 | 1.000 | 0.864 [0.667, 0.953] | 0.927 |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 1 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 23 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 billing_payment_failure | 0 | 1 | 2 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 refund_request | 0 | 0 | 1 | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 18 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 1 | 0 | 0 | 0 |
| 10 how_to_question | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 15 | 0 | 0 | 0 |
| 11 security_report | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 19 | 0 | 0 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 0 |
| 13 other_unclear | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 9 | 9 | 0 | 0 | 0 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 230 |
| repaired_l1 | 0 |
| repaired_l2 | 0 |
| failed_fallback | 0 |
| missing | 0 |

## Notes

- M-07a..d not computed: no prediction carries a policy decision
