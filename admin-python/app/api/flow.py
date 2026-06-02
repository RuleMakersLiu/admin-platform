"""智能体协作流程 API"""
import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response as FastAPIResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Set

from app.ai.flow_manager import pipeline_manager, STAGE_DEFINITIONS, DEFAULT_STAGE_PROMPTS
from app.core.config import settings

router = APIRouter(prefix="/flow", tags=["智能体流程"])
logger = logging.getLogger(__name__)

_pipeline_tasks: Dict[str, asyncio.Task] = {}
_pipeline_subscribers: Dict[str, Set[asyncio.Queue]] = {}
_pipeline_task_lock = asyncio.Lock()
_pipeline_execution_semaphore = asyncio.Semaphore(settings.pipeline_execution_concurrency)


class CreatePipelineRequest(BaseModel):
    project_id: Optional[str] = Field(default="", description="项目ID")
    user_request: str = Field(default="", description="用户需求描述")
    git_config_id: Optional[int] = Field(default=None, description="Git 配置 ID")
    git_repo_url: Optional[str] = Field(default="", description="Git 仓库地址")
    git_branch: Optional[str] = Field(default="main", description="分支名")
    skill_config: Optional[dict] = Field(default=None, description="每阶段 Skill 配置")
    backend_project_id: Optional[str] = Field(default="", description="后端项目ID")
    backend_project_ids: Optional[List[str]] = Field(default=None, description="后端关联项目ID列表")
    frontend_project_id: Optional[str] = Field(default="", description="前端项目ID")
    backend_tech: Optional[str] = Field(default="", description="后端技术栈 如 java/spring-boot")
    frontend_tech: Optional[str] = Field(default="", description="前端技术栈 如 javascript/vue")


class MatchProjectSkillRequest(BaseModel):
    user_request: str = Field(default="", description="产品需求描述")


class RollbackPipelineRequest(BaseModel):
    stage: Optional[str] = Field(default=None, description="目标回退阶段")
    feedback: Optional[str] = Field(default="", description="回退修改意见")


class ExecuteStageRequest(BaseModel):
    user_input: Optional[str] = Field(default="", description="用户补充输入")


class ConfirmStageRequest(BaseModel):
    confirmed: bool = Field(..., description="是否确认")
    feedback: Optional[str] = Field(default="", description="修订反馈")


class UpdateProjectSkillRequest(BaseModel):
    project_brief: Optional[str] = Field(default=None, description="Project brief")
    skill_content: Optional[str] = Field(default=None, description="Project Skill Markdown")
    tenant_scope_ids: Optional[List[int]] = Field(default=None, description="适用租户")


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


def _sse_event(event: Dict) -> str:
    """Format a pipeline event as an SSE frame."""
    event_type = event.get("type") or "message"
    data = json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"


async def _broadcast_pipeline_event(pipeline_id: str, event: Dict[str, Any]) -> None:
    subscribers = list(_pipeline_subscribers.get(pipeline_id, set()))
    for queue in subscribers:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Pipeline %s subscriber queue full, dropping event", pipeline_id)


def _active_pipeline_task_count() -> int:
    return sum(1 for task in _pipeline_tasks.values() if not task.done())


async def _run_pipeline_background(pipeline_id: str, user_input: str) -> None:
    try:
        await _broadcast_pipeline_event(
            pipeline_id,
            {
                "type": "queued",
                "pipeline_id": pipeline_id,
                "active_tasks": _active_pipeline_task_count(),
                "concurrency": settings.pipeline_execution_concurrency,
            },
        )
        async with _pipeline_execution_semaphore:
            await _broadcast_pipeline_event(
                pipeline_id,
                {
                    "type": "dequeued",
                    "pipeline_id": pipeline_id,
                    "active_tasks": _active_pipeline_task_count(),
                    "concurrency": settings.pipeline_execution_concurrency,
                },
            )
            result = await pipeline_manager.execute_stage(
                pipeline_id,
                user_input,
                stream_callback=lambda event: _broadcast_pipeline_event(pipeline_id, event),
            )
        await _broadcast_pipeline_event(
            pipeline_id,
            {"type": "done", "pipeline_id": pipeline_id, "result": result},
        )
    except Exception as e:
        logger.exception("Pipeline %s background execution failed", pipeline_id)
        await _broadcast_pipeline_event(
            pipeline_id,
            {"type": "error", "pipeline_id": pipeline_id, "error": str(e)},
        )
    finally:
        async with _pipeline_task_lock:
            task = _pipeline_tasks.get(pipeline_id)
            if task and task.done():
                _pipeline_tasks.pop(pipeline_id, None)


