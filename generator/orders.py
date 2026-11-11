"""Generate deterministic synthetic orders and their model-backed line items."""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Sequence

from backend.models.customer import Customer
from backend.models.id_generators import generate_order_id
from backend.models.order import Order, OrderItem
from backend.models.product import Product
from generator.config import DATA_YEAR, FULL_MODE, RANDOM_SEED, STARTER_MODE
from generator.customers import generate_customers
from generator.products import PRODUCT_COUNT, generate_products


PAYMENT_STATUSES = ("Pending", "Paid", "Failed", "Refunded")
DELIVERY_STATUSES = ("Pending", "Processing", "Shipped", "Delivered", "Returned", "Cancelled")


def _values_from_model_constraint(field_name: str) -> tuple[str, ...]:
    """Read permitted values for a checked Order field from its SQLAlchemy model."""
    for constraint in Order.__table__.constraints:
        expression = str(getattr(constraint, "sqltext", ""))
        match = re.search(rf"\b{re.escape(field_name)}\s+IN\s*\(([^)]*)\)", expression, re.IGNORECASE)
        if match:
            values = tuple(re.findall(r"'((?:[^']|'')*)'", match.group(1)))
            if values:
                return tuple(value.replace("''", "'") for value in values)
    raise RuntimeError(f"No IN check constraint found for Order.{field_name}.")


_ORDER_STATUSES = _values_from_model_constraint("order_status")


def order_count_for_mode(mode: str) -> int:
    """Return the configured number of orders for Starter or Full mode."""
    configurations = {"starter": STARTER_MODE, "full": FULL_MODE}
    try:
        return configurations[mode.strip().lower()]["orders"]
    except (AttributeError, KeyError) as error:
        raise ValueError("mode must be either 'starter' or 'full'") from error


def _random_order_date(rng: random.Random) -> datetime:
    """Choose a reproducible timezone-aware order date within DATA_YEAR."""
    start = datetime(DATA_YEAR, 1, 1, tzinfo=timezone.utc)
    seconds_in_year = 365 * 24 * 60 * 60
    if DATA_YEAR % 4 == 0 and (DATA_YEAR % 100 != 0 or DATA_YEAR % 400 == 0):
        seconds_in_year += 24 * 60 * 60
    return start + timedelta(seconds=rng.randrange(seconds_in_year))


def _statuses_for_order(order_status: str, rng: random.Random) -> tuple[str, str]:
    """Choose plausible transient payment and delivery states for an order state."""
    if order_status == "Pending":
        return "Pending", "Pending"
    if order_status == "Processing":
        return "Paid", "Processing"
    if order_status == "Completed":
        return "Paid", "Delivered"
    if order_status == "Cancelled":
        return rng.choice(("Pending", "Failed", "Refunded")), "Cancelled"
    return "Refunded", "Returned"


def _validate_inputs(customers: Sequence[Customer], products: Sequence[Product], mode: str) -> None:
    """Ensure the mode has the expected unique customers and products to reference."""
    expected_customers = {"starter": STARTER_MODE["customers"], "full": FULL_MODE["customers"]}[mode]
    if len(customers) != expected_customers:
        raise ValueError(f"{mode.title()} mode requires exactly {expected_customers} customers.")
    if len(products) != PRODUCT_COUNT:
        raise ValueError(f"Order generation requires exactly {PRODUCT_COUNT} products.")
    if len(products) != len({product.id for product in products}) or not products:
        raise ValueError("Product inputs must have unique IDs and contain at least one product.")
    if len(customers) != len({customer.id for customer in customers}):
        raise ValueError("Customer inputs must have unique IDs.")
    if not all(isinstance(customer, Customer) and customer.id for customer in customers):
        raise ValueError("Every customer input must be a persisted-model Customer with an ID.")
    if not all(isinstance(product, Product) and product.id for product in products):
        raise ValueError("Every product input must be a Product model with an ID.")
    for product in products:
        price = product.unit_price
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            raise ValueError(f"Product {product.id} must have a positive finite unit price.")


