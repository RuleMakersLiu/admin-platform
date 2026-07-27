"""评测 Golden Case 模型：固定 输入→期望标准，用于回归评测与质量门控。

一条 golden case = 一份确定的需求/输入 + 一组评判标准。评测 runner 拿它跑
pipeline（或对已有产物）并用 LLM-as-judge 按标准打分，形成可追踪的质量回归。
"""
import time
from typing import Optional

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EvalGoldenCase(Base):
    __tablename__ = "eval_golden_case"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), default="general")  # frontend/backend/fullstack/general
    project_type: Mapped[Optional[str]] = mapped_column(String(64))  # 目标技能/项目类型
    input_spec: Mapped[str] = mapped_column(Text)  # JSON：需求/prompt（+ 可选期望产物）
    expected_criteria: Mapped[str] = mapped_column(Text)  # JSON：评判标准/检查点
    tags: Mapped[Optional[str]] = mapped_column(String(256))
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger)

    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
