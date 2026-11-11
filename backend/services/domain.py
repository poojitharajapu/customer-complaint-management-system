"""Database-backed business operations shared by API routers."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Agent, Assignment, Category, Complaint, ComplaintMessage, ComplaintReopenHistory
from backend.models import ComplaintStatusHistory, Customer, Order, PriorityRule, Resolution, SLAClock, SLAEvent, Survey
from backend.models.id_generators import generate_assignment_id, generate_complaint_id, generate_customer_id
from backend.models.id_generators import generate_message_id, generate_resolution_id, generate_survey_id, generate_agent_id
from generator.complaints import classify_complaint, _score_priority
from generator.metrics import calculate_resolution_feedback_metrics
from generator.resolutions import extract_refund_amount
from generator.config import DATA_YEAR
from generator.slas import sla_target_minutes, calculate_deadline


ALLOWED_STATUSES = {"New", "Assigned", "In Progress", "Pending Customer", "Pending Vendor", "Resolved", "Closed", "Reopened"}
TRANSITIONS = {
    "New": {"Assigned", "In Progress", "Pending Customer", "Pending Vendor", "Resolved"},
    "Assigned": {"In Progress", "Pending Customer", "Pending Vendor", "Resolved"},
    "In Progress": {"Pending Customer", "Pending Vendor", "Resolved"},
    "Pending Customer": {"In Progress", "Resolved"},
    "Pending Vendor": {"In Progress", "Resolved"},
    "Resolved": {"Closed"},
    "Closed": {"Reopened"},
    "Reopened": {"In Progress", "Pending Customer", "Pending Vendor", "Resolved"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    """Normalize SQLite's naive timestamp results to UTC for arithmetic."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _next_sequence(model, id_column, prefix: str, year: int | None = None) -> int:
    """Find the next sequence from existing convention IDs, tolerating gaps."""
    values = id_column
    rows = model
    ids = rows
    maximum = 0
    for value in ids:
        match = re.search(r"(\d+)$", value or "")
        if match: maximum = max(maximum, int(match.group(1)))
    return maximum + 1


def next_customer_id(db: Session) -> str:
    ids = db.scalars(select(Customer.id)).all()
    maximum = max((int(x.split("-")[-1]) for x in ids if re.fullmatch(r"CUS-\d+", x)), default=0)
    return generate_customer_id(maximum + 1)


def next_agent_id(db: Session) -> str:
    ids = db.scalars(select(Agent.id)).all()
    maximum = max((int(x.split("-")[-1]) for x in ids if re.fullmatch(r"AGT-\d+", x)), default=0)
    return generate_agent_id(maximum + 1)


def _complaint_id(db: Session) -> str:
    ids = db.scalars(select(Complaint.id)).all()
    maximum = max((int(x.rsplit("-", 1)[-1]) for x in ids if re.fullmatch(r"CMP-\d{4}-\d+", x)), default=0)
    return generate_complaint_id(maximum + 1, year=DATA_YEAR)


def _item_dict(obj) -> dict:
    """Serialize a simple model response without returning ORM internals."""
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def customer_dict(customer: Customer) -> dict:
    return _item_dict(customer)


def complaint_dict(complaint: Complaint) -> dict:
    return {
        "id": complaint.id, "customer_id": complaint.customer_id, "order_id": complaint.order_id,
        "product_id": complaint.product_id, "category_id": complaint.category_id,
        "category_name": complaint.category.name, "title": complaint.title,
        "description": complaint.description, "channel": complaint.channel,
        "priority": complaint.priority, "severity": getattr(complaint, "severity", None),
        "status": complaint.status, "reopen_count": complaint.reopen_count,
        "created_at": complaint.created_at, "updated_at": complaint.updated_at,
    }


