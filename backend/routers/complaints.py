"""Complaint registration, filtering, updates, status changes, and history."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.dependencies import get_db
from backend.models import Complaint, ComplaintStatusHistory, Category
from backend.schemas import ComplaintCreate, ComplaintOut, ComplaintUpdate, StatusUpdate
from backend.services.domain import change_status, complaint_dict, create_complaint, paginate

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post("", response_model=ComplaintOut, status_code=201, name="register_complaint")
def register(payload: ComplaintCreate, db: Session = Depends(get_db)):
    return complaint_dict(create_complaint(db, payload.model_dump()))


@router.get("", name="list_complaints")
def list_complaints(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = None, category: str | None = None, priority: str | None = None, status: str | None = None, customer_id: str | None = None, created_from: datetime | None = None, created_to: datetime | None = None, db: Session = Depends(get_db)):
    query = select(Complaint)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Complaint.title.ilike(pattern), Complaint.description.ilike(pattern)))
    if category: query = query.join(Category).where(Category.name == category)
    if priority: query = query.where(Complaint.priority == priority)
    if status: query = query.where(Complaint.status == status)
    if customer_id: query = query.where(Complaint.customer_id == customer_id)
    if created_from: query = query.where(Complaint.created_at >= created_from)
    if created_to: query = query.where(Complaint.created_at <= created_to)
    result = paginate(db, query, page, page_size)
    return {**result, "items": [complaint_dict(x) for x in result["items"]]}


@router.get("/{complaint_id}", response_model=ComplaintOut, name="get_complaint")
def get_complaint(complaint_id: str, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    return complaint_dict(complaint)


@router.patch("/{complaint_id}", response_model=ComplaintOut, name="update_complaint")
def update_complaint(complaint_id: str, payload: ComplaintUpdate, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(complaint, key, value)
    complaint.updated_at = datetime.now().astimezone()
    db.commit(); db.refresh(complaint)
    return complaint_dict(complaint)


@router.patch("/{complaint_id}/status", response_model=ComplaintOut, name="change_complaint_status")
def status_change(complaint_id: str, payload: StatusUpdate, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    change_status(db, complaint, payload.status, payload.changed_by, payload.reason)
    db.commit(); db.refresh(complaint)
    return complaint_dict(complaint)


@router.get("/{complaint_id}/history", name="get_complaint_history")
def history(complaint_id: str, db: Session = Depends(get_db)):
    if db.get(Complaint, complaint_id) is None: raise HTTPException(404, "Complaint not found.")
    rows = db.scalars(select(ComplaintStatusHistory).where(ComplaintStatusHistory.complaint_id == complaint_id).order_by(ComplaintStatusHistory.changed_at)).all()
    return [{"id": x.id, "from_status": x.from_status, "to_status": x.to_status, "changed_by": x.changed_by, "reason": x.reason, "changed_at": x.changed_at} for x in rows]
