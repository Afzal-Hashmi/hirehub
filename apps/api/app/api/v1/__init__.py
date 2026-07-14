from fastapi import APIRouter

from app.api.v1 import ai, applications, auth, candidates, interviews, notifications, organizations, superadmin, jobs

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(organizations.router)
router.include_router(jobs.router)
router.include_router(candidates.router)
router.include_router(applications.router)
router.include_router(interviews.router)
router.include_router(ai.router)
router.include_router(notifications.router)
router.include_router(superadmin.router)
