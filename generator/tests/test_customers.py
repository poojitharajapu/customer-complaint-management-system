"""Tests for the deterministic synthetic Customer generator."""

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import backend.models  # Register all relationships before creating mapped tables.
from backend.models.base import Base
from backend.models.customer import Customer
from generator.config import RANDOM_SEED
from generator.customers import (
    customer_count_for_mode,
    generate_customers,
    validate_customer_records,
)


def _snapshot(customers: list[Customer]) -> list[tuple[object, ...]]:
    """Convert generated ORM objects to comparable field tuples."""
    return [
        (
            customer.id,
            customer.first_name,
            customer.last_name,
            customer.email,
            customer.phone,
            customer.company_name,
            customer.tier,
            customer.status,
            customer.is_vulnerable,
            customer.created_at,
            customer.updated_at,
        )
        for customer in customers
    ]


class CustomerGeneratorTests(unittest.TestCase):
    """Exercise mode sizes, deterministic output, constraints, and isolated persistence."""

    def test_configured_mode_sizes_and_ids(self) -> None:
        """Starter and Full modes use their shared configured counts and sequential IDs."""
        starter = generate_customers("starter")
        full = generate_customers("full")
        self.assertEqual(customer_count_for_mode("starter"), 50)
        self.assertEqual(customer_count_for_mode("full"), 5_000)
        self.assertEqual(len(starter), 50)
        self.assertEqual(len(full), 5_000)
        self.assertEqual(starter[0].id, "CUS-000001")
        self.assertEqual(starter[-1].id, "CUS-000050")
        self.assertEqual(full[-1].id, "CUS-005000")

    def test_same_seed_produces_identical_customers(self) -> None:
        """The configured seed reproduces every generated field and timestamp."""
        first_run = generate_customers("starter", seed=RANDOM_SEED)
        second_run = generate_customers("starter", seed=RANDOM_SEED)
        self.assertEqual(_snapshot(first_run), _snapshot(second_run))

    def test_records_validate_and_use_synthetic_contact_details(self) -> None:
        """Generated values are unique where required and stay in synthetic namespaces."""
        customers = generate_customers("starter", seed=RANDOM_SEED)
        validate_customer_records(customers)
        self.assertEqual(len({customer.email for customer in customers}), 50)
        self.assertTrue(all(customer.email.endswith("@example.invalid") for customer in customers))
        self.assertTrue(all("+1-202-555-01" in customer.phone for customer in customers))
        self.assertTrue(all(customer.created_at.year == 2026 for customer in customers))

    def test_insert_and_retrieve_in_isolated_database(self) -> None:
        """Generated Customer instances persist and read back in an in-memory SQLite DB."""
        customers = generate_customers("starter", seed=RANDOM_SEED)
        engine = create_engine("sqlite:///:memory:")
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                session.add_all(customers)
                session.commit()
                retrieved = session.scalars(
                    select(Customer).order_by(Customer.id)
                ).all()
                self.assertEqual(_snapshot(retrieved), _snapshot(customers))
        finally:
            engine.dispose()

    def test_invalid_mode_is_rejected(self) -> None:
        """Unsupported mode names fail with a clear validation error."""
        with self.assertRaises(ValueError):
            generate_customers("unknown")


if __name__ == "__main__":
    unittest.main()
