# E3 on val: tw-e3-zeroshot-qwen35-2b

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | 20a3c843-25ff-4295-82fc-d3bba6091cd2 |
| Created | 2026-10-13T01:58:16+00:00 |
| Experiment / split | E3 / val (open) |
| System | tw-e3-zeroshot-qwen35-2b |
| Git SHA | 286ba022a8c38b13d26af683bf9ee8fe2cb4988f |
| Gold | records.jsonl (54a09e69ecfc) |
| Predictions | qwen35-2b_val (86f05cf4e04e) |
| Data manifests | data/manifests/val.json (a9ea2dcc4829) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 230, scored 230, missing 0, extra 0, with decision 0 |
| Holdout | phase P2; origins val 230 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.772 [0.717, 0.821] | stratified-percentile-bootstrap | 230 |  |  |
| M-01.intent_accuracy | 0.722 [0.661, 0.776] | wilson | 230 | 166 |  |
| M-01.other_unclear_f1 | 0.000 [0.000, 0.000] | stratified-percentile-bootstrap | 230 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.000 [0.000, 0.176] | clopper-pearson | 19 | 0 |  |
| M-01.other_unclear_precision | n/a | undefined (n = 0) | 0 |  |  |
| M-02.routing_accuracy | 0.770 [0.711, 0.819] | wilson | 230 | 177 | policy final queue for 0, model queue for 208, none for 22 |
| M-03.priority_accuracy | 0.443 [0.381, 0.508] | wilson | 230 | 102 |  |
| M-03.priority_within_one | 0.839 [0.786, 0.881] | wilson | 230 | 193 |  |
| M-03.product_area_accuracy | 0.561 [0.496, 0.623] | wilson | 230 | 129 |  |
| M-03.sentiment_macro_f1 | 0.136 [0.108, 0.164] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.churn_macro_f1 | 0.598 [0.526, 0.672] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.entity_f1 | 0.425 [0.391, 0.461] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 862, matched 286; ticket-cluster bootstrap |
| M-03.entity_precision | 0.332 [0.296, 0.370] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 862, matched 286; ticket-cluster bootstrap |
| M-03.entity_recall | 0.592 [0.550, 0.634] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 862, matched 286; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 0.783 [0.581, 0.903] | wilson | 23 | 18 |  |
| M-03c.model.billing_payment_failure_recall | 0.750 [0.551, 0.880] | wilson | 24 | 18 |  |
| M-03c.model.cancellation_request_recall | 0.895 [0.686, 0.971] | wilson | 19 | 17 |  |
| M-03c.model.service_outage_recall | 0.964 [0.823, 0.994] | wilson | 28 | 27 |  |
| M-03c.model.security_report_recall | 0.727 [0.518, 0.868] | wilson | 22 | 16 |  |
| M-03c.model.pooled_recall | 0.828 [0.749, 0.886] | wilson | 116 | 96 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-04.json_validity | 0.904 [0.859, 0.936] | wilson | 230 | 208 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 0.904 [0.859, 0.936] | wilson | 230 | 208 |  |
| M-04.schema_repair | 0.000 [0.000, 0.016] | clopper-pearson | 230 | 0 |  |
| M-04.failed | 0.096 [0.064, 0.141] | wilson | 230 | 22 | failed_fallback plus missing predictions |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 13 | 18 | 13 | 0.722 | 1.000 [0.753, 1.000] | 0.839 |
| account_access_issue | 12 | 3 | 3 | 1.000 | 0.250 [0.089, 0.532] | 0.400 |
| billing_duplicate_charge | 23 | 19 | 18 | 0.947 | 0.783 [0.581, 0.903] | 0.857 |
| billing_payment_failure | 24 | 18 | 18 | 1.000 | 0.750 [0.551, 0.880] | 0.857 |
| refund_request | 15 | 16 | 11 | 0.688 | 0.733 [0.480, 0.891] | 0.710 |
| cancellation_request | 19 | 17 | 17 | 1.000 | 0.895 [0.686, 0.971] | 0.944 |
| plan_pricing_inquiry | 6 | 8 | 6 | 0.750 | 1.000 [0.541, 1.000] | 0.857 |
| service_outage | 28 | 42 | 27 | 0.643 | 0.964 [0.823, 0.994] | 0.771 |
| bug_report | 14 | 12 | 8 | 0.667 | 0.571 [0.326, 0.786] | 0.615 |
| how_to_question | 16 | 21 | 12 | 0.571 | 0.750 [0.505, 0.898] | 0.649 |
| security_report | 22 | 16 | 16 | 1.000 | 0.727 [0.518, 0.868] | 0.842 |
| privacy_legal_request | 19 | 18 | 17 | 0.944 | 0.895 [0.686, 0.971] | 0.919 |
| other_unclear | 19 | 0 | 0 | n/a | 0.000 [0.000, 0.176] | 0.000 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 23 | 19 | 18 | 0.947 | 0.783 [0.581, 0.903] | 0.857 |
| billing_payment_failure | 24 | 18 | 18 | 1.000 | 0.750 [0.551, 0.880] | 0.857 |
| cancellation_request | 19 | 17 | 17 | 1.000 | 0.895 [0.686, 0.971] | 0.944 |
| service_outage | 28 | 42 | 27 | 0.643 | 0.964 [0.823, 0.994] | 0.771 |
| security_report | 22 | 16 | 16 | 1.000 | 0.727 [0.518, 0.868] | 0.842 |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | inv |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 5 | 3 | 0 | 0 | 0 | 0 | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 1 |
| 3 billing_duplicate_charge | 0 | 0 | 18 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 billing_payment_failure | 0 | 0 | 1 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 |
| 5 refund_request | 0 | 0 | 0 | 0 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 3 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 0 | 0 | 0 | 0 | 0 | 1 |
| 9 bug_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 8 | 0 | 0 | 0 | 0 | 2 |
| 10 how_to_question | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | 0 | 12 | 0 | 0 | 0 | 0 |
| 11 security_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 1 | 0 | 16 | 0 | 0 | 2 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 17 | 0 | 2 |
| 13 other_unclear | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | 2 | 9 | 0 | 0 | 0 | 4 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 208 |
| repaired_l1 | 0 |
| repaired_l2 | 0 |
| failed_fallback | 22 |
| missing | 0 |

## Notes

- M-07a..d not computed: no prediction carries a policy decision
