"""Create and validate one model-backed SLA clock per complaint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from backend.models.complaint import Complaint
from backend.models.id_generators import generate_sla_clock_id
from backend.models.sla import SLAClock


SLA_TARGET_HOURS = {"Critical": 4, "High": 8, "Medium": 24, "Low": 72}


def sla_target_minutes(priority: str) -> int:
    """Return the configured SLA target in minutes for a supported priority."""
    try:
        return SLA_TARGET_HOURS[priority] * 60
    except KeyError as error:
        raise ValueError(f"Unsupported SLA priority: {priority}") from error


def calculate_deadline(start_time: datetime, target_minutes: int, paused_minutes: int = 0) -> datetime:
    """Calculate the due time by extending active target time by elapsed paused minutes."""
    if target_minutes <= 0 or paused_minutes < 0:
        raise ValueError("SLA target must be positive and paused minutes cannot be negative.")
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    return start_time + timedelta(minutes=target_minutes + paused_minutes)


def generate_slas(complaints: Sequence[Complaint]) -> list[SLAClock]:
    """Create a running SLA clock with the correct priority target for each complaint."""
    if not complaints:
        raise ValueError("SLA generation requires complaints.")
    clocks: list[SLAClock] = []
    for complaint in complaints:
        target = sla_target_minutes(complaint.priority)
        clock = SLAClock(
            id=generate_sla_clock_id(complaint.id),
            complaint=complaint,
            complaint_id=complaint.id,
            target_duration_minutes=target,
            elapsed_active_minutes=0,
            elapsed_paused_minutes=0,
            clock_state="Running",
            start_time=complaint.created_at,
            deadline=calculate_deadline(complaint.created_at, target),
            is_breached=False,
        )
        clocks.append(clock)
    validate_slas(clocks, complaints)
    return clocks


def validate_slas(clocks: Sequence[SLAClock], complaints: Sequence[Complaint]) -> None:
    """Verify one correct clock per complaint, target durations, and due-time arithmetic."""
    complaint_map = {complaint.id: complaint for complaint in complaints}
    seen_complaints: set[str] = set()
    for clock in clocks:
        complaint_id = clock.complaint.id if clock.complaint is not None else clock.complaint_id
        complaint = complaint_map.get(complaint_id)
        if complaint is None or clock.complaint is not complaint:
            raise ValueError(f"SLA clock {clock.id} references an unknown complaint.")
        if complaint_id in seen_complaints or clock.id != generate_sla_clock_id(complaint.id):
            raise ValueError(f"Complaint {complaint_id} has duplicate or invalid SLA clock IDs.")
        expected_target = sla_target_minutes(complaint.priority)
        if clock.target_duration_minutes != expected_target:
            raise ValueError(f"SLA clock {clock.id} target does not match complaint priority.")
        expected_deadline = calculate_deadline(
            clock.start_time,
            clock.target_duration_minutes,
            clock.elapsed_paused_minutes,
        )
        if clock.deadline != expected_deadline:
            raise ValueError(f"SLA clock {clock.id} deadline does not account for paused time.")
        if clock.elapsed_active_minutes < 0 or clock.elapsed_paused_minutes < 0:
            raise ValueError(f"SLA clock {clock.id} has negative elapsed time.")
        if clock.is_breached != (clock.breached_at is not None):
            raise ValueError(f"SLA clock {clock.id} breach flag and timestamp disagree.")
        if clock.is_breached and clock.breached_at <= clock.deadline:
            raise ValueError(f"SLA clock {clock.id} breach time must be after its adjusted deadline.")
        if clock.clock_state not in ("Running", "Paused", "Stopped", "Breached"):
            raise ValueError(f"SLA clock {clock.id} has an unsupported state.")
        if clock.clock_state == "Paused" and clock.last_pause_time is None:
            raise ValueError(f"Paused SLA clock {clock.id} has no pause timestamp.")
        if clock.clock_state == "Stopped" and clock.stop_time is None:
            raise ValueError(f"Stopped SLA clock {clock.id} has no stop timestamp.")
        seen_complaints.add(complaint_id)
    if seen_complaints != set(complaint_map):
        raise ValueError("Every complaint must have exactly one SLA clock.")
