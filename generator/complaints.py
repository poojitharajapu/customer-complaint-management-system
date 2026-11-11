"""Generate, classify, and score reproducible synthetic complaints."""

from __future__ import annotations

import argparse
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from backend.models.category import Category
from backend.models.complaint import Complaint, ComplaintReopenHistory, ComplaintStatusHistory
from backend.models.customer import Customer
from backend.models.id_generators import generate_category_id, generate_complaint_id
from backend.models.order import Order
from backend.models.priority_rule import PriorityRule
from backend.models.product import Product
from generator.config import DATA_YEAR, FULL_MODE, PRIORITIES, RANDOM_SEED, STARTER_MODE
from generator.customers import generate_customers
from generator.orders import generate_orders
from generator.products import PRODUCT_COUNT, generate_products


ISSUE_CATEGORIES = (
    "Product Defect",
    "Delivery Delay",
    "Refund",
    "Payment Issue",
    "Account Issue",
    "Service Quality",
    "Wrong Item",
    "Missing Item",
    "Safety Issue",
    "Other",
)
COMPLAINT_CHANNELS = ("Web", "Email", "Phone", "Chat", "Mobile")
COMPLAINT_STATUSES = (
    "New",
    "In Progress",
    "Pending Customer",
    "Pending Vendor",
    "Resolved",
    "Closed",
    "Reopened",
)
SEVERITY_LEVELS = tuple(PRIORITIES)
_PRIORITY_RANK = {priority: rank for rank, priority in enumerate(reversed(PRIORITIES))}
_PRIORITY_BY_RANK = {rank: priority for priority, rank in _PRIORITY_RANK.items()}
_BASE_PRIORITY = {
    "Product Defect": "High",
    "Delivery Delay": "Medium",
    "Refund": "High",
    "Payment Issue": "High",
    "Account Issue": "Medium",
    "Service Quality": "Medium",
    "Wrong Item": "High",
    "Missing Item": "High",
    "Safety Issue": "Critical",
    "Other": "Low",
}
_SEVERITY = {
    "Product Defect": "High",
    "Delivery Delay": "Medium",
    "Refund": "Medium",
    "Payment Issue": "High",
    "Account Issue": "Medium",
    "Service Quality": "Low",
    "Wrong Item": "Medium",
    "Missing Item": "High",
    "Safety Issue": "Critical",
    "Other": "Low",
}
_CHANNELS = tuple(COMPLAINT_CHANNELS)
_YEAR_START = datetime(DATA_YEAR, 1, 1, tzinfo=timezone.utc)
_YEAR_END = datetime(DATA_YEAR, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
_REPEAT_CUTOFF = datetime(DATA_YEAR, 11, 1, tzinfo=timezone.utc)
_SAFETY_TERMS = (
    "smoke", "smoking", "spark", "sparking", "sparks", "burn", "burning",
    "overheat", "overheating", "electric shock", "shock hazard", "caught fire",
    "fire hazard", "tip-over", "tipped over", "unsafe", "safety concern", "injury",
)
_CLASSIFICATION_RULES = (
    ("Safety Issue", ("smoke", "smoking", "spark", "sparking", "sparks", "burn", "burning", "overheat", "overheating", "electric shock", "shock hazard", "caught fire", "fire hazard", "tip-over", "tipped over", "unsafe", "safety concern", "injury")),
    ("Payment Issue", ("charged twice", "duplicate charge", "payment declined", "card was charged", "charged but", "billing error", "payment issue")),
    ("Refund", ("refund", "money back", "reimbursement", "returned the item")),
    ("Wrong Item", ("wrong item", "incorrect item", "different item", "sent the wrong")),
    ("Missing Item", ("missing item", "item is missing", "not in the package", "package was empty", "part of my order is missing")),
    ("Delivery Delay", ("delivery is late", "delivery was late", "shipment is delayed", "tracking has not", "order has not arrived", "package has not arrived", "never arrived", "delivery delay")),
    ("Account Issue", ("cannot sign in", "can't sign in", "cannot log in", "can't log in", "locked out", "password reset", "account access", "account is locked")),
    ("Service Quality", ("support experience", "agent was rude", "poor service", "customer service", "no one responded", "unhelpful support")),
    ("Product Defect", ("stopped working", "does not work", "doesn't work", "not working", "defective", "faulty", "malfunction", "cracked", "broken", "leaking", "arrived damaged")),
)
_SCENARIO_TEXT = {
    "Product Defect": (
        ("Product stopped working", "The {product} arrived damaged and stopped working after the first use. The controls no longer respond."),
        ("Defective product", "The {product} is faulty. It worked briefly, then failed during normal use."),
    ),
    "Delivery Delay": (
        ("Delivery has not arrived", "My order has not arrived and tracking has not updated for several days. Please check the delivery."),
        ("Shipment is delayed", "The shipment is delayed beyond the estimated date and the carrier has provided no new update."),
    ),
    "Refund": (
        ("Refund still pending", "I returned the {product}, but the refund is still pending and has not appeared on my payment method."),
        ("Request for money back", "The return was accepted, but I have not received my money back. Please review the reimbursement."),
    ),
    "Payment Issue": (
        ("Duplicate payment charge", "My card was charged twice for this purchase. Please investigate the duplicate charge."),
        ("Payment was declined", "The payment was declined even though the amount was taken from my account. Please review the billing error."),
    ),
    "Account Issue": (
        ("Unable to access account", "I cannot sign in to my account after resetting the password and need help restoring account access."),
        ("Account locked", "I am locked out of my account and the password reset link does not work."),
    ),
    "Service Quality": (
        ("Poor support experience", "The support experience was unhelpful and I have not received a response to my earlier request."),
        ("Customer service concern", "The agent was rude and did not explain what would happen next. Please review the service."),
    ),
    "Wrong Item": (
        ("Wrong item received", "The package contained the wrong item instead of the {product} I selected."),
        ("Incorrect product in package", "A different item was sent. Please arrange the correct product to be delivered."),
    ),
    "Missing Item": (
        ("Item missing from package", "One item is missing from the package even though the order summary lists it."),
        ("Package contents incomplete", "The package was not empty, but the {product} listed on my order was not in the package."),
    ),
    "Safety Issue": (
        ("Product sparked during use", "The {product} sparked during normal use and produced smoke. I unplugged it because of the fire hazard."),
        ("Possible burn hazard", "The {product} overheated and became hot enough to cause a burn. I stopped using it immediately."),
    ),
    "Other": (
        ("Product information request", "I need clarification about the setup guide and the product features. The guide does not answer my question."),
        ("General order question", "Please explain the information shown on my account page. I need help understanding the service details."),
    ),
}


@dataclass(frozen=True)
class _Scenario:
    """Keep authored scenario labels separate from classifier input fields."""

    expected_category: str
    title: str
    description: str


def complaint_count_for_mode(mode: str) -> int:
    """Return the complaint count from the shared Starter or Full configuration."""
    configurations = {"starter": STARTER_MODE, "full": FULL_MODE}
    try:
        return configurations[mode.strip().lower()]["complaints"]
    except (AttributeError, KeyError) as error:
        raise ValueError("mode must be either 'starter' or 'full'") from error


def _category_objects(products: Sequence[Product], supplied: Sequence[Category] | None) -> dict[str, Category]:
    """Reuse matching Category models and create any missing classification categories."""
    candidates: list[Category] = list(supplied or ())
    candidates.extend(product.category for product in products if product.category is not None)
    by_name: dict[str, Category] = {}
    used_ids: set[str] = set()
    max_id = 0
    for category in candidates:
        if category.id in used_ids and category.name not in by_name:
            raise ValueError(f"Duplicate category ID in supplied category models: {category.id}")
        used_ids.add(category.id)
        match = re.fullmatch(r"CAT-(\d+)", category.id or "")
        if match:
            max_id = max(max_id, int(match.group(1)))
        if category.name in by_name and by_name[category.name].id != category.id:
            raise ValueError(f"Category name {category.name!r} has multiple IDs.")
        by_name[category.name] = category

    next_id = max_id + 1
    for name in ISSUE_CATEGORIES:
        if name in by_name:
            continue
        while generate_category_id(next_id) in used_ids:
            next_id += 1
        category = Category(
            id=generate_category_id(next_id),
            name=name,
            slug=name.lower().replace(" ", "-"),
            description=f"Complaint classification category: {name}.",
            default_priority=_BASE_PRIORITY[name],
            is_active=True,
            created_at=_YEAR_START,
            updated_at=_YEAR_START,
        )
        by_name[name] = category
        used_ids.add(category.id)
        next_id += 1
    return {name: by_name[name] for name in ISSUE_CATEGORIES}


def classify_complaint(
    title: str,
    description: str,
    *,
    order_status: str | None = None,
    product_description: str | None = None,
) -> str:
    """Classify input text using ordered keyword rules and limited structured context."""
    text = f"{title} {description}".casefold()
    product_text = (product_description or "").casefold()
    for category, keywords in _CLASSIFICATION_RULES:
        if any(keyword in text for keyword in keywords):
            return category
    if order_status == "Refunded" or "refund" in product_text:
        return "Refund"
    return "Other"


def detect_repeat_complaint(
    customer: Customer,
    product: Product | None,
    category: Category,
    earlier_complaints: Iterable[Complaint],
) -> Complaint | None:
    """Find the earliest non-repeat complaint for the same customer, product, and category."""
    product_id = product.id if product is not None else None
    matches = [
        complaint
        for complaint in earlier_complaints
        if not getattr(complaint, "repeat_of_id", None)
        and complaint.customer is not None
        and complaint.customer.id == customer.id
        and (complaint.product.id if complaint.product is not None else None) == product_id
        and complaint.category is not None
        and complaint.category.name == category.name
    ]
    return min(matches, key=lambda complaint: _as_utc(complaint.created_at)) if matches else None


def _scenario_for(
    expected_category: str,
    customer: Customer,
    product: Product,
    rng: random.Random,
) -> _Scenario:
    """Create synthetic customer wording while keeping its expected label separate."""
    title, description = rng.choice(_SCENARIO_TEXT[expected_category])
    return _Scenario(
        expected_category=expected_category,
        title=title,
        description=description.format(product=product.name),
    )


def _complaint_date(order: Order | None, rng: random.Random, after: datetime | None = None) -> datetime:
    """Choose a date after its order and optional earlier complaint, bounded to DATA_YEAR."""
    if order is not None:
        earliest = _as_utc(order.order_date)
    elif after is not None:
        earliest = _as_utc(after) + timedelta(hours=1)
    else:
        year_seconds = int((_YEAR_END - _YEAR_START).total_seconds())
        earliest = _YEAR_START + timedelta(seconds=rng.randrange(year_seconds))
    if after is not None:
        earliest = max(earliest, _as_utc(after) + timedelta(hours=1))
    if earliest > _YEAR_END:
        raise ValueError("Order or repeat complaint date falls outside the configured data year.")
    available = int((_YEAR_END - earliest).total_seconds())
    return earliest + timedelta(seconds=rng.randint(0, min(45 * 24 * 60 * 60, available)))


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive timestamps and aware timestamps to UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _status_path(status: str) -> tuple[str, ...]:
    """Return valid preceding states for the requested complaint lifecycle status."""
    paths = {
        "New": ("New",),
        "In Progress": ("New", "In Progress"),
        "Pending Customer": ("New", "In Progress", "Pending Customer"),
        "Pending Vendor": ("New", "In Progress", "Pending Vendor"),
        "Resolved": ("New", "In Progress", "Resolved"),
        "Closed": ("New", "In Progress", "Resolved", "Closed"),
        "Reopened": ("New", "In Progress", "Resolved", "Reopened"),
    }
    return paths[status]


def _attach_lifecycle_history(complaint: Complaint, rng: random.Random) -> None:
    """Attach chronologically ordered status and optional reopen audit history."""
    path = _status_path(complaint.status)
    timestamps = [complaint.created_at]
    for _ in path[1:]:
        remaining = max(0, int((_YEAR_END - timestamps[-1]).total_seconds()))
        step = rng.randint(1, min(3 * 60 * 60, remaining)) if remaining else 0
        timestamps.append(timestamps[-1] + timedelta(seconds=step))

    history: list[ComplaintStatusHistory] = []
    for index, (to_status, changed_at) in enumerate(zip(path, timestamps)):
        from_status = path[index - 1] if index else None
        history.append(
            ComplaintStatusHistory(
                from_status=from_status,
                to_status=to_status,
                changed_by="CUSTOMER" if index == 0 else "SYSTEM",
                reason="Complaint submitted." if index == 0 else f"Status changed from {from_status} to {to_status}.",
                changed_at=changed_at,
            )
        )
    complaint.status_history = history
    complaint.updated_at = timestamps[-1]
    if complaint.status == "Reopened":
        complaint.reopen_count = 1
        complaint.reopen_history = [
            ComplaintReopenHistory(
                reopen_sequence=1,
                reopened_by=complaint.customer.id,
                reopen_reason="The customer reports that the previously addressed issue has returned.",
                reopened_at=timestamps[-1],
            )
        ]


def _matching_rule(
    category: Category,
    customer: Customer,
    text: str,
    rules: Sequence[PriorityRule],
) -> PriorityRule | None:
    """Select the most specific active category, tier, or keyword PriorityRule."""
    candidates: list[tuple[int, str, PriorityRule]] = []
    for rule in rules:
        if not rule.is_active:
            continue
        matches = 0
        specificity = 0
        if rule.category_id is not None:
            if rule.category_id != category.id:
                continue
            matches += 1
            specificity += 4
        if rule.customer_tier is not None:
            if rule.customer_tier != customer.tier:
                continue
            matches += 1
            specificity += 2
        if rule.keyword_trigger:
            if rule.keyword_trigger.casefold() not in text.casefold():
                continue
            matches += 1
            specificity += 1
        if matches:
            candidates.append((specificity, rule.id, rule))
    return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2] if candidates else None


