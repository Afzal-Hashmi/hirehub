"""
FastAPI dependency injection — the heart of multi-tenant security.

Every protected route gets the current user + their org membership injected.
All DB queries in route handlers must filter by org_id from these deps.
"""
import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token
from app.database import get_db
from app.models.organization import Organization, OrganizationFeatureFlags
from app.models.user import GlobalRole, OrgRole, User, UserOrganizationMembership

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_current_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current_user


class OrgContext:
    """Resolved org membership for the current user in the requested organization."""

    def __init__(
        self,
        user: User,
        organization: Organization,
        membership: UserOrganizationMembership,
        feature_flags: OrganizationFeatureFlags,
    ):
        self.user = user
        self.organization = organization
        self.membership = membership
        self.feature_flags = feature_flags

    @property
    def org_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def role(self) -> OrgRole:
        return self.membership.role

    def require_role(self, *roles: OrgRole) -> None:
        if self.role not in roles and not self.user.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {[r.value for r in roles]}",
            )

    def require_feature(self, flag: str) -> None:
        if not self.feature_flags.get(flag):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{flag}' is not enabled for your organization",
            )


async def get_org_context(
    x_organization_id: str = Header(..., description="Organization UUID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgContext:
    try:
        org_id = uuid.UUID(x_organization_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization ID")

    # Super admins can access any org
    if current_user.is_super_admin:
        result = await db.execute(
            select(Organization)
            .where(Organization.id == org_id, Organization.is_active == True)
            .options(selectinload(Organization.feature_flags))
        )
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        # Create a synthetic "owner" membership for super admins
        synthetic_membership = UserOrganizationMembership(
            user_id=current_user.id, organization_id=org.id, role=OrgRole.OWNER
        )
        flags = org.feature_flags or OrganizationFeatureFlags(
            organization_id=org.id, flags=OrganizationFeatureFlags.DEFAULT_FLAGS
        )
        return OrgContext(current_user, org, synthetic_membership, flags)

    result = await db.execute(
        select(UserOrganizationMembership, Organization, OrganizationFeatureFlags)
        .join(Organization, Organization.id == UserOrganizationMembership.organization_id)
        .outerjoin(OrganizationFeatureFlags, OrganizationFeatureFlags.organization_id == Organization.id)
        .where(
            UserOrganizationMembership.user_id == current_user.id,
            UserOrganizationMembership.organization_id == org_id,
            Organization.is_active == True,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    membership, org, flags = row
    if not flags:
        flags = OrganizationFeatureFlags(
            organization_id=org.id, flags=OrganizationFeatureFlags.DEFAULT_FLAGS
        )
    return OrgContext(current_user, org, membership, flags)


def require_roles(*roles: OrgRole):
    """Factory that returns a dep enforcing minimum role."""

    async def _check(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        ctx.require_role(*roles)
        return ctx

    return _check


def require_feature(flag: str):
    """Factory that returns a dep enforcing a feature flag is enabled."""

    async def _check(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        ctx.require_feature(flag)
        return ctx

    return _check
