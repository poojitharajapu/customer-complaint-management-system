"""Route complaints to suitable active agents and preserve assignment history."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import timedelta
from typing import Sequence

from backend.models.agent import Agent
from backend.models.assignment import Assignment
from backend.models.complaint import Complaint
from backend.models.id_generators import generate_assignment_id
from generator.config import RANDOM_SEED


TERMINAL_STATUSES = {"Resolved", "Closed"}


def team_for_complaint(complaint: Complaint) -> str:
    """Map a classified complaint to its preferred operational support team."""
    category = complaint.category.name
    if category == "Safety Issue":
        return "Safety"
    if category in ("Refund", "Payment Issue"):
        return "Billing"
    if category in ("Delivery Delay", "Wrong Item", "Missing Item"):
        return "Delivery"
    if category == "Product Defect":
        return "Technical Support"
    return "General Support"


def _available_agents(agents: Sequence[Agent], team: str, skill: str | None = None) -> list[Agent]:
    """Return active and available agents on the preferred team with a general fallback."""
    pool = [
        agent for agent in agents
        if agent.is_active and getattr(agent, "availability", "Available") == "Available"
        and agent.team == team
    ]
    if not pool:
        pool = [
            agent for agent in agents
            if agent.is_active and getattr(agent, "availability", "Available") == "Available"
            and agent.team == "General Support"
        ]
    if skill:
        skilled = [agent for agent in pool if skill in getattr(agent, "skills", ())]
        if skilled:
            pool = skilled
    if not pool:
        raise ValueError(f"No active, available agents can serve team {team!r}.")
    return pool


def validate_assignments(assignments: Sequence[Assignment], complaints: Sequence[Complaint]) -> None:
    """Check assignment references, active agents, sequences, routing, and timestamps."""
    complaint_map = {complaint.id: complaint for complaint in complaints}
    grouped: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        complaint = complaint_map.get(assignment.complaint.id if assignment.complaint else assignment.complaint_id)
        if complaint is None or assignment.complaint is not complaint:
            raise ValueError(f"Assignment {assignment.id} references an unknown complaint.")
        if assignment.agent is None or not assignment.agent.is_active:
            raise ValueError(f"Assignment {assignment.id} targets a missing or inactive agent.")
        if getattr(assignment.agent, "availability", "Available") == "Unavailable":
            raise ValueError(f"Assignment {assignment.id} targets an unavailable agent.")
        if assignment.assigned_at < complaint.created_at:
            raise ValueError(f"Assignment {assignment.id} predates complaint creation.")
        if assignment.unassigned_at is not None and assignment.unassigned_at < assignment.assigned_at:
            raise ValueError(f"Assignment {assignment.id} is unassigned before it was assigned.")
        if assignment.sequence_number <= 0 or assignment.id != generate_assignment_id(complaint.id, assignment.sequence_number):
            raise ValueError(f"Assignment {assignment.id} has an invalid sequence ID.")
        grouped[complaint.id].append(assignment)
    for complaint_id, history in grouped.items():
        complaint = complaint_map[complaint_id]
        history.sort(key=lambda item: item.sequence_number)
        current = [item for item in history if item.is_current]
        if complaint.status in TERMINAL_STATUSES and current:
            raise ValueError(f"Terminal complaint {complaint_id} should not retain a current assignment.")
        if complaint.status not in TERMINAL_STATUSES and len(current) != 1:
            raise ValueError(f"Open complaint {complaint_id} must have exactly one current assignment.")
        for sequence, item in enumerate(history, start=1):
            if item.sequence_number != sequence:
                raise ValueError(f"Complaint {complaint_id} assignment history is not contiguous.")
            if sequence > 1 and item.assigned_at < history[sequence - 2].assigned_at:
                raise ValueError(f"Complaint {complaint_id} assignment history is not chronological.")
        current_item = current[0] if current else history[-1]
        if current_item.agent.team != team_for_complaint(complaint):
            raise ValueError(f"Complaint {complaint_id} is not routed to its preferred team.")
        if complaint.category.name == "Safety Issue" and complaint.priority != "Critical":
            raise ValueError(f"Safety complaint {complaint_id} must have Critical priority.")


def generate_assignments(
    complaints: Sequence[Complaint],
    agents: Sequence[Agent],
    seed: int = RANDOM_SEED,
) -> list[Assignment]:
    """Assign each complaint once, with deterministic specialist reassignments for selected cases."""
    if not complaints or not agents:
        raise ValueError("Assignment generation requires complaints and agents.")
    rng = random.Random(seed)
    for complaint in complaints:
        complaint.assignments.clear()
    workload: dict[str, int] = defaultdict(int)
    assignments: list[Assignment] = []
    for complaint_index, complaint in enumerate(complaints, start=1):
        target_team = team_for_complaint(complaint)
        preferred = sorted(
            _available_agents(agents, target_team, complaint.category.name),
            key=lambda agent: (workload[agent.id] / agent.max_active_tickets, agent.id),
        )
        reassign = complaint_index % 13 == 0 and target_team != "General Support"
        if reassign:
            initial_pool = _available_agents(agents, "General Support")
            initial_agent = min(initial_pool, key=lambda agent: (workload[agent.id] / agent.max_active_tickets, agent.id))
            final_agent = preferred[0]
            initial_time = complaint.created_at + timedelta(minutes=rng.randint(2, 15))
            final_time = initial_time + timedelta(minutes=rng.randint(20, 90))
            history = (
                Assignment(
                    id=generate_assignment_id(complaint.id, 1),
                    complaint=complaint,
                    complaint_id=complaint.id,
                    agent=initial_agent,
                    sequence_number=1,
                    assigned_by="SYSTEM_ROUTER",
                    assignment_reason=f"Initial triage by General Support before {target_team} review.",
                    assigned_at=initial_time,
                    unassigned_at=final_time,
                    is_current=False,
                ),
                Assignment(
                    id=generate_assignment_id(complaint.id, 2),
                    complaint=complaint,
                    complaint_id=complaint.id,
                    agent=final_agent,
                    sequence_number=2,
                    assigned_by="SYSTEM_ROUTER",
                    assignment_reason=f"Reassigned to the {target_team} specialist team.",
                    assigned_at=final_time,
                    unassigned_at=None,
                    is_current=complaint.status not in TERMINAL_STATUSES,
                ),
            )
            assignments.extend(history)
            workload[initial_agent.id] += 1
            final_choice = final_agent
        else:
            final_choice = preferred[0]
            assigned_at = complaint.created_at + timedelta(minutes=rng.randint(2, 15))
            assignment = Assignment(
                id=generate_assignment_id(complaint.id, 1),
                complaint=complaint,
                complaint_id=complaint.id,
                agent=final_choice,
                sequence_number=1,
                assigned_by="SYSTEM_ROUTER",
                assignment_reason=f"Matched to {target_team} by complaint category and priority.",
                assigned_at=assigned_at,
                unassigned_at=None,
                is_current=complaint.status not in TERMINAL_STATUSES,
            )
            assignments.append(assignment)
        if complaint.status not in TERMINAL_STATUSES:
            workload[final_choice.id] += 1
    validate_assignments(assignments, complaints)
    return assignments


def main() -> int:
    """Explain the dependency-driven API; assignments require generated complaints and agents."""
    raise SystemExit("Use generate_assignments(complaints, agents) after generating those model records.")


if __name__ == "__main__":
    main()
