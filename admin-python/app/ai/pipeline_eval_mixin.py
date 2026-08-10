"""流水线 eval 子域：评分 / LLM-as-judge / 质量门 / 人工评分。

从 DevPipelineManager 抽出的内聚方法簇，作为 mixin——方法体原样搬迁，仍经 self 访问
DevPipelineManager 的全部状态/方法（mixin 合并后 self 即完整实例）。execute_stage 等
编排逻辑不动，仅把 eval 相关叶子方法归类于此。
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evaluators import DEFAULT_EVAL_CRITERIA, extract_eval_scores
from app.core.config import settings
from app.models.agent_models import DevPipeline

logger = logging.getLogger(__name__)


class PipelineEvalMixin:
    """eval 评分/judge/质量门/人工评分——由 DevPipelineManager 继承。"""

    @staticmethod
    def _compute_overall_score(stages: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
            """按权重把各阶段质量分汇总成 0-100 总分。

            权重（按可用维度归一化）：pm 0.15 / design 0.15 / preview 0.30 /
            review 0.20 / testing 0.20。review/tests 的 passed 信号映射为 100/40、100/30。
            """
            def _num(stage_key: str, *path: str) -> Optional[int]:
                so = (stages.get(stage_key) or {}).get("structured_output") or {}
                obj: Any = so
                for p in path:
                    obj = (obj or {}).get(p) if isinstance(obj, dict) else None
                if isinstance(obj, (int, float)):
                    return max(0, min(100, int(obj)))
                return None

            pm = _num("requirement", "pm_quality", "score")
            design = _num("page_design", "design_quality", "score")
            preview = _num("prototype", "preview_quality", "score")
            if preview is None:
                preview = _num("ui_preview", "preview_quality", "score")

            cr_so = (stages.get("code_review") or {}).get("structured_output") or {}
            review_passed = cr_so.get("review_passed")
            t_so = (stages.get("testing") or {}).get("structured_output") or {}
            tests_passed = t_so.get("tests_passed")

            weights = {"pm": 0.15, "design": 0.15, "preview": 0.30, "review": 0.20, "testing": 0.20}
            components: List[Tuple[str, int, float]] = []
            if pm is not None:
                components.append(("pm", pm, weights["pm"]))
            if design is not None:
                components.append(("design", design, weights["design"]))
            if preview is not None:
                components.append(("preview", preview, weights["preview"]))
            if isinstance(review_passed, bool):
                components.append(("review", 100 if review_passed else 40, weights["review"]))
            if isinstance(tests_passed, bool):
                components.append(("testing", 100 if tests_passed else 30, weights["testing"]))

            if not components:
                return None, {
                    "pm_quality_score": None, "design_quality_score": None, "preview_quality_score": None,
                    "review_passed": review_passed, "tests_passed": tests_passed, "components": {},
                }

            total_w = sum(w for _, _, w in components)
            overall = round(sum(score * w for _, score, w in components) / total_w)
            return overall, {
                "pm_quality_score": pm,
                "design_quality_score": design,
                "preview_quality_score": preview,
                "review_passed": review_passed,
                "tests_passed": tests_passed,
                "components": {name: score for name, score, _ in components},
            }

    async def _record_pipeline_eval(
            self, pipe: "DevPipeline", stages: Dict[str, Any]
        ) -> None:
            """Pipeline terminal: aggregate eval signals into pipeline_eval_result.

            用独立 session 写入并自行 commit，确保 eval 失败（可观测层）不影响 _complete_pipeline 主事务。
            """
            from app.models.pipeline_eval import PipelineEvalResult

            overall, breakdown = self._compute_overall_score(stages)

            testing_stage = stages.get("testing") or {}
            skill_result = testing_stage.get("skill_result") or {}
            t_so = testing_stage.get("structured_output") or {}
            tests_passed_count = skill_result.get("tests_passed")
            tests_failed_count = skill_result.get("tests_failed")
            tests_total = t_so.get("test_cases_total")
            if tests_total is None:
                computed = (tests_passed_count or 0) + (tests_failed_count or 0)
                tests_total = computed if computed > 0 else None

            stage_scores: Dict[str, Any] = {}
            for sk, sd in stages.items():
                so = (sd or {}).get("structured_output") or {}
                entry = {
                    k: so[k] for k in (
                        "pm_quality", "design_quality", "preview_quality",
                        "review_passed", "tests_passed", "test_cases_total",
                        "test_cases_passed", "coverage_estimate",
                        "auto_repair_iterations", "auto_repair_summary",
                    ) if k in so
                }
                if entry:
                    stage_scores[sk] = entry

            retry_count = pipe.retry_count or 0
            prototype_so = (stages.get("prototype") or {}).get("structured_output") or {}
            auto_repair = prototype_so.get("auto_repair_iterations") or retry_count

            review_passed = breakdown["review_passed"]
            tests_passed = breakdown["tests_passed"]
            # LLM-as-judge 分（eval 阶段 structured_output）——统一经 extract_eval_scores 抽取（持久化与门控同源）
            eval_so = (stages.get("eval") or {}).get("structured_output") or {}
            _llm = extract_eval_scores(eval_so)
            now = int(time.time() * 1000)
            values = {
                "eval_id": f"EVAL-{pipe.pipeline_id}",
                "pipeline_id": pipe.pipeline_id,
                "tenant_id": pipe.tenant_id,
                "project_id": pipe.project_id,
                "status": pipe.status,
                "overall_score": overall,
                "pm_quality_score": breakdown["pm_quality_score"],
                "design_quality_score": breakdown["design_quality_score"],
                "preview_quality_score": breakdown["preview_quality_score"],
                "judge_score": _llm["judge_score"],
                "hallucination_score": _llm["hallucination_score"],
                "vision_score": _llm["vision_score"],
                "e2e_passed": _llm["e2e_passed"],
                "review_passed": int(review_passed) if isinstance(review_passed, bool) else None,
                "tests_passed": int(tests_passed) if isinstance(tests_passed, bool) else None,
                "tests_total": tests_total,
                "tests_passed_count": tests_passed_count,
                "tests_failed_count": tests_failed_count,
                "retry_count": retry_count,
                "auto_repair_iterations": auto_repair,
                "framework": skill_result.get("framework"),
                "test_duration_ms": skill_result.get("duration_ms"),
                "stage_scores": json.dumps(stage_scores, ensure_ascii=False),
                "update_time": now,
            }

            async with async_session_maker() as session:
                # 汇总该 pipeline 的 LLM 用量，回填成本列（B3）
                try:
                    from sqlalchemy import func

                    from app.models.llm_usage_log import LLMUsageLog
                    usage_row = (await session.execute(
                        select(
                            func.coalesce(func.sum(LLMUsageLog.input_tokens), 0),
                            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0),
                        ).where(
                            LLMUsageLog.pipeline_id == pipe.pipeline_id,
                        )
                    )).one()
                    values["cost_input_tokens"] = int(usage_row[0] or 0)
                    values["cost_output_tokens"] = int(usage_row[1] or 0)
                except Exception:
                    pass  # 用量汇总失败不阻断 eval 写入

                existing = await session.execute(
                    select(PipelineEvalResult).where(
                        PipelineEvalResult.pipeline_id == pipe.pipeline_id,
                        PipelineEvalResult.is_deleted == 0,
                    )
                )
                rec = existing.scalar_one_or_none()
                if rec is not None:
                    for k, v in values.items():
                        setattr(rec, k, v)
                else:
                    rec = PipelineEvalResult(**values, create_time=now)
                    session.add(rec)
                await session.commit()
                # 自动评审：若该 pipeline 关联了 golden case（EvalRun），评审并回写
                try:
                    await self._auto_judge_eval_runs(pipe, session)
                except Exception as e:
                    logger.warning("auto-judge eval runs failed for %s: %s", pipe.pipeline_id, e)

    async def _auto_judge_eval_runs(self, pipe: "DevPipeline", session: AsyncSession) -> None:
            """管线终态：对该 pipeline 关联的待评审 EvalRun 自动评审并回写。"""
            from app.models.eval_run import EvalRun
            from app.models.eval_golden_case import EvalGoldenCase
            from app.ai.eval_judge import extract_pipeline_output, judge_hallucination, judge_output

            stmt = select(EvalRun).where(
                EvalRun.pipeline_id == pipe.pipeline_id,
                EvalRun.is_deleted == 0,
                EvalRun.status.in_(["running", "pending"]),
            )
            runs = (await session.execute(stmt)).scalars().all()
            if not runs:
                return
            output = extract_pipeline_output(pipe.stages_data)
            for run in runs:
                case = (await session.execute(
                    select(EvalGoldenCase).where(
                        EvalGoldenCase.id == run.golden_case_id,
                        EvalGoldenCase.is_deleted == 0,
                    )
                )).scalar_one_or_none()
                if not case:
                    run.status = "failed"
                    run.judgment = json.dumps({"error": "golden case 不存在或已删除"}, ensure_ascii=False)
                    continue
                result = await judge_output(case.input_spec, output, case.expected_criteria)
                # 幻觉评审（与功能评审正交），合并写入 judgment 供看板聚合
                try:
                    halluc = await judge_hallucination(case.input_spec, output)
                except Exception as exc:  # noqa: BLE001
                    halluc = {"error": str(exc)}
                if not halluc.get("error"):
                    result["hallucination_score"] = halluc.get("hallucination_score")
                    result["hallucination_flagged"] = halluc.get("flagged")
                    result["hallucination_summary"] = halluc.get("summary")
                run.status = "failed" if result.get("error") else "judged"
                run.overall_score = result.get("overall_score")
                run.judgment = json.dumps(result, ensure_ascii=False)
                run.update_time = int(time.time() * 1000)
            await session.commit()

    @staticmethod
    def _eval_quality_gate_reason(eval_struct: Dict[str, Any]) -> Optional[str]:
            """eval 阶段质量门控：LLM judge 低分 → 返回升级人工的理由；否则 None。

            judge 缺失/出错（overall_score=None）→ 不 gate（fail-open，沿用全栈 fail-open 哲学，
            避免评测故障卡死流水线）。门控开关/阈值见 settings.eval_quality_gate_*。
            """
            if not settings.eval_quality_gate_enabled:
                return None
            judge_score = extract_eval_scores(eval_struct)["judge_score"]
            if isinstance(judge_score, (int, float)) and judge_score < settings.eval_quality_gate_score:
                return (
                    f"自动评测低分（judge {int(judge_score)} < "
                    f"{settings.eval_quality_gate_score}），需人工复核交付质量"
                )
            return None

    async def _run_eval_stage(
            self, pipe: "DevPipeline", stages: Dict[str, Any], emit: Optional[Any] = None
        ) -> Tuple[str, Dict[str, Any]]:
            """eval 阶段：对流水线产物做自评（功能 judge + 幻觉 + 视觉 + E2E），返回 (markdown, structured)。

            视觉截图与 E2E 断言共用一个真实沙箱预览（生命周期：start→截图/断言→stop），失败各自
            best-effort 回退 Vue2 渲染桩并静默。无 golden case 时用 DEFAULT_EVAL_CRITERIA。
            评测本身不重试、不阻塞报告——失败由调用方兜底为 error 文案。
            """
            from app.ai.eval_judge import extract_pipeline_output, judge_output, judge_hallucination, judge_output_vision
            from app.services.vision_eval_service import (
                acquire_live_preview, render_pipeline_screenshot, run_e2e_assertions,
            )
            from app.ai.e2e_expectations import derive_e2e_expectations

            output = extract_pipeline_output(pipe.stages_data)
            requirement = (pipe.user_request or "").strip() or stages.get("requirement", {}).get("output", "")
            structured: Dict[str, Any] = {}

            structured["judge"] = await judge_output({"request": requirement}, output, DEFAULT_EVAL_CRITERIA)
            try:
                structured["hallucination"] = await judge_hallucination(requirement, output)
            except Exception as exc:  # noqa: BLE001
                structured["hallucination"] = {"error": str(exc)[:200]}

            # 视觉 + E2E：同一真实沙箱预览上跑（用完即停），各自 best-effort 静默
            try:
                artifact = await self.get_pipeline_artifact(pipe.pipeline_id)
                frontend_files = artifact.get("frontend_files") or {}
            except Exception:  # noqa: BLE001
                frontend_files = {}
            page_design_doc = stages.get("page_design", {}).get("output") or ""
            expectations = derive_e2e_expectations(requirement, page_design_doc)

            async with acquire_live_preview(pipe.pipeline_id) as live_url:
                # 视觉评审：真实预览截图（live）优先，失败回退渲染桩
                try:
                    shot = await render_pipeline_screenshot(pipe.pipeline_id, live_url=live_url)
                    structured["vision"] = await judge_output_vision(
                        shot["data_uri"], {"request": requirement}, DEFAULT_EVAL_CRITERIA
                    )
                except Exception as exc:  # noqa: BLE001
                    structured["vision_error"] = str(exc)[:200]

                # E2E 断言：同一预览上跑（几乎零额外成本）；live 不可用回退桩
                try:
                    e2e = await run_e2e_assertions(
                        frontend_files, expectations, screenshot=False, live_url=live_url,
                    )
                    structured["e2e"] = {
                        "passed": e2e.get("passed"),
                        "issues": e2e.get("issues") or [],
                        "source": "live" if live_url else "stub",
                    }
                    if e2e.get("harness_error"):
                        structured["e2e"]["note"] = e2e["harness_error"]
                    elif e2e.get("stub_incompatible"):
                        structured["e2e"]["note"] = "桩不兼容（模块化 UI 库未注册），跳过"
                except Exception as exc:  # noqa: BLE001
                    structured["e2e_error"] = str(exc)[:200]

            # eval 报告格式化器住在 flow_manager（prompt 构造区），lazy import 破循环
            from app.ai.flow_manager import _format_eval_report
            return _format_eval_report(structured), structured

    async def _record_eval_safe(self, pipe: "DevPipeline", stages: Dict[str, Any]) -> None:
            """Record pipeline eval in fail-soft mode (completed + failed terminal paths)."""
            try:
                await self._record_pipeline_eval(pipe, stages)
            except Exception as exc:
                logger.warning(
                    f"Pipeline eval record suppressed for {getattr(pipe, 'pipeline_id', '?')}: {exc}"
                )

    async def set_eval_human_score(
            self,
            pipeline_id: str,
            tenant_id: int,
            admin_id: int,
            score: int,
            comment: Optional[str],
        ) -> Dict[str, Any]:
            """人工覆盖分：upsert pipeline_eval_result 的 human_* 列（不动 LLM/规则分，重跑 eval 不清零）。

            返回最新人工分；pipeline 不存在抛 ValueError，租户越权抛 PermissionError（由 API 层转 HTTP 码）。
            """
            from app.models.pipeline_eval import PipelineEvalResult

            async with async_session_maker() as session:
                pipe = (await session.execute(
                    select(DevPipeline).where(DevPipeline.pipeline_id == pipeline_id)
                )).scalar_one_or_none()
                if not pipe:
                    raise ValueError("pipeline 不存在")
                if tenant_id and pipe.tenant_id != tenant_id:
                    raise PermissionError("无权评测该 pipeline")
                rec = (await session.execute(
                    select(PipelineEvalResult).where(
                        PipelineEvalResult.pipeline_id == pipeline_id,
                        PipelineEvalResult.is_deleted == 0,
                    )
                )).scalar_one_or_none()
                now = int(time.time() * 1000)
                if rec is None:
                    rec = PipelineEvalResult(
                        eval_id=f"EVAL-{pipeline_id}",
                        pipeline_id=pipeline_id,
                        tenant_id=pipe.tenant_id,
                        project_id=pipe.project_id,
                        status=pipe.status,
                        create_time=now,
                    )
                    session.add(rec)
                rec.human_score = score
                rec.human_comment = (comment or "")[:500] or None
                rec.human_scored_by = admin_id
                rec.human_scored_at = now
                await session.commit()
                return {
                    "pipeline_id": pipeline_id,
                    "human_score": rec.human_score,
                    "human_comment": rec.human_comment,
                }
