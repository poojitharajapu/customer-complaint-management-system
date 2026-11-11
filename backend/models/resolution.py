"""
Resolution SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, Optional
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.complaint import Complaint
    from backend.models.agent import Agent


class Resolution(Base):
    """
    Resolution entity recording the root cause, action taken, and outcome of a complaint.
    Preserves resolution history across multiple attempts if reopened.
    ID format: RES-<complaint-id> (or RES-<complaint-id>-01 for multi-attempt)
    """
    __tablename__ = "resolutions"
    __table_args__ = (
        UniqueConstraint("complaint_id", "attempt_number", name="uq_resolution_complaint_attempt"),
        CheckConstraint("attempt_number > 0", name="chk_resolution_attempt_positive"),
        CheckConstraint(
            "resolution_type IN ('Refund', 'Replacement', 'Configuration Fix', 'Explanation Provided', 'Credit Issued', 'Bug Fix', 'Account Update')",
            name="chk_resolution_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    resolved_by_agent_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    root_cause: Mapped[str] = mapped_column(String(255), nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    customer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_accepted_by_customer: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="resolutions")
    resolved_by_agent: Mapped["Agent"] = relationship("Agent", back_populates="resolutions")

    def __repr__(self) -> str:
        return f"<Resolution(id='{self.id}', complaint_id='{self.complaint_id}', attempt={self.attempt_number}, type='{self.resolution_type}')>"

