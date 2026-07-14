"""
Unified notification dispatch — sends in-app + Slack + SMS/WhatsApp.
Routes are determined by per-member preferences and org feature flags.
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)


async def create_in_app_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str | None = None,
    action_url: str | None = None,
    metadata: dict | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        organization_id=organization_id,
        type=type,
        title=title,
        body=body,
        action_url=action_url,
        metadata=metadata,
    )
    db.add(notification)
    await db.flush()
    return notification


def send_slack_notification(webhook_url: str, text: str, blocks: list | None = None) -> bool:
    try:
        import httpx

        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        resp = httpx.post(webhook_url, json=payload, timeout=5)
        return resp.status_code == 200
    except Exception as exc:
        logger.error("Slack notification failed: %s", exc)
        return False


def send_sms(to_number: str, message: str) -> bool:
    from app.config import settings

    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to_number,
        )
        return True
    except Exception as exc:
        logger.error("SMS send failed to %s: %s", to_number, exc)
        return False


def send_whatsapp(to_number: str, message: str) -> bool:
    from app.config import settings

    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{to_number}",
        )
        return True
    except Exception as exc:
        logger.error("WhatsApp send failed to %s: %s", to_number, exc)
        return False
