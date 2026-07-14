"""Periodic Celery tasks for reminders and cleanup."""
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.config import settings
from app.models.interview import Interview, InterviewStatus
from app.models.invite import InviteStatus, OrganizationInvite
from app.services.email_service import send_email
from app.workers.celery_app import celery_app


def _get_sync_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(settings.DATABASE_URL_SYNC)
    return sessionmaker(engine)()


@celery_app.task(name="notifications.interview_reminders")
def send_interview_reminders():
    """Send reminders for interviews happening in the next 25 hours (catches 24h window)."""
    from datetime import timedelta

    db = _get_sync_db()
    try:
        now = datetime.now(UTC)
        window_start = now + timedelta(hours=1)
        window_end = now + timedelta(hours=25)

        upcoming = db.execute(
            select(Interview).where(
                Interview.scheduled_at.between(window_start, window_end),
                Interview.status.in_([InterviewStatus.SCHEDULED, InterviewStatus.CONFIRMED]),
            )
        ).scalars().all()

        for interview in upcoming:
            # TODO: fetch candidate info and send reminder
            pass

        return {"sent": len(upcoming)}
    finally:
        db.close()


@celery_app.task(name="notifications.expire_invites")
def expire_stale_invites():
    db = _get_sync_db()
    try:
        now = datetime.now(UTC)
        result = db.execute(
            update(OrganizationInvite)
            .where(
                OrganizationInvite.expires_at < now,
                OrganizationInvite.status == InviteStatus.PENDING,
            )
            .values(status=InviteStatus.EXPIRED)
        )
        db.commit()
        return {"expired": result.rowcount}
    finally:
        db.close()
