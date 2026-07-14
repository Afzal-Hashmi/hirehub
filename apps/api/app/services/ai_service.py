"""
All Claude API calls live here. Each method is self-contained and can be
called from both sync Celery tasks (via asyncio.run) and async FastAPI routes.
"""
import json
import re

import anthropic

from app.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-6"


def _extract_json(text: str) -> dict | list:
    """Pull JSON out of a Claude response that may include prose."""
    match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        return json.loads(match.group(0))
    match = re.search(r"\[[\s\S]+\]", text)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No JSON found in response: {text[:200]}")


def parse_resume(resume_text: str) -> dict:
    """
    Extract structured candidate info from raw resume text.
    Returns: skills, experience_years, education, work_history, summary
    """
    prompt = f"""Parse the following resume and extract structured information.

Resume text:
<resume>
{resume_text[:8000]}
</resume>

Return ONLY valid JSON (no prose) in this exact schema:
{{
  "skills": ["skill1", "skill2"],
  "experience_years": 5.0,
  "education": [
    {{"degree": "BS Computer Science", "institution": "MIT", "year": 2018}}
  ],
  "work_history": [
    {{
      "company": "Acme Corp",
      "title": "Senior Engineer",
      "start_date": "2020-01",
      "end_date": "2023-06",
      "description": "..."
    }}
  ],
  "summary": "2-3 sentence professional summary"
}}"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(message.content[0].text)


def score_candidate_fit(
    resume_text: str,
    job_title: str,
    job_description: str,
    requirements: str,
    skills_required: list[str],
) -> dict:
    """
    Score how well a candidate fits a job (0-100) and explain.
    Returns: score, strengths, gaps, recommendation
    """
    skills_str = ", ".join(skills_required) if skills_required else "Not specified"
    prompt = f"""You are an expert technical recruiter. Evaluate this candidate's fit for the role.

JOB: {job_title}
DESCRIPTION: {job_description[:2000]}
REQUIREMENTS: {requirements[:1000] if requirements else 'Not specified'}
REQUIRED SKILLS: {skills_str}

CANDIDATE RESUME:
<resume>
{resume_text[:5000]}
</resume>

Return ONLY valid JSON:
{{
  "score": 78,
  "strengths": ["Has 5 years of Python experience", "Led similar team sizes"],
  "gaps": ["No cloud infrastructure experience", "Missing required certification"],
  "recommendation": "Strong candidate with minor skill gaps. Recommend phone screen.",
  "hiring_decision": "recommend"
}}

hiring_decision must be one of: "strong_recommend", "recommend", "neutral", "not_recommend", "strong_not_recommend"
score is 0-100."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(message.content[0].text)


def generate_interview_questions(
    job_title: str,
    job_description: str,
    interview_type: str,
    candidate_resume_text: str | None = None,
    num_questions: int = 8,
) -> list[dict]:
    """
    Generate tailored interview questions.
    Returns list of {question, type, rationale, follow_up}
    """
    candidate_context = ""
    if candidate_resume_text:
        candidate_context = f"""
CANDIDATE BACKGROUND (use to personalize questions):
{candidate_resume_text[:2000]}"""

    prompt = f"""Generate {num_questions} interview questions for this role and interview type.

ROLE: {job_title}
INTERVIEW TYPE: {interview_type}
JOB DESCRIPTION: {job_description[:1500]}{candidate_context}

Return ONLY valid JSON array:
[
  {{
    "question": "Tell me about a time you led a cross-functional project under a tight deadline.",
    "type": "behavioral",
    "rationale": "Tests leadership and time management from job requirements.",
    "follow_up": "What would you do differently if you could repeat that experience?"
  }}
]

question types: behavioral, technical, situational, culture_fit, role_specific"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(message.content[0].text)


def draft_email(
    email_type: str,
    candidate_name: str,
    job_title: str,
    company_name: str,
    extra_context: dict | None = None,
) -> dict:
    """
    Draft a personalized email to a candidate.
    email_type: application_received | interview_invite | rejection | offer | scheduling
    Returns: {subject, body, tone_note}
    """
    context_str = ""
    if extra_context:
        context_str = f"\nExtra context: {json.dumps(extra_context)}"

    prompt = f"""Draft a professional, warm email to a job candidate.

EMAIL TYPE: {email_type}
CANDIDATE NAME: {candidate_name}
ROLE: {job_title}
COMPANY: {company_name}{context_str}

Return ONLY valid JSON:
{{
  "subject": "Email subject line",
  "body": "Full email body with proper formatting. Use \\n for line breaks.",
  "tone_note": "Brief note about the tone/approach used"
}}

Guidelines:
- Be warm, professional, and human — not corporate-robotic
- For rejections: be kind, leave door open for future opportunities
- For offers: be enthusiastic, include placeholder {{{{OFFER_DETAILS}}}} where salary/terms go
- For interview invites: include placeholder {{{{INTERVIEW_LINK}}}} and {{{{INTERVIEW_TIME}}}}"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(message.content[0].text)


def generate_offer_letter(
    candidate_name: str,
    job_title: str,
    company_name: str,
    start_date: str,
    salary: int,
    currency: str = "USD",
    extra_details: dict | None = None,
) -> str:
    """Generate a professional offer letter. Returns HTML string."""
    details_str = json.dumps(extra_details) if extra_details else ""
    prompt = f"""Generate a professional, legally-neutral offer letter.

CANDIDATE: {candidate_name}
ROLE: {job_title}
COMPANY: {company_name}
START DATE: {start_date}
SALARY: {salary:,} {currency}/year
ADDITIONAL DETAILS: {details_str}

Return a complete offer letter as clean HTML. Use professional formatting.
Include placeholders like [SIGNATORY_NAME] and [SIGNATORY_TITLE] for signature block.
Note at the bottom: "This offer is contingent upon successful background check."
Do NOT include any JSON — return raw HTML only."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def generate_skill_markdown(prompt: str, org_name: str) -> dict:
    """
    Generate a structured markdown skill document from a user prompt.
    Returns: {name, description, content (markdown)}
    """
    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": f"""You are an expert HR and talent-acquisition specialist for {org_name}.
A recruiter has given you this skill description:

<prompt>
{prompt}
</prompt>

Generate a comprehensive, structured skill document in Markdown format.
Include sections: Overview, Key Competencies, Assessment Criteria, Interview Questions, Red Flags, and Resources.
Keep it practical and specific to the context described.

Then return ONLY valid JSON in this exact format (no other text):
{{
  "name": "Short skill name (3-6 words)",
  "description": "One sentence describing this skill",
  "content": "The full markdown document as a string with \\n for newlines"
}}""",
            }
        ],
    )
    return _extract_json(message.content[0].text)


def summarize_job_description(title: str, description: str) -> str:
    """One-paragraph AI summary of a JD — used on the public job board."""
    message = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": f"Summarize this job description in 2-3 engaging sentences for a job board listing. Role: {title}\n\n{description[:3000]}",
            }
        ],
    )
    return message.content[0].text.strip()
