# Generated dataset dictionary

All values are synthetic and use seed `20261022`. IDs are stable across runs. Timestamps export in UTC ISO 8601 (`Z`). Generated export rows use model columns plus clearly named synthetic-only metadata where the database has no column for it.

## Entity relationship map

- A customer has orders, complaints, and surveys.
- Products belong to product categories; orders contain one or more order items referencing products.
- Complaints reference a customer, category, and optional order/product.
- Assignments and messages reference complaints; assignments also reference agents.
- Each complaint has one SLA clock with an event timeline, zero or more resolution attempts and status/reopen history, and at most one survey.
- Repeat links point from a newer complaint to an earlier complaint ID. Ground truth and anomaly records are separate evaluation exports, not application tables.

## Entity fields

Each CSV/JSON entity file contains the corresponding SQLAlchemy model columns. In addition:

| Entity | Additional exported fields | Key rules |
|---|---|---|
| Customers | — | `CUS-######`; contact values are synthetic |
| Products | `is_safety_related` | `PRD-######`; 30 products across five categories |
| Categories | — | Stable `CAT-######` IDs |
| Priority rules | — | Ten model-backed category defaults used during complaint priority scoring |
| Orders | `payment_status`, `delivery_status` | `ORD-2026-######`; totals equal order item totals |
| Order items | — | Positive quantity and unit price; line total reconciles |
| Complaints | `priority_reason` | `CMP-2026-######`; safety issues are Critical |
| Agents | — | `AGT-######`; synthetic `.invalid` email addresses |
| Assignments | — | Sequence-specific `ASN-...` IDs; active/available agents |
| Complaint messages | — | Three ordered messages per complaint |
| SLA clocks/events | — | Priority-targeted deadlines; pause/resume/breach timeline |
| Resolutions | — | Supported model resolution types; refund amount is encoded in notes |
| Status/reopen history | — | Chronological lifecycle events |
| Surveys | — | Rating 1–5 and submitted after closure |
| Ground truth | expected category, priority, severity, repeat flag/link, safety, breach, anomaly label | Separate evaluation data; never fed to classifiers |
| Anomalies | anomaly type, description, expected behavior, invalid values, ground-truth label | Six isolated intentionally invalid cases; never inserted into valid tables |
| Validation summary | checks, counts, warnings, errors | Structured run report |

Model columns retain SQLAlchemy names and foreign keys are exported as stable IDs. CSV nested fields (e.g. validation details and anomaly values) use compact JSON text. CSV scalar values are text-form representations of their JSON counterparts.

## Expected record counts

Starter uses 50 customers, 30 products, 15 categories, 10 priority rules, 80 orders, 20 complaints, 10 agents, 60 messages, 20 SLA clocks, and six anomaly records. Full uses 5,000 customers, 30 products, 15 categories, 10 priority rules, 8,000 orders, 2,000 complaints, 50 agents, 6,000 messages, 2,000 SLA clocks, and six anomaly records. Assignments, line items, SLA events, histories, resolutions, and surveys are generated according to business logic and therefore vary by mode/seed.

## Known schema limitations

Product safety flags, order payment/delivery statuses, complaint severity/repeat link/priority reason, and expected scenario labels are generator metadata and have no persisted model columns. Resolution has no numeric refund column; a strict `Synthetic refund amount: $N.NN` marker in customer notes is used and validated against the order total. Complaint closure time is represented by status history. Phase 8 creates ten deterministic category-based PriorityRule records from the existing model and passes them into complaint classification/scoring.
