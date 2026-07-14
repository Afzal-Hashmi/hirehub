import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"


class JobType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"


class WorkMode(str, Enum):
    REMOTE = "remote"
    ONSITE = "onsite"
    HYBRID = "hybrid"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_mode: Mapped[WorkMode] = mapped_column(String(20), default=WorkMode.ONSITE)
    job_type: Mapped[JobType] = mapped_column(String(20), default=JobType.FULL_TIME)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)

    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(3), default="USD")
    salary_visible: Mapped[bool] = mapped_column(Boolean, default=False)

    skills_required: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    experience_min_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_max_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[JobStatus] = mapped_column(String(20), default=JobStatus.DRAFT, nullable=False, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # AI-generated fields cached here to avoid re-running on every view
    ai_jd_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    views_count: Mapped[int] = mapped_column(Integer, default=0)
    applications_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="jobs")
    stages: Mapped[list["JobStage"]] = relationship(
        "JobStage", back_populates="job", order_by="JobStage.order", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )


class JobStage(Base):
    """Pipeline stages per job — fully customizable per org (if flag enabled)."""

    __tablename__ = "job_stages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#6B7280")
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    # true = hired, false = rejected (only relevant when is_terminal=True)
    is_positive_terminal: Mapped[bool] = mapped_column(Boolean, default=False)

    # Auto-trigger email template when candidate enters this stage
    auto_email_template: Mapped[str | None] = mapped_column(String(100), nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="stages")

    DEFAULT_STAGES = [
        {"name": "Applied", "order": 1, "color": "#6B7280", "is_terminal": False},
        {"name": "Screening", "order": 2, "color": "#3B82F6", "is_terminal": False},
        {"name": "Interview", "order": 3, "color": "#8B5CF6", "is_terminal": False},
        {"name": "Technical", "order": 4, "color": "#F59E0B", "is_terminal": False},
        {"name": "Offer", "order": 5, "color": "#10B981", "is_terminal": False},
        {"name": "Hired", "order": 6, "color": "#059669", "is_terminal": True, "is_positive_terminal": True},
        {"name": "Rejected", "order": 7, "color": "#EF4444", "is_terminal": True, "is_positive_terminal": False},
    ]
