"""
SLAClock and SLAEvent SQLAlchemy Models.
"""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.complaint import Complaint


class SLAClock(Base):
    """
    SLAClock entity managing active, paused, and breached time counters for a complaint.
    ID format: SLA-<complaint-id>
    """
    __tablename__ = "sla_clocks"
    __table_args__ = (
        CheckConstraint(
            "clock_state IN ('Running', 'Paused', 'Stopped', 'Breached')",
            name="chk_sla_clock_state",
        ),
        CheckConstraint("target_duration_minutes > 0", name="chk_sla_target_duration_positive"),
        CheckConstraint("elapsed_active_minutes >= 0", name="chk_sla_elapsed_active_nonnegative"),
        CheckConstraint("elapsed_paused_minutes >= 0", name="chk_sla_elapsed_paused_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    target_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    elapsed_active_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    elapsed_paused_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    clock_state: Mapped[str] = mapped_column(String(20), default="Running", nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    last_pause_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_resume_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    breached_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="sla_clock")
    events: Mapped[List["SLAEvent"]] = relationship(
        "SLAEvent",
        back_populates="sla_clock",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<SLAClock(id='{self.id}', state='{self.clock_state}', breached={self.is_breached})>"


class SLAEvent(Base):
    """
    SLAEvent audit trail recording clock events: start, pause, resume, stop, breach.
    """
    __tablename__ = "sla_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('Started', 'Paused', 'Resumed', 'Stopped', 'Breached', 'Adjusted')",
            name="chk_sla_event_type",
        ),
        CheckConstraint("active_minutes_at_event >= 0", name="chk_sla_active_minutes_nonnegative"),
        CheckConstraint("paused_minutes_at_event >= 0", name="chk_sla_paused_minutes_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sla_clock_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("sla_clocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)

    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    active_minutes_at_event: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paused_minutes_at_event: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    sla_clock: Mapped["SLAClock"] = relationship("SLAClock", back_populates="events")

    def __repr__(self) -> str:
        return f"<SLAEvent(sla_clock_id='{self.sla_clock_id}', event='{self.event_type}', at='{self.event_time}')>"

