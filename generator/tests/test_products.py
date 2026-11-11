"""Focused tests for the synthetic product catalogue generator."""

import unittest
from decimal import Decimal

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

import backend.models  # Register the complete SQLAlchemy model graph.
from backend.models.base import Base
from backend.models.product import Product
from generator.config import RANDOM_SEED
from generator.products import PRODUCT_CATEGORIES, generate_products, validate_products


def _snapshot(products: list[Product]) -> list[tuple[object, ...]]:
    """Convert generated products and category names into comparable values."""
    return [
        (
            product.id,
            product.sku,
            product.name,
            product.description,
            product.category.name,
            product.unit_price,
            product.status,
            product.is_safety_related,
            product.created_at,
            product.updated_at,
        )
        for product in products
    ]


class ProductGeneratorTests(unittest.TestCase):
    """Check catalogue size, deterministic values, validation, and isolated persistence."""

    def test_fixed_catalogue_ids_categories_and_values(self) -> None:
        """The catalogue has 30 uniquely identified products across all requested families."""
        products = generate_products()
        validate_products(products)
        self.assertEqual(len(products), 30)
        self.assertEqual(products[0].id, "PRD-000001")
        self.assertEqual(products[-1].id, "PRD-000030")
        self.assertEqual(len({product.id for product in products}), 30)
        self.assertEqual(len({product.sku for product in products}), 30)
        self.assertEqual({product.category.name for product in products}, set(PRODUCT_CATEGORIES))
        self.assertTrue(all(product.name.strip() for product in products))
        self.assertTrue(all(product.unit_price > Decimal("0") for product in products))
        self.assertTrue(all(isinstance(product.is_safety_related, bool) for product in products))
        self.assertTrue(any(product.is_safety_related for product in products))

    def test_same_seed_produces_identical_catalogue(self) -> None:
        """The fixed seed produces identical product fields, prices, and timestamps."""
        first_run = generate_products(seed=RANDOM_SEED)
        second_run = generate_products(seed=RANDOM_SEED)
        self.assertEqual(_snapshot(first_run), _snapshot(second_run))

    def test_insert_and_retrieve_in_isolated_database(self) -> None:
        """Products and their linked category rows persist in in-memory SQLite."""
        products = generate_products(seed=RANDOM_SEED)
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        try:
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                session.add_all(products)
                session.commit()
                retrieved = session.scalars(select(Product).order_by(Product.id)).all()
                self.assertEqual(len(retrieved), 30)
                self.assertEqual(_snapshot(retrieved), _snapshot(products))
                self.assertEqual(
                    session.connection().exec_driver_sql("PRAGMA foreign_key_check").all(),
                    [],
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
