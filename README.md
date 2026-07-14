# HireHub

Multi-tenant SaaS Applicant Tracking System (ATS) — job pipelines, candidate management, interview
scheduling, and AI-assisted screening, with organization-scoped feature flags and a super-admin control
panel.

## Architecture

Monorepo with two apps orchestrated via Docker Compose:

- **`apps/api`** — FastAPI backend (async SQLAlchemy + PostgreSQL, Celery + Redis for background jobs)
- **`apps/web`** — Next.js frontend (App Router, React Query, Zustand, Radix UI, Tailwind)

```
hirehub/
├── apps/
│   ├── api/          FastAPI backend
│   │   ├── app/
│   │   │   ├── api/v1/       Route modules (auth, jobs, candidates, applications, interviews,
│   │   │   │                 organizations, skills, ai, notifications, superadmin)
│   │   │   ├── core/         Config, security, DB session
│   │   │   ├── models/       SQLAlchemy models
│   │   │   ├── schemas/      Pydantic schemas
│   │   │   ├── services/     Business logic
│   │   │   ├── templates/    Email templates
│   │   │   └── workers/      Celery tasks
│   │   └── alembic/          DB migrations
│   └── web/          Next.js frontend
│       └── src/app/
│           ├── (auth)/       Login / register
│           ├── (dashboard)/  Jobs, pipeline, candidates, interviews, analytics, team, settings
│           ├── (superadmin)/ Organizations, feature flags, super-admin console
│           └── portal/[orgSlug]/  Public org-scoped candidate portal
├── docker/
└── docker-compose.yml
```

## Key features

- **Multi-tenant** — organizations are isolated by slug; a public candidate-facing portal is served per
  org at `portal/[orgSlug]`.
- **Org-scoped feature flags** — features can be toggled per organization from the super-admin panel.
- **Super-admin panel** — cross-org visibility into organizations and feature flag management.
- **AI-assisted workflows** — resume/document parsing and screening support via Anthropic's Claude API.
- **Full ATS pipeline** — jobs, candidates, applications, interview scheduling, and analytics.
- **Background processing** — Celery + Redis + Flower for async jobs (emails, notifications, AI tasks).
- **Integrations** — SendGrid (email), Slack & Twilio (notifications), Google Calendar (interview
  scheduling), S3-compatible storage for documents.

## Tech stack

| Layer      | Stack                                                                 |
|------------|------------------------------------------------------------------------|
| Backend    | FastAPI, SQLAlchemy (async), PostgreSQL, Alembic, Celery, Redis        |
| Frontend   | Next.js 15, React 19, React Query, Zustand, Radix UI, Tailwind CSS     |
| Auth       | NextAuth, JWT (python-jose), OAuth (Authlib)                          |
| AI         | Anthropic Claude API                                                   |
| Infra      | Docker Compose (Postgres, Redis, API, worker, beat, Flower, web, Nginx)|

## Getting started

1. Copy the environment template and fill in the required secrets:
   ```bash
   cp .env.example .env
   ```
2. Start the full stack:
   ```bash
   docker compose up --build
   ```
   This brings up Postgres, Redis, the FastAPI API, Celery worker + beat, Flower (Celery monitoring), the
   Next.js web app, and Nginx.
3. Run database migrations (from `apps/api`):
   ```bash
   alembic upgrade head
   ```

## Services (docker-compose)

- `postgres` — primary database
- `redis` — Celery broker/backend
- `api` — FastAPI application
- `worker` — Celery worker (background jobs, AI processing, notifications)
- `beat` — Celery beat (scheduled tasks)
- `flower` — Celery task monitoring UI
- `web` — Next.js frontend
- `nginx` — reverse proxy
