"""Generate final and historical resolution attempts from Phase 6 complaints."""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from backend.models.agent import Agent
from backend.models.complaint import Complaint, ComplaintReopenHistory, ComplaintStatusHistory
from backend.models.id_generators import generate_resolution_id
from backend.models.resolution import Resolution
from generator.config import RANDOM_SEED


RESOLUTION_TYPES = (
    "Refund",
    "Replacement",
    "Configuration Fix",
    "Explanation Provided",
    "Credit Issued",
    "Bug Fix",
    "Account Update",
)
_RESOLVED_STATUSES = {"Resolved", "Closed"}
_REOPENED_STATUS = "Reopened"
_NONFINAL_STATUSES = {"New", "Assigned", "In Progress", "Pending Customer", "Pending Vendor"}
_REFUND_NOTE_PATTERN = re.compile(r"(?:Synthetic )?refund amount: \$([0-9]+\.[0-9]{2})", re.IGNORECASE)


def _utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and timezone-aware timestamps to UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _resolution_type(complaint: Complaint, rng: random.Random) -> str:
    """Choose a valid persisted resolution type suitable for the complaint category."""
    issue = complaint.category.name
    if issue == "Refund" and complaint.order is not None:
        return "Refund"
    if issue == "Payment Issue":
        return "Refund" if complaint.order is not None and rng.random() < 0.6 else "Credit Issued"
    if issue in ("Product Defect", "Safety Issue"):
        return rng.choice(("Replacement", "Configuration Fix"))
    if issue in ("Wrong Item", "Missing Item"):
        return "Replacement"
    if issue == "Account Issue":
        return "Account Update"
    if issue == "Delivery Delay":
        return rng.choice(("Replacement", "Explanation Provided"))
    if issue == "Service Quality":
        return "Credit Issued"
    return "Explanation Provided"


def _resolution_time(complaint: Complaint) -> datetime:
    """Use the resolved status event and SLA stop/breach event to place the resolution."""
    resolved_event = next(
        (event for event in complaint.status_history if event.to_status == "Resolved"),
        None,
    )
    candidates = [_utc(resolved_event.changed_at)] if resolved_event else [_utc(complaint.created_at)]
    clock = complaint.sla_clock
    if clock is not None:
        if clock.stop_time is not None:
            candidates.append(_utc(clock.stop_time))
        if clock.breached_at is not None:
            candidates.append(_utc(clock.breached_at))
    return max(candidates)


def _resolution_text(complaint: Complaint, resolution_type: str) -> tuple[str, str]:
    """Create a synthetic root cause and action using available order/product details."""
    product_name = complaint.product.name if complaint.product is not None else "the reported item"
    if resolution_type == "Refund":
        return "The returned or disputed purchase qualified for a payment adjustment.", "A refund was approved for the eligible order amount."
    if resolution_type == "Replacement":
        return f"The report about {product_name} or its delivery was confirmed.", f"A replacement or corrected delivery for {product_name} was arranged."
    if resolution_type == "Configuration Fix":
        return f"The reported {product_name} issue was caused by a correctable setup or component fault.", f"Troubleshooting steps or repair guidance for {product_name} were provided."
    if resolution_type == "Credit Issued":
        return "A service or payment concern warranted a goodwill adjustment.", "A service credit was applied and explained to the customer."
    if resolution_type == "Account Update":
        return "The customer account contained an access or profile issue.", "The account setting was corrected and access guidance was sent."
    if resolution_type == "Bug Fix":
        return "A reproducible software issue affected the reported service.", "The issue was corrected and the customer was notified."
    return "The complaint was reviewed and a clear explanation addressed the reported concern.", "The applicable policy and next steps were explained to the customer."


