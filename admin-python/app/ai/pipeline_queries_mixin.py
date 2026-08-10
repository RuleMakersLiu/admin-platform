"""流水线查询子域：状态/列表/详情/产物/统计/删除——纯读为主。

从 DevPipelineManager 抽出的查询方法簇，作为 mixin（self 即完整实例）。编排逻辑不动。
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.agent_models import DevPipeline
from app.ai.pipeline_skills import get_workspace_path

logger = logging.getLogger(__name__)


class PipelineQueriesMixin:
    """流水线查询/读取方法——由 DevPipelineManager 继承。"""

    def _parse_stages(self, pipe: DevPipeline) -> Dict[str, Any]:
            """把 pipe.stages_data JSON 反序列化成 dict；缺失则回退初始化。"""
            if pipe.stages_data:
                return json.loads(pipe.stages_data)
            return _init_stages()

    def _to_status_dict(self, pipe: DevPipeline) -> Dict[str, Any]:
            """把 pipe ORM 对象转成对外暴露的状态字典（含 skill snapshot 概要）。"""
            stages = self._parse_stages(pipe)
            pipe_config = json.loads(pipe.skill_config or "{}")
            skill_snapshot = pipe_config.get("project_skill_snapshot") or {}
            backend_skill_snapshot = pipe_config.get("backend_project_skill_snapshot") or {}
            backend_skill_snapshots = pipe_config.get("backend_project_skill_snapshots") or []
            return {
                "pipeline_id": pipe.pipeline_id,
                "project_id": pipe.project_id or "",
                "user_request": pipe.user_request or "",
                "status": pipe.status,
                "current_stage": pipe.current_stage,
                "pipeline_mode": pipe_config.get("pipeline_mode", "full"),
                "project_skill": {
                    "project_id": skill_snapshot.get("project_id", ""),
                    "project_name": skill_snapshot.get("project_name", ""),
                    "skill_version": skill_snapshot.get("skill_version"),
                    "confirmed_at": skill_snapshot.get("confirmed_at"),
                } if skill_snapshot else None,
                "backend_project_skill": {
                    "project_id": backend_skill_snapshot.get("project_id", ""),
                    "project_name": backend_skill_snapshot.get("project_name", ""),
                    "skill_version": backend_skill_snapshot.get("skill_version"),
                    "confirmed_at": backend_skill_snapshot.get("confirmed_at"),
                } if backend_skill_snapshot else None,
                "backend_project_skills": [
                    {
                        "project_id": snapshot.get("project_id", ""),
                        "project_name": snapshot.get("project_name", ""),
                        "skill_version": snapshot.get("skill_version"),
                        "confirmed_at": snapshot.get("confirmed_at"),
                    }
                    for snapshot in backend_skill_snapshots
                ],
                "stages": stages,
                "retry_count": pipe.retry_count,
                "workspace_path": pipe.workspace_path or "",
                "git_repo_url": pipe.git_repo_url or "",
                "git_branch": pipe.git_branch or "",
                "git_commit_sha": pipe.git_commit_sha or "",
                "deploy_task_id": pipe.deploy_task_id or "",
                "created_at": str(pipe.create_time),
                "updated_at": str(pipe.update_time),
            }

    async def list_intervention_pipelines(self, tenant_id: int) -> List[Dict[str, Any]]:
            """列出租户内所有 needs_human 流水线（供开发人员介入队列）。"""
            async with async_session_maker() as session:
                stmt = select(DevPipeline).where(
                    DevPipeline.tenant_id == tenant_id,
                    DevPipeline.status == PipelineStatus.NEEDS_HUMAN.value,
                    DevPipeline.is_deleted == 0,
                ).order_by(DevPipeline.update_time.desc())
                rows = (await session.execute(stmt)).scalars().all()
                result: List[Dict[str, Any]] = []
                for pipe in rows:
                    stages = self._parse_stages(pipe)
                    stage = stages.get(pipe.current_stage) or {}
                    human_review = stage.get("human_review") or {}
                    result.append({
                        "pipeline_id": pipe.pipeline_id,
                        "current_stage": pipe.current_stage,
                        "current_stage_name": STAGE_NAMES.get(pipe.current_stage, pipe.current_stage),
                        "user_request": (pipe.user_request or "")[:120],
                        "update_time": pipe.update_time,
                        "reason": human_review.get("reason") or stage.get("error", ""),
                        "issues": human_review.get("issues", []),
                        "file_hints": human_review.get("file_hints", []),
                        "retry_count": human_review.get("retry_count", 0),
                    })
                return result

    async def get_pipeline_status(self, pipeline_id: str) -> Dict[str, Any]:
            """返回流水线完整状态（含 stages/skill snapshot/workspace/git/deploy 信息）。

            对 frontend_contract_review 模式下的 prototype + 现有功能改造 + 未选页面的场景，
            会现场计算页面候选并塞进 structured_output。
            """
            async with async_session_maker() as session:
                pipe = await self._load_pipeline(session, pipeline_id)
                status = self._to_status_dict(pipe)
                pipe_config = json.loads(pipe.skill_config or "{}")
                current_stage = pipe.current_stage
                current_structured = (
                    (status.get("stages") or {})
                    .get(current_stage or "", {})
                    .get("structured_output")
                    or {}
                )
                if (
                    pipe.status == PipelineStatus.WAITING_CONFIRM.value
                    and current_stage == "prototype"
                    and pipe_config.get("pipeline_mode") == "frontend_contract_review"
                    and _is_existing_feature_change_request(pipe.user_request or "")
                    and not str(pipe_config.get("selected_frontend_page_path") or "").strip()
                    and not current_structured.get("needs_frontend_page_selection")
                ):
                    frontend_project_id = str(pipe_config.get("frontend_project_id") or pipe.project_id or "").strip()
                    page_candidates: Dict[str, Any] = {
                        "project_id": frontend_project_id,
                        "requires_selection": True,
                        "candidates": [],
                        "uncertain": True,
                    }
                    if frontend_project_id:
                        page_candidates = await get_frontend_page_candidates_for_requirement(
                            frontend_project_id,
                            pipe.user_request or "",
                        )
                    stage_status = (status.get("stages") or {}).get(current_stage, {})
                    stage_status["structured_output"] = {
                        **current_structured,
                        "needs_frontend_page_selection": True,
                        "frontend_page_candidates": page_candidates,
                    }
                    stage_status["output"] = (
                        "这是现有页面功能改造，请先选择要修改的页面功能。"
                        "系统会基于所选页面重新生成，不会新建替代页面。"
                    )
                    status["stages"][current_stage] = stage_status
                return status

    async def get_preview(self, pipeline_id: str) -> Dict[str, Any]:
            """取最新预览（prototype 优先，ui_preview 兜底）的 HTML 与原始输出。"""
            async with async_session_maker() as session:
                pipe = await self._load_pipeline(session, pipeline_id)
                stages = self._parse_stages(pipe)
                preview_stage = stages.get("prototype", {}) or stages.get("ui_preview", {})
                if not preview_stage.get("preview_html"):
                    preview_stage = stages.get("ui_preview", {}) or preview_stage
                return {
                    "pipeline_id": pipeline_id,
                    "preview_html": preview_stage.get("preview_html", ""),
                    "output": preview_stage.get("output", ""),
                }

    async def get_pipeline_artifact(self, pipeline_id: str) -> Dict[str, Any]:
            """取对外暴露的产物视图（预览/契约/前端文件/审查/报告）。"""
            async with async_session_maker() as session:
                pipe = await self._load_pipeline(session, pipeline_id)
                stages = self._parse_stages(pipe)
                artifact = _build_pipeline_artifact(stages)
                pipe_config = json.loads(pipe.skill_config or "{}")
                artifact.update({
                    "pipeline_id": pipeline_id,
                    "status": pipe.status,
                    "pipeline_mode": pipe_config.get("pipeline_mode", "full"),
                })
                return artifact

    async def get_pipeline_frontend_project_snapshot(self, pipeline_id: str) -> Dict[str, Any]:
            """取该流水线锁定时的前端 Project Skill 快照（无则空 dict）。"""
            async with async_session_maker() as session:
                pipe = await self._load_pipeline(session, pipeline_id)
                pipe_config = json.loads(pipe.skill_config or "{}")
                snapshot = pipe_config.get("project_skill_snapshot") or {}
                if not snapshot:
                    return {}
                return dict(snapshot)

    async def get_stage_output(self, pipeline_id: str, stage: str = "") -> Dict[str, Any]:
            """取指定阶段的产物（output/structured_output/preview_html/code_files）。"""
            async with async_session_maker() as session:
                pipe = await self._load_pipeline(session, pipeline_id)
                stages = self._parse_stages(pipe)
                target = stage or pipe.current_stage
                stage_data = stages.get(target, {})
                return {
                    "pipeline_id": pipeline_id,
                    "stage": target,
                    "output": stage_data.get("output", ""),
                    "structured_output": stage_data.get("structured_output", {}),
                    "preview_html": stage_data.get("preview_html", ""),
                    "code_files": stage_data.get("code_files", {}),
                }

    async def list_pipelines(self, tenant_id: int = 0) -> List[Dict[str, Any]]:
            """列出租户内所有未删流水线（按创建时间倒序，无 eval 分数）。"""
            async with async_session_maker() as session:
                query = select(DevPipeline).where(DevPipeline.is_deleted == 0)
                if tenant_id:
                    query = query.where(DevPipeline.tenant_id == tenant_id)
                query = query.order_by(DevPipeline.create_time.desc())
                result = await session.execute(query)
                pipes = result.scalars().all()
                return [
                    {
                        "pipeline_id": p.pipeline_id,
                        "project_id": p.project_id or "",
                        "user_request": p.user_request or "",
                        "status": p.status,
                        "current_stage": p.current_stage,
                        "retry_count": p.retry_count,
                        "create_time": p.create_time,
                        "update_time": p.update_time,
                    }
                    for p in pipes
                ]

    async def list_eval_pipelines(
            self, tenant_id: int = 0, limit: int = 50
        ) -> List[Dict[str, Any]]:
            """带评测分数的 pipeline 列表（left join pipeline_eval_result）。"""
            from app.models.pipeline_eval import PipelineEvalResult

            async with async_session_maker() as session:
                query = (
                    select(DevPipeline, PipelineEvalResult)
                    .outerjoin(
                        PipelineEvalResult,
                        (PipelineEvalResult.pipeline_id == DevPipeline.pipeline_id)
                        & (PipelineEvalResult.is_deleted == 0),
                    )
                    .where(DevPipeline.is_deleted == 0)
                )
                if tenant_id:
                    query = query.where(DevPipeline.tenant_id == tenant_id)
                query = query.order_by(DevPipeline.create_time.desc()).limit(limit)
                result = await session.execute(query)
                rows = result.all()
                return [
                    {
                        "pipeline_id": p.pipeline_id,
                        "project_id": p.project_id or "",
                        "user_request": (p.user_request or "")[:120],
                        "status": p.status,
                        "current_stage": p.current_stage,
                        "retry_count": p.retry_count,
                        "create_time": p.create_time,
                        "update_time": p.update_time,
                        "overall_score": e.overall_score if e else None,
                        "pm_quality_score": e.pm_quality_score if e else None,
                        "design_quality_score": e.design_quality_score if e else None,
                        "preview_quality_score": e.preview_quality_score if e else None,
                        "judge_score": e.judge_score if e else None,
                        "hallucination_score": e.hallucination_score if e else None,
                        "vision_score": e.vision_score if e else None,
                        "e2e_passed": e.e2e_passed if e else None,
                        "human_score": e.human_score if e else None,
                        "human_comment": e.human_comment if e else None,
                        "review_passed": e.review_passed if e else None,
                        "tests_passed": e.tests_passed if e else None,
                    }
                    for p, e in rows
                ]

    async def get_eval_stats(
            self, tenant_id: int = 0, days: int = 30
        ) -> Dict[str, Any]:
            """tenant 维度评测聚合：平均分、通过率、retry 均值、分桶、按天趋势。"""
            from app.models.pipeline_eval import PipelineEvalResult

            cutoff = int((time.time() - days * 86400) * 1000)
            async with async_session_maker() as session:
                query = select(PipelineEvalResult).where(
                    PipelineEvalResult.is_deleted == 0,
                    PipelineEvalResult.create_time >= cutoff,
                )
                if tenant_id:
                    query = query.where(PipelineEvalResult.tenant_id == tenant_id)
                result = await session.execute(query)
                records = result.scalars().all()

            if not records:
                return {
                    "total": 0, "avg_overall_score": None, "review_pass_rate": None,
                    "tests_pass_rate": None, "avg_retry_count": None,
                    "score_buckets": {"lt60": 0, "60_80": 0, "gte80": 0},
                    "daily_trend": [],
                }

            scores = [r.overall_score for r in records if r.overall_score is not None]
            review = [r.review_passed for r in records if r.review_passed is not None]
            tests = [r.tests_passed for r in records if r.tests_passed is not None]
            retries = [r.retry_count for r in records if r.retry_count is not None]

            buckets = {"lt60": 0, "60_80": 0, "gte80": 0}
            for s in scores:
                if s < 60:
                    buckets["lt60"] += 1
                elif s < 80:
                    buckets["60_80"] += 1
                else:
                    buckets["gte80"] += 1

            daily: Dict[str, List[int]] = {}
            for r in records:
                if r.overall_score is None or not r.create_time:
                    continue
                day = time.strftime("%Y-%m-%d", time.localtime(r.create_time / 1000))
                daily.setdefault(day, []).append(r.overall_score)
            trend = [
                {"date": day, "avg_score": round(sum(v) / len(v)), "count": len(v)}
                for day, v in sorted(daily.items())
            ]

            return {
                "total": len(records),
                "avg_overall_score": round(sum(scores) / len(scores)) if scores else None,
                "review_pass_rate": round(sum(1 for v in review if v) / len(review), 4) if review else None,
                "tests_pass_rate": round(sum(1 for v in tests if v) / len(tests), 4) if tests else None,
                "avg_retry_count": round(sum(retries) / len(retries), 2) if retries else None,
                "score_buckets": buckets,
                "daily_trend": trend,
            }

    async def delete_pipeline(self, pipeline_id: str, tenant_id: int = 0) -> None:
            """软删除流水线（is_deleted=1）。tenant_id 非零时附加租户过滤。"""
            """软删除流水线"""
            async with async_session_maker() as session:
                query = update(DevPipeline).where(
                    DevPipeline.pipeline_id == pipeline_id,
                    DevPipeline.is_deleted == 0,
                )
                if tenant_id:
                    query = query.where(DevPipeline.tenant_id == tenant_id)
                query = query.values(is_deleted=1, update_time=int(time.time() * 1000))
                result = await session.execute(query)
                if result.rowcount == 0:
                    raise ValueError("流水线不存在")
                await session.commit()
