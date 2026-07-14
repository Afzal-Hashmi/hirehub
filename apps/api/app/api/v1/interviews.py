"""Interview scheduling — manual assignment + candidate self-booking."""
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.dependencies import OrgContext, get_org_context, require_roles
from app.core.security import generate_secure_token
from app.database import get_db
from app.models.application import Application, ApplicationActivity
from app.models.interview import Interview, InterviewFeedback, InterviewSlot, InterviewStatus, InterviewType
from app.models.user import OrgRole, User
from app.workers.tasks.email_tasks import task_send_interview_invitation, task_send_self_booking_link

router = APIRouter(prefix="/interviews", tags=["interviews"])


class ScheduleInterviewRequest(BaseModel):
    application_id: uuid.UUID
    title: str
    interview_type: InterviewType = InterviewType.VIDEO
    scheduled_at: datetime
    duration_minutes: int = 60
    timezone: str = "UTC"
    interviewer_ids: list[uuid.UUID]
    meeting_link: str | None = None
    meeting_provider: str | None = None
    notes: str | None = None


class SendSelfBookingRequest(BaseModel):
    application_id: uuid.UUID
    title: str
    interview_type: InterviewType = InterviewType.VIDEO
    duration_minutes: int = 60
    expires_hours: int = 48
    interviewer_ids: list[uuid.UUID]
    notes: str | None = None


class ConfirmSelfBookingRequest(BaseModel):
    scheduled_at: datetime
    timezone: str = "UTC"


class SubmitFeedbackRequest(BaseModel):
    overall_rating: int
    recommendation: str
    scorecard: dict | None = None
    strengths: str | None = None
    concerns: str | None = None
    private_notes: str | None = None


class GenerateQuestionsRequest(BaseModel):
    application_id: uuid.UUID
    interview_type: InterviewType
    num_questions: int = 8