def _close_and_reopen(complaint: Complaint, resolution: Resolution, rng: random.Random) -> None:
    """Record a prior closure and subsequent reopen while preserving the original resolution."""
    resolved_events = [event for event in complaint.status_history if event.to_status == "Resolved"]
    resolved_event = resolved_events[-1] if resolved_events else None
    if resolved_event is None:
        raise ValueError(f"Reopened complaint {complaint.id} has no preceding Resolved transition.")
    before = [event for event in complaint.status_history if event.to_status != "Reopened" and event.to_status != "Closed"]
    resolved_event.changed_at = resolution.resolved_at
    closure_time = resolution.resolved_at + timedelta(minutes=rng.randint(5, 90))
    reopen_time = closure_time + timedelta(hours=rng.randint(1, 48))
    actor = resolution.resolved_by_agent_id
    closed_event = ComplaintStatusHistory(
        complaint=complaint,
        complaint_id=complaint.id,
        from_status="Resolved",
        to_status="Closed",
        changed_by=actor,
        reason="The initial resolution was completed and the case was closed.",
        changed_at=closure_time,
    )
    reopened_event = ComplaintStatusHistory(
        complaint=complaint,
        complaint_id=complaint.id,
        from_status="Closed",
        to_status="Reopened",
        changed_by=complaint.customer.id,
        reason="The customer reported that the addressed issue had returned.",
        changed_at=reopen_time,
    )
    complaint.status_history = before + [closed_event, reopened_event]
    reopen_record = complaint.reopen_history[0] if complaint.reopen_history else ComplaintReopenHistory(
        complaint=complaint,
        complaint_id=complaint.id,
        reopen_sequence=1,
        reopened_by=complaint.customer.id,
        reopen_reason="The customer reported that the addressed issue had returned.",
    )
    reopen_record.reopen_sequence = 1
    reopen_record.previous_resolution = resolution
    reopen_record.previous_resolution_id = resolution.id
    reopen_record.reopened_by = complaint.customer.id
    reopen_record.reopen_reason = "The customer reported that the addressed issue had returned."
    reopen_record.reopened_at = reopen_time
    complaint.reopen_history = [reopen_record]
    complaint.status = "Reopened"
    complaint.reopen_count = 1
    complaint.updated_at = reopen_time


def generate_resolutions(
    complaints: Sequence[Complaint],
    agents: Sequence[Agent],
    seed: int = RANDOM_SEED,
) -> list[Resolution]:
    """Create one final resolution for closed complaints and one historical attempt for reopened cases."""
    if not complaints or not agents:
        raise ValueError("Resolution generation requires complaints and agents.")
    rng = random.Random(seed)
    resolutions: list[Resolution] = []
    for complaint in complaints:
        original_status = complaint.status
        if original_status not in _RESOLVED_STATUSES and original_status != _REOPENED_STATUS:
            if complaint.resolutions:
                raise ValueError(f"Unresolved complaint {complaint.id} already has a resolution.")
            continue
        assignment_history = sorted(complaint.assignments, key=lambda item: item.sequence_number)
        if not assignment_history:
            raise ValueError(f"Resolved complaint {complaint.id} has no assigned agent.")
        agent = assignment_history[-1].agent
        resolution_type = _resolution_type(complaint, rng)
        root_cause, action_taken = _resolution_text(complaint, resolution_type)
        resolved_at = _resolution_time(complaint)
        refund_amount: Decimal | None = None
        notes = "Synthetic resolution record; no real customer data was used."
        if resolution_type == "Refund":
            if complaint.order is None:
                raise ValueError(f"Refund resolution for {complaint.id} has no related order.")
            amount = complaint.order.total_amount
            factor = Decimal(rng.randint(50, 100)) / Decimal("100")
            refund_amount = (amount * factor).quantize(Decimal("0.01"))
            refund_amount = min(refund_amount, amount)
            notes += f" Synthetic refund amount: ${refund_amount:.2f}."
        resolution = Resolution(
            id=generate_resolution_id(complaint.id, attempt=1),
            complaint=complaint,
            complaint_id=complaint.id,
            attempt_number=1,
            resolved_by_agent=agent,
            resolved_by_agent_id=agent.id,
            root_cause=root_cause,
            action_taken=action_taken,
            customer_notes=notes,
            resolution_type=resolution_type,
            is_accepted_by_customer=bool(rng.random() < 0.82),
            resolved_at=resolved_at,
        )
        resolution.refund_amount = refund_amount
        resolutions.append(resolution)
        if original_status == _REOPENED_STATUS:
            _close_and_reopen(complaint, resolution, rng)
        else:
            resolved_event = next(event for event in complaint.status_history if event.to_status == "Resolved")
            resolved_event.changed_at = resolved_at
            closed_event = next((event for event in complaint.status_history if event.to_status == "Closed"), None)
            if closed_event is None:
                closed_event = ComplaintStatusHistory(
                    complaint=complaint,
                    complaint_id=complaint.id,
                    from_status="Resolved",
                    to_status="Closed",
                    changed_by=agent.id,
                    reason="The final resolution was confirmed and the case was closed.",
                    changed_at=resolved_at + timedelta(minutes=rng.randint(5, 90)),
                )
            else:
                closed_event.from_status = "Resolved"
                closed_event.changed_at = max(_utc(closed_event.changed_at), resolved_at + timedelta(minutes=1))
            complaint.status = "Closed"
            complaint.updated_at = closed_event.changed_at
            complaint.reopen_count = 0
            complaint.reopen_history = []
    validate_resolutions(complaints, resolutions)
    return resolutions


