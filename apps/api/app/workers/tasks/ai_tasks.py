"""Celery tasks for AI operations — offloaded from HTTP request cycle."""
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.services.ai_service import parse_resume, score_candidate_fit
from app.workers.celery_app import celery_app


def _get_sync_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(settings.DATABASE_URL_SYNC)
    return sessionmaker(engine)()


@celery_app.task(name="ai.parse_resume", bind=True, max_retries=3)
def task_parse_resume(self, candidate_id: str, organization_id: str):
    db: Session = _get_sync_db()
    try:
        candidate = db.execute(
            select(Candidate).where(
                Candidate.id == uuid.UUID(candidate_id),
                Candidate.organization_id == uuid.UUID(organization_id),
            )
        ).scalar_one_or_none()

        if not candidate or not candidate.resume_text:
            return {"status": "skipped", "reason": "no resume text"}

        parsed = parse_resume(candidate.resume_text)

        db.execute(
            update(Candidate)
            .where(Candidate.id == candidate.id)
            .values(
                parsed_skills=parsed.get("skills"),
                parsed_experience_years=parsed.get("experience_years"),
                parsed_education=parsed.get("education"),
                parsed_work_history=parsed.get("work_history"),
                ai_summary=parsed.get("summary"),
            )
        )
        db.commit()
        return {"status": "ok", "candidate_id": candidate_id}
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


@celery_app.task(name="ai.score_application", bind=True, max_retries=3)
def task_score_application(self, application_id: str, organization_id: str):
    db: Session = _get_sync_db()
    try:
        row = db.execute(
            select(Application, Candidate, Job)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.id == uuid.UUID(application_id),
                Application.organization_id == uuid.UUID(organization_id),
            )
        ).first()

        if not row:
            return {"status": "not_found"}

        application, candidate, job = row

        if not candidate.resume_text:
            return {"status": "skipped", "reason": "no resume text"}

        result = score_candidate_fit(
            resume_text=candidate.resume_text,
            job_title=job.title,
            job_description=job.description,
            requirements=job.requirements or "",
            skills_required=job.skills_required or [],
        )

        db.execute(
            update(Application)
            .where(Application.id == application.id)
            .values(ai_score=result.get("score"), ai_fit_analysis=result)
        )
        db.commit()
        return {"status": "ok", "score": result.get("score")}
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()
