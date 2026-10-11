# E1 on val: tw-rules-baseline@rules_baseline.v1+2b18a02d5f8f

Estimates are `point [low, high]` at the stated level; method and n per row (evals/ANALYSIS_PLAN.md).

| Field | Value |
|---|---|
| Run | d6f60da9-d835-40e1-b922-ead69b6521ae |
| Created | 2026-10-11T23:54:14+00:00 |
| Experiment / split | E1 / val (open) |
| System | tw-rules-baseline@rules_baseline.v1+2b18a02d5f8f |
| Git SHA | fc26ebebe3f1089aec260b10bca8103bcbe9e0ca |
| Gold | records.jsonl (54a09e69ecfc) |
| Predictions | e1_val (12fba87af387) |
| Data manifests | data/manifests/val.json (a9ea2dcc4829) |
| Analysis plan | evals/ANALYSIS_PLAN.md (8c9476decdb2) |
| Taxonomy / label rules | 2026-09-v1 / label_rules.v1 |
| Bootstrap | B = 10000, seed 2026, level 95% |
| Records | gold 230, scored 230, missing 0, extra 0, with decision 230 |
| Holdout | phase P2; origins val 230 |

## Metrics

| Metric | Estimate | Method | n | k | Notes |
|---|---|---|---|---|---|
| M-01.intent_macro_f1 | 0.761 [0.711, 0.809] | stratified-percentile-bootstrap | 230 |  |  |
| M-01.intent_accuracy | 0.743 [0.683, 0.796] | wilson | 230 | 171 |  |
| M-01.other_unclear_f1 | 0.121 [0.000, 0.278] | stratified-percentile-bootstrap | 230 |  | reported separately; not part of the 12-intent macro-F1 |
| M-01.other_unclear_recall | 0.105 [0.029, 0.314] | wilson | 19 | 2 |  |
| M-01.other_unclear_precision | 0.143 [0.040, 0.399] | wilson | 14 | 2 |  |
| M-02.routing_accuracy | 0.813 [0.758, 0.858] | wilson | 230 | 187 | policy final queue for 230, model queue for 0, none for 0 |
| M-03.priority_accuracy | 0.513 [0.449, 0.577] | wilson | 230 | 118 |  |
| M-03.priority_within_one | 0.913 [0.870, 0.943] | wilson | 230 | 210 |  |
| M-03.product_area_accuracy | 0.735 [0.674, 0.788] | wilson | 230 | 169 |  |
| M-03.sentiment_macro_f1 | 0.240 [0.197, 0.282] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.churn_macro_f1 | 0.701 [0.640, 0.761] | stratified-percentile-bootstrap | 230 |  |  |
| M-03.entity_f1 | 0.784 [0.750, 0.816] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 609, matched 428; ticket-cluster bootstrap |
| M-03.entity_precision | 0.703 [0.656, 0.748] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 609, matched 428; ticket-cluster bootstrap |
| M-03.entity_recall | 0.886 [0.853, 0.916] | ticket-cluster-percentile-bootstrap | 230 |  | gold entities 483, predicted 609, matched 428; ticket-cluster bootstrap |
| M-03c.model.billing_duplicate_charge_recall | 0.696 [0.491, 0.844] | wilson | 23 | 16 |  |
| M-03c.model.billing_payment_failure_recall | 0.875 [0.690, 0.957] | wilson | 24 | 21 |  |
| M-03c.model.cancellation_request_recall | 0.947 [0.754, 0.991] | wilson | 19 | 18 |  |
| M-03c.model.service_outage_recall | 1.000 [0.877, 1.000] | clopper-pearson | 28 | 28 |  |
| M-03c.model.security_report_recall | 0.727 [0.518, 0.868] | wilson | 22 | 16 |  |
| M-03c.model.pooled_recall | 0.853 [0.778, 0.906] | wilson | 116 | 99 | primary intent == gold primary intent, pooled over the 5 critical classes |
| M-03c.system.billing_duplicate_charge_recall | 0.696 [0.491, 0.844] | wilson | 23 | 16 |  |
| M-03c.system.billing_payment_failure_recall | 0.958 [0.798, 0.993] | wilson | 24 | 23 |  |
| M-03c.system.cancellation_request_recall | 0.947 [0.754, 0.991] | wilson | 19 | 18 |  |
| M-03c.system.service_outage_recall | 1.000 [0.877, 1.000] | clopper-pearson | 28 | 28 |  |
| M-03c.system.security_report_recall | 0.727 [0.518, 0.868] | wilson | 22 | 16 |  |
| M-03c.system.pooled_recall | 0.871 [0.798, 0.920] | wilson | 116 | 101 | model primary/secondary intent, the class's forced reason or N6, pooled |
| M-04.json_validity | 1.000 [0.984, 1.000] | clopper-pearson | 230 | 230 | (first_pass + repaired_l1 + repaired_l2) / total |
| M-04.first_pass | 1.000 [0.984, 1.000] | clopper-pearson | 230 | 230 |  |
| M-04.schema_repair | 0.000 [0.000, 0.016] | clopper-pearson | 230 | 0 |  |
| M-04.failed | 0.000 [0.000, 0.016] | clopper-pearson | 230 | 0 | failed_fallback plus missing predictions |
| M-07a.forced_escalation | 0.913 [0.857, 0.949]; one-sided 95% lower bound 0.8657 | wilson | 150 | 137 | gate 1.00; published with n and the one-sided exact 95% lower bound |
| M-07b.correct_abstention | 0.553 [0.412, 0.686] | wilson | 47 | 26 |  |
| M-07c.over_escalation | 0.180 [0.098, 0.308] | wilson | 50 | 9 | lower is better |
| M-07d.human_request_recall_explicit | n/a | undefined (n = 0) | 0 |  |  |
| M-07d.human_request_recall_indirect | n/a | undefined (n = 0) | 0 |  |  |
| M-07d.human_request_recall | n/a | undefined (n = 0) | 0 |  |  |
| M-07d.false_positive_rate | 0.009 [0.002, 0.031] | wilson | 230 | 2 | customer_requested_human reason on tickets without a request; lower is better |