def extract_refund_amount(resolution: Resolution) -> Decimal:
    """Read a refund amount from persisted customer notes, returning zero for other types."""
    if resolution.resolution_type != "Refund":
        return Decimal("0.00")
    match = _REFUND_NOTE_PATTERN.search(resolution.customer_notes or "")
    if match is None:
        raise ValueError(f"Refund resolution {resolution.id} has no recorded amount in its notes.")
    return Decimal(match.group(1))


def validate_resolutions(complaints: Sequence[Complaint], resolutions: Sequence[Resolution]) -> None:
    """Check resolution cardinality, links, supported types, amounts, and lifecycle chronology."""
    by_complaint: dict[str, list[Resolution]] = {}
    agent_ids = {
        assignment.agent.id
        for complaint in complaints
        for assignment in complaint.assignments
        if assignment.agent is not None
    }
    allowed_statuses = _RESOLVED_STATUSES | {_REOPENED_STATUS} | _NONFINAL_STATUSES
    for resolution in resolutions:
        complaint = resolution.complaint
        if complaint is None or resolution.complaint_id != complaint.id:
            raise ValueError(f"Resolution {resolution.id} references an invalid complaint.")
        if resolution.id != generate_resolution_id(complaint.id, resolution.attempt_number):
            raise ValueError(f"Resolution {resolution.id} has an invalid deterministic ID.")
        if resolution.resolved_by_agent_id not in agent_ids:
            raise ValueError(f"Resolution {resolution.id} references an unknown agent.")
        if resolution.resolution_type not in RESOLUTION_TYPES:
            raise ValueError(f"Resolution {resolution.id} has a type outside the model constraint.")
        if _utc(resolution.resolved_at) <= _utc(complaint.created_at):
            raise ValueError(f"Resolution {resolution.id} does not follow complaint creation.")
        if resolution.resolution_type == "Refund":
            amount = extract_refund_amount(resolution)
            if complaint.order is None or amount <= 0 or amount > complaint.order.total_amount:
                raise ValueError(f"Resolution {resolution.id} refund amount is invalid for its order.")
        by_complaint.setdefault(complaint.id, []).append(resolution)

    for complaint in complaints:
        if complaint.status not in allowed_statuses:
            raise ValueError(f"Complaint {complaint.id} has an unsupported final status.")
        history = sorted(complaint.status_history, key=lambda event: _utc(event.changed_at))
        if not history or history[-1].to_status != complaint.status:
            raise ValueError(f"Complaint {complaint.id} history does not match its final status.")
        if any(_utc(after.changed_at) < _utc(before.changed_at) for before, after in zip(history, history[1:])):
            raise ValueError(f"Complaint {complaint.id} status history is not chronological.")
        attempts = by_complaint.get(complaint.id, [])
        if complaint.status == "Closed":
            if len(attempts) != 1 or not any(
                event.to_status == "Closed" and _utc(event.changed_at) > _utc(attempts[0].resolved_at)
                for event in history
            ):
                raise ValueError(f"Closed complaint {complaint.id} needs one resolution and later closure.")
        elif complaint.status == "Reopened":
            if len(attempts) != 1 or not complaint.reopen_history:
                raise ValueError(f"Reopened complaint {complaint.id} needs its prior resolution and reopen record.")
            reopen = complaint.reopen_history[0]
            if reopen.previous_resolution_id != attempts[0].id:
                raise ValueError(f"Reopen record for {complaint.id} does not reference its prior resolution.")
            closed_at = next((event.changed_at for event in history if event.to_status == "Closed"), None)
            reopened_at = next((event.changed_at for event in history if event.to_status == "Reopened"), None)
            if closed_at is None or reopened_at is None:
                raise ValueError(f"Reopened complaint {complaint.id} lacks close/reopen transitions.")
            if not (_utc(attempts[0].resolved_at) < _utc(closed_at) < _utc(reopened_at)):
                raise ValueError(f"Reopened complaint {complaint.id} has inconsistent resolution chronology.")
        elif attempts:
            raise ValueError(f"Unresolved complaint {complaint.id} must not have a resolution.")


def main() -> int:
    """Explain that resolutions are generated after complaints, assignments, and SLA data."""
    raise SystemExit("Use generate_resolutions(complaints, agents) within the Phase 7 pipeline.")


if __name__ == "__main__":
    main()
