"""
Customer SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, List
from sqlalchemy import String, Boolean, CheckConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.order import Order
    from backend.models.complaint import Complaint
    from backend.models.survey import Survey


class Customer(Base, TimestampMixin):
    """
    Customer entity representing consumers or organizations submitting complaints.
    ID format: CUS-000001
    """
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("tier IN ('Standard', 'Premium', 'Enterprise', 'VIP')", name="chk_customer_tier"),
        CheckConstraint("status IN ('Active', 'Inactive', 'Suspended')", name="chk_customer_status"),
    )

    # Primary key
    id: Mapped[str] = mapped_column(String(30), primary_key=True)

    # Required fields
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # Optional fields
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # State, Tier & Vulnerability flag
    tier: Mapped[str] = mapped_column(String(50), default="Standard", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Active", nullable=False)
    is_vulnerable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("0"),
        nullable=False,
    )

    # Relationships
    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    complaints: Mapped[List["Complaint"]] = relationship(
        "Complaint",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    surveys: Mapped[List["Survey"]] = relationship(
        "Survey",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Customer(id='{self.id}', name='{self.first_name} {self.last_name}', email='{self.email}', tier='{self.tier}', vulnerable={self.is_vulnerable})>"
