"""
Assignment SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, Optional
from datetime import datetime, timezone
from sqlalchemy import (
    String,
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


class Assignment(Base):
    """
    Assignment entity tracking ticket assignments, reassignments, and ownership history.
    ID format: ASN-<complaint-id>-001
    """
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("complaint_id", "sequence_number", name="uq_asn_complaint_seq"),
        CheckConstraint("sequence_number > 0", name="chk_asn_sequence_positive"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assignment_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    unassigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="assignments")
    agent: Mapped["Agent"] = relationship("Agent", back_populates="assignments")

    def __repr__(self) -> str:
        return f"<Assignment(id='{self.id}', complaint_id='{self.complaint_id}', agent_id='{self.agent_id}', current={self.is_current})>"

