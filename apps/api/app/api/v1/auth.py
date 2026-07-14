"""
OAuth2 (Google/GitHub) + JWT auth endpoints.
NextAuth.js on the frontend exchanges the OAuth token here for our own JWT.
"""
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.database import get_db
from app.models.organization import Organization, OrganizationFeatureFlags
from app.models.user import GlobalRole, OrgRole, User, UserOrganizationMembership

router = APIRouter(prefix="/auth", tags=["auth"])


class OAuthExchangeRequest(BaseModel):
    provider: str  # "google" | "github"
    access_token: str
    # NextAuth passes us the raw OAuth access token to verify on our side


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    global_role: str


class RefreshRequest(BaseModel):
    refresh_token: str


async def _get_google_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")
    return resp.json()


async def _get_github_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"token {access_token}"}
        user_resp = await client.get("https://api.github.com/user", headers=headers)
        email_resp = await client.get("https://api.github.com/user/emails", headers=headers)
    if user_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub token")
    user_data = user_resp.json()
    if email_resp.status_code == 200:
        emails = email_resp.json()
        primary = next((e["email"] for e in emails if e.get("primary") and e.get("verified")), None)
        if primary:
            user_data["email"] = primary
    return user_data


@router.post("/oauth/exchange", response_model=TokenResponse)
async def oauth_exchange(payload: OAuthExchangeRequest, db: AsyncSession = Depends(get_db)):
    """Exchange an OAuth provider token for our JWTs. Creates user on first login."""
    if payload.provider == "google":
        info = await _get_google_user_info(payload.access_token)
        email = info.get("email", "")
        full_name = info.get("name", email)
        avatar_url = info.get("picture")
        provider_id = info.get("id")
    elif payload.provider == "github":
        info = await _get_github_user_info(payload.access_token)
        email = info.get("email", "")
        full_name = info.get("name") or info.get("login", email)
        avatar_url = info.get("avatar_url")
        provider_id = str(info.get("id", ""))
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider")

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email not available from provider")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # Check if this is the designated super admin
        global_role = (
            GlobalRole.SUPER_ADMIN if email == settings.SUPER_ADMIN_EMAIL else GlobalRole.USER
        )
        user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            oauth_provider=payload.provider,
            oauth_provider_id=provider_id,
            global_role=global_role,
        )
        db.add(user)
        await db.flush()
    else:
        user.last_login_at = datetime.now(UTC)
        user.avatar_url = avatar_url or user.avatar_url

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        global_role=user.global_role,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise ValueError("not a refresh token")
        user_id = data["sub"]
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        global_role=user.global_role,
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserOrganizationMembership, Organization)
        .join(Organization, Organization.id == UserOrganizationMembership.organization_id)
        .where(UserOrganizationMembership.user_id == current_user.id, Organization.is_active == True)
    )
    memberships = [
        {
            "organization_id": str(org.id),
            "organization_name": org.name,
            "organization_slug": org.slug,
            "organization_logo": org.logo_url,
            "role": mem.role,
        }
        for mem, org in result.all()
    ]
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
        "global_role": current_user.global_role,
        "organizations": memberships,
    }
