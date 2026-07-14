import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Primary color for white-labeling candidate portal
    brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True, default="#4F46E5")

    # Seat management
    max_seats: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Excludes the owner themselves; owner + max_seats = total allowed users

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    feature_flags: Mapped["OrganizationFeatureFlags"] = relationship(
        "OrganizationFeatureFlags", back_populates="organization", uselist=False, cascade="all, delete-orphan"
    )
    memberships: Mapped[list["UserOrganizationMembership"]] = relationship(
        "UserOrganizationMembership", back_populates="organization", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="organization", cascade="all, delete-orphan")
    candidates: Mapped[list["Candidate"]] = relationship(
        "Candidate", back_populates="organization", cascade="all, delete-orphan"
    )
    invites: Mapped[list["OrganizationInvite"]] = relationship(
        "OrganizationInvite", back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationFeatureFlags(Base):
    """
    JSONB feature flags per org — super-admin toggles these.
    Default flags are set on org creation; super-admin can override any key.

    Flag schema example:
    {
        "ai_resume_scoring": true,
        "ai_question_gen": true,
        "ai_fit_analysis": true,
        "ai_email_drafting": true,
        "google_calendar_sync": false,
        "slack_notifications": false,
        "sms_notifications": false,
        "whatsapp_notifications": false,
        "candidate_self_booking": true,
        "public_job_board": true,
        "analytics_dashboard": true,
        "bulk_import": false,
        "offer_letter_gen": true,
        "video_interviews": false,
        "custom_pipeline_stages": true
    }
    """

    __tablename__ = "organization_feature_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # FK defined via string to avoid circular import issues at module load
        nullable=False,
        unique=True,
        index=True,
    )
    flags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="feature_flags")

    DEFAULT_FLAGS: dict = {
        "ai_resume_scoring": True,
        "ai_question_gen": True,
        "ai_fit_analysis": True,
        "ai_email_drafting": True,
        "google_calendar_sync": False,
        "slack_notifications": False,
        "sms_notifications": False,
        "whatsapp_notifications": False,
        "candidate_self_booking": True,
        "public_job_board": True,
        "analytics_dashboard": True,
        "bulk_import": False,
        "offer_letter_gen": True,
        "video_interviews": False,
        "custom_pipeline_stages": True,
        "custom_skills": True,
    }

    def get(self, flag: str, default: bool = False) -> bool:
        return self.flags.get(flag, default)
