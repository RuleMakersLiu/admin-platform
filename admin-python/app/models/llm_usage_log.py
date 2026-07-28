"""LLM 调用用量记录（按 pipeline / tenant 归因，支撑 eval 成本列与成本看板）。"""
import time
from typing import Optional

from sqlalchemy import BigInteger, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    pipeline_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    # 性能与成功指标（migration 014）—— 支撑 AI 效果评测体系
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)        # 单次调用总延迟
    ttft_ms: Mapped[Optional[int]] = mapped_column(Integer)           # 流式首字延迟；非流式 None
    success: Mapped[int] = mapped_column(Integer, default=1)          # 1 成功 / 0 失败
    error: Mapped[Optional[str]] = mapped_column(String(255))         # 失败错误摘要
    stage: Mapped[Optional[str]] = mapped_column(String(64))          # 调用来源/阶段
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
