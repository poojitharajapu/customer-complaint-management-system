"""Pydantic request/response schemas for the HTTP API."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _valid_email(value: str | None) -> str | None:
    """Validate basic email syntax without adding an email validation dependency."""
    if value is None:
        return None
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("A valid email address is required.")
    return value


class CustomerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    company_name: str | None = Field(default=None, max_length=150)
    tier: Literal["Standard", "Premium", "Enterprise", "VIP"] = "Standard"
    status: Literal["Active", "Inactive", "Suspended"] = "Active"
    is_vulnerable: bool = False

    _check_email = field_validator("email")(_valid_email)


class CustomerUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    company_name: str | None = Field(default=None, max_length=150)
    tier: Literal["Standard", "Premium", "Enterprise", "VIP"] | None = None
    status: Literal["Active", "Inactive", "Suspended"] | None = None
    is_vulnerable: bool | None = None

    _check_email = field_validator("email")(_valid_email)


class CustomerOut(ORMModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: str | None
    company_name: str | None
    tier: str
    status: str
    is_vulnerable: bool
    created_at: datetime


class ComplaintCreate(BaseModel):
    customer_id: str
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=5)
    channel: Literal["Web", "Email", "Phone", "Chat", "Mobile"] = "Web"
    order_id: str | None = None
    product_id: str | None = None
    category_name: str | None = Field(default=None, max_length=100)


class ComplaintUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=5)
    channel: Literal["Web", "Email", "Phone", "Chat", "Mobile"] | None = None

    @field_validator("title", "description", "channel")
    @classmethod
    def reject_null_updates(cls, value):
        if value is None:
            raise ValueError("This field cannot be null when supplied.")
        return value


class StatusUpdate(BaseModel):
    status: Literal["Assigned", "In Progress", "Pending Customer", "Pending Vendor"]
    changed_by: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=2000)


class ComplaintOut(BaseModel):
    id: str
    customer_id: str
    order_id: str | None
    product_id: str | None
    category_id: str
    category_name: str
    title: str
    description: str
    channel: str
    priority: str
    severity: str | None = None
    status: str
    reopen_count: int
    created_at: datetime
    updated_at: datetime


class AgentCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    team: str = Field(min_length=1, max_length=100)
    role: Literal["Support Agent", "Senior Specialist", "Team Lead", "Manager"] = "Support Agent"
    max_active_tickets: int = Field(default=10, ge=1, le=500)
    is_active: bool = True

    _check_email = field_validator("email")(_valid_email)


class AgentOut(ORMModel):
    id: str
    first_name: str
    last_name: str
    email: str
    team: str
    role: str
    max_active_tickets: int
    is_active: bool


class AssignmentCreate(BaseModel):
    agent_id: str


class MessageCreate(BaseModel):
    sender_type: Literal["Customer", "Agent"]
    sender_id: str
    message_body: str = Field(min_length=1, max_length=10000)
    is_internal_note: bool = False


class MessageOut(ORMModel):
    id: str
    complaint_id: str
    sequence_number: int
    sender_type: str
    sender_id: str
    sender_name: str
    message_body: str
    is_internal_note: bool
    created_at: datetime


class ResolutionCreate(BaseModel):
    resolved_by_agent_id: str
    resolution_type: Literal["Refund", "Replacement", "Configuration Fix", "Explanation Provided", "Credit Issued", "Bug Fix", "Account Update"]
    root_cause: str = Field(min_length=2, max_length=255)
    action_taken: str = Field(min_length=2)
    customer_notes: str | None = None
    accepted_by_customer: bool | None = None
    refund_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class ResolutionOut(ORMModel):
    id: str
    complaint_id: str
    attempt_number: int
    resolved_by_agent_id: str
    root_cause: str
    action_taken: str
    customer_notes: str | None
    resolution_type: str
    is_accepted_by_customer: bool | None
    resolved_at: datetime


class ReopenRequest(BaseModel):
    reopened_by: str
    reason: str = Field(min_length=3, max_length=2000)


class SurveyCreate(BaseModel):
    customer_id: str
    rating: int = Field(ge=1, le=5)
    nps_score: int | None = Field(default=None, ge=0, le=10)
    feedback_comments: str | None = None
    timeliness_rating: int | None = Field(default=None, ge=1, le=5)
    agent_helpfulness_rating: int | None = Field(default=None, ge=1, le=5)


class SurveyOut(ORMModel):
    id: str
    complaint_id: str
    customer_id: str
    rating: int
    nps_score: int | None
    satisfaction_level: str
    feedback_comments: str | None
    submitted_at: datetime


class PageInfo(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    pages: int
