"""工作流编排模型：Dify 式可视化编排的 DSL 定义与运行记录。

- WorkflowDefinition: 用户在画布上编排出的 DSL（draft/published 双态，版本递增）
- WorkflowRun: 一次执行的状态机（running → waiting_human / completed / failed）

表结构经 Base.metadata.create_all 自动建表（见 app.core.database.init_db）。
"""
import time

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now_ms() -> int:
    return int(time.time() * 1000)


class WorkflowDefinition(Base):
    """工作流定义（DSL 草稿与发布版本）。

    dsl 结构（WorkflowDSL）：
      {"version": 1, "name": "...", "nodes": [...], "edges": [{"from","to","when"?}]}
    """

    __tablename__ = "workflow_definition"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(512), default="")
    dsl: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft / published
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[int] = mapped_column(BigInteger, default=_now_ms)
    update_time: Mapped[int] = mapped_column(BigInteger, default=_now_ms, onupdate=_now_ms)
    is_deleted: Mapped[int] = mapped_column(Integer, default=0, index=True)


class WorkflowRun(Base):
    """一次工作流执行：供前端轮询展示节点状态与产物。"""

    __tablename__ = "workflow_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    workflow_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    # running / waiting_human / completed / failed
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)  # node_id -> node 输出快照
    error: Mapped[str] = mapped_column(Text, default="")
    waiting_node: Mapped[str] = mapped_column(String(64), default="")  # 等待人工输入的节点
    waiting_message: Mapped[str] = mapped_column(Text, default="")
    dsl_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # 执行时的 DSL 版本快照
    create_time: Mapped[int] = mapped_column(BigInteger, default=_now_ms)
    update_time: Mapped[int] = mapped_column(BigInteger, default=_now_ms, onupdate=_now_ms)
    is_deleted: Mapped[int] = mapped_column(Integer, default=0, index=True)
