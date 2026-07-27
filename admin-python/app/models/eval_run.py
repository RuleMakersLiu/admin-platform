"""评测运行记录：把 golden case 与一次 pipeline 执行关联，承载自动评审结果。

run-from-golden-case 创建一条 EvalRun(status=running) 并触发管线执行；
管线到达终态时 _record_pipeline_eval 自动评审并回写 judgment/overall_score。
"""
import time
from typing import Optional

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EvalRun(Base):
    __tablename__ = "eval_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    golden_case_id: Mapped[int] = mapped_column(BigInteger, index=True)
    pipeline_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running / judged / failed

    overall_score: Mapped[Optional[int]] = mapped_column(Integer)
    judgment: Mapped[Optional[str]] = mapped_column(Text)  # JSON：评审详情

    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