async def _ensure_pipeline_background_task(pipeline_id: str, user_input: str) -> None:
    async with _pipeline_task_lock:
        task = _pipeline_tasks.get(pipeline_id)
        if task and not task.done():
            return
        if _active_pipeline_task_count() >= settings.pipeline_execution_queue_limit:
            raise RuntimeError(
                f"开发流水线执行队列已满，当前最多支持 {settings.pipeline_execution_queue_limit} 个并发等待任务"
            )
        _pipeline_tasks[pipeline_id] = asyncio.create_task(
            _run_pipeline_background(pipeline_id, user_input),
        )


@router.post("/pipeline/create")
async def create_pipeline(request: CreatePipelineRequest, http_request: Request):
    """创建开发流水线"""
    try:
        if not request.user_request or not request.user_request.strip():
            raise HTTPException(status_code=400, detail="需求描述不能为空")

        tenant_id = _get_tenant_id(http_request)
        admin_id = _get_admin_id(http_request)
        raw_body = {}
        try:
            raw_body = await http_request.json()
        except Exception:
            raw_body = {}
        pipeline_mode = raw_body.get("pipeline_mode") or "full"
        skill_config = dict(request.skill_config or {})
        from app.services.knowledge_service import resolve_project_skill_tenant_scope
        tenant_scope = await resolve_project_skill_tenant_scope(admin_id, tenant_id)
        allowed_tenant_ids = tenant_scope.get("allowed_tenant_ids") or []
        skill_config["tenant_scope"] = tenant_scope
        backend_project_id = request.backend_project_id or ""
        backend_project_ids = [str(item) for item in (request.backend_project_ids or []) if str(item).strip()]
        frontend_project_id = request.frontend_project_id or ""
        backend_tech = request.backend_tech or ""
        frontend_tech = request.frontend_tech or ""

        if pipeline_mode == "frontend_contract_review" and not backend_project_id:
            from app.services.knowledge_service import match_backend_project_skill_for_requirement

            backend_match = await match_backend_project_skill_for_requirement(
                request.user_request.strip(),
                tenant_id=tenant_id,
                exclude_project_id=frontend_project_id or request.project_id or "",
                allowed_tenant_ids=allowed_tenant_ids,
            )
            if backend_match:
                backend_matches = backend_match.get("matches") or [backend_match]
                backend_skill = (backend_matches[0].get("skill") if backend_matches else backend_match.get("skill")) or {}
                backend_project_id = str(backend_skill.get("project_id") or "")
                backend_project_ids = [
                    str((item.get("skill") or {}).get("project_id") or "")
                    for item in backend_matches
                    if (item.get("skill") or {}).get("project_id")
                ]
                backend_tech = backend_tech or "/".join(
                    part for part in [backend_skill.get("language"), backend_skill.get("framework")] if part
                )
                skill_config["backend_project_skills"] = [
                    {
                        "project_id": (item.get("skill") or {}).get("project_id"),
                        "project_name": (item.get("skill") or {}).get("project_name"),
                        "skill_version": (item.get("skill") or {}).get("skill_version"),
                        "confirmed_at": (item.get("skill") or {}).get("confirmed_at"),
                        "match_source": item.get("match_source"),
                        "match_reason": item.get("match_reason"),
                        "match_confidence": item.get("confidence"),
                    }
                    for item in backend_matches
                ]
                skill_config["backend_project_skill"] = {
                    "project_id": backend_skill.get("project_id"),
                    "project_name": backend_skill.get("project_name"),
                    "skill_version": backend_skill.get("skill_version"),
                    "confirmed_at": backend_skill.get("confirmed_at"),
                    "match_source": backend_match.get("match_source"),
                    "match_reason": backend_match.get("match_reason"),
                    "match_confidence": backend_match.get("confidence"),
                }
                logger.info(
                    "Auto matched backend Project Skill for product pipeline: project_id=%s reason=%s",
                    backend_project_id,
                    backend_match.get("match_reason"),
                )

        pipeline_id = await pipeline_manager.create_pipeline(
            project_id=request.project_id,
            user_request=request.user_request.strip(),
            tenant_id=tenant_id,
            creator_id=admin_id,
            git_config_id=request.git_config_id,
            git_repo_url=request.git_repo_url,
            git_branch=request.git_branch,
            skill_config=skill_config,
            backend_tech=backend_tech,
            frontend_tech=frontend_tech,
            backend_project_id=backend_project_id,
            backend_project_ids=backend_project_ids,
            frontend_project_id=frontend_project_id,
            pipeline_mode=pipeline_mode,
        )
        return {
            "code": 200,
            "message": "流水线创建成功",
            "data": {"pipeline_id": pipeline_id, "status": "pending"},
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/match")
async def match_project_skill(request: MatchProjectSkillRequest, http_request: Request):
    """Match a product requirement to a confirmed project Skill."""
    if not request.user_request or not request.user_request.strip():
        raise HTTPException(status_code=400, detail="需求描述不能为空")

    from app.services.knowledge_service import (
        match_backend_project_skill_for_requirement,
        match_frontend_project_skill_for_requirement,
        match_project_skill_for_requirement,
        resolve_project_skill_tenant_scope,
    )
    tenant_id = _get_tenant_id(http_request)
    admin_id = _get_admin_id(http_request)
    tenant_scope = await resolve_project_skill_tenant_scope(admin_id, tenant_id)
    allowed_tenant_ids = tenant_scope.get("allowed_tenant_ids") or []

    match = await match_frontend_project_skill_for_requirement(
        request.user_request.strip(),
        tenant_id=tenant_id,
        allowed_tenant_ids=allowed_tenant_ids,
    )
    if not match:
        match = await match_project_skill_for_requirement(
            request.user_request.strip(),
            tenant_id=tenant_id,
            allowed_tenant_ids=allowed_tenant_ids,
        )
    if not match:
        raise HTTPException(status_code=404, detail="未找到可用的已确认项目 Skill，请先由开发角色完成项目接入和 Skill 确认")

    backend_match = await match_backend_project_skill_for_requirement(
        request.user_request.strip(),
        tenant_id=tenant_id,
        exclude_project_id=str((match.get("skill") or {}).get("project_id") or ""),
        allowed_tenant_ids=allowed_tenant_ids,
    )
    if backend_match:
        match["backend_match"] = backend_match
        match["backend_matches"] = backend_match.get("matches") or [backend_match]
    try:
        from app.ai.flow_manager import get_frontend_page_candidates_for_requirement

        frontend_project_id = str((match.get("skill") or {}).get("project_id") or "")
        if frontend_project_id:
            match["frontend_page_candidates"] = await get_frontend_page_candidates_for_requirement(
                frontend_project_id,
                request.user_request.strip(),
            )
    except Exception as exc:
        logger.warning("Failed to load frontend page candidates: %s", exc)
        match["frontend_page_candidates"] = {
            "requires_selection": False,
            "candidates": [],
            "error": str(exc),
        }
    match["tenant_scope"] = tenant_scope
    return {"code": 200, "message": "匹配成功", "data": match}


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


@router.post("/pipeline/{pipeline_id}/execute-stream")
async def execute_stage_stream(pipeline_id: str, request: ExecuteStageRequest = None):
    """Stream current pipeline execution as SSE events."""
    user_input = request.user_input if request else ""

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=300)
        _pipeline_subscribers.setdefault(pipeline_id, set()).add(queue)

        try:
            await _ensure_pipeline_background_task(pipeline_id, user_input)
            yield _sse_event({"type": "heartbeat", "pipeline_id": pipeline_id})
            while True:
                task = _pipeline_tasks.get(pipeline_id)
                if (not task or task.done()) and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield _sse_event({"type": "heartbeat", "pipeline_id": pipeline_id})
                    continue
                yield _sse_event(event)
        except ValueError as e:
            yield _sse_event({"type": "error", "pipeline_id": pipeline_id, "error": str(e)})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.getLogger(__name__).exception("Pipeline stream failed")
            yield _sse_event({"type": "error", "pipeline_id": pipeline_id, "error": str(e)})
        finally:
            subscribers = _pipeline_subscribers.get(pipeline_id)
            if subscribers:
                subscribers.discard(queue)
                if not subscribers:
                    _pipeline_subscribers.pop(pipeline_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


@router.post("/pipeline/{pipeline_id}/sandbox-preview/start")
async def start_sandbox_preview(pipeline_id: str):
    """Start a real frontend dev server for generated frontend files."""
    from app.services.sandbox_preview_service import sandbox_preview_service

    try:
        artifact = await pipeline_manager.get_pipeline_artifact(pipeline_id)
        project_info = await pipeline_manager.get_pipeline_frontend_project_snapshot(pipeline_id)
        result = await sandbox_preview_service.start(
            pipeline_id,
            artifact.get("frontend_files") or {},
            project_info,
        )
        return {"code": 200, "message": "真实预览已启动", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to start sandbox preview")
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route("/pipeline/{pipeline_id}/sandbox-preview/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def proxy_sandbox_preview(pipeline_id: str, path: str = "", request: Request = None):
    """Proxy sandbox preview assets to the per-pipeline frontend dev server."""
    from app.services.sandbox_preview_service import sandbox_preview_service

    query_token = request.query_params.get("preview_token") if request else ""
    token = query_token
    if not token and request:
        token = request.cookies.get(f"sandbox_preview_token_{pipeline_id}", "")
    asset_suffixes = (
        ".js", ".css", ".map", ".json", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".ico", ".woff", ".woff2", ".ttf", ".eot",
    )
    is_asset_request = bool(path) and (
        path.startswith(("assets/", "js/", "css/", "img/", "fonts/"))
        or path.lower().endswith(asset_suffixes)
    )
    is_dev_server_request = bool(path) and path.startswith(("sockjs-node/", "__webpack_dev_server__/"))
    referer = request.headers.get("referer", "") if request else ""
    preview_path_prefix = f"/api/flow/pipeline/{pipeline_id}/sandbox-preview/"
    is_preview_runtime_api_request = bool(path) and path.startswith(("api/", "javaApi/", "logApi/", "socket.io/")) and (
        preview_path_prefix in referer
    )
    if not sandbox_preview_service.validate_token(pipeline_id, token or "") and not (
        (is_asset_request or is_dev_server_request or is_preview_runtime_api_request)
        and sandbox_preview_service.is_running(pipeline_id)
    ):
        raise HTTPException(status_code=403, detail="预览令牌无效或已过期")
    try:
        upstream = await sandbox_preview_service.proxy(
            pipeline_id,
            path,
            request.url.query if request else "",
            dict(request.headers) if request else {},
            request.method if request else "GET",
            await request.body() if request else b"",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    response = FastAPIResponse(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
        headers={
            key: value
            for key, value in upstream.headers.items()
            if key.lower() in {"cache-control", "etag", "last-modified"}
        },
    )
    if query_token and sandbox_preview_service.validate_token(pipeline_id, query_token):
        response.set_cookie(
            key=f"sandbox_preview_token_{pipeline_id}",
            value=query_token,
            path=f"/api/flow/pipeline/{pipeline_id}/sandbox-preview/",
            max_age=8 * 60 * 60,
            httponly=False,
            samesite="lax",
        )
    return response


@router.get("/pipeline/{pipeline_id}/artifact")
async def get_pipeline_artifact(pipeline_id: str):
    """Get the first-version deliverables: preview, frontend files, API contract, and review."""
    try:
        artifact = await pipeline_manager.get_pipeline_artifact(pipeline_id)
        return {"code": 200, "message": "查询成功", "data": artifact}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/pipeline/{pipeline_id}/frontend-download")
async def download_frontend_files(pipeline_id: str):
    """Download generated frontend files as a zip archive."""
    import io
    import zipfile

    try:
        artifact = await pipeline_manager.get_pipeline_artifact(pipeline_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    files = artifact.get("frontend_files") or {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if not files:
            archive.writestr("README.md", "No generated frontend files are available yet.\n")
        for raw_path, content in files.items():
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            safe_path = "/".join(part for part in safe_path.split("/") if part not in ("", ".", ".."))
            if not safe_path:
                continue
            archive.writestr(safe_path, content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2))
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{pipeline_id}-frontend.zip"'},
    )


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
async def rollback_pipeline(pipeline_id: str, request: RollbackPipelineRequest = None):
    """回退到指定阶段，清空该阶段之后的结果。"""
    try:
        result = await pipeline_manager.rollback(
            pipeline_id,
            target_stage=request.stage if request else None,
            feedback=request.feedback if request else "",
        )
        return {"code": 200, "message": "回退成功", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/pipeline/{pipeline_id}")
async def delete_pipeline(pipeline_id: str, http_request: Request):
    """删除流水线"""
    tenant_id = _get_tenant_id(http_request)
    try:
        await pipeline_manager.delete_pipeline(pipeline_id, tenant_id)
        return {"code": 200, "message": "删除成功"}
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


# ==================== 项目知识库 ====================

@router.post("/projects/{project_id}/analyze")
async def analyze_project_api(project_id: str):
    """触发项目知识库分析（后台异步执行）"""
    import asyncio
    from app.services.knowledge_service import analyze_project

    # 后台执行，不阻塞 API 响应
    asyncio.create_task(_do_analyze(project_id))
    return {"code": 200, "message": "分析任务已启动", "data": {"project_id": project_id, "status": "analyzing"}}


async def _do_analyze(project_id: str):
    """后台执行项目分析"""
    try:
        from app.services.knowledge_service import analyze_project
        result = await analyze_project(project_id, force=True)
        logger.info(f"Project {project_id} analysis done: {bool(result)}")
    except Exception as e:
        logging.getLogger(__name__).error(f"Project analysis failed: {e}")


@router.get("/projects/{project_id}/knowledge")
async def get_project_knowledge_api(project_id: str):
    """获取项目知识库"""
    from app.models.agent_models import ProjectKnowledge
    from app.core.database import async_session_maker
    from sqlalchemy import select

    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        k = result.scalar_one_or_none()
        if not k:
            return {"code": 200, "data": None, "message": "未分析"}

    return {
        "code": 200,
        "data": {
            "project_id": k.project_id,
            "project_name": k.project_name,
            "language": k.language,
            "framework": k.framework,
            "tech_summary": k.tech_summary,
            "architecture": k.architecture,
            "component_patterns": k.component_patterns,
            "api_patterns": k.api_patterns,
            "permission_model": k.permission_model,
            "coding_style": k.coding_style,
            "key_files": json.loads(k.key_files) if k.key_files else [],
            "analysis_status": k.analysis_status,
            "project_brief": k.project_brief,
            "skill_content": k.skill_content,
            "skill_status": k.skill_status,
            "skill_version": k.skill_version,
            "confirmed_by": k.confirmed_by,
            "confirmed_at": k.confirmed_at,
            "analysis_error": k.analysis_error,
        }
    }


@router.get("/projects/{project_id}/skill")
async def get_project_skill_api(project_id: str):
    """Get the project-level Skill draft/confirmed state."""
    from app.services.knowledge_service import get_project_skill

    skill = await get_project_skill(project_id)
    if not skill:
        return {"code": 200, "message": "未分析", "data": None}
    return {"code": 200, "message": "查询成功", "data": skill}


@router.put("/projects/{project_id}/skill")
async def update_project_skill_api(project_id: str, request: UpdateProjectSkillRequest, http_request: Request):
    """Save developer-edited project Skill content and return it to draft state."""
    from app.services.knowledge_service import (
        resolve_project_skill_tenant_scope,
        update_project_skill,
        update_project_tenant_scope,
    )

    skill = await update_project_skill(
        project_id,
        skill_content=request.skill_content,
        project_brief=request.project_brief,
    )
    if not skill:
        raise HTTPException(status_code=404, detail="项目知识不存在，请先触发项目分析")
    if request.tenant_scope_ids is not None:
        tenant_scope = await resolve_project_skill_tenant_scope(
            _get_admin_id(http_request),
            _get_tenant_id(http_request),
        )
        allowed = set(int(item) for item in tenant_scope.get("allowed_tenant_ids") or [])
        requested = [int(item) for item in request.tenant_scope_ids]
        if 0 in requested and tenant_scope.get("scope_type") != "system_admin":
            raise HTTPException(status_code=403, detail="只有系统管理员可以配置全局适用租户")
        invalid = [item for item in requested if item != 0 and item not in allowed]
        if invalid:
            raise HTTPException(status_code=403, detail=f"无权配置租户: {invalid}")
        await update_project_tenant_scope(project_id, requested, admin_id=_get_admin_id(http_request))
        skill["tenant_scope_ids"] = requested
    return {"code": 200, "message": "保存成功", "data": skill}


@router.post("/projects/{project_id}/skill/confirm")
async def confirm_project_skill_api(project_id: str, http_request: Request):
    """Confirm a project Skill so product pipelines can use it."""
    from app.services.knowledge_service import confirm_project_skill

    try:
        skill = await confirm_project_skill(project_id, confirmed_by=_get_admin_id(http_request))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not skill:
        raise HTTPException(status_code=404, detail="项目知识不存在，请先触发项目分析")
    return {"code": 200, "message": "确认成功", "data": skill}
