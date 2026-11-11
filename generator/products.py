"""Generate a reproducible 30-item synthetic product catalogue."""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from backend.models.category import Category
from backend.models.id_generators import generate_category_id, generate_product_id
from backend.models.product import Product
from generator.config import DATA_YEAR, RANDOM_SEED


PRODUCT_COUNT = 30
PRODUCT_CATEGORIES = (
    "Electronics",
    "Home Appliances",
    "Accessories",
    "Furniture",
    "Personal Care",
)
_CATEGORY_DESCRIPTIONS = {
    "Electronics": "Synthetic consumer electronics product family.",
    "Home Appliances": "Synthetic household appliance product family.",
    "Accessories": "Synthetic everyday accessory product family.",
    "Furniture": "Synthetic home and office furniture product family.",
    "Personal Care": "Synthetic personal care product family.",
}
_PRODUCT_SPECS = (
    ("Wireless Router", "Electronics", "Dual-band network router for home connectivity.", "129.00", False),
    ("Portable Power Bank", "Electronics", "Rechargeable portable battery pack with charge indicators.", "39.00", False),
    ("Compact Air Purifier", "Electronics", "Small-room air purifier with replaceable filter.", "89.00", False),
    ("Smart Plug Adapter", "Electronics", "Wi-Fi enabled plug adapter for remote power control.", "24.00", True),
    ("LED Desk Lamp", "Electronics", "Dimmable LED desk lamp with an adjustable arm.", "34.00", False),
    ("Bluetooth Speaker", "Electronics", "Portable wireless speaker with rechargeable battery.", "59.00", False),
    ("Electric Kettle", "Home Appliances", "Rapid-boil kettle with automatic shutoff and dry-boil protection.", "44.00", True),
    ("Countertop Toaster", "Home Appliances", "Two-slot toaster with adjustable browning controls.", "36.00", True),
    ("Compact Space Heater", "Home Appliances", "Portable heater with tip-over and overheat shutoff safeguards.", "74.00", True),
    ("Tabletop Fan", "Home Appliances", "Three-speed fan with a guarded blade assembly.", "29.00", True),
    ("Humidifier", "Home Appliances", "Cool-mist humidifier with automatic low-water shutoff.", "49.00", True),
    ("Cordless Hand Mixer", "Home Appliances", "Rechargeable hand mixer with detachable beaters.", "54.00", True),
    ("USB-C Charging Cable", "Accessories", "Braided one-metre charging and data cable.", "12.00", False),
    ("Laptop Sleeve", "Accessories", "Padded sleeve sized for a compact laptop.", "27.00", False),
    ("Reusable Water Bottle", "Accessories", "Insulated stainless-steel bottle with a screw cap.", "22.00", False),
    ("Travel Power Strip", "Accessories", "Compact multi-outlet strip with overload protection.", "31.00", True),
    ("Protective Phone Case", "Accessories", "Shock-absorbing case for a standard-size phone.", "19.00", False),
    ("Adjustable Monitor Stand", "Accessories", "Desktop stand with adjustable height and cable clearance.", "42.00", False),
    ("Ergonomic Office Chair", "Furniture", "Adjustable task chair with a five-point base and locking casters.", "249.00", False),
    ("Compact Bookshelf", "Furniture", "Four-tier bookcase with a wall-anchor safety fitting.", "119.00", True),
    ("Folding Step Stool", "Furniture", "Foldable household step stool with a non-slip standing surface.", "38.00", True),
    ("Writing Desk", "Furniture", "Simple home-office desk with a stable steel frame.", "179.00", False),
    ("Bedside Table", "Furniture", "Small bedside table with a single storage drawer.", "69.00", False),
    ("Dining Chair", "Furniture", "Stackable dining chair with a reinforced frame.", "58.00", False),
    ("Electric Toothbrush", "Personal Care", "Rechargeable toothbrush with a sealed charging base.", "47.00", True),
    ("Hair Dryer", "Personal Care", "Compact hair dryer with thermal cutoff protection.", "52.00", True),
    ("Water Flosser", "Personal Care", "Countertop oral irrigator with a pressure control dial.", "64.00", True),
    ("Electric Shaver", "Personal Care", "Rechargeable wet-and-dry shaver with a protective cap.", "78.00", True),
    ("Heating Pad", "Personal Care", "Adjustable warming pad with automatic timed shutoff.", "41.00", True),
    ("Digital Bathroom Scale", "Personal Care", "Battery-powered digital scale with a tempered glass platform.", "33.00", True),
)
def _values_from_model_constraint(field_name: str) -> tuple[str, ...]:
    """Read allowed values for a checked Product field from the SQLAlchemy model."""
    for constraint in Product.__table__.constraints:
        expression = str(getattr(constraint, "sqltext", ""))
        match = re.search(rf"\b{re.escape(field_name)}\s+IN\s*\(([^)]*)\)", expression, re.IGNORECASE)
        if match:
            values = tuple(re.findall(r"'((?:[^']|'')*)'", match.group(1)))
            if values:
                return tuple(value.replace("''", "'") for value in values)
    raise RuntimeError(f"No IN check constraint found for Product.{field_name}.")


