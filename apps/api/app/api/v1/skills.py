"""Custom Skills — tenant-specific AI-generated skill documents stored as markdown."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrgContext, require_roles
from app.database import get_db
from app.models.skill import CustomSkill
from app.models.user import OrgRole
from app.services.ai_service import generate_skill_markdown

router = APIRouter(prefix="/skills", tags=["skills"])


class GenerateSkillRequest(BaseModel):
    prompt: str


class SaveSkillRequest(BaseModel):
    name: str
    description: str | None = None
    source_prompt: str
    content: str


class UpdateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None


def _skill_out(skill: CustomSkill) -> dict:
    return {
        "id": str(skill.id),
        "organization_id": str(skill.organization_id),
        "created_by": str(skill.created_by),
        "name": skill.name,
        "description": skill.description,
        "source_prompt": skill.source_prompt,
        "content": skill.content,
        "created_at": skill.created_at.isoformat(),
        "updated_at": skill.updated_at.isoformat(),
    }


@router.post("/generate")
async def generate_skill(
    payload: GenerateSkillRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
):
    ctx.require_feature("custom_skills")
    result = generate_skill_markdown(
        prompt=payload.prompt,
        org_name=ctx.organization.name,
    )
    return result


@router.post("")
async def create_skill(
    payload: SaveSkillRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("custom_skills")
    skill = CustomSkill(
        organization_id=ctx.org_id,
        created_by=ctx.user.id,
        name=payload.name,
        description=payload.description,
        source_prompt=payload.source_prompt,
        content=payload.content,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _skill_out(skill)


@router.get("")
async def list_skills(
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER, OrgRole.INTERVIEWER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("custom_skills")
    result = await db.execute(
        select(CustomSkill)
        .where(CustomSkill.organization_id == ctx.org_id)
        .order_by(CustomSkill.created_at.desc())
    )
    skills = result.scalars().all()
    return [_skill_out(s) for s in skills]


@router.get("/{skill_id}")
async def get_skill(
    skill_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER, OrgRole.INTERVIEWER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("custom_skills")
    skill = await db.get(CustomSkill, skill_id)
    if not skill or skill.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _skill_out(skill)


@router.patch("/{skill_id}")
async def update_skill(
    skill_id: uuid.UUID,
    payload: UpdateSkillRequest,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("custom_skills")
    skill = await db.get(CustomSkill, skill_id)
    if not skill or skill.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    if payload.name is not None:
        skill.name = payload.name
    if payload.description is not None:
        skill.description = payload.description
    if payload.content is not None:
        skill.content = payload.content
    await db.commit()
    await db.refresh(skill)
    return _skill_out(skill)


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: uuid.UUID,
    ctx: OrgContext = Depends(require_roles(OrgRole.OWNER, OrgRole.RECRUITER)),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_feature("custom_skills")
    skill = await db.get(CustomSkill, skill_id)
    if not skill or skill.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
    return {"ok": True}
