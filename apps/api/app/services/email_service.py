"""SendGrid email delivery with Jinja2 HTML templates."""
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config import settings

logger = logging.getLogger(__name__)

_template_dir = Path(__file__).parent.parent / "templates" / "email"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_template_dir)),
    autoescape=select_autoescape(["html"]),
)

sg = SendGridAPIClient(settings.SENDGRID_API_KEY) if settings.SENDGRID_API_KEY else None


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_content: str,
    from_email: str | None = None,
    from_name: str | None = None,
) -> bool:
    if not sg:
        logger.warning("SendGrid not configured — email not sent to %s", to_email)
        return False
    try:
        message = Mail(
            from_email=(from_email or settings.EMAIL_FROM, from_name or settings.EMAIL_FROM_NAME),
            to_emails=(to_email, to_name),
            subject=subject,
            html_content=html_content,
        )
        sg.send(message)
        return True
    except Exception as exc:
        logger.error("SendGrid error sending to %s: %s", to_email, exc)
        return False


def render_template(template_name: str, context: dict) -> str:
    try:
        template = _jinja_env.get_template(f"{template_name}.html")
        return template.render(**context)
    except Exception:
        # Fallback to plain text wrapped in minimal HTML
        return f"<p>{context.get('body', '')}</p>"


def send_application_received(candidate_email: str, candidate_name: str, job_title: str, company_name: str) -> bool:
    html = render_template(
        "application_received",
        {"candidate_name": candidate_name, "job_title": job_title, "company_name": company_name},
    )
    return send_email(candidate_email, candidate_name, f"Application received — {job_title} at {company_name}", html)


def send_interview_invitation(
    candidate_email: str,
    candidate_name: str,
    job_title: str,
    company_name: str,
    interview_time: str,
    interview_link: str,
    interviewer_name: str,
    duration_minutes: int = 60,
) -> bool:
    html = render_template(
        "interview_invitation",
        {
            "candidate_name": candidate_name,
            "job_title": job_title,
            "company_name": company_name,
            "interview_time": interview_time,
            "interview_link": interview_link,
            "interviewer_name": interviewer_name,
            "duration_minutes": duration_minutes,
        },
    )
    return send_email(
        candidate_email,
        candidate_name,
        f"Interview scheduled — {job_title} at {company_name}",
        html,
    )


def send_rejection(
    candidate_email: str, candidate_name: str, job_title: str, company_name: str, custom_body: str | None = None
) -> bool:
    html = render_template(
        "rejection",
        {
            "candidate_name": candidate_name,
            "job_title": job_title,
            "company_name": company_name,
            "custom_body": custom_body,
        },
    )
    return send_email(candidate_email, candidate_name, f"Update on your application — {job_title}", html)


def send_offer(
    candidate_email: str,
    candidate_name: str,
    job_title: str,
    company_name: str,
    offer_letter_url: str,
    deadline: str,
) -> bool:
    html = render_template(
        "offer",
        {
            "candidate_name": candidate_name,
            "job_title": job_title,
            "company_name": company_name,
            "offer_letter_url": offer_letter_url,
            "deadline": deadline,
        },
    )
    return send_email(candidate_email, candidate_name, f"Offer letter — {job_title} at {company_name}", html)


def send_team_invite(invitee_email: str, invited_by_name: str, org_name: str, invite_url: str) -> bool:
    html = render_template(
        "team_invite",
        {"invited_by_name": invited_by_name, "org_name": org_name, "invite_url": invite_url},
    )
    return send_email(invitee_email, "", f"You're invited to join {org_name} on HireHub", html)


def send_self_booking_link(
    candidate_email: str, candidate_name: str, job_title: str, company_name: str, booking_url: str
) -> bool:
    html = render_template(
        "self_booking",
        {
            "candidate_name": candidate_name,
            "job_title": job_title,
            "company_name": company_name,
            "booking_url": booking_url,
        },
    )
    return send_email(candidate_email, candidate_name, f"Schedule your interview — {job_title}", html)
