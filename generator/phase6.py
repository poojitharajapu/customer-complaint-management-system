"""Build the complete Phase 6 dataset graph in memory without database writes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.models.agent import Agent
from backend.models.assignment import Assignment
from backend.models.category import Category
from backend.models.complaint import Complaint
from backend.models.complaint_message import ComplaintMessage
from backend.models.customer import Customer
from backend.models.order import Order
from backend.models.priority_rule import PriorityRule
from backend.models.product import Product
from backend.models.sla import SLAClock, SLAEvent
from generator.agents import generate_agents
from generator.assignments import generate_assignments
from generator.complaints import generate_complaints
from generator.config import DATA_YEAR, RANDOM_SEED
from backend.models.id_generators import generate_category_id, generate_priority_rule_id
from generator.customers import generate_customers
from generator.messages import generate_messages
from generator.orders import generate_orders
from generator.products import generate_products
from generator.sla_events import generate_sla_events
from generator.slas import generate_slas


@dataclass
class Phase6Dataset:
    """Hold generated records together, including non-persisted classification metadata."""

    customers: list[Customer]
    products: list[Product]
    categories: list[Category]
    priority_rules: list[PriorityRule]
    orders: list[Order]
    complaints: list[Complaint]
    agents: list[Agent]
    assignments: list[Assignment]
    messages: list[ComplaintMessage]
    sla_clocks: list[SLAClock]
    sla_events: list[SLAEvent]


_DEFAULT_RULE_PRIORITIES = {
    "Product Defect": "High", "Delivery Delay": "Medium", "Refund": "High",
    "Payment Issue": "High", "Account Issue": "Medium", "Service Quality": "Medium",
    "Wrong Item": "High", "Missing Item": "High", "Safety Issue": "Critical", "Other": "Low",
}
_PRIORITY_SLA_HOURS = {"Critical": 4, "High": 8, "Medium": 24, "Low": 72}


def _complaint_categories_and_rules(products: list[Product]) -> tuple[list[Category], list[PriorityRule]]:
    """Create deterministic issue categories and model-backed priority rules."""
    timestamp = datetime(DATA_YEAR, 1, 1, tzinfo=timezone.utc)
    categories = {product.category.id: product.category for product in products if product.category is not None}
    max_id = max((int(category.id.removeprefix("CAT-")) for category in categories.values()), default=0)
    for offset, (name, priority) in enumerate(_DEFAULT_RULE_PRIORITIES.items(), start=1):
        category = Category(
            id=generate_category_id(max_id + offset), name=name,
            slug=name.lower().replace(" ", "-"),
            description=f"Complaint classification category: {name}.",
            default_priority=priority, is_active=True,
            created_at=timestamp, updated_at=timestamp,
        )
        categories[category.id] = category
    issue_categories = sorted(
        (category for category in categories.values() if category.name in _DEFAULT_RULE_PRIORITIES),
        key=lambda category: category.id,
    )
    rules = []
    for sequence, category in enumerate(issue_categories, start=1):
        priority = _DEFAULT_RULE_PRIORITIES[category.name]
        rule = PriorityRule(
            id=generate_priority_rule_id(sequence),
            name=f"Default {category.name} priority",
            category=category,
            target_priority=priority,
            sla_target_hours=Decimal(_PRIORITY_SLA_HOURS[priority]),
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
        rules.append(rule)
    return list(categories.values()), rules


def generate_phase6_dataset(mode: str = "starter", seed: int = RANDOM_SEED) -> Phase6Dataset:
    """Generate customer-through-SLA records in dependency order, without persistence."""
    customers = generate_customers(mode, seed=seed)
    products = generate_products(seed=seed)
    # Product generation predates the Phase 6 pipeline and its Category timestamps
    # use model defaults; normalize those shared rows for whole-dataset repeatability.
    category_timestamp = datetime(DATA_YEAR, 1, 1, tzinfo=timezone.utc)
    for product in products:
        if product.category is not None:
            product.category.created_at = category_timestamp
            product.category.updated_at = category_timestamp
    categories, priority_rules = _complaint_categories_and_rules(products)
    orders = generate_orders(mode, seed=seed, customers=customers, products=products)
    complaints = generate_complaints(
        mode, seed=seed, customers=customers, products=products, orders=orders,
        categories=categories, priority_rules=priority_rules,
    )
    agents = generate_agents(mode, seed=seed)
    assignments = generate_assignments(complaints, agents, seed=seed)
    messages = generate_messages(complaints, agents, assignments, seed=seed)
    sla_clocks = generate_slas(complaints)
    sla_events = generate_sla_events(sla_clocks, seed=seed)
    return Phase6Dataset(
        customers=customers,
        products=products,
        categories=categories,
        priority_rules=priority_rules,
        orders=orders,
        complaints=complaints,
        agents=agents,
        assignments=assignments,
        messages=messages,
        sla_clocks=sla_clocks,
        sla_events=sla_events,
    )


def main() -> int:
    """Run the complete Phase 6 pipeline in memory and print record counts."""
    parser = argparse.ArgumentParser(description="Generate the Phase 6 operations dataset in memory.")
    parser.add_argument("--mode", choices=("starter", "full"), default="starter")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    dataset = generate_phase6_dataset(mode=args.mode, seed=args.seed)
    print(f"Generated Phase 6 {args.mode.title()} dataset (seed={args.seed}):")
    for name in (
        "customers", "products", "orders", "complaints", "agents",
        "assignments", "messages", "sla_clocks", "sla_events",
    ):
        print(f"  {name}: {len(getattr(dataset, name))}")
    print("Records remain in memory; no database writes were performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