def validate_orders(orders: Iterable[Order]) -> None:
    """Validate IDs, references, item values, transient states, dates, and computed totals."""
    seen_ids: set[str] = set()
    for index, order in enumerate(orders, start=1):
        if not isinstance(order, Order):
            raise ValueError(f"Record {index} is not an Order model instance.")
        expected_id = generate_order_id(index, year=DATA_YEAR)
        if order.id != expected_id or order.id in seen_ids:
            raise ValueError(f"Order ID at position {index} is invalid, non-sequential, or duplicated.")
        if order.customer is None or not order.customer.id:
            raise ValueError(f"Order {order.id} must reference a customer.")
        if order.order_status not in _ORDER_STATUSES:
            raise ValueError(f"Order {order.id} has a status outside model constraints.")
        payment_status = getattr(order, "payment_status", None)
        delivery_status = getattr(order, "delivery_status", None)
        if payment_status not in PAYMENT_STATUSES:
            raise ValueError(f"Order {order.id} has an invalid payment status.")
        if delivery_status not in DELIVERY_STATUSES:
            raise ValueError(f"Order {order.id} has an invalid delivery status.")
        if order.order_date is None or order.order_date.tzinfo is None:
            raise ValueError(f"Order {order.id} must have a timezone-aware order date.")
        if not order.items:
            raise ValueError(f"Order {order.id} must contain at least one item.")

        item_products: set[str] = set()
        calculated_total = Decimal("0.00")
        for item in order.items:
            if item.order is not order or item.product is None or not item.product.id:
                raise ValueError(f"Order {order.id} contains an item with an invalid relationship.")
            if isinstance(item.quantity, bool) or not isinstance(item.quantity, int) or item.quantity <= 0:
                raise ValueError(f"Order {order.id} has a non-positive or non-integer quantity.")
            if not isinstance(item.unit_price, Decimal) or not item.unit_price.is_finite() or item.unit_price <= 0:
                raise ValueError(f"Order {order.id} has an item with a non-positive unit price.")
            if item.unit_price != item.product.unit_price:
                raise ValueError(f"Order {order.id} line price does not match the referenced product.")
            expected_item_total = (item.unit_price * item.quantity).quantize(Decimal("0.01"))
            if item.total_price != expected_item_total:
                raise ValueError(f"Order {order.id} has an incorrect line total.")
            if item.product.id in item_products:
                raise ValueError(f"Order {order.id} contains the same product more than once.")
            item_products.add(item.product.id)
            calculated_total += item.total_price
        if not isinstance(order.total_amount, Decimal) or order.total_amount != calculated_total:
            raise ValueError(f"Order {order.id} total does not equal the sum of its order items.")
        seen_ids.add(order.id)


def generate_orders(
    mode: str = "starter",
    seed: int = RANDOM_SEED,
    customers: Sequence[Customer] | None = None,
    products: Sequence[Product] | None = None,
) -> list[Order]:
    """Generate the configured orders, reusing supplied or seeded customer/product models."""
    normalized_mode = mode.strip().lower()
    count = order_count_for_mode(normalized_mode)
    if customers is None:
        customers = generate_customers(normalized_mode, seed=seed)
    if products is None:
        products = generate_products(seed=seed)
    _validate_inputs(customers, products, normalized_mode)

    rng = random.Random(seed)
    orders: list[Order] = []
    for sequence in range(1, count + 1):
        customer = customers[sequence - 1] if sequence <= len(customers) else rng.choice(customers)
        order_status = rng.choice(_ORDER_STATUSES)
        payment_status, delivery_status = _statuses_for_order(order_status, rng)
        order_date = max(_random_order_date(rng), customer.created_at)

        # Rotate the first line across the catalogue so every product is referenced.
        first_product = products[(sequence - 1) % len(products)]
        remaining_products = [product for product in products if product.id != first_product.id]
        line_count = min(rng.randint(1, 4), len(products))
        selected_products = [first_product]
        if line_count > 1:
            selected_products.extend(rng.sample(remaining_products, k=line_count - 1))

        items: list[OrderItem] = []
        for product in selected_products:
            quantity = rng.randint(1, 5)
            unit_price = product.unit_price.quantize(Decimal("0.01"))
            total_price = (unit_price * quantity).quantize(Decimal("0.01"))
            items.append(
                OrderItem(
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                )
            )
        total_amount = sum((item.total_price for item in items), start=Decimal("0.00"))
        order = Order(
            id=generate_order_id(sequence, year=DATA_YEAR),
            customer=customer,
            order_date=order_date,
            order_status=order_status,
            total_amount=total_amount,
            items=items,
            created_at=order_date,
            updated_at=order_date,
        )
        # These states are metadata only; Order has no corresponding database columns.
        order.payment_status = payment_status
        order.delivery_status = delivery_status
        orders.append(order)

    validate_orders(orders)
    return orders