def _score_priority(
    category: Category,
    customer: Customer,
    title: str,
    description: str,
    repeated: bool,
    rules: Sequence[PriorityRule],
) -> tuple[str, str, str]:
    """Return severity, final priority, and a human-readable scoring explanation."""
    issue = category.name
    severity = _SEVERITY[issue]
    text = f"{title} {description}"
    rule = _matching_rule(category, customer, text, rules)
    base = rule.target_priority if rule else _BASE_PRIORITY[issue]
    priority = max((severity, base), key=lambda value: _PRIORITY_RANK[value])
    reasons = [f"{issue} baseline is {base}; severity is {severity}."]
    if rule:
        reasons.append(f"Matched PriorityRule {rule.id} ({rule.target_priority}).")
    else:
        reasons.append("No active matching PriorityRule; used the documented category baseline.")
    if customer.is_vulnerable and priority != "Critical":
        priority = _PRIORITY_BY_RANK[min(len(PRIORITIES) - 1, _PRIORITY_RANK[priority] + 1)]
        reasons.append("Raised one level because the customer is marked vulnerable.")
    if repeated and priority != "Critical":
        priority = _PRIORITY_BY_RANK[min(len(PRIORITIES) - 1, _PRIORITY_RANK[priority] + 1)]
        reasons.append("Raised one level because this is a repeat complaint.")
    if issue == "Safety Issue" or any(term in text.casefold() for term in _SAFETY_TERMS):
        priority = "Critical"
        reasons.append("Safety signals require Critical priority.")
    return severity, priority, " ".join(reasons)


