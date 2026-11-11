"""Complaint conversation APIs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import get_db
from backend.models import Complaint, ComplaintMessage
from backend.schemas import MessageCreate
from backend.services.domain import create_message

router = APIRouter(prefix="/complaints", tags=["Messages"])


@router.post("/{complaint_id}/messages", status_code=201, name="add_complaint_message")
def add_message(complaint_id: str, payload: MessageCreate, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    message = create_message(db, complaint, payload.model_dump())
    return {"id": message.id, "complaint_id": message.complaint_id, "sequence_number": message.sequence_number, "sender_type": message.sender_type, "sender_id": message.sender_id, "sender_name": message.sender_name, "message_body": message.message_body, "is_internal_note": message.is_internal_note, "created_at": message.created_at}


@router.get("/{complaint_id}/messages", name="get_complaint_conversation")
def conversation(complaint_id: str, db: Session = Depends(get_db)):
    if db.get(Complaint, complaint_id) is None: raise HTTPException(404, "Complaint not found.")
    rows = db.scalars(select(ComplaintMessage).where(ComplaintMessage.complaint_id == complaint_id).order_by(ComplaintMessage.created_at, ComplaintMessage.sequence_number)).all()
    return [{"id": x.id, "sequence_number": x.sequence_number, "sender_type": x.sender_type, "sender_id": x.sender_id, "sender_name": x.sender_name, "message_body": x.message_body, "is_internal_note": x.is_internal_note, "created_at": x.created_at} for x in rows]
