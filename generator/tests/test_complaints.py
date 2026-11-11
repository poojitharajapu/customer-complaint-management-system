"""Focused tests for complaint generation, classification, scoring, and persistence."""

import unittest

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # Register all mapped relationships before isolated DB creation.
from backend.models.base import Base
from backend.models.category import Category
from backend.models.complaint import Complaint
from backend.models.customer import Customer
from backend.models.order import Order
from backend.models.product import Product
from backend.models.priority_rule import PriorityRule
from generator.config import RANDOM_SEED
from generator.customers import generate_customers
from generator.orders import generate_orders
from generator.products import generate_products
from generator.complaints import (
    ISSUE_CATEGORIES,
    SEVERITY_LEVELS,
    classify_complaint,
    complaint_count_for_mode,
    generate_complaints,
    _score_priority,
    validate_complaints,
)


def _snapshot(complaints: list[Complaint]) -> list[tuple[object, ...]]:
    """Convert complaint fields, classifications, and repeat metadata to comparable values."""
    return [
        (
            complaint.id,
            complaint.customer.id,
            complaint.order.id if complaint.order else None,
            complaint.product.id if complaint.product else None,
            complaint.category.name,
            complaint.title,
            complaint.description,
            complaint.channel,
            complaint.priority,
            complaint.status,
            complaint.reopen_count,
            complaint.created_at,
            complaint.updated_at,
            complaint.severity,
            complaint.priority_reason,
            getattr(complaint, "repeat_of_id", None),
            tuple(
                (entry.from_status, entry.to_status, entry.changed_at)
                for entry in complaint.status_history
            ),
        )
        for complaint in complaints
    ]


