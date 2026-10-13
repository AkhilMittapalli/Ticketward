# E3 on val: tw-e3-zeroshot-qwen3-4b-2507

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | 1b9169f8-7c55-4160-9d5d-dc37d36438d0 |
| Created | 2026-10-13T01:58:34+00:00 |
| Experiment / split | E3 / val (open) |
| System | tw-e3-zeroshot-qwen3-4b-2507 |
| Git SHA | 286ba022a8c38b13d26af683bf9ee8fe2cb4988f |
| Gold | records.jsonl (54a09e69ecfc) |
| Predictions | qwen3-4b-2507_val (249d0739fe5f) |
| Data manifests | data/manifests/val.json (a9ea2dcc4829) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 230, scored 230, missing 0, extra 0, with decision 0 |
| Holdout | phase P2; origins val 230 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.898 [0.866, 0.926] | stratified-percentile-bootstrap | 230 |  |  |
| M-01.intent_accuracy | 0.861 [0.810, 0.900] | wilson | 230 | 198 |  |
| M-01.other_unclear_f1 | 0.000 [0.000, 0.000] | stratified-percentile-bootstrap | 230 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.000 [0.000, 0.176] | clopper-pearson | 19 | 0 |  |
| M-01.other_unclear_precision | n/a | undefined (n = 0) | 0 |  |  |
| M-02.routing_accuracy | 0.939 [0.900, 0.963] | wilson | 230 | 216 | policy final queue for 0, model queue for 230, none for 0 |
| M-03.priority_accuracy | 0.561 [0.496, 0.623] | wilson | 230 | 129 |  |
| M-03.priority_within_one | 0.965 [0.933, 0.982] | wilson | 230 | 222 |  |
| M-03.product_area_accuracy | 0.796 [0.739, 0.843] | wilson | 230 | 183 |  |
| M-03.sentiment_macro_f1 | 0.242 [0.189, 0.297] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.churn_macro_f1 | 0.465 [0.409, 0.525] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.entity_f1 | 0.477 [0.444, 0.511] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 975, matched 348; ticket-cluster bootstrap |
| M-03.entity_precision | 0.357 [0.324, 0.392] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 975, matched 348; ticket-cluster bootstrap |
| M-03.entity_recall | 0.720 [0.687, 0.754] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 975, matched 348; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 1.000 [0.852, 1.000] | clopper-pearson | 23 | 23 |  |
| M-03c.model.billing_payment_failure_recall | 0.958 [0.798, 0.993] | wilson | 24 | 23 |  |
| M-03c.model.cancellation_request_recall | 1.000 [0.824, 1.000] | clopper-pearson | 19 | 19 |  |
| M-03c.model.service_outage_recall | 1.000 [0.877, 1.000] | clopper-pearson | 28 | 28 |  |
| M-03c.model.security_report_recall | 0.909 [0.722, 0.975] | wilson | 22 | 20 |  |
| M-03c.model.pooled_recall | 0.974 [0.927, 0.991] | wilson | 116 | 113 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-04.json_validity | 1.000 [0.984, 1.000] | clopper-pearson | 230 | 230 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 0.996 [0.976, 0.999] | wilson | 230 | 229 |  |
| M-04.schema_repair | 0.004 [0.001, 0.024] | wilson | 230 | 1 |  |
| M-04.failed | 0.000 [0.000, 0.016] | clopper-pearson | 230 | 0 | failed_fallback plus missing predictions |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 13 | 13 | 13 | 1.000 | 1.000 [0.753, 1.000] | 1.000 |
| account_access_issue | 12 | 12 | 11 | 0.917 | 0.917 [0.646, 0.985] | 0.917 |
| billing_duplicate_charge | 23 | 25 | 23 | 0.920 | 1.000 [0.852, 1.000] | 0.958 |
| billing_payment_failure | 24 | 23 | 23 | 1.000 | 0.958 [0.798, 0.993] | 0.979 |
| refund_request | 15 | 14 | 14 | 1.000 | 0.933 [0.702, 0.988] | 0.966 |
| cancellation_request | 19 | 19 | 19 | 1.000 | 1.000 [0.824, 1.000] | 1.000 |
| plan_pricing_inquiry | 6 | 7 | 6 | 0.857 | 1.000 [0.541, 1.000] | 0.923 |
| service_outage | 28 | 29 | 28 | 0.966 | 1.000 [0.877, 1.000] | 0.982 |
| bug_report | 14 | 9 | 6 | 0.667 | 0.429 [0.214, 0.674] | 0.522 |
| how_to_question | 16 | 40 | 16 | 0.400 | 1.000 [0.794, 1.000] | 0.571 |
| security_report | 22 | 20 | 20 | 1.000 | 0.909 [0.722, 0.975] | 0.952 |
| privacy_legal_request | 19 | 19 | 19 | 1.000 | 1.000 [0.824, 1.000] | 1.000 |
| other_unclear | 19 | 0 | 0 | n/a | 0.000 [0.000, 0.176] | 0.000 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 23 | 25 | 23 | 0.920 | 1.000 [0.852, 1.000] | 0.958 |
| billing_payment_failure | 24 | 23 | 23 | 1.000 | 0.958 [0.798, 0.993] | 0.979 |
| cancellation_request | 19 | 19 | 19 | 1.000 | 1.000 [0.824, 1.000] | 1.000 |
| service_outage | 28 | 29 | 28 | 0.966 | 1.000 [0.877, 1.000] | 0.982 |
| security_report | 22 | 20 | 20 | 1.000 | 0.909 [0.722, 0.975] | 0.952 |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 0 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 23 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 billing_payment_failure | 0 | 0 | 1 | 23 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 refund_request | 0 | 0 | 1 | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 6 | 7 | 0 | 0 | 0 |
| 10 how_to_question | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 |
| 11 security_report | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 20 | 0 | 0 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 0 |
| 13 other_unclear | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 3 | 14 | 0 | 0 | 0 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 229 |
| repaired_l1 | 1 |
| repaired_l2 | 0 |
| failed_fallback | 0 |
| missing | 0 |

## Notes

- M-07a..d not computed: no prediction carries a policy decision
