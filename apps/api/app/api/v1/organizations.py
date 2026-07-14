"""Organization CRUD + invite management + feature flag read endpoint for org owners."""
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr
from python_slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrgContext, get_current_user, get_org_context, require_roles
from app.database import get_db
from app.models.invite import InviteStatus, OrganizationInvite
from app.models.organization import Organization, OrganizationFeatureFlags
from app.models.user import OrgRole, User, UserOrganizationMembership
from app.workers.tasks.email_tasks import task_send_team_invite

router = APIRouter(prefix="/organizations", tags=["organizations"])


class CreateOrgRequest(BaseModel):
    name: str
    website: str | None = None
    industry: str | None = None
    size: str | None = None


class UpdateOrgRequest(BaseModel):
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    size: str | None = None
    description: str | None = None
    brand_color: str | None = None


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.VIEWER


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: CreateOrgRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Any authenticated user can create a new organization and becomes its owner."""
    base_slug = slugify(payload.name)
    slug = base_slug
    counter = 1
    while (await db.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none():
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = Organization(name=payload.name, slug=slug, website=payload.website,
                       industry=payload.industry, size=payload.size)
    db.add(org)
    await db.flush()

    flags = OrganizationFeatureFlags(
        organization_id=org.id,
        flags=OrganizationFeatureFlags.DEFAULT_FLAGS,
    )
    db.add(flags)

    membership = UserOrganizationMembership(
        user_id=current_user.id,
        organization_id=org.id,
        role=OrgRole.OWNER,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(org)

    return {"id": str(org.id), "name": org.name, "slug": org.slug, "role": "owner"}


@router.get("/{org_id}")
async def get_organization(ctx: OrgContext = Depends(get_org_context)):
    org = ctx.organization
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "logo_url": org.logo_url,
        "website": org.website,
        "description": org.description,
        "industry": org.industry,
        "size": org.size,
        "brand_color": org.brand_color,
        "max_seats": org.max_seats,
        "is_active": org.is_active,
    }


@router.patch("/{org_id}")
async def update_organization(
    payload: UpdateOrgRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    org = ctx.organization
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(org, field, value)
    db.add(org)
    await db.commit()
    return {"id": str(org.id), "name": org.name}


@router.get("/{org_id}/members")
async def list_members(ctx: OrgContext = Depends(get_org_context), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserOrganizationMembership, User)
        .join(User, User.id == UserOrganizationMembership.user_id)
        .where(UserOrganizationMembership.organization_id == ctx.org_id)
    )
    return [
        {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "role": mem.role,
            "joined_at": mem.joined_at.isoformat(),
        }
        for mem, user in result.all()
    ]


@router.post("/{org_id}/invite")
async def invite_member(
    payload: InviteMemberRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    """Invite a new team member. Enforces max_seats limit."""
    # Count current members (excluding owner)
    member_count = await db.scalar(
        select(func.count()).where(
            UserOrganizationMembership.organization_id == ctx.org_id,
            UserOrganizationMembership.role != OrgRole.OWNER,
        )
    )
    pending_invites = await db.scalar(
        select(func.count()).where(
            OrganizationInvite.organization_id == ctx.org_id,
            OrganizationInvite.status == InviteStatus.PENDING,
        )
    )
    if (member_count + pending_invites) >= ctx.organization.max_seats:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Seat limit reached ({ctx.organization.max_seats}). Contact support to increase.",
        )

    # Check if already a member
    existing = await db.scalar(
        select(func.count())
        .select_from(UserOrganizationMembership)
        .join(User, User.id == UserOrganizationMembership.user_id)
        .where(
            UserOrganizationMembership.organization_id == ctx.org_id,
            User.email == payload.email,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

    token = secrets.token_urlsafe(32)
    invite = OrganizationInvite(
        organization_id=ctx.org_id,
        invited_by=ctx.user.id,
        email=payload.email,
        role=payload.role,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()

    invite_url = f"{settings.NEXT_PUBLIC_APP_URL}/invite/{token}"
    task_send_team_invite.delay(
        payload.email, ctx.user.full_name, ctx.organization.name, invite_url
    )

    return {"message": "Invite sent", "expires_at": invite.expires_at.isoformat()}


@router.post("/invite/accept/{token}")
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrganizationInvite).where(
            OrganizationInvite.token == token,
            OrganizationInvite.status == InviteStatus.PENDING,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found or already used")

    if invite.expires_at < datetime.now(UTC):
        invite.status = InviteStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite has expired")

    if invite.email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invite was sent to a different email address",
        )

    membership = UserOrganizationMembership(
        user_id=current_user.id,
        organization_id=invite.organization_id,
        role=invite.role,
    )
    db.add(membership)

    invite.status = InviteStatus.ACCEPTED
    invite.accepted_at = datetime.now(UTC)
    await db.commit()

    return {"message": "Joined organization", "organization_id": str(invite.organization_id)}


@router.get("/{org_id}/feature-flags")
async def get_feature_flags(ctx: OrgContext = Depends(require_roles(OrgRole.OWNER))):
    return ctx.feature_flags.flags
