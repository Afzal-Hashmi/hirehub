"""On-demand AI endpoints — all gated by feature flags."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import OrgContext, require_roles
from app.database import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.user import OrgRole
from app.services.ai_service import (
    draft_email,
    generate_interview_questions,
    generate_offer_letter,
    score_candidate_fit,
    summarize_job_description,
)

router = APIRouter(prefix="/ai", tags=["ai"])


class DraftEmailRequest(BaseModel):
    email_type: str
    candidate_name: str
    job_title: str
    extra_context: dict | None = None


class GenerateQuestionsRequest(BaseModel):
    job_id: uuid.UUID
    interview_type: str
    candidate_id: uuid.UUID | None = None
    num_questions: int = 8


class GenerateOfferRequest(BaseModel):
    application_id: uuid.UUID
    start_date: str
    salary: int
    currency: str = "USD"
    extra_details: dict | None = None


class FitAnalysisRequest(BaseModel):
    application_id: uuid.UUID


@router.post("/draft-email")
async def ai_draft_email(
    payload: DraftEmailRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
):
    ctx.require_feature("ai_email_drafting")
    result = draft_email(
        email_type=payload.email_type,
        candidate_name=payload.candidate_name,
        job_title=payload.job_title,
        company_name=ctx.organization.name,
        extra_context=payload.extra_context,
    )
    return result


@router.post("/generate-questions")
async def ai_generate_questions(
    payload: GenerateQuestionsRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER, OrgRole.INTERVIEWER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("ai_question_gen")

    job = await db.get(Job, payload.job_id)
    if not job or job.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Job not found")

    resume_text = None
    if payload.candidate_id:
        candidate = await db.get(Candidate, payload.candidate_id)
        if candidate and candidate.organization_id == ctx.org_id:
            resume_text = candidate.resume_text

    questions = generate_interview_questions(
        job_title=job.title,
        job_description=job.description,
        interview_type=payload.interview_type,
        candidate_resume_text=resume_text,
        num_questions=payload.num_questions,
    )
    return {"questions": questions}


@router.post("/fit-analysis")
async def ai_fit_analysis(
    payload: FitAnalysisRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("ai_fit_analysis")

    result = await db.execute(
        select(Application)
        .where(Application.id == payload.application_id, Application.organization_id == ctx.org_id)
        .options(selectinload(Application.candidate), selectinload(Application.job))
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if not application.candidate.resume_text:
        raise HTTPException(status_code=400, detail="No resume text available for this candidate")

    analysis = score_candidate_fit(
        resume_text=application.candidate.resume_text,
        job_title=application.job.title,
        job_description=application.job.description,
        requirements=application.job.requirements or "",
        skills_required=application.job.skills_required or [],
    )

    application.ai_score = analysis.get("score")
    application.ai_fit_analysis = analysis
    await db.commit()

    return analysis


@router.post("/generate-offer-letter")
async def ai_generate_offer_letter(
    payload: GenerateOfferRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("offer_letter_gen")

    result = await db.execute(
        select(Application)
        .where(Application.id == payload.application_id, Application.organization_id == ctx.org_id)
        .options(selectinload(Application.candidate), selectinload(Application.job))
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    letter_html = generate_offer_letter(
        candidate_name=application.candidate.full_name,
        job_title=application.job.title,
        company_name=ctx.organization.name,
        start_date=payload.start_date,
        salary=payload.salary,
        currency=payload.currency,
        extra_details=payload.extra_details,
    )
    return {"offer_letter_html": letter_html}


@router.post("/summarize-jd/{job_id}")
async def ai_summarize_jd(
    job_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("public_job_board")
    job = await db.get(Job, job_id)
    if not job or job.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Job not found")

    summary = summarize_job_description(job.title, job.description)
    job.ai_jd_summary = summary
    await db.commit()
    return {"summary": summary}
