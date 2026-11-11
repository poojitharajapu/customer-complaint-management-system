"""
Complaint, ComplaintStatusHistory, and ComplaintReopenHistory SQLAlchemy Models.
"""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.customer import Customer
    from backend.models.order import Order
    from backend.models.product import Product
    from backend.models.category import Category
    from backend.models.complaint_message import ComplaintMessage
    from backend.models.assignment import Assignment
    from backend.models.sla import SLAClock
    from backend.models.resolution import Resolution
    from backend.models.survey import Survey


class Complaint(Base, TimestampMixin):
    """
    Complaint entity representing an issue submitted by a customer.
    ID format: CMP-2026-000001
    """
    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('Web', 'Email', 'Phone', 'Chat', 'Mobile')",
            name="chk_complaint_channel",
        ),
        CheckConstraint(
            "priority IN ('Critical', 'High', 'Medium', 'Low')",
            name="chk_complaint_priority",
        ),
        CheckConstraint(
            "status IN ('New', 'Assigned', 'In Progress', 'Pending Customer', 'Pending Vendor', 'Resolved', 'Closed', 'Reopened')",
            name="chk_complaint_status",
        ),
        CheckConstraint("reopen_count >= 0", name="chk_complaint_reopen_count"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)

    customer_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(30),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[Optional[str]] = mapped_column(
        String(30),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(50), default="Web", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="New", nullable=False)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="complaints")
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="complaints")
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="complaints")
    category: Mapped["Category"] = relationship("Category", back_populates="complaints")

    messages: Mapped[List["ComplaintMessage"]] = relationship(
        "ComplaintMessage",
        back_populates="complaint",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment",
        back_populates="complaint",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[List["ComplaintStatusHistory"]] = relationship(
        "ComplaintStatusHistory",
        back_populates="complaint",
        cascade="all, delete-orphan",
    )
    reopen_history: Mapped[List["ComplaintReopenHistory"]] = relationship(
        "ComplaintReopenHistory",
        back_populates="complaint",
        cascade="all, delete-orphan",
    )
    sla_clock: Mapped[Optional["SLAClock"]] = relationship(
        "SLAClock",
        back_populates="complaint",
        uselist=False,
        cascade="all, delete-orphan",
    )
    resolutions: Mapped[List["Resolution"]] = relationship(
        "Resolution",
        back_populates="complaint",
        cascade="all, delete-orphan",
    )
    survey: Mapped[Optional["Survey"]] = relationship(
        "Survey",
        back_populates="complaint",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Complaint(id='{self.id}', title='{self.title[:30]}', priority='{self.priority}', status='{self.status}')>"


class ComplaintStatusHistory(Base):
    """
    Audit trail preserving every status transition of a complaint.
    """
    __tablename__ = "complaint_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    complaint_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="status_history")

    def __repr__(self) -> str:
        return f"<ComplaintStatusHistory(complaint_id='{self.complaint_id}', {self.from_status} -> {self.to_status})>"


class ComplaintReopenHistory(Base):
    """
    Audit trail recording each time a resolved complaint is reopened.
    """
    __tablename__ = "complaint_reopen_history"
    __table_args__ = (
        UniqueConstraint("complaint_id", "reopen_sequence", name="uq_complaint_reopen_seq"),
        CheckConstraint("reopen_sequence > 0", name="chk_reopen_sequence_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    complaint_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reopen_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    previous_resolution_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        ForeignKey("resolutions.id", ondelete="SET NULL"),
        nullable=True,
    )

    reopened_by: Mapped[str] = mapped_column(String(100), nullable=False)
    reopen_reason: Mapped[str] = mapped_column(Text, nullable=False)

    reopened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="reopen_history")
    previous_resolution: Mapped[Optional["Resolution"]] = relationship("Resolution")

    def __repr__(self) -> str:
        return f"<ComplaintReopenHistory(complaint_id='{self.complaint_id}', seq={self.reopen_sequence})>"

