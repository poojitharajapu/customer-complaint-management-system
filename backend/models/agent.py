"""
Agent SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String, Integer, Boolean, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.models.assignment import Assignment
    from backend.models.resolution import Resolution


class Agent(Base, TimestampMixin):
    """
    Agent entity managing support staff members, their roles, and team affiliations.
    ID format: AGT-000001
    """
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Support Agent', 'Senior Specialist', 'Team Lead', 'Manager')",
            name="chk_agent_role",
        ),
        CheckConstraint("max_active_tickets > 0", name="chk_agent_max_tickets"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Team & Role
    team: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="Support Agent", nullable=False)
    max_active_tickets: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment",
        back_populates="agent",
    )
    resolutions: Mapped[List["Resolution"]] = relationship(
        "Resolution",
        back_populates="resolved_by_agent",
    )

    def __repr__(self) -> str:
        return f"<Agent(id='{self.id}', name='{self.first_name} {self.last_name}', team='{self.team}', role='{self.role}')>"

