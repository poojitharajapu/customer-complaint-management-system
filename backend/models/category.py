"""
Category SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String, Boolean, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.complaint import Complaint
    from backend.models.priority_rule import PriorityRule


class Category(Base, TimestampMixin):
    """
    Category entity classifying complaints (e.g., Billing, Technical Support, Delivery).
    ID format: CAT-000001
    """
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("default_priority IN ('Critical', 'High', 'Medium', 'Low')", name="chk_category_default_priority"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Optional self-referential hierarchy
    parent_category_id: Mapped[Optional[str]] = mapped_column(
        String(30),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    default_priority: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    complaints: Mapped[List["Complaint"]] = relationship(
        "Complaint",
        back_populates="category",
    )
    priority_rules: Mapped[List["PriorityRule"]] = relationship(
        "PriorityRule",
        back_populates="category",
        cascade="all, delete-orphan",
    )
    parent_category: Mapped[Optional["Category"]] = relationship(
        "Category",
        remote_side=[id],
        back_populates="subcategories",
    )
    subcategories: Mapped[List["Category"]] = relationship(
        "Category",
        back_populates="parent_category",
    )

    def __repr__(self) -> str:
        return f"<Category(id='{self.id}', name='{self.name}', default_priority='{self.default_priority}')>"

