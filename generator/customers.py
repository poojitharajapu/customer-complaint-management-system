"""Deterministic synthetic customer generation for Starter and Full modes."""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

from backend.models.customer import Customer
from backend.models.id_generators import generate_customer_id
from generator.config import DATA_YEAR, FULL_MODE, RANDOM_SEED, STARTER_MODE


# These syllables form fictional names without using a list of real people.
_NAME_PARTS = (
    "Bel", "Caro", "Davi", "Eri", "Fena", "Gali", "Haro", "Iver",
    "Jori", "Kela", "Lumi", "Maro", "Neri", "Ovia", "Pavo", "Quin",
    "Ralo", "Sela", "Tavi", "Uli", "Vero", "Weni", "Xavi", "Yori", "Zela",
)
_COMPANY_ENDINGS = ("Works", "Labs", "Studio", "Collective", "Supply", "Group")


def _values_from_model_constraint(field_name: str) -> tuple[str, ...]:
    """Read the permitted values for a checked field from Customer's model."""
    for constraint in Customer.__table__.constraints:
        expression = str(getattr(constraint, "sqltext", ""))
        match = re.search(rf"\b{re.escape(field_name)}\s+IN\s*\(([^)]*)\)", expression, re.IGNORECASE)
        if match:
            values = tuple(re.findall(r"'((?:[^']|'')*)'", match.group(1)))
            if values:
                return tuple(value.replace("''", "'") for value in values)
    raise RuntimeError(f"No IN check constraint found for Customer.{field_name}.")


_TIERS = _values_from_model_constraint("tier")
_STATUSES = _values_from_model_constraint("status")
_CUSTOMER_FIELDS = {column.name: column for column in Customer.__table__.columns}


def customer_count_for_mode(mode: str) -> int:
    """Return the configured customer count for the named generation mode."""
    configurations = {"starter": STARTER_MODE, "full": FULL_MODE}
    try:
        return configurations[mode.strip().lower()]["customers"]
    except (AttributeError, KeyError) as error:
        raise ValueError("mode must be either 'starter' or 'full'") from error


def _fictional_name(rng: random.Random, syllables: int) -> str:
    """Build a pronounceable fictional name from seeded syllable choices."""
    parts = [rng.choice(_NAME_PARTS) for _ in range(syllables)]
    return parts[0] + "".join(part.lower() for part in parts[1:])


def _random_created_at(rng: random.Random) -> datetime:
    """Choose a reproducible UTC timestamp somewhere in the configured data year."""
    start = datetime(DATA_YEAR, 1, 1, tzinfo=timezone.utc)
    seconds_in_year = 365 * 24 * 60 * 60
    if DATA_YEAR % 4 == 0 and (DATA_YEAR % 100 != 0 or DATA_YEAR % 400 == 0):
        seconds_in_year += 24 * 60 * 60
    return start + timedelta(seconds=rng.randrange(seconds_in_year))


def validate_customer_records(records: Iterable[Customer]) -> None:
    """Check generated Customer objects against model columns and key constraints."""
    seen_ids: set[str] = set()
    seen_emails: set[str] = set()
    for index, customer in enumerate(records, start=1):
        if not isinstance(customer, Customer):
            raise ValueError(f"Record {index} is not a Customer model instance.")
        for field_name, column in _CUSTOMER_FIELDS.items():
            value = getattr(customer, field_name)
            if value is None:
                if not column.nullable and not column.primary_key:
                    raise ValueError(f"Customer {customer.id} is missing required field {field_name}.")
                continue
            if isinstance(value, str) and column.type.length and len(value) > column.type.length:
                raise ValueError(f"Customer {customer.id} field {field_name} exceeds {column.type.length} characters.")
        if customer.id != generate_customer_id(index):
            raise ValueError(f"Customer ID at position {index} is not deterministic/sequential.")
        if customer.id in seen_ids:
            raise ValueError(f"Duplicate customer ID: {customer.id}")
        if customer.email in seen_emails:
            raise ValueError(f"Duplicate customer email: {customer.email}")
        if not customer.email.endswith("@example.invalid"):
            raise ValueError(f"Customer email must use the reserved .invalid domain: {customer.email}")
        if customer.tier not in _TIERS or customer.status not in _STATUSES:
            raise ValueError(f"Customer {customer.id} has a tier or status outside model constraints.")
        if not isinstance(customer.is_vulnerable, bool):
            raise ValueError(f"Customer {customer.id} is_vulnerable must be boolean.")
        if customer.created_at is None or customer.created_at.tzinfo is None:
            raise ValueError(f"Customer {customer.id} must have a timezone-aware created_at timestamp.")
        if customer.updated_at is None or customer.updated_at.tzinfo is None:
            raise ValueError(f"Customer {customer.id} must have a timezone-aware updated_at timestamp.")
        seen_ids.add(customer.id)
        seen_emails.add(customer.email)


def generate_customers(mode: str = "starter", seed: int = RANDOM_SEED) -> list[Customer]:
    """Generate validated Customer ORM objects using configured mode size and seed."""
    count = customer_count_for_mode(mode)
    rng = random.Random(seed)
    customers: list[Customer] = []
    for sequence in range(1, count + 1):
        first_name = _fictional_name(rng, 2)
        last_name = _fictional_name(rng, 2 if rng.random() < 0.8 else 3)
        email = f"{first_name.lower()}.{last_name.lower()}.{sequence:06d}@example.invalid"
        # 555-01xx is reserved for fictional use; repeats are allowed by the schema.
        phone = f"+1-202-555-01{rng.randrange(100):02d}"
        company_name = None
        if rng.random() < 0.4:
            company_name = f"{_fictional_name(rng, 2)} {_COMPANY_ENDINGS[rng.randrange(len(_COMPANY_ENDINGS))]}"
        created_at = _random_created_at(rng)
        customers.append(
            Customer(
                id=generate_customer_id(sequence),
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                company_name=company_name,
                tier=rng.choice(_TIERS),
                status=rng.choice(_STATUSES),
                is_vulnerable=rng.random() < 0.08,
                created_at=created_at,
                updated_at=created_at,
            )
        )
    validate_customer_records(customers)
    return customers
