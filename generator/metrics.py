"""Reusable resolution, reopening, survey, and refund metrics."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from typing import Sequence

from backend.models.complaint import Complaint
from backend.models.resolution import Resolution
from backend.models.survey import Survey
from generator.resolutions import extract_refund_amount


def _utc(value: datetime) -> datetime:
    """Normalize naive SQLite values and aware timestamps before duration arithmetic."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def calculate_resolution_feedback_metrics(
    complaints: Sequence[Complaint],
    resolutions: Sequence[Resolution],
    surveys: Sequence[Survey],
) -> dict[str, int | Decimal]:
    """Calculate outcome, time, reopening, feedback, and refund totals from generated records."""
    if not complaints:
        raise ValueError("Metrics require at least one complaint.")
    total = len(complaints)
    resolved = [complaint for complaint in complaints if complaint.status in ("Resolved", "Closed")]
    reopened = [complaint for complaint in complaints if complaint.status == "Reopened"]
    resolution_by_complaint = {resolution.complaint.id: resolution for resolution in resolutions}
    durations_hours = [
        Decimal(str((_utc(resolution_by_complaint[complaint.id].resolved_at) - _utc(complaint.created_at)).total_seconds()))
        / Decimal("3600")
        for complaint in resolved
        if complaint.id in resolution_by_complaint
    ]
    ratings = [survey.rating for survey in surveys]
    refunds = sum(
        (extract_refund_amount(resolution) for resolution in resolutions if resolution.resolution_type == "Refund"),
        start=Decimal("0.00"),
    )
    resolution_rate = (Decimal(len(resolved)) * Decimal("100") / Decimal(total)).quantize(Decimal("0.01"))
    reopen_rate = (Decimal(len(reopened)) * Decimal("100") / Decimal(total)).quantize(Decimal("0.01"))
    average_resolution_hours = (
        (sum(durations_hours, start=Decimal("0")) / Decimal(len(durations_hours))).quantize(Decimal("0.01"))
        if durations_hours else Decimal("0.00")
    )
    average_rating = (
        (Decimal(sum(ratings)) / Decimal(len(ratings))).quantize(Decimal("0.01"))
        if ratings else Decimal("0.00")
    )
    return {
        "total_resolved_complaints": len(resolved),
        "total_unresolved_complaints": total - len(resolved),
        "resolution_rate_percent": resolution_rate,
        "average_resolution_time_hours": average_resolution_hours,
        "reopened_complaint_count": len(reopened),
        "reopened_rate_percent": reopen_rate,
        "survey_response_count": len(surveys),
        "average_customer_satisfaction_rating": average_rating,
        "positive_feedback_count": sum(rating >= 4 for rating in ratings),
        "negative_feedback_count": sum(rating <= 2 for rating in ratings),
        "refund_amount_total": refunds,
    }