@router.get("")
async def list_interviews(
    application_id: uuid.UUID | None = None,
    interviewer_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Interview)
        .where(Interview.organization_id == ctx.org_id)
        .options(
            selectinload(Interview.interviewers).selectinload(InterviewSlot.interviewer),
            selectinload(Interview.application).selectinload(Application.candidate),
        )
        .order_by(Interview.scheduled_at.asc())
    )
    if application_id:
        query = query.where(Interview.application_id == application_id)
    if status_filter:
        query = query.where(Interview.status == status_filter)

    result = await db.execute(query)
    interviews = result.scalars().all()

    if interviewer_id:
        interviews = [
            i for i in interviews if any(s.interviewer_id == interviewer_id for s in i.interviewers)
        ]

    return [
        {
            "id": str(i.id),
            "title": i.title,
            "interview_type": i.interview_type,
            "status": i.status,
            "scheduled_at": i.scheduled_at.isoformat(),
            "duration_minutes": i.duration_minutes,
            "meeting_link": i.meeting_link,
            "candidate": {
                "id": str(i.application.candidate.id),
                "full_name": i.application.candidate.full_name,
            },
            "interviewers": [
                {"id": str(s.interviewer.id), "name": s.interviewer.full_name, "confirmed": s.confirmed}
                for s in i.interviewers
            ],
        }
        for i in interviews
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def schedule_interview(
    payload: ScheduleInterviewRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application)
        .where(Application.id == payload.application_id, Application.organization_id == ctx.org_id)
        .options(selectinload(Application.candidate), selectinload(Application.job))
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    interview = Interview(
        organization_id=ctx.org_id,
        application_id=payload.application_id,
        scheduled_by=ctx.user.id,
        title=payload.title,
        interview_type=payload.interview_type,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        timezone=payload.timezone,
        meeting_link=payload.meeting_link,
        meeting_provider=payload.meeting_provider,
        notes=payload.notes,
    )
    db.add(interview)
    await db.flush()

    for interviewer_id in payload.interviewer_ids:
        slot = InterviewSlot(
            interview_id=interview.id,
            interviewer_id=interviewer_id,
            organization_id=ctx.org_id,
        )
        db.add(slot)

    activity = ApplicationActivity(
        application_id=payload.application_id,
        organization_id=ctx.org_id,
        actor_id=ctx.user.id,
        actor_name=ctx.user.full_name,
        activity_type="interview_scheduled",
        metadata={"interview_title": payload.title, "scheduled_at": payload.scheduled_at.isoformat()},
    )
    db.add(activity)
    await db.commit()

    # Send email notification to candidate
    formatted_time = payload.scheduled_at.strftime("%B %d, %Y at %I:%M %p %Z")
    task_send_interview_invitation.delay(
        application.candidate.email,
        application.candidate.full_name,
        application.job.title,
        ctx.organization.name,
        formatted_time,
        payload.meeting_link or "To be provided",
        ctx.user.full_name,
        payload.duration_minutes,
    )

    return {"id": str(interview.id), "title": interview.title, "scheduled_at": interview.scheduled_at.isoformat()}


@router.post("/self-booking/send")
async def send_self_booking_link(
    payload: SendSelfBookingRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("candidate_self_booking")

    result = await db.execute(
        select(Application)
        .where(Application.id == payload.application_id, Application.organization_id == ctx.org_id)
        .options(selectinload(Application.candidate), selectinload(Application.job))
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    token = generate_secure_token(32)
    expires_at = datetime.now(UTC) + timedelta(hours=payload.expires_hours)

    interview = Interview(
        organization_id=ctx.org_id,
        application_id=payload.application_id,
        scheduled_by=ctx.user.id,
        title=payload.title,
        interview_type=payload.interview_type,
        scheduled_at=expires_at,  # Placeholder; will be updated on booking
        duration_minutes=payload.duration_minutes,
        status=InterviewStatus.SCHEDULED,
        self_booking_token=token,
        self_booking_expires_at=expires_at,
        notes=payload.notes,
    )
    db.add(interview)
    await db.flush()

    for interviewer_id in payload.interviewer_ids:
        slot = InterviewSlot(
            interview_id=interview.id,
            interviewer_id=interviewer_id,
            organization_id=ctx.org_id,
        )
        db.add(slot)

    await db.commit()

    booking_url = f"{settings.NEXT_PUBLIC_APP_URL}/book/{token}"
    task_send_self_booking_link.delay(
        application.candidate.email,
        application.candidate.full_name,
        application.job.title,
        ctx.organization.name,
        booking_url,
    )

    return {"booking_url": booking_url, "expires_at": expires_at.isoformat()}


@router.get("/self-booking/{token}")
async def get_self_booking_info(token: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint — returns interview info for the candidate booking page."""
    result = await db.execute(
        select(Interview)
        .where(Interview.self_booking_token == token)
        .options(
            selectinload(Interview.application).selectinload(Application.job),
            selectinload(Interview.interviewers).selectinload(InterviewSlot.interviewer),
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking link not found")

    if interview.self_booking_expires_at and interview.self_booking_expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Booking link has expired")

    return {
        "interview_title": interview.title,
        "interview_type": interview.interview_type,
        "duration_minutes": interview.duration_minutes,
        "job_title": interview.application.job.title,
        "expires_at": interview.self_booking_expires_at.isoformat(),
    }


@router.post("/self-booking/{token}/confirm")
async def confirm_self_booking(
    token: str,
    payload: ConfirmSelfBookingRequest,
    db: AsyncSession = Depends(get_db),
):
    """Candidate picks a time slot and confirms the interview."""
    result = await db.execute(
        select(Interview)
        .where(Interview.self_booking_token == token)
        .options(
            selectinload(Interview.application).selectinload(Application.candidate),
            selectinload(Interview.application).selectinload(Application.job),
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking link not found")

    if interview.self_booking_expires_at and interview.self_booking_expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Booking link has expired")

    interview.scheduled_at = payload.scheduled_at
    interview.timezone = payload.timezone
    interview.status = InterviewStatus.CONFIRMED
    interview.self_booking_token = None  # Consume token

    await db.commit()

    return {
        "message": "Interview confirmed",
        "scheduled_at": interview.scheduled_at.isoformat(),
        "duration_minutes": interview.duration_minutes,
    }


@router.get("/{interview_id}")
async def get_interview(
    interview_id: uuid.UUID,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Interview)
        .where(Interview.id == interview_id, Interview.organization_id == ctx.org_id)
        .options(
            selectinload(Interview.interviewers).selectinload(InterviewSlot.interviewer),
            selectinload(Interview.feedback).selectinload(InterviewFeedback.interviewer),
            selectinload(Interview.application).selectinload(Application.candidate),
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    return {
        "id": str(interview.id),
        "title": interview.title,
        "interview_type": interview.interview_type,
        "status": interview.status,
        "scheduled_at": interview.scheduled_at.isoformat(),
        "duration_minutes": interview.duration_minutes,
        "timezone": interview.timezone,
        "meeting_link": interview.meeting_link,
        "notes": interview.notes,
        "ai_questions": interview.ai_questions,
        "candidate": {
            "full_name": interview.application.candidate.full_name,
            "email": interview.application.candidate.email,
        },
        "interviewers": [
            {"id": str(s.interviewer.id), "name": s.interviewer.full_name, "confirmed": s.confirmed}
            for s in interview.interviewers
        ],
        "feedback": [
            {
                "interviewer": f.interviewer.full_name,
                "overall_rating": f.overall_rating,
                "recommendation": f.recommendation,
                "strengths": f.strengths,
                "concerns": f.concerns,
                "submitted_at": f.submitted_at.isoformat(),
            }
            for f in interview.feedback
        ],
    }


@router.post("/{interview_id}/feedback")
async def submit_feedback(
    interview_id: uuid.UUID,
    payload: SubmitFeedbackRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER, OrgRole.INTERVIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Interview).where(Interview.id == interview_id, Interview.organization_id == ctx.org_id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    feedback = InterviewFeedback(
        interview_id=interview_id,
        interviewer_id=ctx.user.id,
        organization_id=ctx.org_id,
        **payload.model_dump(),
    )
    db.add(feedback)
    await db.commit()
    return {"message": "Feedback submitted"}


@router.post("/{interview_id}/generate-questions")
async def generate_questions(
    interview_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER, OrgRole.INTERVIEWER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("ai_question_gen")

    result = await db.execute(
        select(Interview)
        .where(Interview.id == interview_id, Interview.organization_id == ctx.org_id)
        .options(
            selectinload(Interview.application)
            .selectinload(Application.job),
            selectinload(Interview.application)
            .selectinload(Application.candidate),
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    from app.services.ai_service import generate_interview_questions

    questions = generate_interview_questions(
        job_title=interview.application.job.title,
        job_description=interview.application.job.description,
        interview_type=interview.interview_type,
        candidate_resume_text=interview.application.candidate.resume_text,
    )

    interview.ai_questions = questions
    await db.commit()

    return {"questions": questions}


@router.patch("/{interview_id}/cancel")
async def cancel_interview(
    interview_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Interview).where(Interview.id == interview_id, Interview.organization_id == ctx.org_id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    interview.status = InterviewStatus.CANCELLED
    await db.commit()
    return {"status": "cancelled"}
