"""Pipeline 评测结果模型（Eval 闭环：把埋在 stages_data 里的评测信号结构化为可 SQL 聚合的扁平列）"""
import time
from typing import Optional

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PipelineEvalResult(Base):
    """pipeline 终态评测结果：聚合各 stage 的 pm/design/preview quality、review/tests 通过情况、
    retry/修复轮次为统一记录，支撑质量看板与趋势分析。"""
    __tablename__ = "pipeline_eval_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    eval_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    pipeline_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))  # completed / failed

    # 综合分 + 各维度分（0-100；维度未评测时为 None）
    overall_score: Mapped[Optional[int]] = mapped_column(Integer)
    pm_quality_score: Mapped[Optional[int]] = mapped_column(Integer)
    design_quality_score: Mapped[Optional[int]] = mapped_column(Integer)
    preview_quality_score: Mapped[Optional[int]] = mapped_column(Integer)

    # LLM-as-judge 评测分（eval 阶段产物；0-100，未评测/出错时 None）。与上面规则维度分并列——
    # 不并入 overall_score（保看板 bucket/pass-rate 阈值 60 不变），单独成列供看板展示 + 质量门控。
    judge_score: Mapped[Optional[int]] = mapped_column(Integer)
    hallucination_score: Mapped[Optional[int]] = mapped_column(Integer)
    vision_score: Mapped[Optional[int]] = mapped_column(Integer)
    e2e_passed: Mapped[Optional[int]] = mapped_column(Integer)  # 0/1

    # 人工覆盖分（人工对最终交付的主观打分；用于校准 LLM judge）。_record_pipeline_eval 的 upsert
    # 不写这些列——重跑 eval 不会清掉人工分。
    human_score: Mapped[Optional[int]] = mapped_column(Integer)            # 0-100
    human_comment: Mapped[Optional[str]] = mapped_column(String(500))
    human_scored_by: Mapped[Optional[int]] = mapped_column(BigInteger)    # admin id
    human_scored_at: Mapped[Optional[int]] = mapped_column(BigInteger)    # epoch ms

    # 布尔门控结果（0/1）
    review_passed: Mapped[Optional[int]] = mapped_column(Integer)
    tests_passed: Mapped[Optional[int]] = mapped_column(Integer)

    # 测试计数
    tests_total: Mapped[Optional[int]] = mapped_column(Integer)
    tests_passed_count: Mapped[Optional[int]] = mapped_column(Integer)
    tests_failed_count: Mapped[Optional[int]] = mapped_column(Integer)

    # 修复过程
    retry_count: Mapped[Optional[int]] = mapped_column(Integer)
    auto_repair_iterations: Mapped[Optional[int]] = mapped_column(Integer)

    # 测试元信息
    framework: Mapped[Optional[str]] = mapped_column(String(32))
    test_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # 各 stage 详细分 / issue 数（JSON）
    stage_scores: Mapped[Optional[str]] = mapped_column(Text)

    # cost 预留（本期不填，需 model_router 改造后回填）
    cost_input_tokens: Mapped[Optional[int]] = mapped_column(BigInteger)
    cost_output_tokens: Mapped[Optional[int]] = mapped_column(BigInteger)

    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
