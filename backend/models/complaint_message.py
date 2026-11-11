"""
ComplaintMessage SQLAlchemy Model.
"""

from typing import TYPE_CHECKING
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


class ComplaintMessage(Base):
    """
    ComplaintMessage entity preserving communication history between customers and agents.
    ID format: MSG-<complaint-id>-001
    """
    __tablename__ = "complaint_messages"
    __table_args__ = (
        UniqueConstraint("complaint_id", "sequence_number", name="uq_msg_complaint_seq"),
        CheckConstraint(
            "sender_type IN ('Customer', 'Agent', 'System')",
            name="chk_msg_sender_type",
        ),
        CheckConstraint("sequence_number > 0", name="chk_msg_sequence_positive"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(150), nullable=False)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ComplaintMessage(id='{self.id}', sender='{self.sender_name}' ({self.sender_type}))>"