def _validate_dependencies(
    customers: Sequence[Customer],
    products: Sequence[Product],
    orders: Sequence[Order],
    mode: str,
) -> None:
    """Check dependency counts and unique IDs before creating complaint references."""
    expected_customers = {"starter": STARTER_MODE["customers"], "full": FULL_MODE["customers"]}[mode]
    expected_orders = {"starter": STARTER_MODE["orders"], "full": FULL_MODE["orders"]}[mode]
    if len(customers) != expected_customers or len({item.id for item in customers}) != len(customers):
        raise ValueError(f"{mode.title()} complaints require {expected_customers} unique customers.")
    if len(products) != PRODUCT_COUNT or len({item.id for item in products}) != len(products):
        raise ValueError(f"Complaint generation requires {PRODUCT_COUNT} unique products.")
    if len(orders) != expected_orders or len({item.id for item in orders}) != len(orders):
        raise ValueError(f"{mode.title()} complaints require {expected_orders} unique orders.")
    if not all(isinstance(item, Customer) for item in customers):
        raise ValueError("Customer inputs must be Customer model instances.")
    if not all(isinstance(item, Product) for item in products):
        raise ValueError("Product inputs must be Product model instances.")
    if not all(isinstance(item, Order) for item in orders):
        raise ValueError("Order inputs must be Order model instances.")


