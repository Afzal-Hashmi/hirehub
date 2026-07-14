from celery import Celery

from app.config import settings

celery_app = Celery(
    "hirehub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.email_tasks",
        "app.workers.tasks.ai_tasks",
        "app.workers.tasks.notification_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Send interview reminders 24h and 1h before scheduled time
        "interview-reminders-hourly": {
            "task": "app.workers.tasks.notification_tasks.send_interview_reminders",
            "schedule": 3600.0,
        },
        # Expire stale invites daily
        "expire-invites-daily": {
            "task": "app.workers.tasks.notification_tasks.expire_stale_invites",
            "schedule": 86400.0,
        },
    },
)
