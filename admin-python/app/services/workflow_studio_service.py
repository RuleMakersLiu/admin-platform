"""工作流编排执行服务（Dify 式 Studio）：DSL CRUD + 编译执行 + 人工输入恢复。

与 services/workflow_service.py（既有聊天流程编排）是两套关注点：
本服务面向可视化画布产出的 WorkflowDSL（见 ai/workflow_compiler.py）。

执行模型：
- run 走 asyncio 后台任务，DB 中 WorkflowRun 记录状态机（前端轮询）
- human_input 节点触发 LangGraph interrupt，图与 checkpointer 常驻进程内
  （MVP 用 MemorySaver；重启丢失运行态，定义不受影响——持久化升级点见调研报告）
- resume 以 Command(resume=value) 续跑同一 thread
"""
import asyncio
import logging
import uuid
from typing import Any, Optional

from langgraph.types import Command
from sqlalchemy import select

from app.ai.workflow_compiler import (
    WorkflowValidationError,
    compile_workflow,
    extract_waiting,
    validate_dsl,
)
from app.core.database import async_session_maker
from app.models.workflow_models import WorkflowDefinition, WorkflowRun

logger = logging.getLogger(__name__)

# run_id -> 编译产物（进程内执行态；重启后 waiting 的 run 只能重跑）
_ACTIVE_GRAPHS: dict[str, Any] = {}


