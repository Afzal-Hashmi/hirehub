"""Super-admin endpoints — full platform management. Requires global SUPER_ADMIN role."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_super_admin
from app.database import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.interview import Interview
from app.models.job import Job
from app.models.organization import Organization, OrganizationFeatureFlags
from app.models.user import GlobalRole, User, UserOrganizationMembership

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


class UpdateFeatureFlagsRequest(BaseModel):
    flags: dict[str, bool]


class UpdateOrgSeatsRequest(BaseModel):
    max_seats: int


class UpdateOrgStatusRequest(BaseModel):
    is_active: bool


@router.get("/stats")
async def platform_stats(
    _=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard stats across all organizations."""
    org_count = await db.scalar(select(func.count()).select_from(Organization))
    user_count = await db.scalar(select(func.count()).select_from(User))
    job_count = await db.scalar(select(func.count()).select_from(Job))
    candidate_count = await db.scalar(select(func.count()).select_from(Candidate))
    application_count = await db.scalar(select(func.count()).select_from(Application))
    interview_count = await db.scalar(select(func.count()).select_from(Interview))

    return {
        "organizations": org_count,
        "users": user_count,
        "jobs": job_count,
        "candidates": candidate_count,
        "applications": application_count,
        "interviews": interview_count,
    }


@router.get("/organizations")
async def list_all_organizations(
    page: int = 1,
    limit: int = 20,
    _=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    result = await db.execute(
        select(Organization)
        .options(selectinload(Organization.feature_flags))
        .order_by(Organization.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    orgs = result.scalars().all()
    total = await db.scalar(select(func.count()).select_from(Organization))

    items = []
    for org in orgs:
        member_count = await db.scalar(
            select(func.count()).where(UserOrganizationMembership.organization_id == org.id)
        )
        items.append({
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "is_active": org.is_active,
            "max_seats": org.max_seats,
            "member_count": member_count,
            "created_at": org.created_at.isoformat(),
            "feature_flags": org.feature_flags.flags if org.feature_flags else {},
        })

    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/organizations/{org_id}")
async def get_organization_detail(
    org_id: uuid.UUID,
    _=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Organization)
        .where(Organization.id == org_id)
        .options(selectinload(Organization.feature_flags), selectinload(Organization.memberships))
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    jobs_count = await db.scalar(select(func.count()).where(Job.organization_id == org_id))
    candidates_count = await db.scalar(select(func.count()).where(Candidate.organization_id == org_id))

    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "logo_url": org.logo_url,
        "website": org.website,
        "industry": org.industry,
        "size": org.size,
        "is_active": org.is_active,
        "max_seats": org.max_seats,
        "member_count": len(org.memberships),
        "jobs_count": jobs_count,
        "candidates_count": candidates_count,
        "created_at": org.created_at.isoformat(),
        "feature_flags": org.feature_flags.flags if org.feature_flags else OrganizationFeatureFlags.DEFAULT_FLAGS,
    }


@router.patch("/organizations/{org_id}/feature-flags")
async def update_feature_flags(
    org_id: uuid.UUID,
    payload: UpdateFeatureFlagsRequest,
    current_user: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Merge-update feature flags for an org. Only provided keys are changed."""
    result = await db.execute(
        select(OrganizationFeatureFlags).where(OrganizationFeatureFlags.organization_id == org_id)
    )
    flags = result.scalar_one_or_none()
    if not flags:
        org = await db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        flags = OrganizationFeatureFlags(
            organization_id=org_id,
            flags={**OrganizationFeatureFlags.DEFAULT_FLAGS, **payload.flags},
            updated_by=current_user.id,
        )
        db.add(flags)
    else:
        flags.flags = {**flags.flags, **payload.flags}
        flags.updated_by = current_user.id

    await db.commit()
    return {"flags": flags.flags}


@router.patch("/organizations/{org_id}/seats")
async def update_org_seats(
    org_id: uuid.UUID,
    payload: UpdateOrgSeatsRequest,
    _=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    org.max_seats = payload.max_seats
    await db.commit()
    return {"max_seats": org.max_seats}


@router.patch("/organizations/{org_id}/status")
async def update_org_status(
    org_id: uuid.UUID,
    payload: UpdateOrgStatusRequest,
    _=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    org.is_active = payload.is_active
    await db.commit()
    return {"is_active": org.is_active}


@router.get("/users")
async def list_all_users(
    page: int = 1,
    limit: int = 20,
    _=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()
    total = await db.scalar(select(func.count()).select_from(User))
    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "global_role": u.global_role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": total,
    }


@router.patch("/users/{user_id}/promote-super-admin")
async def promote_to_super_admin(
    user_id: uuid.UUID,
    _=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.global_role = GlobalRole.SUPER_ADMIN
    await db.commit()
    return {"message": f"{user.email} is now a super admin"}