def paginate(db: Session, query, page: int, page_size: int) -> dict:
    """Apply stable ID ordering and return a consistent page envelope."""
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(query.column_descriptions[0]["entity"].id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": math.ceil(total / page_size) if total else 0}


def create_customer(db: Session, values: dict) -> Customer:
    customer = Customer(id=next_customer_id(db), **values)
    db.add(customer); db.commit(); db.refresh(customer)
    return customer


def create_complaint(db: Session, values: dict) -> Complaint:
    customer = db.get(Customer, values["customer_id"])
    if customer is None: raise HTTPException(404, "Customer not found.")
    order = db.get(Order, values.get("order_id")) if values.get("order_id") else None
    product = None
    if values.get("order_id") and order is None: raise HTTPException(404, "Order not found.")
    if order and order.customer_id != customer.id: raise HTTPException(422, "Order does not belong to the selected customer.")
    if values.get("product_id"):
        from backend.models import Product
        product = db.get(Product, values["product_id"])
        if product is None: raise HTTPException(404, "Product not found.")
        if order and product.id not in {item.product_id for item in order.items}: raise HTTPException(422, "Product is not part of the selected order.")
    classification = classify_complaint(values["title"], values["description"], order_status=order.order_status if order else None, product_description=product.description if product else None)
    requested_category = values.get("category_name")
    category_name = requested_category or classification
    category = db.scalar(select(Category).where(Category.name == category_name, Category.is_active.is_(True)))
    if category is None: raise HTTPException(422, f"Active category {category_name!r} is not configured.")
    rules = db.scalars(select(PriorityRule).where(PriorityRule.is_active.is_(True))).all()
    severity, priority, _reason = _score_priority(category, customer, values["title"], values["description"], False, rules)
    now = _now()
    complaint = Complaint(
        id=_complaint_id(db), customer=customer, order=order, product=product, category=category,
        title=values["title"], description=values["description"], channel=values["channel"],
        priority=priority, status="New", created_at=now, updated_at=now,
    )
    complaint.severity = severity
    db.add(complaint)
    db.flush()
    db.add(ComplaintStatusHistory(complaint_id=complaint.id, from_status=None, to_status="New", changed_by=customer.id, reason="Complaint registered through API.", changed_at=now))
    target = sla_target_minutes(priority)
    clock = SLAClock(id=f"SLA-{complaint.id}", complaint=complaint, target_duration_minutes=target, elapsed_active_minutes=0, elapsed_paused_minutes=0, clock_state="Running", start_time=now, deadline=calculate_deadline(now, target), is_breached=False)
    db.add(clock); db.flush()
    db.add(SLAEvent(sla_clock_id=clock.id, event_type="Started", triggered_by="SYSTEM", event_time=now, active_minutes_at_event=0, paused_minutes_at_event=0, reason="SLA started when complaint was registered."))
    db.commit(); db.refresh(complaint)
    return complaint


def change_status(db: Session, complaint: Complaint, target: str, actor: str, reason: str | None = None) -> None:
    if target not in ALLOWED_STATUSES: raise HTTPException(422, "Unsupported complaint status.")
    if target not in TRANSITIONS.get(complaint.status, set()): raise HTTPException(409, f"Invalid status transition: {complaint.status} to {target}.")
    now = _now()
    db.add(ComplaintStatusHistory(complaint_id=complaint.id, from_status=complaint.status, to_status=target, changed_by=actor, reason=reason, changed_at=now))
    complaint.status = target; complaint.updated_at = now


def assign_complaint(db: Session, complaint: Complaint, agent: Agent) -> Assignment:
    if not agent.is_active: raise HTTPException(409, "Cannot assign to an inactive agent.")
    if complaint.category.name == "Safety Issue" and agent.team != "Safety": raise HTTPException(409, "Safety complaints must be assigned to the Safety team.")
    current_load = db.scalar(select(func.count()).select_from(Assignment).where(Assignment.agent_id == agent.id, Assignment.is_current.is_(True))) or 0
    if current_load >= agent.max_active_tickets: raise HTTPException(409, "Agent is at active ticket capacity.")
    now = _now()
    previous = db.scalars(select(Assignment).where(Assignment.complaint_id == complaint.id, Assignment.is_current.is_(True))).all()
    for item in previous: item.is_current = False; item.unassigned_at = now
    sequence = (db.scalar(select(func.max(Assignment.sequence_number)).where(Assignment.complaint_id == complaint.id)) or 0) + 1
    assignment = Assignment(id=generate_assignment_id(complaint.id, sequence), complaint=complaint, agent=agent, sequence_number=sequence, assigned_by="API", assignment_reason="Assigned through API routing.", assigned_at=now, is_current=True)
    db.add(assignment)
    if complaint.status == "New": change_status(db, complaint, "Assigned", "API", "Agent assignment created.")
    db.commit(); db.refresh(assignment)
    return assignment


def create_message(db: Session, complaint: Complaint, values: dict) -> ComplaintMessage:
    sender_type, sender_id = values["sender_type"], values["sender_id"]
    if sender_type == "Customer":
        sender = db.get(Customer, sender_id)
        if sender is None or sender.id != complaint.customer_id: raise HTTPException(422, "Customer sender must be the complaint's customer.")
        sender_name = f"{sender.first_name} {sender.last_name}"
    else:
        sender = db.get(Agent, sender_id)
        if sender is None or not sender.is_active: raise HTTPException(422, "Agent sender must reference an active agent.")
        sender_name = f"{sender.first_name} {sender.last_name}"
    sequence = (db.scalar(select(func.max(ComplaintMessage.sequence_number)).where(ComplaintMessage.complaint_id == complaint.id)) or 0) + 1
    message = ComplaintMessage(id=generate_message_id(complaint.id, sequence), complaint=complaint, sequence_number=sequence, sender_type=sender_type, sender_id=sender_id, sender_name=sender_name, message_body=values["message_body"], is_internal_note=values["is_internal_note"], created_at=_now())
    db.add(message); db.commit(); db.refresh(message)
    return message


def add_resolution(db: Session, complaint: Complaint, values: dict) -> Resolution:
    if complaint.status in {"Closed", "Resolved"}: raise HTTPException(409, "Complaint already has a resolution or is closed.")
    agent = db.get(Agent, values["resolved_by_agent_id"])
    if agent is None or not agent.is_active: raise HTTPException(422, "Resolution agent must be active.")
    now = _now()
    refund_amount = values.get("refund_amount")
    notes = values.get("customer_notes")
    if values["resolution_type"] == "Refund":
        if complaint.order is None or refund_amount is None:
            raise HTTPException(422, "Refund resolution requires an order and an explicit refund_amount.")
        if refund_amount > complaint.order.total_amount:
            raise HTTPException(422, "Refund amount cannot exceed the linked order total.")
        marker = f"Refund amount: ${refund_amount:.2f}."
        notes = f"{notes.strip()} {marker}" if notes and notes.strip() else marker
    elif refund_amount is not None:
        raise HTTPException(422, "refund_amount is only valid for Refund resolutions.")
    sequence = (db.scalar(select(func.max(Resolution.attempt_number)).where(Resolution.complaint_id == complaint.id)) or 0) + 1
    res = Resolution(id=generate_resolution_id(complaint.id, sequence), complaint=complaint, attempt_number=sequence, resolved_by_agent=agent, root_cause=values["root_cause"], action_taken=values["action_taken"], customer_notes=notes, resolution_type=values["resolution_type"], is_accepted_by_customer=values.get("accepted_by_customer"), resolved_at=now)
    db.add(res)
    change_status(db, complaint, "Resolved", agent.id, "Resolution recorded.")
    change_status(db, complaint, "Closed", agent.id, "Resolution completed and complaint closed.")
    complaint.reopen_count = 0
    for assignment in db.scalars(select(Assignment).where(Assignment.complaint_id == complaint.id, Assignment.is_current.is_(True))).all():
        assignment.is_current = False
        assignment.unassigned_at = now
    clock = db.scalar(select(SLAClock).where(SLAClock.complaint_id == complaint.id))
    if clock:
        clock.clock_state = "Stopped"; clock.stop_time = now
        db.add(SLAEvent(sla_clock_id=clock.id, event_type="Stopped", triggered_by=agent.id, event_time=now, active_minutes_at_event=clock.elapsed_active_minutes, paused_minutes_at_event=clock.elapsed_paused_minutes, reason="Complaint resolved and closed."))
    db.commit(); db.refresh(res)
    return res


def reopen_complaint(db: Session, complaint: Complaint, reopened_by: str, reason: str) -> Complaint:
    if complaint.status != "Closed": raise HTTPException(409, "Only a closed complaint can be reopened.")
    previous = db.scalar(select(Resolution).where(Resolution.complaint_id == complaint.id).order_by(Resolution.attempt_number.desc()))
    if previous is None: raise HTTPException(409, "Complaint has no historical resolution to reopen.")
    reopening_agent = previous.resolved_by_agent
    if reopening_agent is None or not reopening_agent.is_active:
        raise HTTPException(409, "The prior resolution agent is unavailable; reassign before reopening.")
    now = _now()
    reopen_sequence = (db.scalar(select(func.max(ComplaintReopenHistory.reopen_sequence)).where(ComplaintReopenHistory.complaint_id == complaint.id)) or 0) + 1
    complaint.reopen_count = reopen_sequence
    db.add(ComplaintReopenHistory(complaint_id=complaint.id, reopen_sequence=reopen_sequence, previous_resolution_id=previous.id, reopened_by=reopened_by, reopen_reason=reason, reopened_at=now))
    change_status(db, complaint, "Reopened", reopened_by, reason)
    sequence = (db.scalar(select(func.max(Assignment.sequence_number)).where(Assignment.complaint_id == complaint.id)) or 0) + 1
    db.add(Assignment(id=generate_assignment_id(complaint.id, sequence), complaint=complaint, agent=reopening_agent, sequence_number=sequence, assigned_by="SYSTEM_REOPEN", assignment_reason="Returned to the prior resolution agent after reopening.", assigned_at=now, is_current=True))
    clock = db.scalar(select(SLAClock).where(SLAClock.complaint_id == complaint.id))
    if clock:
        clock.clock_state = "Running"; clock.start_time = now; clock.deadline = calculate_deadline(now, clock.target_duration_minutes); clock.elapsed_active_minutes = 0; clock.elapsed_paused_minutes = 0; clock.stop_time = None; clock.last_pause_time = None; clock.last_resume_time = None; clock.is_breached = False; clock.breached_at = None
        db.add(SLAEvent(sla_clock_id=clock.id, event_type="Started", triggered_by="SYSTEM", event_time=now, active_minutes_at_event=0, paused_minutes_at_event=0, reason="SLA restarted for reopened complaint."))
    db.commit(); db.refresh(complaint)
    return complaint


def create_survey(db: Session, complaint: Complaint, values: dict) -> Survey:
    if complaint.status != "Closed": raise HTTPException(409, "Survey can only be submitted after complaint closure.")
    if complaint.customer_id != values["customer_id"]: raise HTTPException(422, "Survey customer must match the complaint customer.")
    if complaint.survey is not None: raise HTTPException(409, "A survey already exists for this complaint.")
    rating = values["rating"]
    level = "Very Dissatisfied" if rating == 1 else "Dissatisfied" if rating == 2 else "Neutral" if rating == 3 else "Satisfied" if rating == 4 else "Very Satisfied"
    survey = Survey(id=generate_survey_id(complaint.id), complaint=complaint, customer_id=values["customer_id"], rating=rating, nps_score=values.get("nps_score"), satisfaction_level=level, feedback_comments=values.get("feedback_comments"), timeliness_rating=values.get("timeliness_rating"), agent_helpfulness_rating=values.get("agent_helpfulness_rating"), submitted_at=_now())
    db.add(survey); db.commit(); db.refresh(survey)
    return survey


def _sla_clock(db: Session, complaint_id: str) -> SLAClock:
    clock = db.scalar(select(SLAClock).where(SLAClock.complaint_id == complaint_id))
    if clock is None: raise HTTPException(404, "SLA clock not found for complaint.")
    return clock


def change_sla_state(db: Session, complaint_id: str, action: str) -> SLAClock:
    """Pause or resume an SLA while accounting paused minutes in its deadline."""
    clock = _sla_clock(db, complaint_id); now = _now()
    if action == "pause":
        if clock.clock_state != "Running": raise HTTPException(409, "Only a running SLA can be paused.")
        clock.clock_state = "Paused"; clock.last_pause_time = now; kind = "Paused"; reason = "Paused by API request."
    elif action == "resume":
        if clock.clock_state != "Paused" or clock.last_pause_time is None: raise HTTPException(409, "Only a paused SLA can be resumed.")
        paused = max(0, int((now - _utc(clock.last_pause_time)).total_seconds() // 60))
        clock.elapsed_paused_minutes += paused
        clock.deadline = clock.deadline + timedelta(minutes=paused)
        clock.last_resume_time = now; clock.last_pause_time = None; clock.clock_state = "Running"; kind = "Resumed"; reason = "Resumed by API request."
    else:
        raise HTTPException(422, "Unsupported SLA action.")
    db.add(SLAEvent(sla_clock_id=clock.id, event_type=kind, triggered_by="API", event_time=now, active_minutes_at_event=clock.elapsed_active_minutes, paused_minutes_at_event=clock.elapsed_paused_minutes, reason=reason))
    db.commit(); db.refresh(clock)
    return clock


def escalate_sla(db: Session, complaint_id: str, reason: str) -> SLAEvent:
    """Record an auditable manual SLA escalation event."""
    clock = _sla_clock(db, complaint_id)
    event = SLAEvent(sla_clock_id=clock.id, event_type="Adjusted", triggered_by="API_ESCALATION", event_time=_now(), active_minutes_at_event=clock.elapsed_active_minutes, paused_minutes_at_event=clock.elapsed_paused_minutes, reason=f"Escalation: {reason[:230]}")
    db.add(event); db.commit(); db.refresh(event)
    return event


def resolution_survey_metrics(db: Session) -> dict:
    complaints = db.scalars(select(Complaint)).all(); resolutions = db.scalars(select(Resolution)).all(); surveys = db.scalars(select(Survey)).all()
    if not complaints:
        return {"total_resolved_complaints": 0, "total_unresolved_complaints": 0, "resolution_rate_percent": Decimal("0.00"), "average_resolution_time_hours": Decimal("0.00"), "reopened_complaint_count": 0, "reopened_rate_percent": Decimal("0.00"), "survey_response_count": len(surveys), "average_customer_satisfaction_rating": Decimal("0.00"), "positive_feedback_count": 0, "negative_feedback_count": 0, "refund_amount_total": sum((extract_refund_amount(r) for r in resolutions), Decimal("0.00"))}
    return calculate_resolution_feedback_metrics(complaints, resolutions, surveys)
