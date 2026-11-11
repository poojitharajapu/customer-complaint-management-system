"""Agent CRUD, active-agent listing, and complaint assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.dependencies import get_db
from backend.models import Agent, Assignment, Complaint
from backend.schemas import AgentCreate, AgentOut, AssignmentCreate
from backend.services.domain import assign_complaint, next_agent_id

router = APIRouter(tags=["Agents and Assignments"])


@router.post("/agents", response_model=AgentOut, status_code=201, name="create_agent")
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    agent = Agent(id=next_agent_id(db), **payload.model_dump())
    db.add(agent); db.commit(); db.refresh(agent)
    return agent


@router.get("/agents", name="list_agents")
def list_agents(active_only: bool = False, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(Agent)
    if active_only: query = query.where(Agent.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Agent.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/agents/{agent_id}", response_model=AgentOut, name="get_agent")
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if agent is None: raise HTTPException(404, "Agent not found.")
    return agent


@router.post("/complaints/{complaint_id}/assignments", status_code=201, name="assign_complaint")
def assign(complaint_id: str, payload: AssignmentCreate, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id); agent = db.get(Agent, payload.agent_id)
    if complaint is None: raise HTTPException(404, "Complaint not found.")
    if agent is None: raise HTTPException(404, "Agent not found.")
    assignment = assign_complaint(db, complaint, agent)
    return {"id": assignment.id, "complaint_id": assignment.complaint_id, "agent_id": assignment.agent_id, "sequence_number": assignment.sequence_number, "assigned_at": assignment.assigned_at, "is_current": assignment.is_current}


@router.get("/complaints/{complaint_id}/assignments", name="assignment_history")
def assignment_history(complaint_id: str, db: Session = Depends(get_db)):
    if db.get(Complaint, complaint_id) is None: raise HTTPException(404, "Complaint not found.")
    rows = db.scalars(select(Assignment).where(Assignment.complaint_id == complaint_id).order_by(Assignment.sequence_number)).all()
    return [{"id": x.id, "agent_id": x.agent_id, "sequence_number": x.sequence_number, "assigned_at": x.assigned_at, "unassigned_at": x.unassigned_at, "is_current": x.is_current} for x in rows]
