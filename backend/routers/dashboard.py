"""Database-derived dashboard metrics."""

from collections import Counter
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.dependencies import get_db
from backend.models import Complaint, Resolution, SLAClock, Survey
from backend.services.domain import resolution_survey_metrics
from generator.resolutions import extract_refund_amount

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", name="dashboard_summary")
def dashboard_summary(db: Session = Depends(get_db)):
    complaints = db.scalars(select(Complaint)).all()
    total = len(complaints)
    by_category = Counter(x.category.name for x in complaints)
    by_priority = Counter(x.priority for x in complaints)
    by_status = Counter(x.status for x in complaints)
    open_statuses = {"New", "Assigned", "In Progress", "Pending Customer", "Pending Vendor", "Reopened"}
    slas = db.scalars(select(SLAClock)).all()
    breached = sum(x.is_breached for x in slas)
    resolutions = db.scalars(select(Resolution)).all()
    metrics = resolution_survey_metrics(db)
    return {
        "total_complaints": total,
        "open_complaints": sum(x.status in open_statuses for x in complaints),
        "resolved_closed_complaints": sum(x.status in {"Resolved", "Closed"} for x in complaints),
        "complaints_by_category": dict(sorted(by_category.items())),
        "complaints_by_priority": dict(sorted(by_priority.items())),
        "complaints_by_status": dict(sorted(by_status.items())),
        "sla_breach_count": breached,
        "sla_compliance_percent": round((len(slas) - breached) * 100 / len(slas), 2) if slas else 0.0,
        "average_resolution_time_hours": metrics["average_resolution_time_hours"],
        "reopened_complaint_count": metrics["reopened_complaint_count"],
        "customer_satisfaction_average": metrics["average_customer_satisfaction_rating"],
        "refund_total": sum((extract_refund_amount(x) for x in resolutions), Decimal("0.00")),
    }