def validate_complaints(complaints: Iterable[Complaint]) -> None:
    """Validate complaint IDs, relationships, labels, priorities, dates, and repeat metadata."""
    seen: dict[str, Complaint] = {}
    allowed_priorities = set(PRIORITIES)
    for index, complaint in enumerate(complaints, start=1):
        if not isinstance(complaint, Complaint):
            raise ValueError(f"Record {index} is not a Complaint model instance.")
        expected_id = generate_complaint_id(index, year=DATA_YEAR)
        if complaint.id != expected_id or complaint.id in seen:
            raise ValueError(f"Complaint ID at position {index} is invalid, non-sequential, or duplicated.")
        if complaint.customer is None or complaint.category is None:
            raise ValueError(f"Complaint {complaint.id} must reference a customer and category.")
        if complaint.order is not None and complaint.order.customer.id != complaint.customer.id:
            raise ValueError(f"Complaint {complaint.id} order belongs to a different customer.")
        if complaint.order is not None and complaint.product is not None:
            ordered_product_ids = {item.product.id for item in complaint.order.items}
            if complaint.product.id not in ordered_product_ids:
                raise ValueError(f"Complaint {complaint.id} product is not part of its order.")
        if complaint.category.name not in ISSUE_CATEGORIES:
            raise ValueError(f"Complaint {complaint.id} has an unsupported classification category.")
        if complaint.channel not in COMPLAINT_CHANNELS or complaint.status not in COMPLAINT_STATUSES:
            raise ValueError(f"Complaint {complaint.id} has an unsupported channel or status.")
        if complaint.priority not in allowed_priorities:
            raise ValueError(f"Complaint {complaint.id} has an unsupported priority.")
        if not hasattr(complaint, "severity") or complaint.severity not in SEVERITY_LEVELS:
            raise ValueError(f"Complaint {complaint.id} has invalid severity metadata.")
        if complaint.created_at is None or complaint.created_at.tzinfo is None:
            raise ValueError(f"Complaint {complaint.id} needs a timezone-aware creation date.")
        if complaint.updated_at is None or complaint.updated_at < complaint.created_at:
            raise ValueError(f"Complaint {complaint.id} has an invalid update date.")
        if complaint.order is not None and _as_utc(complaint.created_at) < _as_utc(complaint.order.order_date):
            raise ValueError(f"Complaint {complaint.id} predates its order.")
        history = complaint.status_history
        if not history or history[-1].to_status != complaint.status:
            raise ValueError(f"Complaint {complaint.id} status history does not end at its current status.")
        history_dates = [event.changed_at for event in history]
        if history_dates != sorted(history_dates) or history_dates[0] < complaint.created_at:
            raise ValueError(f"Complaint {complaint.id} status history is not chronological.")
        repeat_of_id = getattr(complaint, "repeat_of_id", None)
        if repeat_of_id:
            original = seen.get(repeat_of_id)
            if original is None or original is complaint:
                raise ValueError(f"Complaint {complaint.id} repeat link must point to an earlier complaint.")
            original_product_id = original.product.id if original.product is not None else None
            complaint_product_id = complaint.product.id if complaint.product is not None else None
            if original.customer.id != complaint.customer.id or original_product_id != complaint_product_id:
                raise ValueError(f"Complaint {complaint.id} repeat link does not match customer/product.")
            if original.category.name != complaint.category.name or original.created_at >= complaint.created_at:
                raise ValueError(f"Complaint {complaint.id} repeat link has a different issue or invalid date order.")
        if complaint.status == "Reopened":
            if complaint.reopen_count < 1 or not complaint.reopen_history:
                raise ValueError(f"Complaint {complaint.id} is reopened without reopen audit history.")
        elif complaint.reopen_count != 0:
            raise ValueError(f"Complaint {complaint.id} has a reopen count but is not reopened.")
        seen[complaint.id] = complaint


