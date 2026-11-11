"""Generate post-closure customer feedback surveys."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Sequence

from backend.models.complaint import Complaint
from backend.models.id_generators import generate_survey_id
from backend.models.survey import Survey
from generator.config import RANDOM_SEED


_LEVEL_BY_RATING = {
    1: "Very Dissatisfied",
    2: "Dissatisfied",
    3: "Neutral",
    4: "Satisfied",
    5: "Very Satisfied",
}
_POSITIVE_COMMENTS = (
    "The team handled the issue clearly and kept me informed.",
    "The solution worked as explained. Thank you for the helpful support.",
)
_NEGATIVE_COMMENTS = (
    "The issue took too long to resolve and I had to follow up several times.",
    "The outcome did not fully address my concern. I expected clearer updates.",
)
_NEUTRAL_COMMENTS = (
    "The issue was addressed. The process was acceptable overall.",
    "The response answered my question, though there is room to improve updates.",
)


def _utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and timezone-aware timestamps to UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _closure_time(complaint: Complaint) -> datetime:
    """Find the persisted closure status event, falling back to a resolved event."""
    closure = next((event for event in reversed(complaint.status_history) if event.to_status == "Closed"), None)
    if closure is None:
        closure = next((event for event in reversed(complaint.status_history) if event.to_status == "Resolved"), None)
    if closure is None:
        raise ValueError(f"Eligible complaint {complaint.id} has no closure/resolution timestamp.")
    return _utc(closure.changed_at)


def validate_surveys(surveys: Sequence[Survey], complaints: Sequence[Complaint]) -> None:
    """Validate survey uniqueness, references, ratings, and post-closure submission times."""
    complaint_map = {complaint.id: complaint for complaint in complaints}
    seen: set[str] = set()
    for survey in surveys:
        complaint = complaint_map.get(survey.complaint.id if survey.complaint else survey.complaint_id)
        if complaint is None or survey.complaint is not complaint:
            raise ValueError(f"Survey {survey.id} references an unknown complaint.")
        if survey.id in seen or survey.id != generate_survey_id(complaint.id):
            raise ValueError(f"Survey {survey.id} has an invalid or duplicate ID.")
        if complaint.status not in ("Resolved", "Closed"):
            raise ValueError(f"Survey {survey.id} was submitted for a complaint that is not resolved/closed.")
        if survey.customer.id != complaint.customer.id or survey.customer_id != complaint.customer.id:
            raise ValueError(f"Survey {survey.id} references the wrong customer.")
        if not 1 <= survey.rating <= 5 or survey.satisfaction_level != _LEVEL_BY_RATING[survey.rating]:
            raise ValueError(f"Survey {survey.id} has an invalid satisfaction rating.")
        if survey.nps_score is not None and not 0 <= survey.nps_score <= 10:
            raise ValueError(f"Survey {survey.id} has an invalid NPS score.")
        if _utc(survey.submitted_at) <= _closure_time(complaint):
            raise ValueError(f"Survey {survey.id} was submitted before complaint closure.")
        seen.add(survey.id)


def generate_surveys(
    complaints: Sequence[Complaint],
    seed: int = RANDOM_SEED,
) -> list[Survey]:
    """Generate post-closure surveys for a deterministic subset of resolved complaints."""
    if not complaints:
        raise ValueError("Survey generation requires complaints.")
    rng = random.Random(seed)
    surveys: list[Survey] = []
    response_number = 0
    for sequence, complaint in enumerate(complaints, start=1):
        if complaint.status not in ("Resolved", "Closed"):
            continue
        if sequence % 3 == 0:
            continue  # About two thirds of eligible customers respond.
        if not complaint.resolutions:
            raise ValueError(f"Resolved complaint {complaint.id} has no resolution record.")
        response_number += 1
        if response_number == 1:
            rating = 5
        elif response_number == 2:
            rating = 1
        else:
            rating = rng.choices((1, 2, 3, 4, 5), weights=(10, 12, 18, 28, 32), k=1)[0]
        if rating >= 4:
            comments = rng.choice(_POSITIVE_COMMENTS)
        elif rating <= 2:
            comments = rng.choice(_NEGATIVE_COMMENTS)
        else:
            comments = rng.choice(_NEUTRAL_COMMENTS)
        submitted_at = _closure_time(complaint) + timedelta(hours=rng.randint(2, 72))
        survey = Survey(
            id=generate_survey_id(complaint.id),
            complaint=complaint,
            complaint_id=complaint.id,
            customer=complaint.customer,
            customer_id=complaint.customer.id,
            rating=rating,
            nps_score=(rating - 1) * 2,
            satisfaction_level=_LEVEL_BY_RATING[rating],
            feedback_comments=comments,
            timeliness_rating=max(1, min(5, rating + rng.choice((-1, 0, 0, 1)))),
            agent_helpfulness_rating=max(1, min(5, rating + rng.choice((-1, 0, 0, 1)))),
            submitted_at=submitted_at,
        )
        surveys.append(survey)
    validate_surveys(surveys, complaints)
    return surveys
