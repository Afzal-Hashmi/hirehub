import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApplicationStatus(str, Enum):
    ACTIVE = "active"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ON_HOLD = "on_hold"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_stages.id", ondelete="SET NULL"), nullable=True
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        String(20), default=ApplicationStatus.ACTIVE, nullable=False, index=True
    )

    # AI scoring (0-100)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_fit_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"score": 85, "strengths": [...], "gaps": [...], "recommendation": "..."}

    # Offer details (when stage = Offer)
    offer_salary: Mapped[int | None] = mapped_column(None, nullable=True)
    offer_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    offer_letter_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    hired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="applications")
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="applications")
    current_stage: Mapped["JobStage | None"] = relationship("JobStage")
    assignee: Mapped["User | None"] = relationship("User")
    activities: Mapped[list["ApplicationActivity"]] = relationship(
        "ApplicationActivity", back_populates="application", order_by="ApplicationActivity.created_at.desc()",
        cascade="all, delete-orphan"
    )
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationActivity(Base):
    """Immutable audit trail of every action taken on an application."""

    __tablename__ = "application_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g. "stage_change", "note_added", "interview_scheduled", "offer_sent", "ai_scored"

    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"from_stage": "...", "to_stage": "...", "note": "..."}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped["Application"] = relationship("Application", back_populates="activities")
