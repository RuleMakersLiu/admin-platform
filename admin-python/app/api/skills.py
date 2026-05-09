"""Skills 管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any

from app.ai.skills import skill_registry, skill_manager

router = APIRouter(prefix="/skills", tags=["Skills技能系统"])


class ExecuteSkillRequest(BaseModel):
    skill_id: str
    params: dict = {}


class ManageSkillRequest(BaseModel):
    action: str  # create, edit, patch, delete
    name: str
    content: Optional[str] = None
    category: Optional[str] = None
    old_string: Optional[str] = None
    new_string: Optional[str] = None


@router.get("/list")
async def list_skills(
    category: Optional[str] = None,
    agent_type: Optional[str] = None,
):
    """列出所有可用 Skills"""
    skills = skill_registry.list_skills(category=category, agent_type=agent_type)
    return {
        "code": 200,
        "data": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "agent_type": s.agent_type,
                "input_schema": s.input_schema,
                "output_schema": s.output_schema,
                "version": s.version,
            }
            for s in skills
        ],
    }


@router.get("/toolsets")
async def list_toolsets():
    """列出所有工具集"""
    from app.ai.toolsets import get_all_toolsets
    return {"code": 200, "data": get_all_toolsets()}


@router.get("/toolsets/{name}")
async def get_toolset(name: str):
    """获取工具集详情"""
    from app.ai.toolsets import get_toolset_info
    info = get_toolset_info(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Toolset '{name}' not found")
    return {"code": 200, "data": info}


@router.get("/{skill_id}")
async def get_skill(skill_id: str):
    """获取 Skill 详情"""
    skill = skill_registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    return {
        "code": 200,
        "data": {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "agent_type": skill.agent_type,
            "input_schema": skill.input_schema,
            "output_schema": skill.output_schema,
            "examples": skill.examples,
            "version": skill.version,
        },
    }


@router.get("/{skill_id}/view")
async def view_skill(skill_id: str):
    """获取技能完整详情（含指令）"""
    result = skill_registry.view_skill(skill_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return {"code": 200, "data": result}


@router.post("/execute")
async def execute_skill(req: ExecuteSkillRequest):
    """执行 Skill"""
    result = await skill_registry.execute(req.skill_id, **req.params)
    return {
        "code": 200 if result.status == "completed" else 500,
        "data": {
            "execution_id": result.execution_id,
            "status": result.status,
            "output": result.output,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        },
    }


@router.post("/manage")
async def manage_skill(req: ManageSkillRequest):
    """创建/编辑/删除技能（Agent自我完善）"""
    if req.action == "create":
        if not req.content:
            raise HTTPException(status_code=400, detail="content required for create")
        result = skill_manager.create_skill(req.name, req.content, req.category)
    elif req.action == "edit":
        if not req.content:
            raise HTTPException(status_code=400, detail="content required for edit")
        result = skill_manager.edit_skill(req.name, req.content)
    elif req.action == "patch":
        if not req.old_string:
            raise HTTPException(status_code=400, detail="old_string required for patch")
        result = skill_manager.patch_skill(req.name, req.old_string, req.new_string or "")
    elif req.action == "delete":
        result = skill_manager.delete_skill(req.name)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return {"code": 200, "data": result}
