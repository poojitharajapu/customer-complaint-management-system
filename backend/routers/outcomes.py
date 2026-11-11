"""Resolution, reopen, survey, and customer-feedback endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import get_db
from backend.models import Complaint, Resolution, Survey
from backend.schemas import ReopenRequest, ResolutionCreate, SurveyCreate
from backend.services.domain import add_resolution, create_survey, reopen_complaint, resolution_survey_metrics

router = APIRouter(tags=["Resolutions and Surveys"])


@router.post("/complaints/{complaint_id}/resolutions", status_code=201, name="resolve_complaint")
def resolve(complaint_id: str, payload: ResolutionCreate, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    result = add_resolution(db, complaint, payload.model_dump())
    return {"id": result.id, "complaint_id": result.complaint_id, "attempt_number": result.attempt_number, "resolution_type": result.resolution_type, "resolved_at": result.resolved_at, "status": complaint.status}


@router.get("/complaints/{complaint_id}/resolutions", name="resolution_history")
def resolution_history(complaint_id: str, db: Session = Depends(get_db)):
    if db.get(Complaint, complaint_id) is None: raise HTTPException(404, "Complaint not found.")
    rows = db.scalars(select(Resolution).where(Resolution.complaint_id == complaint_id).order_by(Resolution.attempt_number)).all()
    return [{"id": x.id, "attempt_number": x.attempt_number, "resolved_by_agent_id": x.resolved_by_agent_id, "resolution_type": x.resolution_type, "root_cause": x.root_cause, "action_taken": x.action_taken, "resolved_at": x.resolved_at} for x in rows]


@router.post("/complaints/{complaint_id}/reopen", name="reopen_complaint")
def reopen(complaint_id: str, payload: ReopenRequest, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    reopened = reopen_complaint(db, complaint, payload.reopened_by, payload.reason)
    return {"id": reopened.id, "status": reopened.status, "reopen_count": reopened.reopen_count}


@router.post("/complaints/{complaint_id}/surveys", status_code=201, name="submit_customer_survey")
def submit_survey(complaint_id: str, payload: SurveyCreate, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    survey = create_survey(db, complaint, payload.model_dump())
    return {"id": survey.id, "complaint_id": survey.complaint_id, "customer_id": survey.customer_id, "rating": survey.rating, "satisfaction_level": survey.satisfaction_level, "submitted_at": survey.submitted_at}


@router.get("/surveys", name="list_surveys")
def list_surveys(db: Session = Depends(get_db)):
    rows = db.scalars(select(Survey).order_by(Survey.submitted_at.desc())).all()
    return [{"id": x.id, "complaint_id": x.complaint_id, "customer_id": x.customer_id, "rating": x.rating, "nps_score": x.nps_score, "satisfaction_level": x.satisfaction_level, "submitted_at": x.submitted_at} for x in rows]


@router.get("/metrics/customer-satisfaction", name="customer_satisfaction_metrics")
def satisfaction_metrics(db: Session = Depends(get_db)):
    return resolution_survey_metrics(db)
