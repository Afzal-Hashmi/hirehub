import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterviewType(str, Enum):
    PHONE_SCREEN = "phone_screen"
    VIDEO = "video"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    PANEL = "panel"
    ONSITE = "onsite"
    CULTURE_FIT = "culture_fit"


class InterviewStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    interview_type: Mapped[InterviewType] = mapped_column(String(30), default=InterviewType.VIDEO)
    status: Mapped[InterviewStatus] = mapped_column(
        String(20), default=InterviewStatus.SCHEDULED, nullable=False, index=True
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Video meeting
    meeting_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)  # google_meet, zoom, teams
    google_calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Self-booking
    self_booking_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    self_booking_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI-generated questions for this interview
    ai_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # [{"question": "...", "type": "behavioral", "rationale": "..."}]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    application: Mapped["Application"] = relationship("Application", back_populates="interviews")
    interviewers: Mapped[list["InterviewSlot"]] = relationship(
        "InterviewSlot", back_populates="interview", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["InterviewFeedback"]] = relationship(
        "InterviewFeedback", back_populates="interview", cascade="all, delete-orphan"
    )


class InterviewSlot(Base):
    """Maps interviewers to interviews — supports panel interviews."""

    __tablename__ = "interview_slots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    interview: Mapped["Interview"] = relationship("Interview", back_populates="interviewers")
    interviewer: Mapped["User"] = relationship("User")


class InterviewFeedback(Base):
    """Scorecard submitted by an interviewer after the interview."""

    __tablename__ = "interview_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Overall rating 1-5
    overall_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "strong_hire", "hire", "neutral", "no_hire", "strong_no_hire"

    # Structured scorecard
    scorecard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"technical_skills": 4, "communication": 5, "problem_solving": 3, ...}

    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    concerns: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship("Interview", back_populates="feedback")
    interviewer: Mapped["User"] = relationship("User")
