"""
Deterministic ID generation utilities for all domain entities.

Formats:
- Customer:       CUS-000001
- Order:          ORD-2026-000001
- Complaint:      CMP-2026-000001
- Message:        MSG-<complaint-id>-001
- SLA Clock:      SLA-<complaint-id>
- Resolution:     RES-<complaint-id> (or RES-<complaint-id>-01 for multi-attempt)
- Survey:         SRV-<complaint-id>
- Agent:          AGT-000001
- Product:        PRD-000001
- Category:       CAT-000001
- Priority Rule:  RUL-000001
- Assignment:     ASN-<complaint-id>-001
"""

from datetime import datetime, timezone


def generate_customer_id(sequence_num: int) -> str:
    """Returns formatted Customer ID, e.g. CUS-000001"""
    return f"CUS-{sequence_num:06d}"


def generate_order_id(sequence_num: int, year: int | None = None) -> str:
    """Returns formatted Order ID, e.g. ORD-2026-000001"""
    if year is None:
        year = datetime.now(timezone.utc).year
    return f"ORD-{year}-{sequence_num:06d}"


def generate_complaint_id(sequence_num: int, year: int | None = None) -> str:
    """Returns formatted Complaint ID, e.g. CMP-2026-000001"""
    if year is None:
        year = datetime.now(timezone.utc).year
    return f"CMP-{year}-{sequence_num:06d}"


def generate_message_id(complaint_id: str, message_seq: int) -> str:
    """Returns formatted Message ID, e.g. MSG-CMP-2026-000001-001"""
    return f"MSG-{complaint_id}-{message_seq:03d}"


def generate_sla_clock_id(complaint_id: str) -> str:
    """Returns formatted SLA Clock ID, e.g. SLA-CMP-2026-000001"""
    return f"SLA-{complaint_id}"


def generate_resolution_id(complaint_id: str, attempt: int = 1) -> str:
    """
    Returns formatted Resolution ID.
    Single attempt: RES-<complaint-id>
    Multiple attempts: RES-<complaint-id>-01
    """
    if attempt == 1:
        return f"RES-{complaint_id}"
    return f"RES-{complaint_id}-{attempt:02d}"


def generate_survey_id(complaint_id: str) -> str:
    """Returns formatted Survey ID, e.g. SRV-CMP-2026-000001"""
    return f"SRV-{complaint_id}"


def generate_agent_id(sequence_num: int) -> str:
    """Returns formatted Agent ID, e.g. AGT-000001"""
    return f"AGT-{sequence_num:06d}"


def generate_product_id(sequence_num: int) -> str:
    """Returns formatted Product ID, e.g. PRD-000001"""
    return f"PRD-{sequence_num:06d}"


def generate_category_id(sequence_num: int) -> str:
    """Returns formatted Category ID, e.g. CAT-000001"""
    return f"CAT-{sequence_num:06d}"


def generate_priority_rule_id(sequence_num: int) -> str:
    """Returns formatted Priority Rule ID, e.g. RUL-000001"""
    return f"RUL-{sequence_num:06d}"


def generate_assignment_id(complaint_id: str, sequence_num: int) -> str:
    """Returns formatted Assignment ID, e.g. ASN-CMP-2026-000001-001"""
    return f"ASN-{complaint_id}-{sequence_num:03d}"

