"""
Order and OrderItem SQLAlchemy Models.
"""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    String,
    Text,
    DateTime,
    Numeric,
    Integer,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.customer import Customer
    from backend.models.product import Product
    from backend.models.complaint import Complaint


class Order(Base, TimestampMixin):
    """
    Order entity representing purchases made by customers.
    ID format: ORD-2026-000001
    """
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="chk_order_total_amount"),
        CheckConstraint(
            "order_status IN ('Pending', 'Processing', 'Completed', 'Cancelled', 'Refunded')",
            name="chk_order_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    order_status: Mapped[str] = mapped_column(String(30), default="Completed", nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)
    shipping_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    complaints: Mapped[List["Complaint"]] = relationship(
        "Complaint",
        back_populates="order",
    )

    def __repr__(self) -> str:
        return f"<Order(id='{self.id}', customer_id='{self.customer_id}', total={self.total_amount}, status='{self.order_status}')>"


class OrderItem(Base):
    """
    Bridge table connecting Orders and Products (Many-to-Many).
    Represents individual line items in an order.
    """
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_order_product"),
        CheckConstraint("quantity > 0", name="chk_order_item_quantity"),
        CheckConstraint("unit_price >= 0", name="chk_order_item_unit_price"),
        CheckConstraint("total_price >= 0", name="chk_order_item_total_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="order_items")

    def __repr__(self) -> str:
        return f"<OrderItem(order_id='{self.order_id}', product_id='{self.product_id}', qty={self.quantity})>"

