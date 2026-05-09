"""智能体协作流程 API"""
import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict

from app.ai.flow_manager import pipeline_manager, STAGE_DEFINITIONS, DEFAULT_STAGE_PROMPTS

router = APIRouter(prefix="/flow", tags=["智能体流程"])


class CreatePipelineRequest(BaseModel):
    project_id: Optional[str] = Field(default="", description="项目ID")
    user_request: str = Field(default="", description="用户需求描述")
    git_config_id: Optional[int] = Field(default=None, description="Git 配置 ID")
    git_repo_url: Optional[str] = Field(default="", description="Git 仓库地址")
    git_branch: Optional[str] = Field(default="main", description="分支名")
    skill_config: Optional[dict] = Field(default=None, description="每阶段 Skill 配置")


class ExecuteStageRequest(BaseModel):
    user_input: Optional[str] = Field(default="", description="用户补充输入")


class ConfirmStageRequest(BaseModel):
    confirmed: bool = Field(..., description="是否确认")
    feedback: Optional[str] = Field(default="", description="修订反馈")


def _get_tenant_id(request: Request) -> int:
    """从请求头获取租户ID"""
    try:
        return int(request.headers.get("X-Tenant-Id", "0"))
    except (ValueError, TypeError):
        return 0


def _get_admin_id(request: Request) -> int:
    """从请求头获取管理员ID"""
    try:
        return int(request.headers.get("X-Admin-Id", "0"))
    except (ValueError, TypeError):
        return 0


