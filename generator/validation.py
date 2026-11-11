"""Cross-entity validation for the generated valid baseline dataset."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timezone
from decimal import Decimal
from typing import Any

from generator.assignments import validate_assignments
from generator.complaints import validate_complaints
from generator.messages import validate_messages
from generator.orders import validate_orders
from generator.resolutions import validate_resolutions, extract_refund_amount
from generator.sla_events import validate_sla_events
from generator.slas import validate_slas, sla_target_minutes
from generator.surveys import validate_surveys
from generator.config import PRIORITIES


@dataclass
class ValidationReport:
    total_checks: int
    passed_checks: int
    failed_checks: int
    warnings: list[str]
    errors: list[dict[str, str]]
    entity_counts: dict[str, int]
    checks: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def validate_complete_dataset(dataset: Any) -> ValidationReport:
    """Run reusable cross-entity checks and return every pass/failure in a report."""
    p6 = dataset.phase7.phase6
    p7 = dataset.phase7
    checks: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    def run(name: str, callback) -> None:
        try:
            callback()
            checks.append({"name": name, "status": "passed"})
        except Exception as exc:  # preserve every failure in the report
            detail = str(exc)
            checks.append({"name": name, "status": "failed"})
            errors.append({"check": name, "detail": detail})

    def ids_unique(name: str, records: list[Any]) -> None:
        # Auto-increment IDs remain unset until a database flush. They are
        # validated as database-generated keys by the isolated insertion tests.
        vals = [r.id for r in records if r.id is not None]
        if len(vals) != len(set(vals)):
            raise ValueError(f"Duplicate primary keys in {name}.")

    entities = {
        "customers": p6.customers, "products": p6.products, "categories": _categories(p6),
        "priority_rules": p6.priority_rules,
        "orders": p6.orders, "order_items": [i for o in p6.orders for i in o.items],
        "complaints": p6.complaints, "agents": p6.agents, "assignments": p6.assignments,
        "messages": p6.messages, "sla_clocks": p6.sla_clocks, "sla_events": p6.sla_events,
        "resolutions": p7.resolutions, "status_history": [h for c in p6.complaints for h in c.status_history],
        "reopen_history": [h for c in p6.complaints for h in c.reopen_history], "surveys": p7.surveys,
    }
    for name, records in entities.items():
        run(f"unique_ids:{name}", lambda n=name, rs=records: ids_unique(n, rs))

    run("order_rules", lambda: validate_orders(p6.orders))
    run("complaint_rules", lambda: validate_complaints(p6.complaints))
    run("assignment_rules", lambda: validate_assignments(p6.assignments, p6.complaints))
    run("message_rules", lambda: validate_messages(p6.messages, p6.complaints))
    run("sla_clock_rules", lambda: validate_slas(p6.sla_clocks, p6.complaints))
    run("sla_event_rules", lambda: validate_sla_events(p6.sla_events, p6.sla_clocks))
    run("resolution_lifecycle", lambda: validate_resolutions(p6.complaints, p7.resolutions))
    run("survey_rules", lambda: validate_surveys(p7.surveys, p6.complaints))

    customer_ids, product_ids, order_ids, complaint_ids, agent_ids = (
        {x.id for x in p6.customers}, {x.id for x in p6.products}, {x.id for x in p6.orders},
        {x.id for x in p6.complaints}, {x.id for x in p6.agents},
    )
    run("foreign_keys", lambda: _assert_foreign_keys(dataset, customer_ids, product_ids, order_ids, complaint_ids, agent_ids))
    run("lifecycle_dates", lambda: _assert_dates(dataset))
    run("safety_priority", lambda: _assert_safety(p6.complaints))
    run("refund_reconciliation", lambda: _assert_refunds(p6.complaints, p7.resolutions))
    run("repeat_links", lambda: _assert_repeats(p6.complaints))
    run("sla_priority_targets", lambda: _assert_targets(p6.complaints, p6.sla_clocks))
    run("priority_rule_constraints", lambda: _assert_priority_rules(p6.priority_rules, _categories(p6)))

    failed = len(errors)
    classification_mismatches = sum(
        getattr(complaint, "expected_category", complaint.category.name) != complaint.category.name
        for complaint in p6.complaints
    )
    warnings: list[str] = []
    if classification_mismatches:
        warnings.append(f"{classification_mismatches} complaint classification(s) differ from their authored scenario ground-truth labels.")
    return ValidationReport(len(checks), len(checks) - failed, failed, warnings, errors,
                            {name: len(records) for name, records in entities.items()}, checks)


def _categories(p6):
    unique = {}
    for product in p6.products:
        if product.category: unique[product.category.id] = product.category
    for complaint in p6.complaints:
        if complaint.category: unique[complaint.category.id] = complaint.category
    return list(unique.values())


def _assert_foreign_keys(dataset, customers, products, orders, complaints, agents):
    p6, p7 = dataset.phase7.phase6, dataset.phase7
    for order in p6.orders:
        if order.customer.id not in customers: raise ValueError(f"Orphan order {order.id} customer")
        for item in order.items:
            if item.product.id not in products: raise ValueError(f"Orphan order item in {order.id}")
    for complaint in p6.complaints:
        if complaint.customer.id not in customers: raise ValueError(f"Orphan complaint {complaint.id} customer")
        if complaint.order and complaint.order.id not in orders: raise ValueError(f"Orphan complaint order {complaint.id}")
        if complaint.product and complaint.product.id not in products: raise ValueError(f"Orphan complaint product {complaint.id}")
        if getattr(complaint, "repeat_of_id", None) and complaint.repeat_of_id not in complaints: raise ValueError(f"Orphan repeat {complaint.id}")
    for item in p6.assignments:
        if item.complaint.id not in complaints or item.agent.id not in agents: raise ValueError(f"Orphan assignment {item.id}")
        if not item.agent.is_active or getattr(item.agent, "availability", "Available") == "Unavailable": raise ValueError(f"Assignment to inactive/unavailable agent: {item.id}")
    for msg in p6.messages:
        if msg.complaint.id not in complaints: raise ValueError(f"Orphan message {msg.id}")
    for res in p7.resolutions:
        if res.complaint.id not in complaints or res.resolved_by_agent_id not in agents: raise ValueError(f"Orphan resolution {res.id}")
    for survey in p7.surveys:
        if survey.complaint.id not in complaints or survey.customer.id not in customers: raise ValueError(f"Orphan survey {survey.id}")


def _assert_dates(dataset):
    p6, p7 = dataset.phase7.phase6, dataset.phase7
    for order in p6.orders:
        if _utc(order.order_date) < _utc(order.customer.created_at): raise ValueError(f"Order predates customer: {order.id}")
    for complaint in p6.complaints:
        if complaint.order and _utc(complaint.created_at) < _utc(complaint.order.order_date): raise ValueError(f"Complaint predates order: {complaint.id}")
    for message in p6.messages:
        if _utc(message.created_at) < _utc(message.complaint.created_at): raise ValueError(f"Message predates complaint: {message.id}")
    for assignment in p6.assignments:
        if _utc(assignment.assigned_at) < _utc(assignment.complaint.created_at): raise ValueError(f"Assignment predates complaint: {assignment.id}")
    for clock in p6.sla_clocks:
        if _utc(clock.start_time) != _utc(clock.complaint.created_at): raise ValueError(f"SLA starts outside complaint creation: {clock.id}")
    for resolution in p7.resolutions:
        if _utc(resolution.resolved_at) <= _utc(resolution.complaint.created_at): raise ValueError(f"Resolution predates complaint: {resolution.id}")
    for complaint in p6.complaints:
        events = sorted(complaint.status_history, key=lambda x: _utc(x.changed_at))
        close = next((x.changed_at for x in events if x.to_status == "Closed"), None)
        if close:
            resolution = next((r for r in p7.resolutions if r.complaint.id == complaint.id), None)
            if resolution and _utc(close) <= _utc(resolution.resolved_at): raise ValueError(f"Closure precedes resolution: {complaint.id}")
        reopen = [x.reopened_at for x in complaint.reopen_history]
        if reopen and (close is None or any(_utc(x) <= _utc(close) for x in reopen)): raise ValueError(f"Reopen precedes closure: {complaint.id}")
        if complaint.survey and (close is None or _utc(complaint.survey.submitted_at) <= _utc(close)): raise ValueError(f"Survey predates closure: {complaint.id}")


def _assert_safety(complaints):
    for complaint in complaints:
        if complaint.category.name == "Safety Issue" and complaint.priority != "Critical": raise ValueError(f"Safety complaint {complaint.id} is not Critical")


def _assert_refunds(complaints, resolutions):
    for resolution in resolutions:
        amount = extract_refund_amount(resolution)
        if amount < 0: raise ValueError(f"Negative refund in {resolution.id}")
        if resolution.resolution_type == "Refund" and (not resolution.complaint.order or amount > resolution.complaint.order.total_amount): raise ValueError(f"Refund exceeds order in {resolution.id}")


def _assert_repeats(complaints):
    by_id = {x.id:x for x in complaints}
    for complaint in complaints:
        target_id = getattr(complaint, "repeat_of_id", None)
        if not target_id: continue
        target = by_id.get(target_id)
        if not target or _utc(target.created_at) >= _utc(complaint.created_at): raise ValueError(f"Repeat link is invalid: {complaint.id}")
        visited, current = {complaint.id}, target
        while getattr(current, "repeat_of_id", None):
            if current.id in visited: raise ValueError(f"Repeat cycle from {complaint.id}")
            visited.add(current.id); current = by_id[current.repeat_of_id]


def _assert_targets(complaints, clocks):
    by_id = {x.complaint_id:x for x in clocks}
    for complaint in complaints:
        if by_id[complaint.id].target_duration_minutes != sla_target_minutes(complaint.priority): raise ValueError(f"SLA target mismatch: {complaint.id}")


def _assert_priority_rules(rules, categories):
    category_ids = {x.id for x in categories}
    for rule in rules:
        category_id = rule.category.id if rule.category is not None else rule.category_id
        if category_id not in category_ids or rule.category is None:
            raise ValueError(f"Priority rule {rule.id} has an invalid category reference")
        if rule.target_priority not in PRIORITIES or rule.sla_target_hours <= 0:
            raise ValueError(f"Priority rule {rule.id} has invalid priority or SLA target")
        if not rule.is_active:
            raise ValueError(f"Priority rule {rule.id} must be active for this baseline")

