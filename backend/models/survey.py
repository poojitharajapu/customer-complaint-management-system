"""
Survey SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, Optional
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.complaint import Complaint
    from backend.models.customer import Customer


class Survey(Base):
    """
    Survey entity capturing customer satisfaction (CSAT) and feedback post-resolution.
    ID format: SRV-<complaint-id>
    """
    __tablename__ = "surveys"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="chk_survey_rating_range"),
        CheckConstraint(
            "nps_score IS NULL OR (nps_score >= 0 AND nps_score <= 10)",
            name="chk_survey_nps_range",
        ),
        CheckConstraint(
            "satisfaction_level IN ('Very Dissatisfied', 'Dissatisfied', 'Neutral', 'Satisfied', 'Very Satisfied')",
            name="chk_survey_satisfaction_level",
        ),
        CheckConstraint(
            "timeliness_rating IS NULL OR (timeliness_rating >= 1 AND timeliness_rating <= 5)",
            name="chk_survey_timeliness_range",
        ),
        CheckConstraint(
            "agent_helpfulness_rating IS NULL OR (agent_helpfulness_rating >= 1 AND agent_helpfulness_rating <= 5)",
            name="chk_survey_helpfulness_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    customer_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    nps_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    satisfaction_level: Mapped[str] = mapped_column(String(30), nullable=False)
    feedback_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timeliness_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agent_helpfulness_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="survey")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="surveys")

    def __repr__(self) -> str:
        return f"<Survey(id='{self.id}', complaint_id='{self.complaint_id}', rating={self.rating}, level='{self.satisfaction_level}')>"