## Per class: intent

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| sso_login_failure | 13 | 14 | 12 | 0.857 | 0.923 [0.667, 0.986] | 0.889 |
| account_access_issue | 12 | 14 | 11 | 0.786 | 0.917 [0.646, 0.985] | 0.846 |
| billing_duplicate_charge | 23 | 19 | 16 | 0.842 | 0.696 [0.491, 0.844] | 0.762 |
| billing_payment_failure | 24 | 21 | 21 | 1.000 | 0.875 [0.690, 0.957] | 0.933 |
| refund_request | 15 | 12 | 10 | 0.833 | 0.667 [0.417, 0.848] | 0.741 |
| cancellation_request | 19 | 20 | 18 | 0.900 | 0.947 [0.754, 0.991] | 0.923 |
| plan_pricing_inquiry | 6 | 17 | 5 | 0.294 | 0.833 [0.436, 0.970] | 0.435 |
| service_outage | 28 | 36 | 28 | 0.778 | 1.000 [0.877, 1.000] | 0.875 |
| bug_report | 14 | 13 | 5 | 0.385 | 0.357 [0.163, 0.612] | 0.370 |
| how_to_question | 16 | 12 | 9 | 0.750 | 0.562 [0.332, 0.769] | 0.643 |
| security_report | 22 | 16 | 16 | 1.000 | 0.727 [0.518, 0.868] | 0.842 |
| privacy_legal_request | 19 | 22 | 18 | 0.818 | 0.947 [0.754, 0.991] | 0.878 |
| other_unclear | 19 | 14 | 2 | 0.143 | 0.105 [0.029, 0.314] | 0.121 |

## Per class: critical_model

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 23 | 19 | 16 | 0.842 | 0.696 [0.491, 0.844] | 0.762 |
| billing_payment_failure | 24 | 21 | 21 | 1.000 | 0.875 [0.690, 0.957] | 0.933 |
| cancellation_request | 19 | 20 | 18 | 0.900 | 0.947 [0.754, 0.991] | 0.923 |
| service_outage | 28 | 36 | 28 | 0.778 | 1.000 [0.877, 1.000] | 0.875 |
| security_report | 22 | 16 | 16 | 1.000 | 0.727 [0.518, 0.868] | 0.842 |

## Per class: critical_system

| Class | Support | Predicted | TP | Precision | Recall [95% CI] | F1 |
|---|---|---|---|---|---|---|
| billing_duplicate_charge | 23 |  | 16 | n/a | 0.696 [0.491, 0.844] | n/a |
| billing_payment_failure | 24 |  | 23 | n/a | 0.958 [0.798, 0.993] | n/a |
| cancellation_request | 19 |  | 18 | n/a | 0.947 [0.754, 0.991] | n/a |
| service_outage | 28 |  | 28 | n/a | 1.000 [0.877, 1.000] | n/a |
| security_report | 22 |  | 16 | n/a | 0.727 [0.518, 0.868] | n/a |

## Confusion matrix: intent

| gold \ predicted | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 sso_login_failure | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2 account_access_issue | 0 | 11 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 billing_duplicate_charge | 0 | 0 | 16 | 0 | 1 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 2 |
| 4 billing_payment_failure | 0 | 0 | 2 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| 5 refund_request | 0 | 0 | 1 | 0 | 10 | 1 | 1 | 0 | 0 | 0 | 0 | 2 | 0 |
| 6 cancellation_request | 0 | 0 | 0 | 0 | 0 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| 7 plan_pricing_inquiry | 0 | 0 | 0 | 0 | 0 | 1 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 service_outage | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 0 |
| 9 bug_report | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 4 | 5 | 0 | 0 | 0 | 3 |
| 10 how_to_question | 1 | 1 | 0 | 0 | 0 | 0 | 3 | 0 | 1 | 9 | 0 | 0 | 1 |
| 11 security_report | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 16 | 0 | 3 |
| 12 privacy_legal_request | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 18 | 1 |
| 13 other_unclear | 1 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | 6 | 3 | 0 | 2 | 2 |

## Validity tiers

| Tier | Count |
|---|---|
| first_pass | 230 |
| repaired_l1 | 0 |
| repaired_l2 | 0 |
| failed_fallback | 0 |
| missing | 0 |