def generate_complaints(
    mode: str = "starter",
    seed: int = RANDOM_SEED,
    customers: Sequence[Customer] | None = None,
    products: Sequence[Product] | None = None,
    orders: Sequence[Order] | None = None,
    categories: Sequence[Category] | None = None,
    priority_rules: Sequence[PriorityRule] | None = None,
) -> list[Complaint]:
    """Generate, classify, score, and validate the configured complaint dataset."""
    normalized_mode = mode.strip().lower()
    count = complaint_count_for_mode(normalized_mode)
    if customers is None:
        customers = generate_customers(normalized_mode, seed=seed)
    if products is None:
        products = generate_products(seed=seed)
    if orders is None:
        orders = generate_orders(normalized_mode, seed=seed, customers=customers, products=products)
    _validate_dependencies(customers, products, orders, normalized_mode)

    rng = random.Random(seed)
    classification_categories = _category_objects(products, categories)
    priority_rules = tuple(priority_rules or ())
    available_orders: dict[str, list[Order]] = {customer.id: [] for customer in customers}
    for order in orders:
        available_orders.setdefault(order.customer.id, []).append(order)

    label_cycle = list(ISSUE_CATEGORIES)
    rng.shuffle(label_cycle)
    complaints: list[Complaint] = []
    repeat_roots: list[Complaint] = []
    for sequence in range(1, count + 1):
        requested_label = label_cycle[(sequence - 1) % len(label_cycle)]
        scheduled_repeat = sequence > 1 and sequence % 8 == 0 and bool(repeat_roots)
        original: Complaint | None = None
        if scheduled_repeat:
            eligible_roots = [
                complaint for complaint in repeat_roots
                if complaint.created_at < _REPEAT_CUTOFF
            ]
            if eligible_roots:
                original = rng.choice(eligible_roots)
                customer = original.customer
                product = original.product
                order = original.order
                requested_label = original.category.name
            else:
                scheduled_repeat = False
        if not scheduled_repeat:
            customer = rng.choice(customers)
            customer_orders = available_orders.get(customer.id, [])
            order = rng.choice(customer_orders) if customer_orders and rng.random() < 0.82 else None
            if order is not None and order.items:
                product = rng.choice(order.items).product
            else:
                product = rng.choice(products)

        scenario = _scenario_for(requested_label, customer, product, rng)
        complaint_date = _complaint_date(order, rng, after=original.created_at if original else None)
        classification = classify_complaint(
            scenario.title,
            scenario.description,
            order_status=order.order_status if order is not None else None,
            product_description=product.description,
        )
        category = classification_categories[classification]
        original = detect_repeat_complaint(customer, product, category, complaints)
        repeated = original is not None
        if original is not None and complaint_date <= original.created_at:
            complaint_date = _complaint_date(order, rng, after=original.created_at)
        status = rng.choices(
            ("New", "In Progress", "Pending Customer", "Pending Vendor", "Resolved", "Closed", "Reopened"),
            weights=(18, 22, 16, 8, 19, 12, 5),
            k=1,
        )[0]
        complaint = Complaint(
            id=generate_complaint_id(sequence, year=DATA_YEAR),
            customer=customer,
            order=order,
            product=product,
            category=category,
            title=scenario.title,
            description=scenario.description,
            channel=rng.choice(_CHANNELS),
            status=status,
            priority="Medium",
            reopen_count=0,
            created_at=complaint_date,
            updated_at=complaint_date,
        )
        if original is not None:
            complaint.repeat_of_id = original.id
        severity, priority, reason = _score_priority(
            category,
            customer,
            scenario.title,
            scenario.description,
            repeated,
            priority_rules,
        )
        complaint.severity = severity
        complaint.priority = priority
        complaint.priority_reason = reason
        # Export/evaluation label is kept outside mapped columns and never enters
        # classification or priority scoring above.
        complaint.expected_category = scenario.expected_category
        _attach_lifecycle_history(complaint, rng)
        complaints.append(complaint)
        if not repeated and product is not None:
            repeat_roots.append(complaint)

    validate_complaints(complaints)
    return complaints


def main() -> int:
    """Run complaint generation from the command line and print an in-memory summary."""
    parser = argparse.ArgumentParser(description="Generate synthetic customer complaints in memory.")
    parser.add_argument("--mode", choices=("starter", "full"), default="starter")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    complaints = generate_complaints(mode=args.mode, seed=args.seed)
    categories = sorted({complaint.category.name for complaint in complaints})
    repeated_count = sum(bool(getattr(complaint, "repeat_of_id", None)) for complaint in complaints)
    safety_count = sum(complaint.category.name == "Safety Issue" for complaint in complaints)
    print(f"Generated {len(complaints)} complaints in {args.mode.title()} mode (seed={args.seed}).")
    print(f"Categories: {', '.join(categories)}")
    print(f"Repeat complaints: {repeated_count}; safety complaints: {safety_count}.")
    print("Records remain in memory; no database writes were performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