_STATUSES = _values_from_model_constraint("status")


def _create_categories() -> dict[str, Category]:
    """Build the five model-backed product categories referenced by the catalogue."""
    return {
        name: Category(
            id=generate_category_id(index),
            name=name,
            slug=name.lower().replace(" ", "-"),
            description=_CATEGORY_DESCRIPTIONS[name],
            default_priority="Medium",
            is_active=True,
        )
        for index, name in enumerate(PRODUCT_CATEGORIES, start=1)
    }


def _random_created_at(rng: random.Random) -> datetime:
    """Return a reproducible UTC timestamp within the configured data year."""
    start = datetime(DATA_YEAR, 1, 1, tzinfo=timezone.utc)
    seconds_in_year = 365 * 24 * 60 * 60
    if DATA_YEAR % 4 == 0 and (DATA_YEAR % 100 != 0 or DATA_YEAR % 400 == 0):
        seconds_in_year += 24 * 60 * 60
    return start + timedelta(seconds=rng.randrange(seconds_in_year))


def validate_products(products: Iterable[Product]) -> None:
    """Validate catalogue identity, names, prices, categories, statuses, and safety flags."""
    seen_ids: set[str] = set()
    seen_skus: set[str] = set()
    for index, product in enumerate(products, start=1):
        if not isinstance(product, Product):
            raise ValueError(f"Record {index} is not a Product model instance.")
        if product.id != generate_product_id(index) or product.id in seen_ids:
            raise ValueError(f"Product ID at position {index} is missing, invalid, or duplicated.")
        if not isinstance(product.name, str) or not product.name.strip() or len(product.name) > 150:
            raise ValueError(f"Product {product.id} must have a valid name of at most 150 characters.")
        if not isinstance(product.sku, str) or not product.sku.strip() or len(product.sku) > 50:
            raise ValueError(f"Product {product.id} must have a valid SKU of at most 50 characters.")
        if product.sku in seen_skus:
            raise ValueError(f"Duplicate product SKU: {product.sku}")
        if not isinstance(product.unit_price, Decimal) or not product.unit_price.is_finite() or product.unit_price <= 0:
            raise ValueError(f"Product {product.id} must have a positive finite price.")
        if product.unit_price.as_tuple().exponent < -2 or product.unit_price >= Decimal("100000000"):
            raise ValueError(f"Product {product.id} price does not fit Numeric(10, 2).")
        category = product.category
        if category is None or category.name not in PRODUCT_CATEGORIES:
            raise ValueError(f"Product {product.id} has an invalid product category.")
        if product.status not in _STATUSES:
            raise ValueError(f"Product {product.id} has a status outside model constraints.")
        if not isinstance(getattr(product, "is_safety_related", None), bool):
            raise ValueError(f"Product {product.id} safety flag must be boolean.")
        if product.created_at is None or product.created_at.tzinfo is None:
            raise ValueError(f"Product {product.id} must have a timezone-aware created_at timestamp.")
        seen_ids.add(product.id)
        seen_skus.add(product.sku)


def generate_products(seed: int = RANDOM_SEED) -> list[Product]:
    """Generate, validate, and return the fixed 30-product synthetic catalogue."""
    rng = random.Random(seed)
    categories = _create_categories()
    specs = list(_PRODUCT_SPECS)
    rng.shuffle(specs)
    products: list[Product] = []
    for sequence, (name, category_name, description, base_price, safety_related) in enumerate(specs, start=1):
        price_adjustment = Decimal(rng.randint(-300, 300)) / Decimal("100")
        unit_price = (Decimal(base_price) + price_adjustment).quantize(Decimal("0.01"))
        status = rng.choices(_STATUSES, weights=(0.82, 0.08, 0.10), k=1)[0]
        created_at = _random_created_at(rng)
        details = description
        if safety_related:
            details += " Safety-related product; reports may concern overheating, electrical, burn, or stability hazards."
        product = Product(
            id=generate_product_id(sequence),
            sku=f"SYN-PRD-{sequence:06d}",
            name=name,
            description=details,
            category=categories[category_name],
            unit_price=unit_price,
            status=status,
            created_at=created_at,
            updated_at=created_at,
        )
        # The existing schema has no safety flag column, so this remains in-memory metadata.
        product.is_safety_related = safety_related
        products.append(product)
    validate_products(products)
    return products