class ComplaintGeneratorTests(unittest.TestCase):
    """Generate shared fixtures once, then verify modes and model behavior without live DB access."""

    @classmethod
    def setUpClass(cls) -> None:
        """Prepare deterministic Starter and Full input pools and complaint datasets."""
        cls.products = generate_products(seed=RANDOM_SEED)
        cls.starter_customers = generate_customers("starter", seed=RANDOM_SEED)
        cls.starter_orders = generate_orders(
            "starter", seed=RANDOM_SEED, customers=cls.starter_customers, products=cls.products
        )
        cls.starter = generate_complaints(
            "starter",
            seed=RANDOM_SEED,
            customers=cls.starter_customers,
            products=cls.products,
            orders=cls.starter_orders,
        )
        cls.full_customers = generate_customers("full", seed=RANDOM_SEED)
        cls.full_products = generate_products(seed=RANDOM_SEED)
        cls.full_orders = generate_orders(
            "full", seed=RANDOM_SEED, customers=cls.full_customers, products=cls.full_products
        )
        cls.full = generate_complaints(
            "full",
            seed=RANDOM_SEED,
            customers=cls.full_customers,
            products=cls.full_products,
            orders=cls.full_orders,
        )

    def test_starter_and_full_counts_and_sequential_ids(self) -> None:
        """Configured Starter and Full modes return their expected unique sequential IDs."""
        self.assertEqual(complaint_count_for_mode("starter"), 20)
        self.assertEqual(complaint_count_for_mode("full"), 2_000)
        self.assertEqual(len(self.starter), 20)
        self.assertEqual(len(self.full), 2_000)
        self.assertEqual(self.starter[0].id, "CMP-2026-000001")
        self.assertEqual(self.starter[-1].id, "CMP-2026-000020")
        self.assertEqual(self.full[-1].id, "CMP-2026-002000")
        self.assertEqual(len({complaint.id for complaint in self.full}), 2_000)

    def test_references_categories_statuses_priorities_and_safety(self) -> None:
        """Relationships resolve to supplied models and all classifications remain constrained."""
        validate_complaints(self.full)
        customer_ids = {customer.id for customer in self.full_customers}
        product_ids = {product.id for product in self.products}
        order_ids = {order.id for order in self.full_orders}
        self.assertEqual({complaint.category.name for complaint in self.full}, set(ISSUE_CATEGORIES))
        for complaint in self.full:
            self.assertIn(complaint.customer.id, customer_ids)
            self.assertTrue(complaint.order is None or complaint.order.id in order_ids)
            self.assertTrue(complaint.product is None or complaint.product.id in product_ids)
            self.assertIn(complaint.category.name, ISSUE_CATEGORIES)
            self.assertIn(complaint.priority, {"Critical", "High", "Medium", "Low"})
            self.assertIn(complaint.severity, SEVERITY_LEVELS)
        safety = [complaint for complaint in self.full if complaint.category.name == "Safety Issue"]
        self.assertTrue(safety)
        self.assertTrue(all(complaint.priority == "Critical" for complaint in safety))
        self.assertTrue(any(complaint.order is None for complaint in self.full))

    def test_repeat_links_and_lifecycle_dates(self) -> None:
        """Repeat metadata points backward to matching complaints; histories are chronological."""
        by_id = {complaint.id: complaint for complaint in self.full}
        repeats = [complaint for complaint in self.full if getattr(complaint, "repeat_of_id", None)]
        reopened = [complaint for complaint in self.full if complaint.status == "Reopened"]
        self.assertTrue(repeats)
        self.assertTrue(reopened)
        for complaint in self.full:
            if complaint.order is not None:
                self.assertGreaterEqual(complaint.created_at, complaint.order.order_date)
            history_dates = [event.changed_at for event in complaint.status_history]
            self.assertEqual(history_dates, sorted(history_dates))
            self.assertEqual(complaint.status_history[-1].to_status, complaint.status)
            self.assertGreaterEqual(complaint.updated_at, complaint.created_at)
            if complaint.status == "Reopened":
                self.assertEqual(complaint.reopen_count, 1)
                self.assertEqual(len(complaint.reopen_history), 1)
        for repeated in repeats:
            original = by_id[repeated.repeat_of_id]
            self.assertLess(original.id, repeated.id)
            self.assertLess(original.created_at, repeated.created_at)
            self.assertEqual(original.customer.id, repeated.customer.id)
            self.assertEqual(original.product.id if original.product else None, repeated.product.id if repeated.product else None)
            self.assertEqual(original.category.name, repeated.category.name)

    def test_classifier_uses_text_without_ground_truth(self) -> None:
        """Explainable keyword rules classify free text without receiving scenario labels."""
        examples = {
            "Product Defect": ("Faulty device", "The device stopped working and is defective."),
            "Delivery Delay": ("Late shipment", "The shipment is delayed and tracking has not updated."),
            "Refund": ("Refund pending", "My returned item refund is still pending."),
            "Payment Issue": ("Duplicate charge", "My card was charged twice."),
            "Account Issue": ("Sign in failure", "I cannot sign in after a password reset."),
            "Service Quality": ("Poor support", "The agent was rude during my customer service call."),
            "Wrong Item": ("Incorrect item", "The package contained the wrong item."),
            "Missing Item": ("Missing item", "One item is missing from the package."),
            "Safety Issue": ("Smoke from appliance", "The appliance sparked and produced smoke."),
            "Other": ("General question", "Please clarify the setup guide."),
        }
        for expected, (title, description) in examples.items():
            self.assertEqual(classify_complaint(title, description), expected)

    def test_priority_rule_and_customer_repeat_modifiers(self) -> None:
        """Matching PriorityRules set the baseline before vulnerability and repeat boosts."""
        category = Category(id="CAT-TEST-1", name="Service Quality", slug="service-quality")
        customer = Customer(
            id="CUS-TEST-1", first_name="Synthetic", last_name="Person",
            email="synthetic@example.invalid", tier="Standard", status="Active",
            is_vulnerable=True,
        )
        rule = PriorityRule(
            id="RUL-TEST-1", name="Service follow-up", category_id=category.id,
            target_priority="Low", sla_target_hours=24, is_active=True,
        )
        severity, priority, reason = _score_priority(
            category, customer, "Service follow-up", "Please review the support experience.", True, [rule]
        )
        self.assertEqual(severity, "Low")
        self.assertEqual(priority, "High")
        self.assertIn("PriorityRule RUL-TEST-1", reason)
        self.assertIn("vulnerable", reason)
        self.assertIn("repeat complaint", reason)

    def test_same_seed_and_inputs_produce_identical_results(self) -> None:
        """The same seed and ordered model inputs reproduce fields and lifecycle history."""
        customers = generate_customers("starter", seed=RANDOM_SEED)
        products = generate_products(seed=RANDOM_SEED)
        orders = generate_orders("starter", seed=RANDOM_SEED, customers=customers, products=products)
        first = generate_complaints(
            "starter", seed=RANDOM_SEED, customers=customers,
            products=products, orders=orders,
        )
        second = generate_complaints(
            "starter", seed=RANDOM_SEED, customers=customers,
            products=products, orders=orders,
        )
        self.assertEqual(_snapshot(first), _snapshot(second))

    def test_insert_and_retrieve_in_isolated_database(self) -> None:
        """Complaints, dependency models, and allowed history rows persist in memory SQLite."""
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        try:
            Base.metadata.create_all(engine)
            SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
            with SessionLocal() as session:
                session.add_all(self.starter_customers)
                session.add_all(self.products)
                session.add_all(self.starter_orders)
                session.add_all(self.starter)
                session.commit()
                self.assertEqual(session.scalar(select(func.count()).select_from(Complaint)), 20)
                retrieved = session.scalars(select(Complaint).order_by(Complaint.id)).all()
                self.assertEqual(len(retrieved), 20)
                self.assertEqual(retrieved[0].category.name, self.starter[0].category.name)
                self.assertEqual(retrieved[0].customer.id, self.starter[0].customer.id)
                self.assertGreater(
                    session.scalar(select(func.count()).select_from(Category)),
                    len(ISSUE_CATEGORIES),
                )
                self.assertEqual(
                    session.connection().exec_driver_sql("PRAGMA foreign_key_check").all(),
                    [],
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
