"""Complaint SLA clock, event, breach, at-risk, pause, resume, and escalation APIs."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import get_db
from backend.models import Complaint, SLAClock, SLAEvent
from backend.services.domain import change_sla_state, escalate_sla

router = APIRouter(prefix="/slas", tags=["SLAs"])


def _clock_dict(clock: SLAClock):
    return {"id": clock.id, "complaint_id": clock.complaint_id, "target_duration_minutes": clock.target_duration_minutes, "elapsed_active_minutes": clock.elapsed_active_minutes, "elapsed_paused_minutes": clock.elapsed_paused_minutes, "clock_state": clock.clock_state, "start_time": clock.start_time, "deadline": clock.deadline, "is_breached": clock.is_breached, "breached_at": clock.breached_at, "stop_time": clock.stop_time}


@router.get("/breached", name="list_breached_slas")
def breached(db: Session = Depends(get_db)):
    rows = db.scalars(select(SLAClock).where(SLAClock.is_breached.is_(True)).order_by(SLAClock.breached_at)).all()
    return [_clock_dict(x) for x in rows]


@router.get("/at-risk", name="list_at_risk_slas")
def at_risk(within_minutes: int = Query(60, ge=1, le=1440), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    candidates = db.scalars(select(SLAClock).where(SLAClock.clock_state == "Running", SLAClock.is_breached.is_(False))).all()
    cutoff = now + timedelta(minutes=within_minutes)
    rows = [clock for clock in candidates if now <= (clock.deadline.replace(tzinfo=timezone.utc) if clock.deadline.tzinfo is None else clock.deadline.astimezone(timezone.utc)) <= cutoff]
    rows.sort(key=lambda clock: clock.deadline)
    return [_clock_dict(x) for x in rows]


@router.get("/{complaint_id}", name="get_complaint_sla")
def get_sla(complaint_id: str, db: Session = Depends(get_db)):
    if db.get(Complaint, complaint_id) is None: raise HTTPException(404, "Complaint not found.")
    clock = db.scalar(select(SLAClock).where(SLAClock.complaint_id == complaint_id))
    if clock is None: raise HTTPException(404, "SLA clock not found.")
    return _clock_dict(clock)


@router.get("/{complaint_id}/events", name="get_sla_events")
def get_events(complaint_id: str, db: Session = Depends(get_db)):
    if db.get(Complaint, complaint_id) is None: raise HTTPException(404, "Complaint not found.")
    rows = db.scalars(select(SLAEvent).join(SLAClock).where(SLAClock.complaint_id == complaint_id).order_by(SLAEvent.event_time, SLAEvent.id)).all()
    return [{"id": x.id, "event_type": x.event_type, "reason": x.reason, "triggered_by": x.triggered_by, "event_time": x.event_time, "active_minutes_at_event": x.active_minutes_at_event, "paused_minutes_at_event": x.paused_minutes_at_event} for x in rows]


@router.post("/{complaint_id}/pause", name="pause_sla")
def pause(complaint_id: str, db: Session = Depends(get_db)):
    return _clock_dict(change_sla_state(db, complaint_id, "pause"))


@router.post("/{complaint_id}/resume", name="resume_sla")
def resume(complaint_id: str, db: Session = Depends(get_db)):
    return _clock_dict(change_sla_state(db, complaint_id, "resume"))


@router.post("/{complaint_id}/escalate", name="escalate_sla")
def escalate(complaint_id: str, reason: str = Query(min_length=3, max_length=200), db: Session = Depends(get_db)):
    event = escalate_sla(db, complaint_id, reason)
    return {"id": event.id, "sla_clock_id": event.sla_clock_id, "event_type": event.event_type, "reason": event.reason, "event_time": event.event_time}
