"""Candidate management + resume upload + public application endpoint."""
import io
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrgContext, get_org_context, require_roles
from app.database import get_db
from app.models.application import Application, ApplicationStatus
from app.models.candidate import Candidate, CandidateSource
from app.models.job import Job, JobStage, JobStatus
from app.models.user import OrgRole
from app.workers.tasks.ai_tasks import task_parse_resume, task_score_application
from app.workers.tasks.email_tasks import task_send_application_received

router = APIRouter(prefix="/candidates", tags=["candidates"])


class CreateCandidateRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    location: str | None = None
    source: CandidateSource = CandidateSource.DIRECT
    tags: list[str] | None = None
    notes: str | None = None


@router.get("")
async def list_candidates(
    search: str | None = None,
    page: int = 1,
    limit: int = 30,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    query = select(Candidate).where(Candidate.organization_id == ctx.org_id)
    if search:
        search_term = f"%{search}%"
        from sqlalchemy import or_
        query = query.where(
            or_(
                Candidate.first_name.ilike(search_term),
                Candidate.last_name.ilike(search_term),
                Candidate.email.ilike(search_term),
            )
        )
    result = await db.execute(query.order_by(Candidate.created_at.desc()).offset((page - 1) * limit).limit(limit))
    candidates = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "full_name": c.full_name,
            "email": c.email,
            "phone": c.phone,
            "location": c.location,
            "source": c.source,
            "parsed_skills": c.parsed_skills,
            "parsed_experience_years": c.parsed_experience_years,
            "tags": c.tags,
            "created_at": c.created_at.isoformat(),
        }
        for c in candidates
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_candidate(
    payload: CreateCandidateRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    candidate = Candidate(organization_id=ctx.org_id, **payload.model_dump())
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return {"id": str(candidate.id), "full_name": candidate.full_name}


@router.post("/{candidate_id}/resume")
async def upload_resume(
    candidate_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.organization_id == ctx.org_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    if file.content_type not in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF and DOCX files are accepted")

    contents = await file.read()

    # Extract text from PDF/DOCX
    resume_text = ""
    if file.content_type == "application/pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(contents))
            resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            resume_text = ""
    elif file.content_type.endswith("wordprocessingml.document"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(contents))
            resume_text = "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            resume_text = ""

    # Upload to S3 if configured
    from app.config import settings
    resume_url = None
    if settings.AWS_ACCESS_KEY_ID:
        import boto3
        s3 = boto3.client("s3", region_name=settings.AWS_REGION)
        key = f"resumes/{ctx.org_id}/{candidate_id}/{file.filename}"
        s3.upload_fileobj(io.BytesIO(contents), settings.S3_BUCKET_NAME, key)
        resume_url = f"https://{settings.S3_BUCKET_NAME}.s3.amazonaws.com/{key}"

    candidate.resume_url = resume_url
    candidate.resume_text = resume_text
    await db.commit()

    # Trigger AI resume parsing
    if ctx.feature_flags.get("ai_resume_scoring"):
        task_parse_resume.delay(str(candidate_id), str(ctx.org_id))

    return {"message": "Resume uploaded", "resume_url": resume_url, "ai_parsing_queued": True}


@router.get("/{candidate_id}")
async def get_candidate(
    candidate_id: uuid.UUID,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Candidate)
        .where(Candidate.id == candidate_id, Candidate.organization_id == ctx.org_id)
        .options(selectinload(Candidate.applications).selectinload(Application.job))
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    return {
        "id": str(candidate.id),
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "linkedin_url": candidate.linkedin_url,
        "github_url": candidate.github_url,
        "portfolio_url": candidate.portfolio_url,
        "location": candidate.location,
        "source": candidate.source,
        "tags": candidate.tags,
        "notes": candidate.notes,
        "resume_url": candidate.resume_url,
        "ai_summary": candidate.ai_summary,
        "parsed_skills": candidate.parsed_skills,
        "parsed_experience_years": candidate.parsed_experience_years,
        "parsed_education": candidate.parsed_education,
        "parsed_work_history": candidate.parsed_work_history,
        "applications": [
            {"id": str(a.id), "job_title": a.job.title, "status": a.status, "applied_at": a.applied_at.isoformat()}
            for a in candidate.applications
        ],
        "created_at": candidate.created_at.isoformat(),
    }


# ─── Public endpoint — candidate applies via the careers page ────────────────

@router.post("/public/{org_slug}/apply/{job_slug}")
async def public_apply(
    org_slug: str,
    job_slug: str,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str | None = Form(None),
    linkedin_url: str | None = Form(None),
    cover_letter: str | None = Form(None),
    resume: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    """No auth required — public-facing job application form."""
    from app.models.organization import Organization
    org_result = await db.execute(select(Organization).where(Organization.slug == org_slug, Organization.is_active == True))
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    job_result = await db.execute(
        select(Job).where(Job.slug == job_slug, Job.organization_id == org.id, Job.status == JobStatus.PUBLISHED)
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or no longer accepting applications")

    # Upsert candidate (same email = same candidate record per org)
    existing = await db.execute(
        select(Candidate).where(Candidate.email == email, Candidate.organization_id == org.id)
    )
    candidate = existing.scalar_one_or_none()
    if not candidate:
        candidate = Candidate(
            organization_id=org.id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            linkedin_url=linkedin_url,
            source=CandidateSource.CAREERS_PAGE,
        )
        db.add(candidate)
        await db.flush()

    # Prevent duplicate applications
    existing_app = await db.execute(
        select(Application).where(Application.candidate_id == candidate.id, Application.job_id == job.id)
    )
    if existing_app.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already applied to this job")

    # Get first stage
    first_stage = await db.execute(
        select(JobStage).where(JobStage.job_id == job.id).order_by(JobStage.order).limit(1)
    )
    first_stage = first_stage.scalar_one_or_none()

    application = Application(
        organization_id=org.id,
        job_id=job.id,
        candidate_id=candidate.id,
        current_stage_id=first_stage.id if first_stage else None,
        cover_letter=cover_letter,
    )
    db.add(application)
    job.applications_count += 1
    await db.commit()
    await db.refresh(application)

    # Trigger async AI scoring + confirmation email
    task_send_application_received.delay(email, f"{first_name} {last_name}", job.title, org.name)
    task_score_application.delay(str(application.id), str(org.id))

    return {"message": "Application submitted successfully", "application_id": str(application.id)}