@router.post("/pipeline/create")
async def create_pipeline(request: CreatePipelineRequest, http_request: Request):
    """创建开发流水线"""
    try:
        tenant_id = _get_tenant_id(http_request)
        admin_id = _get_admin_id(http_request)
        pipeline_id = await pipeline_manager.create_pipeline(
            project_id=request.project_id,
            user_request=request.user_request,
            tenant_id=tenant_id,
            creator_id=admin_id,
            git_config_id=request.git_config_id,
            git_repo_url=request.git_repo_url,
            git_branch=request.git_branch,
            skill_config=request.skill_config,
        )
        return {
            "code": 200,
            "message": "流水线创建成功",
            "data": {"pipeline_id": pipeline_id, "status": "pending"},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/{pipeline_id}/execute")
async def execute_stage(pipeline_id: str, request: ExecuteStageRequest = None):
    """执行当前流水线阶段"""
    try:
        user_input = request.user_input if request else ""
        result = await pipeline_manager.execute_stage(pipeline_id, user_input)
        return {"code": 200, "message": "阶段执行完成", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/{pipeline_id}/confirm")
async def confirm_stage(pipeline_id: str, request: ConfirmStageRequest):
    """用户确认当前阶段"""
    try:
        result = await pipeline_manager.confirm_stage(
            pipeline_id, request.confirmed, request.feedback,
        )
        return {"code": 200, "message": "确认完成", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{pipeline_id}/status")
async def get_pipeline_status(pipeline_id: str):
    """获取流水线状态"""
    try:
        status = await pipeline_manager.get_pipeline_status(pipeline_id)
        return {"code": 200, "message": "查询成功", "data": status}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/{pipeline_id}/preview")
async def get_preview(pipeline_id: str):
    """获取 UI 预览"""
    try:
        preview = await pipeline_manager.get_preview(pipeline_id)
        return {"code": 200, "message": "查询成功", "data": preview}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/{pipeline_id}/output")
async def get_stage_output(pipeline_id: str, stage: str = ""):
    """获取阶段输出"""
    try:
        output = await pipeline_manager.get_stage_output(pipeline_id, stage)
        return {"code": 200, "message": "查询成功", "data": output}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/list")
async def list_pipelines(http_request: Request):
    """获取流水线列表"""
    tenant_id = _get_tenant_id(http_request)
    pipelines = await pipeline_manager.list_pipelines(tenant_id)
    return {"code": 200, "message": "查询成功", "data": pipelines}


@router.post("/pipeline/{pipeline_id}/rollback")
async def rollback_pipeline(pipeline_id: str):
    """回退到上一阶段"""
    try:
        result = await pipeline_manager.rollback(pipeline_id)
        return {"code": 200, "message": "回退成功", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/{pipeline_id}/files")
async def get_pipeline_files(pipeline_id: str):
    """获取工作区文件列表"""
    import os
    try:
        status = await pipeline_manager.get_pipeline_status(pipeline_id)
        workspace = status.get("workspace_path", "")
        if not workspace or not os.path.isdir(workspace):
            return {"code": 200, "data": {"files": [], "workspace": workspace}}

        files = []
        for root, dirs, filenames in os.walk(workspace):
            # 跳过 .git 目录
            dirs[:] = [d for d in dirs if d != ".git"]
            for fname in filenames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, workspace)
                files.append({
                    "path": rel,
                    "size": os.path.getsize(full),
                })
        return {"code": 200, "data": {"files": files, "workspace": workspace}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/{pipeline_id}/git-status")
async def get_git_status(pipeline_id: str):
    """获取 Git 状态"""
    try:
        status = await pipeline_manager.get_pipeline_status(pipeline_id)
        return {
            "code": 200,
            "data": {
                "repo_url": status.get("git_repo_url", ""),
                "branch": status.get("git_branch", ""),
                "commit_sha": status.get("git_commit_sha", ""),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/{pipeline_id}/deploy-status")
async def get_deploy_status(pipeline_id: str):
    """获取部署任务状态"""
    try:
        status = await pipeline_manager.get_pipeline_status(pipeline_id)
        return {
            "code": 200,
            "data": {
                "deploy_task_id": status.get("deploy_task_id", ""),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/skills")
async def list_pipeline_skills():
    """列出所有可用的 Pipeline Skills"""
    from app.ai.skills import skill_registry
    skills = skill_registry.list_skills()
    return {
        "code": 200,
        "data": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "input_schema": s.input_schema,
                "output_schema": s.output_schema,
            }
            for s in skills
        ],
    }


@router.put("/pipeline/{pipeline_id}/skill-config")
async def update_skill_config(pipeline_id: str, request: Request):
    """更新 Pipeline 的 Skill 配置"""
    import json as json_mod
    from sqlalchemy import select
    from app.core.database import async_session_maker
    from app.models.agent_models import DevPipeline

    body = await request.json()
    skill_config = body.get("skill_config", {})
    async with async_session_maker() as session:
        result = await session.execute(
            select(DevPipeline).where(
                DevPipeline.pipeline_id == pipeline_id,
                DevPipeline.is_deleted == 0,
            )
        )
        pipe = result.scalar_one_or_none()
        if not pipe:
            raise HTTPException(status_code=404, detail="流水线不存在")
        pipe.skill_config = json_mod.dumps(skill_config, ensure_ascii=False)
        await session.commit()
    return {"code": 200, "message": "配置更新成功"}


@router.get("/templates")
async def list_templates():
    """列出流水线模板"""
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "dev_pipeline": {
                "name": "完整开发流水线",
                "description": "需求→UI预览→代码→Review→测试→提交→部署→报告",
                "stages": [
                    {"key": s["key"], "name": s["name"], "agent": s["agent"]}
                    for s in STAGE_DEFINITIONS
                ],
            }
        },
    }


# 兼容旧接口
@router.post("/create")
async def create_flow_legacy(http_request: Request):
    """旧版创建流程（兼容）"""
    tenant_id = _get_tenant_id(http_request)
    pipeline_id = await pipeline_manager.create_pipeline(tenant_id=tenant_id)
    return {"code": 200, "message": "流水线创建成功", "data": {"flow_id": pipeline_id}}


@router.get("/list")
async def list_flows_legacy(http_request: Request):
    """旧版流程列表（兼容）"""
    tenant_id = _get_tenant_id(http_request)
    pipelines = await pipeline_manager.list_pipelines(tenant_id)
    return {"code": 200, "message": "查询成功", "data": pipelines}


# ==================== Prompt 管理 ====================

@router.get("/prompts/defaults")
async def get_default_prompts():
    """获取 8 个阶段的默认 prompt 模板"""
    return {"code": 200, "message": "查询成功", "data": DEFAULT_STAGE_PROMPTS}


@router.get("/projects/{project_code}/prompts")
async def get_project_prompts(project_code: str):
    """获取项目的自定义 prompt"""
    from app.core.database import async_session_maker
    from app.models.agent_models import AgentProject
    from sqlalchemy import select

    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentProject.pipeline_prompts).where(
                AgentProject.project_code == project_code,
                AgentProject.is_deleted == 0,
            )
        )
        row = result.scalar_one_or_none()

    prompts = json.loads(row) if row else {}
    return {"code": 200, "message": "查询成功", "data": prompts}


class UpdatePromptsRequest(BaseModel):
    prompts: Dict[str, str] = Field(..., description="阶段 prompt 映射，key 为阶段名")


@router.put("/projects/{project_code}/prompts")
async def update_project_prompts(project_code: str, request: UpdatePromptsRequest):
    """更新项目的自定义 prompt"""
    from app.core.database import async_session_maker
    from app.models.agent_models import AgentProject
    from sqlalchemy import select, update
    import time

    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentProject).where(
                AgentProject.project_code == project_code,
                AgentProject.is_deleted == 0,
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

        project.pipeline_prompts = json.dumps(request.prompts, ensure_ascii=False)
        project.update_time = int(time.time() * 1000)
        await session.commit()

    return {"code": 200, "message": "更新成功"}
