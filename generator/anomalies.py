"""Build separate, intentionally invalid anomaly examples and detect each case."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class AnomalyRecord:
    id: str
    anomaly_type: str
    affected_entity: str
    description: str
    expected_behavior: str
    ground_truth_label: str
    invalid_values: dict[str, object]
    intentionally_invalid: bool = True


def generate_anomalies() -> list[AnomalyRecord]:
    """Return six invalid scenarios as data; never mutate or persist baseline models."""
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    scenarios = (
        ("invalid_customer_fk", "complaint", "complaint references a customer absent from the customer set", "Customer reference must exist.", {"customer_id": "CUS-MISSING"}),
        ("resolution_before_creation", "resolution", "resolution timestamp precedes complaint creation", "Resolution follows complaint creation.", {"complaint_created_at": "2026-06-01T12:00:00Z", "resolved_at": "2026-06-01T11:00:00Z"}),
        ("incorrect_sla_pause_math", "sla_clock", "paused duration was included in active elapsed time", "Paused time is excluded from active elapsed time and added to due time.", {"wall_elapsed_minutes": 70, "active_minutes": 70, "paused_minutes": 30, "deadline_extension_minutes": 0}),
        ("unlinked_repeat", "complaint", "repeat complaint matches an earlier one but has no repeat_of_id", "A repeat points to an earlier matching complaint.", {"earlier_complaint_id": "CMP-2026-000001", "repeat_of_id": None}),
        ("safety_low_queue", "assignment", "critical safety complaint routed to a low priority queue", "Safety complaints route to the Critical queue.", {"category": "Safety Issue", "priority": "Critical", "queue": "Low"}),
        ("survey_before_closure", "survey", "survey timestamp precedes complaint closure", "Survey submission follows closure.", {"closed_at": "2026-06-01T12:00:00Z", "submitted_at": "2026-06-01T11:00:00Z"}),
    )
    return [AnomalyRecord(f"ANM-{i:06d}", kind, entity, description, expected, "invalid", values)
            for i, (kind, entity, description, expected, values) in enumerate(scenarios, start=1)]


def detect_anomaly(anomaly: AnomalyRecord) -> bool:
    """Apply a deterministic rule to confirm that the represented case is invalid."""
    v = anomaly.invalid_values
    predicates = {
        "invalid_customer_fk": lambda: str(v.get("customer_id", "")).startswith("CUS-MISSING"),
        "resolution_before_creation": lambda: v.get("resolved_at", "") < v.get("complaint_created_at", ""),
        "incorrect_sla_pause_math": lambda: int(v.get("active_minutes", 0)) != int(v.get("wall_elapsed_minutes", 0)) - int(v.get("paused_minutes", 0)) or int(v.get("deadline_extension_minutes", 0)) != int(v.get("paused_minutes", 0)),
        "unlinked_repeat": lambda: bool(v.get("earlier_complaint_id")) and not v.get("repeat_of_id"),
        "safety_low_queue": lambda: v.get("category") == "Safety Issue" and v.get("priority") == "Critical" and v.get("queue") == "Low",
        "survey_before_closure": lambda: v.get("submitted_at", "") < v.get("closed_at", ""),
    }
    return anomaly.intentionally_invalid and anomaly.ground_truth_label == "invalid" and predicates.get(anomaly.anomaly_type, lambda: False)()


def anomalies_as_dicts(anomalies: list[AnomalyRecord]) -> list[dict[str, object]]:
    """Convert separate anomaly records into export-safe dictionaries."""
    return [asdict(anomaly) for anomaly in anomalies]
