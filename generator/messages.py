"""Generate deterministic customer and support-agent conversations."""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Sequence

from backend.models.agent import Agent
from backend.models.assignment import Assignment
from backend.models.complaint import Complaint
from backend.models.complaint_message import ComplaintMessage
from backend.models.id_generators import generate_message_id
from generator.assignments import team_for_complaint
from generator.config import FULL_MODE, RANDOM_SEED, STARTER_MODE


def _mode_for_count(complaint_count: int) -> str:
    """Resolve a supported configured mode from its complaint record count."""
    if complaint_count == STARTER_MODE["complaints"]:
        return "starter"
    if complaint_count == FULL_MODE["complaints"]:
        return "full"
    raise ValueError("Messages require the configured Starter or Full complaint count.")


def _agent_for(complaint: Complaint, agents: Sequence[Agent], assignments: Sequence[Assignment]) -> Agent:
    """Use the complaint's current assignment or select an active available team agent."""
    history = [item for item in assignments if item.complaint and item.complaint.id == complaint.id]
    current = next((item.agent for item in history if item.is_current), None)
    if current is None and history:
        current = max(history, key=lambda item: item.sequence_number).agent
    if current is not None:
        if not current.is_active or getattr(current, "availability", "Available") == "Unavailable":
            raise ValueError(f"Complaint {complaint.id} is assigned to an unavailable agent.")
        return current
    preferred_team = team_for_complaint(complaint)
    pool = [
        agent for agent in agents
        if agent.is_active and getattr(agent, "availability", "Available") == "Available"
        and agent.team == preferred_team
    ]
    if not pool:
        pool = [agent for agent in agents if agent.is_active and getattr(agent, "availability", "Available") == "Available"]
    if not pool:
        raise ValueError("No active, available agent exists for message generation.")
    return pool[0]


def validate_messages(messages: Sequence[ComplaintMessage], complaints: Sequence[Complaint]) -> None:
    """Check message IDs, complaint references, sender fields, and chronological sequences."""
    complaint_map = {complaint.id: complaint for complaint in complaints}
    by_complaint: dict[str, list[ComplaintMessage]] = {}
    seen_ids: set[str] = set()
    for message in messages:
        if message.id in seen_ids:
            raise ValueError(f"Duplicate message ID: {message.id}")
        seen_ids.add(message.id)
        complaint = complaint_map.get(message.complaint.id if message.complaint is not None else message.complaint_id)
        if complaint is None or message.complaint is not complaint:
            raise ValueError(f"Message {message.id} references an unknown complaint.")
        if message.sender_type not in ("Customer", "Agent", "System"):
            raise ValueError(f"Message {message.id} has an unsupported sender type.")
        if not message.sender_id or not message.sender_name or not message.message_body.strip():
            raise ValueError(f"Message {message.id} is missing sender or body details.")
        if message.created_at < complaint.created_at:
            raise ValueError(f"Message {message.id} predates its complaint.")
        by_complaint.setdefault(complaint.id, []).append(message)
    for complaint_id, thread in by_complaint.items():
        thread.sort(key=lambda message: message.sequence_number)
        for sequence, message in enumerate(thread, start=1):
            if message.sequence_number != sequence or message.id != generate_message_id(complaint_id, sequence):
                raise ValueError(f"Complaint {complaint_id} message sequence is not contiguous.")
        times = [message.created_at for message in thread]
        if times != sorted(times):
            raise ValueError(f"Complaint {complaint_id} messages are not chronological.")
        if len(thread) != 3:
            raise ValueError(f"Complaint {complaint_id} should have three conversation messages.")
    if set(by_complaint) != set(complaint_map):
        raise ValueError("Every complaint must have a generated message thread.")


def generate_messages(
    complaints: Sequence[Complaint],
    agents: Sequence[Agent],
    assignments: Sequence[Assignment] | None = None,
    seed: int = RANDOM_SEED,
) -> list[ComplaintMessage]:
    """Generate three-message conversations per configured complaint in Starter or Full mode."""
    mode = _mode_for_count(len(complaints))
    expected = {"starter": STARTER_MODE["messages"], "full": FULL_MODE["messages"]}[mode]
    if expected != len(complaints) * 3:
        raise RuntimeError("Configured message volume must remain three messages per complaint.")
    if not agents or not all(isinstance(agent, Agent) and agent.id for agent in agents):
        raise ValueError("Message generation requires Agent model instances.")
    assignments = tuple(assignments or ())
    rng = random.Random(seed)
    messages: list[ComplaintMessage] = []
    for complaint in complaints:
        complaint.messages.clear()
    for complaint in complaints:
        agent = _agent_for(complaint, agents, assignments)
        customer = complaint.customer
        first_time = complaint.created_at
        agent_time = first_time + timedelta(minutes=rng.randint(20, 240))
        followup_time = agent_time + timedelta(minutes=rng.randint(20, 720))
        bodies = (
            f"I am contacting support about {complaint.title.lower()}. {complaint.description}",
            f"Thank you for the details. I am reviewing the {complaint.category.name.lower()} issue and will update you with the next step.",
            "Thank you for looking into this. Please keep me updated when there is progress.",
        )
        senders = (
            ("Customer", customer.id, f"{customer.first_name} {customer.last_name}", first_time),
            ("Agent", agent.id, f"{agent.first_name} {agent.last_name}", agent_time),
            ("Customer", customer.id, f"{customer.first_name} {customer.last_name}", followup_time),
        )
        for sequence, ((sender_type, sender_id, sender_name, created_at), body) in enumerate(zip(senders, bodies), start=1):
            messages.append(
                ComplaintMessage(
                    id=generate_message_id(complaint.id, sequence),
                    complaint=complaint,
                    complaint_id=complaint.id,
                    sequence_number=sequence,
                    sender_type=sender_type,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    message_body=body,
                    is_internal_note=False,
                    created_at=created_at,
                )
            )
    validate_messages(messages, complaints)
    return messages


def main() -> int:
    """Direct callers to the pipeline function because messages require generated inputs."""
    raise SystemExit(
        "Use generate_messages(complaints, agents, assignments) after generating those model records."
    )


if __name__ == "__main__":
    main()
