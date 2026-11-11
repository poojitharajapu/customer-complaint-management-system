"""
Product SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, List, Optional
from decimal import Decimal
from sqlalchemy import String, Text, Numeric, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.category import Category
    from backend.models.order import OrderItem
    from backend.models.complaint import Complaint


class Product(Base, TimestampMixin):
    """
    Product entity representing goods or services supported by the company.
    ID format: PRD-000001
    """
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="chk_product_unit_price"),
        CheckConstraint("status IN ('Active', 'Discontinued', 'OutOfStock')", name="chk_product_status"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    category_id: Mapped[Optional[str]] = mapped_column(
        String(30),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )

    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Active", nullable=False)

    # Relationships
    category: Mapped[Optional["Category"]] = relationship("Category")
    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="product",
    )
    complaints: Mapped[List["Complaint"]] = relationship(
        "Complaint",
        back_populates="product",
    )

    def __repr__(self) -> str:
        return f"<Product(id='{self.id}', sku='{self.sku}', name='{self.name}', price={self.unit_price})>"

