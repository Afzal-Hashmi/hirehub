"""Application pipeline management — the core hiring workflow."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import OrgContext, get_org_context, require_roles
from app.database import get_db
from app.models.application import Application, ApplicationActivity, ApplicationStatus
from app.models.candidate import Candidate
from app.models.job import Job, JobStage
from app.models.notification import NotificationType
from app.models.user import OrgRole
from app.services.notification_service import create_in_app_notification
from app.workers.tasks.ai_tasks import task_score_application
from app.workers.tasks.email_tasks import task_send_rejection

router = APIRouter(prefix="/applications", tags=["applications"])


class MoveStageRequest(BaseModel):
    stage_id: uuid.UUID


class AssignRequest(BaseModel):
    user_id: uuid.UUID


class RejectRequest(BaseModel):
    reason: str | None = None
    send_email: bool = True
    custom_email_body: str | None = None


class AddNoteRequest(BaseModel):
    note: str


@router.get("")
async def list_applications(
    job_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    page: int = 1,
    limit: int = 50,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Application)
        .where(Application.organization_id == ctx.org_id)
        .options(
            selectinload(Application.candidate),
            selectinload(Application.job),
            selectinload(Application.current_stage),
        )
        .order_by(Application.applied_at.desc())
    )
    if job_id:
        query = query.where(Application.job_id == job_id)
    if stage_id:
        query = query.where(Application.current_stage_id == stage_id)
    if status_filter:
        query = query.where(Application.status == status_filter)

    result = await db.execute(query.offset((page - 1) * limit).limit(limit))
    apps = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "candidate": {
                "id": str(a.candidate.id),
                "full_name": a.candidate.full_name,
                "email": a.candidate.email,
                "avatar_url": None,
            },
            "job": {"id": str(a.job.id), "title": a.job.title},
            "current_stage": (
                {"id": str(a.current_stage.id), "name": a.current_stage.name, "color": a.current_stage.color}
                if a.current_stage
                else None
            ),
            "status": a.status,
            "ai_score": a.ai_score,
            "applied_at": a.applied_at.isoformat(),
        }
        for a in apps
    ]


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID,
    ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application)
        .where(Application.id == application_id, Application.organization_id == ctx.org_id)
        .options(
            selectinload(Application.candidate),
            selectinload(Application.job).selectinload(Job.stages),
            selectinload(Application.current_stage),
            selectinload(Application.activities),
            selectinload(Application.interviews),
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    return {
        "id": str(app.id),
        "status": app.status,
        "ai_score": app.ai_score,
        "ai_fit_analysis": app.ai_fit_analysis,
        "cover_letter": app.cover_letter,
        "applied_at": app.applied_at.isoformat(),
        "candidate": {
            "id": str(app.candidate.id),
            "full_name": app.candidate.full_name,
            "email": app.candidate.email,
            "phone": app.candidate.phone,
            "linkedin_url": app.candidate.linkedin_url,
            "resume_url": app.candidate.resume_url,
            "ai_summary": app.candidate.ai_summary,
            "parsed_skills": app.candidate.parsed_skills,
            "parsed_experience_years": app.candidate.parsed_experience_years,
        },
        "job": {
            "id": str(app.job.id),
            "title": app.job.title,
            "stages": [
                {"id": str(s.id), "name": s.name, "order": s.order, "color": s.color}
                for s in sorted(app.job.stages, key=lambda x: x.order)
            ],
        },
        "current_stage": (
            {"id": str(app.current_stage.id), "name": app.current_stage.name}
            if app.current_stage
            else None
        ),
        "activities": [
            {
                "type": a.activity_type,
                "actor_name": a.actor_name,
                "metadata": a.metadata,
                "created_at": a.created_at.isoformat(),
            }
            for a in app.activities
        ],
        "interviews": [
            {
                "id": str(i.id),
                "title": i.title,
                "status": i.status,
                "scheduled_at": i.scheduled_at.isoformat(),
                "meeting_link": i.meeting_link,
            }
            for i in app.interviews
        ],
    }


@router.patch("/{application_id}/stage")
async def move_stage(
    application_id: uuid.UUID,
    payload: MoveStageRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application)
        .where(Application.id == application_id, Application.organization_id == ctx.org_id)
        .options(selectinload(Application.candidate), selectinload(Application.current_stage))
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    new_stage = await db.get(JobStage, payload.stage_id)
    if not new_stage or new_stage.job_id != app.job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stage for this job")

    old_stage_name = app.current_stage.name if app.current_stage else "None"

    app.current_stage_id = payload.stage_id
    if new_stage.is_terminal:
        app.status = ApplicationStatus.HIRED if new_stage.is_positive_terminal else ApplicationStatus.REJECTED
        if new_stage.is_positive_terminal:
            app.hired_at = datetime.now(UTC)
        else:
            app.rejected_at = datetime.now(UTC)

    activity = ApplicationActivity(
        application_id=app.id,
        organization_id=ctx.org_id,
        actor_id=ctx.user.id,
        actor_name=ctx.user.full_name,
        activity_type="stage_change",
        metadata={"from_stage": old_stage_name, "to_stage": new_stage.name},
    )
    db.add(activity)
    await db.commit()

    return {"stage": new_stage.name, "status": app.status}


@router.post("/{application_id}/reject")
async def reject_application(
    application_id: uuid.UUID,
    payload: RejectRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application)
        .where(Application.id == application_id, Application.organization_id == ctx.org_id)
        .options(selectinload(Application.candidate), selectinload(Application.job))
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    app.status = ApplicationStatus.REJECTED
    app.rejection_reason = payload.reason
    app.rejected_at = datetime.now(UTC)

    activity = ApplicationActivity(
        application_id=app.id,
        organization_id=ctx.org_id,
        actor_id=ctx.user.id,
        actor_name=ctx.user.full_name,
        activity_type="rejected",
        metadata={"reason": payload.reason},
    )
    db.add(activity)
    await db.commit()

    if payload.send_email:
        task_send_rejection.delay(
            app.candidate.email,
            app.candidate.full_name,
            app.job.title,
            ctx.organization.name,
            payload.custom_email_body,
        )

    return {"status": "rejected"}


@router.post("/{application_id}/notes")
async def add_note(
    application_id: uuid.UUID,
    payload: AddNoteRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER, OrgRole.INTERVIEWER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.id == application_id, Application.organization_id == ctx.org_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    activity = ApplicationActivity(
        application_id=app.id,
        organization_id=ctx.org_id,
        actor_id=ctx.user.id,
        actor_name=ctx.user.full_name,
        activity_type="note_added",
        metadata={"note": payload.note},
    )
    db.add(activity)
    await db.commit()
    return {"message": "Note added"}


@router.post("/{application_id}/trigger-ai-scoring")
async def trigger_ai_scoring(
    application_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("ai_fit_analysis")
    result = await db.execute(
        select(Application).where(Application.id == application_id, Application.organization_id == ctx.org_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    task_score_application.delay(str(application_id), str(ctx.org_id))
    return {"message": "AI scoring queued"}
