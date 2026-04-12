from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_token
from app.models.template import FlowTemplate
from app.schemas import TemplateCreate, TemplateOut

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


@router.get("", response_model=List[TemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(FlowTemplate).order_by(FlowTemplate.id.desc()))
    return result.scalars().all()


@router.get("/{template_id:int}", response_model=TemplateOut)
async def get_template(
    template_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)
):
    result = await db.execute(select(FlowTemplate).where(FlowTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    return tpl


@router.post("", response_model=TemplateOut)
async def create_template(
    req: TemplateCreate, db: AsyncSession = Depends(get_db), _=Depends(verify_token)
):
    tpl = FlowTemplate(
        app_name=req.app_name,
        name=req.name,
        yaml_content=req.yaml_content,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.put("/{template_id:int}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    req: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(select(FlowTemplate).where(FlowTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    tpl.app_name = req.app_name
    tpl.name = req.name
    tpl.yaml_content = req.yaml_content
    tpl.version += 1
    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.delete("/{template_id:int}")
async def delete_template(
    template_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)
):
    result = await db.execute(select(FlowTemplate).where(FlowTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    await db.delete(tpl)
    await db.commit()
    return {"message": "Deleted"}
