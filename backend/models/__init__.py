"""
Models package for Customer Complaint Management and SLA Tracking System.
Exposes all domain entities, history tables, and base classes.
"""

from backend.models.base import Base, TimestampMixin
from backend.models.customer import Customer
from backend.models.category import Category
from backend.models.product import Product
from backend.models.order import Order, OrderItem
from backend.models.agent import Agent
from backend.models.priority_rule import PriorityRule
from backend.models.complaint import Complaint, ComplaintStatusHistory, ComplaintReopenHistory
from backend.models.complaint_message import ComplaintMessage
from backend.models.assignment import Assignment
from backend.models.sla import SLAClock, SLAEvent
from backend.models.resolution import Resolution
from backend.models.survey import Survey
from backend.models.id_generators import (
    generate_customer_id,
    generate_order_id,
    generate_complaint_id,
    generate_message_id,
    generate_sla_clock_id,
    generate_resolution_id,
    generate_survey_id,
    generate_agent_id,
    generate_product_id,
    generate_category_id,
    generate_priority_rule_id,
    generate_assignment_id,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "Customer",
    "Category",
    "Product",
    "Order",
    "OrderItem",
    "Agent",
    "PriorityRule",
    "Complaint",
    "ComplaintStatusHistory",
    "ComplaintReopenHistory",
    "ComplaintMessage",
    "Assignment",
    "SLAClock",
    "SLAEvent",
    "Resolution",
    "Survey",
    "generate_customer_id",
    "generate_order_id",
    "generate_complaint_id",
    "generate_message_id",
    "generate_sla_clock_id",
    "generate_resolution_id",
    "generate_survey_id",
    "generate_agent_id",
    "generate_product_id",
    "generate_category_id",
    "generate_priority_rule_id",
    "generate_assignment_id",
]
