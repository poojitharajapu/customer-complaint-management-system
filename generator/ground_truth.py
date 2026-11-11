"""Keep authored scenario labels in a separate export-only structure.

Ground truth is for evaluation and anomaly detection. It is never passed into
the complaint classifier, priority scorer, or other generation decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from backend.models.complaint import Complaint


@dataclass(frozen=True)
class GroundTruthLabel:
    complaint_id: str
    expected_category: str
    expected_priority: str
    expected_severity: str
    expected_repeat: bool
    repeat_of_complaint_id: str | None
    expected_safety: bool
    expected_sla_breach: bool
    anomaly_label: str = "valid"


def build_ground_truth(complaints: Iterable[Complaint], sla_clocks: Iterable[object]) -> list[GroundTruthLabel]:
    """Create evaluation labels from generated scenario metadata and linked outcomes."""
    breach_by_complaint = {
        clock.complaint_id: bool(clock.is_breached) for clock in sla_clocks
    }
    result = []
    for complaint in complaints:
        result.append(GroundTruthLabel(
            complaint_id=complaint.id,
            expected_category=getattr(complaint, "expected_category", complaint.category.name),
            expected_priority=complaint.priority,
            expected_severity=getattr(complaint, "severity", complaint.priority),
            expected_repeat=bool(getattr(complaint, "repeat_of_id", None)),
            repeat_of_complaint_id=getattr(complaint, "repeat_of_id", None),
            expected_safety=getattr(complaint, "expected_category", complaint.category.name) == "Safety Issue",
            expected_sla_breach=breach_by_complaint.get(complaint.id, False),
        ))
    return result


def ground_truth_as_dicts(labels: Iterable[GroundTruthLabel]) -> list[dict[str, object]]:
    """Convert label records to simple dictionaries for deterministic export."""
    return [asdict(label) for label in labels]