class WorkflowStudioService:
    """工作流定义与运行管理。"""

    # ---------------- 定义 CRUD ----------------

    async def list_definitions(self, tenant_id: int = 0) -> list[dict]:
        async with async_session_maker() as session:
            rows = (await session.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.is_deleted == 0,
                    WorkflowDefinition.tenant_id == tenant_id,
                ).order_by(WorkflowDefinition.update_time.desc())
            )).scalars().all()
            return [self._def_to_out(r) for r in rows]

    async def create_definition(
        self, name: str, dsl: dict, tenant_id: int = 0, created_by: int = 0, description: str = "",
    ) -> dict:
        self._validate(dsl)
        async with async_session_maker() as session:
            row = WorkflowDefinition(
                workflow_id=f"wf_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id, name=name, description=description,
                dsl=dsl, created_by=created_by,
            )
            session.add(row)
            await session.commit()
            return self._def_to_out(row)

    async def get_definition(self, workflow_id: str) -> Optional[dict]:
        row = await self._load_def(workflow_id)
        return self._def_to_out(row) if row else None

    async def update_definition(
        self, workflow_id: str, name: Optional[str] = None, dsl: Optional[dict] = None,
        description: Optional[str] = None,
    ) -> dict:
        row = await self._load_def(workflow_id)
        if not row:
            raise KeyError("工作流不存在")
        if dsl is not None:
            self._validate(dsl)
            row.dsl = dsl
            row.version += 1
            row.status = "draft"  # 改动即回草稿，需重新发布
        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        async with async_session_maker() as session:
            await session.merge(row)
            await session.commit()
        return self._def_to_out(row)

    async def publish_definition(self, workflow_id: str) -> dict:
        row = await self._load_def(workflow_id)
        if not row:
            raise KeyError("工作流不存在")
        row.status = "published"
        async with async_session_maker() as session:
            await session.merge(row)
            await session.commit()
        return self._def_to_out(row)

    # ---------------- 运行 ----------------

    async def start_run(self, workflow_id: str, inputs: Optional[dict] = None, tenant_id: int = 0) -> dict:
        definition = await self._load_def(workflow_id)
        if not definition:
            raise KeyError("工作流不存在")
        dsl = definition.dsl or {}
        self._validate(dsl)

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        async with async_session_maker() as session:
            session.add(WorkflowRun(
                run_id=run_id, workflow_id=workflow_id, tenant_id=tenant_id,
                inputs=inputs or {}, dsl_snapshot=dsl,
            ))
            await session.commit()

        asyncio.create_task(self._execute(run_id, dsl, inputs or {}))
        return {"run_id": run_id, "status": "running"}

    async def get_run(self, workflow_id: str, run_id: str) -> Optional[dict]:
        async with async_session_maker() as session:
            row = (await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.run_id == run_id, WorkflowRun.workflow_id == workflow_id,
                    WorkflowRun.is_deleted == 0,
                )
            )).scalar_one_or_none()
            return self._run_to_out(row) if row else None

    async def resume_run(self, workflow_id: str, run_id: str, value: Any) -> dict:
        run = await self.get_run(workflow_id, run_id)
        if not run:
            raise KeyError("运行记录不存在")
        if run["status"] != "waiting_human":
            raise WorkflowValidationError(f"当前状态 {run['status']} 不可恢复（仅 waiting_human）")
        graph = _ACTIVE_GRAPHS.get(run_id)
        if graph is None:
            raise WorkflowValidationError("执行态已丢失（服务重启），请重新运行工作流")

        asyncio.create_task(self._execute(
            run_id, run["dsl_snapshot"], run["inputs"], resume=Command(resume=value),
        ))
        return {"run_id": run_id, "status": "running"}

    # ---------------- 内部 ----------------

    @staticmethod
    def _validate(dsl: dict) -> None:
        try:
            validate_dsl(dsl)
        except WorkflowValidationError:
            raise
        except Exception as exc:
            raise WorkflowValidationError(f"DSL 结构非法: {exc}") from exc

    async def _execute(self, run_id: str, dsl: dict, inputs: dict, resume: Any = None) -> None:
        try:
            graph = _ACTIVE_GRAPHS.get(run_id)
            if graph is None:
                graph, _checkpointer = compile_workflow(dsl)
                _ACTIVE_GRAPHS[run_id] = graph
            config = {"configurable": {"thread_id": run_id}}
            state = resume if resume is not None else {"inputs": inputs, "variables": {}}
            result = await graph.ainvoke(state, config=config)

            waiting = extract_waiting(result)
            if waiting:
                await self._update_run(run_id, status="waiting_human",
                                       waiting_node=waiting.get("node_id", ""),
                                       waiting_message=str(waiting.get("message", "")),
                                       outputs=self._snapshot(result))
            else:
                await self._update_run(run_id, status="completed", outputs=self._snapshot(result),
                                       waiting_node="", waiting_message="")
        except Exception as exc:  # noqa: BLE001 后台任务兜底：任何失败都落到运行记录
            logger.warning("workflow run %s failed: %s", run_id, exc, exc_info=True)
            await self._update_run(run_id, status="failed", error=str(exc)[:2000])
        finally:
            # waiting 的运行保留执行态供 resume；其余释放
            if await self._run_status(run_id) != "waiting_human":
                _ACTIVE_GRAPHS.pop(run_id, None)

    @staticmethod
    def _snapshot(result: Any) -> dict:
        if not isinstance(result, dict):
            return {}
        return dict(result.get("variables") or {})

    async def _run_status(self, run_id: str) -> Optional[str]:
        async with async_session_maker() as session:
            return (await session.execute(
                select(WorkflowRun.status).where(WorkflowRun.run_id == run_id)
            )).scalar_one_or_none()

    async def _update_run(self, run_id: str, **fields: Any) -> None:
        async with async_session_maker() as session:
            row = (await session.execute(
                select(WorkflowRun).where(WorkflowRun.run_id == run_id)
            )).scalar_one_or_none()
            if not row:
                return
            for k, v in fields.items():
                setattr(row, k, v)
            await session.commit()

    async def _load_def(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        async with async_session_maker() as session:
            return (await session.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.workflow_id == workflow_id,
                    WorkflowDefinition.is_deleted == 0,
                )
            )).scalar_one_or_none()

    @staticmethod
    def _def_to_out(row: WorkflowDefinition) -> dict:
        return {
            "workflow_id": row.workflow_id, "name": row.name, "description": row.description,
            "dsl": row.dsl, "status": row.status, "version": row.version,
            "create_time": row.create_time, "update_time": row.update_time,
        }

    @staticmethod
    def _run_to_out(row: WorkflowRun) -> dict:
        return {
            "run_id": row.run_id, "workflow_id": row.workflow_id, "status": row.status,
            "inputs": row.inputs, "outputs": row.outputs, "error": row.error,
            "waiting_node": row.waiting_node, "waiting_message": row.waiting_message,
            "create_time": row.create_time, "update_time": row.update_time,
        }


workflow_studio_service = WorkflowStudioService()
