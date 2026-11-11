"""Generate deterministic SLA pause, resume, escalation, stop, and breach events."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Sequence

from backend.models.sla import SLAClock, SLAEvent
from generator.config import RANDOM_SEED
from generator.slas import calculate_deadline, validate_slas


_WAITING_STATUSES = {"Pending Customer", "Pending Vendor"}
_TERMINAL_STATUSES = {"Resolved", "Closed"}


def _utc(value: datetime) -> datetime:
    """Normalize SQLite's naive datetimes and timezone-aware datetimes to UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def validate_sla_events(events: Sequence[SLAEvent], clocks: Sequence[SLAClock]) -> None:
    """Validate event order, pause/resume transitions, elapsed counters, and escalations."""
    clock_map = {clock.id: clock for clock in clocks}
    grouped: dict[str, list[SLAEvent]] = {clock.id: [] for clock in clocks}
    for event in events:
        clock_id = event.sla_clock.id if event.sla_clock else event.sla_clock_id
        if clock_id not in clock_map or event.sla_clock is not clock_map[clock_id]:
            raise ValueError(f"SLA event references an unknown clock: {clock_id}")
        if event.event_type not in ("Started", "Paused", "Resumed", "Stopped", "Breached", "Adjusted"):
            raise ValueError(f"Unsupported SLA event type: {event.event_type}")
        grouped[clock_id].append(event)

    for clock_id, thread in grouped.items():
        clock = clock_map[clock_id]
        thread.sort(key=lambda event: _utc(event.event_time))
        if not thread or thread[0].event_type != "Started" or sum(e.event_type == "Started" for e in thread) != 1:
            raise ValueError(f"SLA clock {clock_id} must have exactly one first Started event.")
        times = [_utc(event.event_time) for event in thread]
        if times != sorted(times):
            raise ValueError(f"SLA clock {clock_id} events are not chronological.")
        pauses = [i for i, event in enumerate(thread) if event.event_type == "Paused"]
        resumes = [i for i, event in enumerate(thread) if event.event_type == "Resumed"]
        if len(pauses) > 1 or len(resumes) > 1 or len(resumes) > len(pauses):
            raise ValueError(f"SLA clock {clock_id} has invalid pause/resume transitions.")
        if pauses and not resumes:
            complaint_status = clock.complaint.status
            if clock.clock_state != "Paused" or complaint_status not in _WAITING_STATUSES:
                raise ValueError(f"SLA clock {clock_id} has an unmatched pause outside a waiting state.")
        if pauses and resumes and resumes[0] < pauses[0]:
            raise ValueError(f"SLA clock {clock_id} resumes before its pause.")
        if pauses and resumes:
            pause_event, resume_event = thread[pauses[0]], thread[resumes[0]]
            pause_minutes = int((_utc(resume_event.event_time) - _utc(pause_event.event_time)).total_seconds() // 60)
            if pause_minutes != resume_event.paused_minutes_at_event:
                raise ValueError(f"SLA clock {clock_id} pause/resume duration does not match its paused counter.")
            if clock.elapsed_paused_minutes != pause_minutes:
                raise ValueError(f"SLA clock {clock_id} final paused counter does not match its pause interval.")
            if resume_event.active_minutes_at_event != pause_event.active_minutes_at_event:
                raise ValueError(f"SLA clock {clock_id} counted paused time as active time.")
        if clock.deadline != calculate_deadline(
            clock.start_time, clock.target_duration_minutes, clock.elapsed_paused_minutes
        ):
            raise ValueError(f"SLA clock {clock_id} deadline does not account for paused time.")
        breach_events = [event for event in thread if event.event_type == "Breached"]
        if clock.is_breached != (len(breach_events) == 1):
            raise ValueError(f"SLA clock {clock_id} breach event and clock state disagree.")
        if breach_events and _utc(breach_events[0].event_time) <= _utc(clock.deadline):
            raise ValueError(f"SLA clock {clock_id} breached before its adjusted due time.")
        escalations = [event for event in thread if event.event_type == "Adjusted" and (event.reason or "").startswith("Escalation:")]
        if escalations and not (clock.is_breached or any("at risk" in (event.reason or "").lower() for event in escalations)):
            raise ValueError(f"SLA clock {clock_id} has an unsupported escalation event.")
        if clock.elapsed_paused_minutes < 0 or clock.elapsed_active_minutes < 0:
            raise ValueError(f"SLA clock {clock_id} has negative elapsed counters.")


def generate_sla_events(clocks: Sequence[SLAClock], seed: int = RANDOM_SEED) -> list[SLAEvent]:
    """Generate valid clock timelines and update elapsed, pause, breach, and escalation state."""
    if not clocks:
        raise ValueError("SLA event generation requires SLA clocks.")
    rng = random.Random(seed)
    events: list[SLAEvent] = []
    for sequence, clock in enumerate(clocks, start=1):
        complaint = clock.complaint
        if complaint is None:
            raise ValueError(f"SLA clock {clock.id} has no complaint relationship.")
        start = _utc(clock.start_time)
        target = clock.target_duration_minutes
        clock.events.clear()

        def add_event(
            event_type: str,
            when: datetime,
            active_minutes: int,
            paused_minutes: int,
            reason: str | None = None,
            triggered_by: str = "SYSTEM",
        ) -> None:
            events.append(
                SLAEvent(
                    sla_clock=clock,
                    sla_clock_id=clock.id,
                    event_type=event_type,
                    reason=reason,
                    triggered_by=triggered_by,
                    event_time=when,
                    active_minutes_at_event=active_minutes,
                    paused_minutes_at_event=paused_minutes,
                )
            )

        add_event("Started", start, 0, 0, "SLA clock started when complaint was created.")
        pause_candidate = sequence % 4 == 0
        waiting_pause = pause_candidate and complaint.status in _WAITING_STATUSES
        resumed_pause = pause_candidate and not waiting_pause
        pause_active = max(1, target // 4) if pause_candidate else 0
        paused_minutes = 0
        if pause_candidate:
            pause_time = start + timedelta(minutes=pause_active)
            clock.last_pause_time = pause_time
            add_event("Paused", pause_time, pause_active, 0, "Awaiting customer response or external investigation.")
            if waiting_pause:
                paused_minutes = 60
                clock.elapsed_active_minutes = pause_active
                clock.elapsed_paused_minutes = paused_minutes
                clock.deadline = calculate_deadline(start, target, paused_minutes)
                clock.clock_state = "Paused"
                clock.last_resume_time = None
                clock.stop_time = None
                clock.is_breached = False
                clock.breached_at = None
                continue
            paused_minutes = rng.choice((30, 45, 60))
            resume_time = pause_time + timedelta(minutes=paused_minutes)
            clock.last_resume_time = resume_time
            add_event("Resumed", resume_time, pause_active, paused_minutes, "Customer or external party responded; active timing resumed.")
        else:
            clock.last_pause_time = None
            clock.last_resume_time = None

        breached = sequence % 5 == 0
        stopped = not breached and complaint.status in _TERMINAL_STATUSES
        if breached:
            active_minutes = target + 1
            clock.elapsed_active_minutes = active_minutes
            clock.elapsed_paused_minutes = paused_minutes
            clock.deadline = calculate_deadline(start, target, paused_minutes)
            clock.breached_at = clock.deadline + timedelta(minutes=1)
            clock.is_breached = True
            clock.clock_state = "Breached"
            clock.stop_time = None
            add_event("Breached", clock.breached_at, active_minutes, paused_minutes, "SLA target exceeded after excluding paused time.")
            add_event("Adjusted", clock.breached_at + timedelta(minutes=1), active_minutes, paused_minutes, "Escalation: breached SLA routed for urgent review.", "SYSTEM_ESCALATION")
        elif stopped:
            active_minutes = max(1, min(target // 2, target - 1))
            clock.elapsed_active_minutes = active_minutes
            clock.elapsed_paused_minutes = paused_minutes
            clock.deadline = calculate_deadline(start, target, paused_minutes)
            clock.stop_time = start + timedelta(minutes=active_minutes + paused_minutes)
            clock.clock_state = "Stopped"
            clock.is_breached = False
            clock.breached_at = None
            add_event("Stopped", clock.stop_time, active_minutes, paused_minutes, "Complaint reached a terminal status.")
        else:
            at_risk = sequence % 7 == 0
            active_minutes = target - 1 if at_risk else max(1, target // 2)
            clock.elapsed_active_minutes = active_minutes
            clock.elapsed_paused_minutes = paused_minutes
            clock.deadline = calculate_deadline(start, target, paused_minutes)
            clock.stop_time = None
            clock.clock_state = "Running"
            clock.is_breached = False
            clock.breached_at = None
            if at_risk:
                at_risk_time = start + timedelta(minutes=active_minutes + paused_minutes)
                add_event("Adjusted", at_risk_time, active_minutes, paused_minutes, "Escalation: SLA is at risk and nearing its adjusted deadline.", "SYSTEM_ESCALATION")

    validate_slas(clocks, [clock.complaint for clock in clocks if clock.complaint is not None])
    validate_sla_events(events, clocks)
    return events
