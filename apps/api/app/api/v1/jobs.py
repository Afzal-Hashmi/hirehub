import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from python_slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import OrgContext, get_org_context, require_roles
from app.database import get_db
from app.models.job import Job, JobStage, JobStatus, JobType, WorkMode
from app.models.user import OrgRole
from app.workers.tasks.ai_tasks import task_score_application

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    title: str
    department: str | None = None
    location: str | None = None
    work_mode: WorkMode = WorkMode.ONSITE
    job_type: JobType = JobType.FULL_TIME
    description: str
    requirements: str | None = None
    responsibilities: str | None = None
    benefits: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    salary_visible: bool = False
    skills_required: list[str] | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    application_deadline: datetime | None = None


class UpdateJobRequest(BaseModel):
    title: str | None = None
    department: str | None = None
    location: str | None = None
    work_mode: WorkMode | None = None
    job_type: JobType | None = None
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None
    benefits: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_visible: bool | None = None
    skills_required: list[str] | None = None
    application_deadline: datetime | None = None


class UpdateStagesRequest(BaseModel):
    stages: list[dict]


@router.get("")
async def list_jobs(
    status_filter: str | None = None,
    page: int = 1,
    limit: int = 20,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    query = select(Job).where(Job.organization_id == ctx.org_id)
    if status_filter:
        query = query.where(Job.status == status_filter)
    query = query.order_by(Job.created_at.desc()).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query.options(selectinload(Job.stages)))
    jobs = result.scalars().all()

    return [
        {
            "id": str(j.id),
            "title": j.title,
            "department": j.department,
            "location": j.location,
            "work_mode": j.work_mode,
            "job_type": j.job_type,
            "status": j.status,
            "applications_count": j.applications_count,
            "views_count": j.views_count,
            "salary_visible": j.salary_visible,
            "salary_min": j.salary_min if j.salary_visible else None,
            "salary_max": j.salary_max if j.salary_visible else None,
            "salary_currency": j.salary_currency,
            "created_at": j.created_at.isoformat(),
            "published_at": j.published_at.isoformat() if j.published_at else None,
        }
        for j in jobs
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: CreateJobRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    slug = slugify(f"{payload.title}-{ctx.organization.slug}")
    job = Job(
        organization_id=ctx.org_id,
        created_by=ctx.user.id,
        slug=slug,
        **payload.model_dump(),
    )
    db.add(job)
    await db.flush()

    # Create default pipeline stages
    for stage_data in JobStage.DEFAULT_STAGES:
        stage = JobStage(
            job_id=job.id,
            organization_id=ctx.org_id,
            **stage_data,
        )
        db.add(stage)

    await db.commit()
    await db.refresh(job)
    return {"id": str(job.id), "title": job.title, "slug": job.slug, "status": job.status}


@router.get("/{job_id}")
async def get_job(job_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id, Job.organization_id == ctx.org_id)
        .options(selectinload(Job.stages))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return {
        "id": str(job.id),
        "title": job.title,
        "slug": job.slug,
        "department": job.department,
        "location": job.location,
        "work_mode": job.work_mode,
        "job_type": job.job_type,
        "description": job.description,
        "requirements": job.requirements,
        "responsibilities": job.responsibilities,
        "benefits": job.benefits,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_visible": job.salary_visible,
        "skills_required": job.skills_required,
        "experience_min_years": job.experience_min_years,
        "experience_max_years": job.experience_max_years,
        "status": job.status,
        "is_featured": job.is_featured,
        "application_deadline": job.application_deadline.isoformat() if job.application_deadline else None,
        "ai_jd_summary": job.ai_jd_summary,
        "views_count": job.views_count,
        "applications_count": job.applications_count,
        "created_at": job.created_at.isoformat(),
        "published_at": job.published_at.isoformat() if job.published_at else None,
        "stages": [
            {"id": str(s.id), "name": s.name, "order": s.order, "color": s.color,
             "is_terminal": s.is_terminal, "is_positive_terminal": s.is_positive_terminal}
            for s in sorted(job.stages, key=lambda x: x.order)
        ],
    }


@router.patch("/{job_id}")
async def update_job(
    job_id: uuid.UUID,
    payload: UpdateJobRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id, Job.organization_id == ctx.org_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(job, field, value)
    await db.commit()
    return {"id": str(job.id), "title": job.title}


@router.post("/{job_id}/publish")
async def publish_job(
    job_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id, Job.organization_id == ctx.org_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job.status = JobStatus.PUBLISHED
    job.published_at = datetime.now(UTC)
    await db.commit()

    # Trigger AI JD summary in background if flag enabled
    if ctx.feature_flags.get("ai_resume_scoring") and not job.ai_jd_summary:
        from app.services.ai_service import summarize_job_description
        # Fire-and-forget via celery would be cleaner; inline for simplicity here
        pass

    return {"status": "published", "published_at": job.published_at.isoformat()}


@router.post("/{job_id}/close")
async def close_job(
    job_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id, Job.organization_id == ctx.org_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job.status = JobStatus.CLOSED
    await db.commit()
    return {"status": "closed"}


@router.patch("/{job_id}/stages")
async def update_pipeline_stages(
    job_id: uuid.UUID,
    payload: UpdateStagesRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("custom_pipeline_stages")

    result = await db.execute(select(Job).where(Job.id == job_id, Job.organization_id == ctx.org_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    existing = await db.execute(select(JobStage).where(JobStage.job_id == job_id))
    for stage in existing.scalars().all():
        await db.delete(stage)

    for stage_data in payload.stages:
        stage = JobStage(job_id=job_id, organization_id=ctx.org_id, **stage_data)
        db.add(stage)

    await db.commit()
    return {"message": "Pipeline stages updated"}
