# Phase 8 validation report

## Resolution rate formula

`resolution_rate_percent = count(complaints whose final status is Resolved or Closed) / count(all complaints) * 100`, rounded to two decimal places. Reopened complaints are not counted as currently resolved. Resolution rows count attempts, including historical attempts retained for reopened complaints.

For seed `20261022`, the prior Phase 7 report's 698 resolution rows were incorrectly read as the resolved numerator. Those records included historical attempts for reopened complaints; the Phase 7 metric itself used 609 current Resolved/Closed complaints over 2,000 total (30.45%). Phase 8 corrected order dates that predated customer creation, which changes seeded downstream cases. On the corrected integrated pipeline, Full has 594 current Resolved/Closed complaints, 684 resolution attempts (including 90 historical attempts), and a rate of `594 / 2000 * 100 = 29.70%`. Starter has 9 resolved/closed cases, 10 resolution attempts (including 1 reopened history), and a rate of 45.00%. Current Starter average resolution time is 4.31 hours and refund total is $35.62. Full average resolution time is 11.50 hours and refund total is $34,649.05. `generator.metrics.calculate_resolution_feedback_metrics` uses this consistent complaint-based formula.

## Global checks

Validation checks unique available IDs (database autoincrement IDs are necessarily unset before persistence), order arithmetic, complaint constraints, active-agent assignment, message sequences, SLA clocks/events and targets, priority rules, resolution lifecycle and refund bounds, survey rules, foreign-key object references, dates, safety priority, and repeat chronology/cycles. Seed 20261022 validates 31/31 baseline checks in both Starter and Full. Starter counts: 50 customers, 30 products, 15 categories, 10 priority rules, 80 orders/187 line items, 20 complaints, 10 agents, 21 assignments, 60 messages, 20 clocks/43 events, 10 resolutions, 63 status events, 1 reopen, 6 surveys. Full counts: 5,000 customers, 30 products, 15 categories, 10 priority rules, 8,000 orders/19,952 line items, 2,000 complaints, 50 agents, 2,110 assignments, 6,000 messages, 2,000 clocks/4,234 events, 684 resolutions, 5,580 status events, 90 reopens, 401 surveys. The report exposes total/passed/failed checks, errors, warnings, and entity counts. Validation errors cause the Phase 8 CLI to return a non-zero status.

## Anomaly cases

The six `ANM-######` scenarios remain separate from valid SQLAlchemy records: invalid customer foreign key, resolution before complaint creation, bad pause arithmetic, missing earlier-repeat link, safety case routed to Low queue, and survey before closure. Each has invalid values, expected behavior, and a ground-truth invalid label. `generator.anomalies.detect_anomaly` independently evaluates each scenario.

## Baseline-specific note

Authored scenario category labels are preserved independently from classifier output. The fixed Starter seed has one classification mismatch and Full has 30, where an authored scenario is classified differently using structured order context (notably a generic scenario associated with a refunded order). These are reported as warnings instead of being overwritten in ground truth. Complaint exports do not contain expected category, expected severity, or the ground-truth repeat link; those fields live only in the separate ground-truth files.
