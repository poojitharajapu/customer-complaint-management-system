"""
PriorityRule SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, Optional
from decimal import Decimal
from sqlalchemy import String, Boolean, Numeric, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.category import Category


class PriorityRule(Base, TimestampMixin):
    """
    PriorityRule entity defining rules to determine complaint priority
    and SLA target hours based on category, customer tier, or keywords.
    ID format: RUL-000001
    """
    __tablename__ = "priority_rules"
    __table_args__ = (
        CheckConstraint(
            "target_priority IN ('Critical', 'High', 'Medium', 'Low')",
            name="chk_priority_rule_target",
        ),
        CheckConstraint("sla_target_hours > 0", name="chk_priority_rule_sla_hours"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)

    category_id: Mapped[Optional[str]] = mapped_column(
        String(30),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    customer_tier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    keyword_trigger: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    target_priority: Mapped[str] = mapped_column(String(20), nullable=False)
    sla_target_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="priority_rules")

    def __repr__(self) -> str:
        return f"<PriorityRule(id='{self.id}', name='{self.name}', target='{self.target_priority}', hours={self.sla_target_hours})>"

