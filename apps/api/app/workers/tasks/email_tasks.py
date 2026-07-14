from app.services.email_service import (
    send_application_received,
    send_interview_invitation,
    send_offer,
    send_rejection,
    send_self_booking_link,
    send_team_invite,
)
from app.workers.celery_app import celery_app


@celery_app.task(name="email.application_received")
def task_send_application_received(candidate_email: str, candidate_name: str, job_title: str, company_name: str):
    send_application_received(candidate_email, candidate_name, job_title, company_name)


@celery_app.task(name="email.interview_invitation")
def task_send_interview_invitation(
    candidate_email: str,
    candidate_name: str,
    job_title: str,
    company_name: str,
    interview_time: str,
    interview_link: str,
    interviewer_name: str,
    duration_minutes: int = 60,
):
    send_interview_invitation(
        candidate_email, candidate_name, job_title, company_name,
        interview_time, interview_link, interviewer_name, duration_minutes,
    )


@celery_app.task(name="email.rejection")
def task_send_rejection(
    candidate_email: str, candidate_name: str, job_title: str, company_name: str, custom_body: str | None = None
):
    send_rejection(candidate_email, candidate_name, job_title, company_name, custom_body)


@celery_app.task(name="email.offer")
def task_send_offer(
    candidate_email: str, candidate_name: str, job_title: str, company_name: str,
    offer_letter_url: str, deadline: str,
):
    send_offer(candidate_email, candidate_name, job_title, company_name, offer_letter_url, deadline)


@celery_app.task(name="email.team_invite")
def task_send_team_invite(invitee_email: str, invited_by_name: str, org_name: str, invite_url: str):
    send_team_invite(invitee_email, invited_by_name, org_name, invite_url)


@celery_app.task(name="email.self_booking")
def task_send_self_booking_link(
    candidate_email: str, candidate_name: str, job_title: str, company_name: str, booking_url: str
):
    send_self_booking_link(candidate_email, candidate_name, job_title, company_name, booking_url)
