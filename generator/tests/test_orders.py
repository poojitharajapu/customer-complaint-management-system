"""Focused tests for deterministic synthetic orders and order items."""

import unittest
from decimal import Decimal

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

import backend.models  # Register the complete SQLAlchemy model graph.
from backend.models.base import Base
from backend.models.customer import Customer
from backend.models.order import Order, OrderItem
from backend.models.product import Product
from generator.config import RANDOM_SEED
from generator.customers import generate_customers
from generator.orders import (
    DELIVERY_STATUSES,
    PAYMENT_STATUSES,
    generate_orders,
    order_count_for_mode,
    validate_orders,
)
from generator.products import generate_products


def _snapshot(orders: list[Order]) -> list[tuple[object, ...]]:
    """Convert orders and their lines to comparable, database-independent values."""
    return [
        (
            order.id,
            order.customer.id,
            order.order_date,
            order.order_status,
            order.payment_status,
            order.delivery_status,
            order.total_amount,
            tuple(
                (
                    item.product.id,
                    item.quantity,
                    item.unit_price,
                    item.total_price,
                )
                for item in order.items
            ),
        )
        for order in orders
    ]


class OrderGeneratorTests(unittest.TestCase):
    """Verify configured sizes, relationships, calculations, reproducibility, and persistence."""

    def test_starter_and_full_order_counts_and_ids(self) -> None:
        """Both modes use the configured customer/product pools and deterministic order IDs."""
        starter = generate_orders("starter", seed=RANDOM_SEED)
        full = generate_orders("full", seed=RANDOM_SEED)
        self.assertEqual(order_count_for_mode("starter"), 80)
        self.assertEqual(order_count_for_mode("full"), 8_000)
        self.assertEqual(len(starter), 80)
        self.assertEqual(len(full), 8_000)
        self.assertEqual(starter[0].id, "ORD-2026-000001")
        self.assertEqual(starter[-1].id, "ORD-2026-000080")
        self.assertEqual(full[-1].id, "ORD-2026-008000")
        self.assertEqual(len({order.id for order in full}), 8_000)
        self.assertEqual(len({order.customer.id for order in starter}), 50)
        self.assertEqual(len({item.product.id for order in starter for item in order.items}), 30)
        self.assertEqual(len({order.customer.id for order in full}), 5_000)
        self.assertEqual(len({item.product.id for order in full for item in order.items}), 30)
        self.assertLess(len({order.customer.id for order in starter}), len(starter))

    def test_valid_references_items_statuses_and_totals(self) -> None:
        """Every order and line references supplied models and all prices/totals are valid."""
        customers = generate_customers("starter", seed=RANDOM_SEED)
        products = generate_products(seed=RANDOM_SEED)
        orders = generate_orders("starter", seed=RANDOM_SEED, customers=customers, products=products)
        validate_orders(orders)
        customer_ids = {customer.id for customer in customers}
        product_ids = {product.id for product in products}
        self.assertEqual({order.customer.id for order in orders}, customer_ids)
        for order in orders:
            self.assertIn(order.payment_status, PAYMENT_STATUSES)
            self.assertIn(order.delivery_status, DELIVERY_STATUSES)
            self.assertGreater(order.total_amount, Decimal("0.00"))
            self.assertEqual(
                order.total_amount,
                sum((item.total_price for item in order.items), start=Decimal("0.00")),
            )
            for item in order.items:
                self.assertIn(item.product.id, product_ids)
                self.assertIsInstance(item.quantity, int)
                self.assertGreater(item.quantity, 0)
                self.assertGreater(item.unit_price, Decimal("0.00"))
                self.assertEqual(item.total_price, item.unit_price * item.quantity)

    def test_same_seed_and_inputs_produce_identical_orders(self) -> None:
        """The same seed and ordered input pools reproduce every order and line field."""
        customers = generate_customers("starter", seed=RANDOM_SEED)
        products = generate_products(seed=RANDOM_SEED)
        first_run = generate_orders("starter", seed=RANDOM_SEED, customers=customers, products=products)
        second_run = generate_orders("starter", seed=RANDOM_SEED, customers=customers, products=products)
        self.assertEqual(_snapshot(first_run), _snapshot(second_run))

    def test_insert_and_retrieve_in_isolated_database(self) -> None:
        """Customers, products, orders, and order items persist with valid foreign keys."""
        customers = generate_customers("starter", seed=RANDOM_SEED)
        products = generate_products(seed=RANDOM_SEED)
        orders = generate_orders("starter", seed=RANDOM_SEED, customers=customers, products=products)
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        try:
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                session.add_all(orders)
                session.commit()
                self.assertEqual(session.scalar(select(func.count()).select_from(Customer)), 50)
                self.assertEqual(session.scalar(select(func.count()).select_from(Product)), 30)
                self.assertEqual(session.scalar(select(func.count()).select_from(Order)), 80)
                self.assertGreater(session.scalar(select(func.count()).select_from(OrderItem)), 80)
                retrieved = session.scalars(select(Order).order_by(Order.id)).all()
                self.assertEqual(len(retrieved), 80)
                self.assertEqual(_snapshot(retrieved), _snapshot(orders))
                self.assertEqual(
                    session.connection().exec_driver_sql("PRAGMA foreign_key_check").all(),
                    [],
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
