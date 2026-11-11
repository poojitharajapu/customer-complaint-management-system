"""Generate deterministic synthetic support agents."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Iterable

from backend.models.agent import Agent
from backend.models.id_generators import generate_agent_id
from generator.config import DATA_YEAR, RANDOM_SEED


TEAMS = ("Technical Support", "Billing", "Delivery", "General Support", "Safety")
STARTER_AGENT_COUNT = 10
FULL_AGENT_COUNT = 50
_ROLES = ("Support Agent", "Senior Specialist", "Team Lead", "Manager")
_SYLLABLES = ("Ari", "Bela", "Caro", "Davi", "Eli", "Fena", "Gali", "Hiro", "Iver", "Jori", "Kela", "Lumi", "Maro", "Neri", "Ovi", "Pavo", "Ralo", "Sela", "Tavi", "Vero")
_TEAM_SKILLS = {
    "Technical Support": ("Product Defect", "device troubleshooting", "warranty triage"),
    "Billing": ("Refund", "Payment Issue", "billing review"),
    "Delivery": ("Delivery Delay", "Wrong Item", "Missing Item"),
    "General Support": ("Account Issue", "Service Quality", "Other"),
    "Safety": ("Safety Issue", "product hazard escalation", "urgent triage"),
}


def agent_count_for_mode(mode: str) -> int:
    """Return the configured-in-module support team size for Starter or Full mode."""
    counts = {"starter": STARTER_AGENT_COUNT, "full": FULL_AGENT_COUNT}
    try:
        return counts[mode.strip().lower()]
    except (AttributeError, KeyError) as error:
        raise ValueError("mode must be either 'starter' or 'full'") from error


def _fictional_name(rng: random.Random) -> str:
    """Create a synthetic name from seeded syllables instead of real-person data."""
    parts = [rng.choice(_SYLLABLES), rng.choice(_SYLLABLES)]
    return parts[0] + parts[1].lower()


def validate_agents(agents: Iterable[Agent]) -> None:
    """Check agent IDs, unique emails, supported roles, teams, and transient availability."""
    seen_emails: set[str] = set()
    for sequence, agent in enumerate(agents, start=1):
        if not isinstance(agent, Agent) or agent.id != generate_agent_id(sequence):
            raise ValueError(f"Agent at position {sequence} has an invalid model or ID.")
        if not agent.first_name or not agent.last_name or len(agent.first_name) > 100 or len(agent.last_name) > 100:
            raise ValueError(f"Agent {agent.id} must have valid first and last names.")
        if agent.email in seen_emails or not agent.email.endswith("@example.invalid"):
            raise ValueError(f"Agent {agent.id} has a duplicate or non-synthetic email.")
        if agent.team not in TEAMS or agent.role not in _ROLES or agent.max_active_tickets <= 0:
            raise ValueError(f"Agent {agent.id} has invalid team, role, or ticket capacity.")
        if not isinstance(agent.is_active, bool):
            raise ValueError(f"Agent {agent.id} active flag must be boolean.")
        if getattr(agent, "availability", None) not in ("Available", "Busy", "Unavailable"):
            raise ValueError(f"Agent {agent.id} has invalid availability metadata.")
        if not getattr(agent, "skills", None):
            raise ValueError(f"Agent {agent.id} must have at least one skill.")
        seen_emails.add(agent.email)


def generate_agents(mode: str = "starter", seed: int = RANDOM_SEED) -> list[Agent]:
    """Generate 10 Starter or 50 Full synthetic support agents with repeatable values."""
    count = agent_count_for_mode(mode)
    rng = random.Random(seed)
    agents: list[Agent] = []
    for sequence in range(1, count + 1):
        team = TEAMS[(sequence - 1) % len(TEAMS)]
        team_slot = (sequence - 1) // len(TEAMS)
        active = team_slot == 0 or rng.random() >= 0.12
        availability = "Available" if team_slot == 0 else rng.choice(("Available", "Busy", "Unavailable"))
        first_name = _fictional_name(rng)
        last_name = _fictional_name(rng)
        year_start = datetime(DATA_YEAR, 1, 1, tzinfo=timezone.utc)
        year_length = 366 if DATA_YEAR % 4 == 0 and (DATA_YEAR % 100 != 0 or DATA_YEAR % 400 == 0) else 365
        created_at = year_start + timedelta(seconds=rng.randrange(year_length * 24 * 60 * 60))
        agent = Agent(
            id=generate_agent_id(sequence),
            first_name=first_name,
            last_name=last_name,
            email=f"agent{sequence:04d}@example.invalid",
            phone=f"+1-202-555-01{rng.randrange(100):02d}",
            team=team,
            role=rng.choice(_ROLES),
            max_active_tickets=rng.randint(8, 18),
            is_active=active,
            created_at=created_at,
            updated_at=created_at,
        )
        # Skills and availability are not persisted by the current Agent model.
        agent.skills = _TEAM_SKILLS[team]
        agent.availability = availability
        agents.append(agent)
    validate_agents(agents)
    return agents


def main() -> int:
    """Generate a team in memory and print its size without connecting to a database."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic support agents in memory.")
    parser.add_argument("--mode", choices=("starter", "full"), default="starter")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    agents = generate_agents(args.mode, args.seed)
    print(f"Generated {len(agents)} agents in {args.mode.title()} mode; records remain in memory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
