"""模型路由 - 根据任务类型自动选择最优 LLM 模型

策略:
  - 复杂推理（需求分析、代码审查）→ 高性能模型
  - 常规开发（代码生成、测试）→ 均衡模型
  - 简单任务（报告、提交信息）→ 快速模型
"""
import logging
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 当前 pipeline 归因上下文：flow_manager 运行管线时 bind，record_usage 自动归因到该管线
_pipeline_ctx: ContextVar = ContextVar("llm_pipeline_ctx", default=None)


def bind_pipeline_context(pipeline_id: str, tenant_id: Optional[int] = None):
    """绑定当前管线上下文，返回 token（配合 reset_pipeline_context）。"""
    return _pipeline_ctx.set((pipeline_id, tenant_id))


def reset_pipeline_context(token):
    """解除绑定。"""
    _pipeline_ctx.reset(token)


@asynccontextmanager
async def pipeline_context(pipeline_id: str, tenant_id: Optional[int] = None,
                           stage: Optional[str] = None):
    """``async with``：在作用域内把 LLM 用量/延迟归因到该 pipeline（+ 可选阶段）。

    stage 传入时同步绑定当前调用阶段，glm_provider 记录延迟时读取，用于按阶段分组。
    """
    token = bind_pipeline_context(pipeline_id, tenant_id)
    stage_token = None
    if stage:
        try:
            from app.ai.glm_provider import bind_call_stage
            stage_token = bind_call_stage(stage)
        except Exception:  # noqa: BLE001
            stage_token = None
    try:
        yield
    finally:
        reset_pipeline_context(token)
        if stage_token is not None:
            try:
                from app.ai.glm_provider import reset_call_stage
                reset_call_stage(stage_token)
            except Exception:  # noqa: BLE001
                pass


class TaskComplexity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ModelConfig:
    """模型配置"""
    model_name: str
    provider: str  # glm, anthropic, openai
    max_tokens: int = 4096
    temperature: float = 0.7
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


# 智谱 GLM 官方单价（每 1K tokens，单位：元 ¥，2024-2025 公开价，便于成本看板估算）。
# record_usage 在 _models（claude 等）未命中时按模型名/前缀查这里。
GLM_PRICING_PER_1K = {
    "glm-4-plus": (0.05, 0.05),
    "glm-4": (0.1, 0.1),
    "glm-4-air": (0.001, 0.001),
    "glm-4-airx": (0.001, 0.001),
    "glm-4-flash": (0.0001, 0.0001),   # 限时免费/极低
    "glm-4-flashx": (0.0001, 0.0001),
    "glm-4-long": (0.001, 0.001),
    "glm-4v": (0.05, 0.05),
    "glm-4v-plus": (0.05, 0.0),
    "glm-4v-flash": (0.0001, 0.0001),
    "glm-5": (0.5, 0.5),
    "glm-5.1": (0.5, 0.5),
    "embedding-3": (0.0005, 0.0),
    "glm-asr-2512": (0.0, 0.0),
}


def _glm_price(model: str) -> tuple[float, float]:
    """按模型名精确或前缀匹配 GLM 单价 (in, out) per 1K tokens；未匹配返回 (0,0)。"""
    if model in GLM_PRICING_PER_1K:
        return GLM_PRICING_PER_1K[model]
    for key, price in GLM_PRICING_PER_1K.items():
        if model.startswith(key):
            return price
    return (0.0, 0.0)


@dataclass
class UsageRecord:
    """Token 使用 + 性能记录（支撑 AI 效果评测：响应速度/准确率/幻觉/成本）"""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    timestamp: float = 0.0
    pipeline_id: Optional[str] = None
    tenant_id: Optional[int] = None
    latency_ms: Optional[int] = None   # 单次调用总延迟
    ttft_ms: Optional[int] = None      # 流式首字延迟
    success: bool = True
    error: Optional[str] = None
    stage: Optional[str] = None        # 调用来源/阶段


# Agent 类型到任务复杂度的映射
AGENT_COMPLEXITY = {
    "PM": TaskComplexity.HIGH,
    "PJM": TaskComplexity.MEDIUM,
    "BE": TaskComplexity.MEDIUM,
    "FE": TaskComplexity.MEDIUM,
    "QA": TaskComplexity.HIGH,
    "RPT": TaskComplexity.LOW,
    "USER": TaskComplexity.LOW,
}

# Pipeline 阶段到任务复杂度的映射
STAGE_COMPLEXITY = {
    "requirement": TaskComplexity.HIGH,
    "ui_preview": TaskComplexity.MEDIUM,
    "development_be": TaskComplexity.MEDIUM,
    "development_fe": TaskComplexity.MEDIUM,
    "code_review": TaskComplexity.HIGH,
    "testing": TaskComplexity.MEDIUM,
    "commit": TaskComplexity.LOW,
    "deploy": TaskComplexity.LOW,
    "report": TaskComplexity.LOW,
}


class ModelRouter:
    """模型路由器"""

    def __init__(self, default_provider: str = "glm"):
        self.default_provider = default_provider
        self._models: Dict[TaskComplexity, ModelConfig] = {}
        self._usage: List[UsageRecord] = []
        self._usage_lock = Lock()
        self._setup_default_models()

    def _setup_default_models(self):
        """配置默认模型路由"""
        if self.default_provider == "glm":
            self._models = {
                TaskComplexity.HIGH: ModelConfig(
                    model_name="glm-4-plus", provider="glm",
                    max_tokens=4096, temperature=0.7,
                    cost_per_1k_input=0.05, cost_per_1k_output=0.05,
                ),
                TaskComplexity.MEDIUM: ModelConfig(
                    model_name="glm-4-flash", provider="glm",
                    max_tokens=4096, temperature=0.7,
                    cost_per_1k_input=0.001, cost_per_1k_output=0.001,
                ),
                TaskComplexity.LOW: ModelConfig(
                    model_name="glm-4-flash", provider="glm",
                    max_tokens=2048, temperature=0.5,
                    cost_per_1k_input=0.001, cost_per_1k_output=0.001,
                ),
            }
        elif self.default_provider == "anthropic":
            self._models = {
                TaskComplexity.HIGH: ModelConfig(
                    model_name="claude-sonnet-4-20250514", provider="anthropic",
                    max_tokens=4096, temperature=0.7,
                    cost_per_1k_input=0.003, cost_per_1k_output=0.015,
                ),
                TaskComplexity.MEDIUM: ModelConfig(
                    model_name="claude-sonnet-4-20250514", provider="anthropic",
                    max_tokens=4096, temperature=0.7,
                    cost_per_1k_input=0.003, cost_per_1k_output=0.015,
                ),
                TaskComplexity.LOW: ModelConfig(
                    model_name="claude-haiku-4-5-20251001", provider="anthropic",
                    max_tokens=2048, temperature=0.5,
                    cost_per_1k_input=0.001, cost_per_1k_output=0.005,
                ),
            }

    def get_model_for_agent(self, agent_type: str) -> ModelConfig:
        """根据 Agent 类型获取模型配置"""
        complexity = AGENT_COMPLEXITY.get(agent_type, TaskComplexity.MEDIUM)
        return self._models.get(complexity, self._models[TaskComplexity.MEDIUM])

    def get_model_for_stage(self, stage_key: str) -> ModelConfig:
        """根据 Pipeline 阶段获取模型配置"""
        complexity = STAGE_COMPLEXITY.get(stage_key, TaskComplexity.MEDIUM)
        return self._models.get(complexity, self._models[TaskComplexity.MEDIUM])

    def get_model_by_complexity(self, complexity: TaskComplexity) -> ModelConfig:
        """直接按复杂度获取模型"""
        return self._models.get(complexity, self._models[TaskComplexity.MEDIUM])

    def record_usage(self, model: str, input_tokens: int, output_tokens: int,
                     pipeline_id: Optional[str] = None, tenant_id: Optional[int] = None,
                     latency_ms: Optional[int] = None, ttft_ms: Optional[int] = None,
                     success: bool = True, error: Optional[str] = None,
                     stage: Optional[str] = None):
        """记录 token 用量 + 性能/成功指标；pipeline_id/tenant_id 缺省时取当前管线上下文。"""
        ctx = _pipeline_ctx.get()
        if ctx:
            if pipeline_id is None:
                pipeline_id = ctx[0]
            if tenant_id is None:
                tenant_id = ctx[1]

        config = None
        for c in self._models.values():
            if c.model_name == model:
                config = c
                break

        cost = 0.0
        if config:
            cost = (input_tokens / 1000 * config.cost_per_1k_input +
                    output_tokens / 1000 * config.cost_per_1k_output)
        else:
            # _models 仅含 claude 等；GLM 模型按官方单价估算
            in_rate, out_rate = _glm_price(model)
            if in_rate or out_rate:
                cost = input_tokens / 1000 * in_rate + output_tokens / 1000 * out_rate

        record = UsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            timestamp=time.time(),
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            success=success,
            error=(error[:255] if error else None),
            stage=stage,
        )

        with self._usage_lock:
            self._usage.append(record)
            if len(self._usage) > 10000:
                self._usage = self._usage[-5000:]

    async def flush_usage(self, session) -> int:
        """把缓冲区的用量批量写入 llm_usage_log，返回写入条数；失败回灌避免丢失。"""
        with self._usage_lock:
            if not self._usage:
                return 0
            batch = self._usage[:]
            self._usage.clear()
        try:
            from app.models.llm_usage_log import LLMUsageLog

            now = int(time.time() * 1000)
            session.add_all([
                LLMUsageLog(
                    tenant_id=r.tenant_id, pipeline_id=r.pipeline_id, model=r.model,
                    input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                    cost=r.cost, create_time=now,
                    latency_ms=r.latency_ms, ttft_ms=r.ttft_ms,
                    success=1 if r.success else 0, error=r.error, stage=r.stage,
                )
                for r in batch
            ])
            await session.commit()
            return len(batch)
        except Exception as e:
            logger.error(f"flush_usage failed: {e}")
            with self._usage_lock:
                self._usage = batch + self._usage
            return 0

    def get_usage_stats(self, hours: int = 24) -> Dict:
        """获取最近 N 小时的使用统计"""
        cutoff = time.time() - hours * 3600
        with self._usage_lock:
            recent = [r for r in self._usage if r.timestamp >= cutoff]

        if not recent:
            return {"total_requests": 0, "total_tokens": 0, "total_cost": 0.0}

        total_input = sum(r.input_tokens for r in recent)
        total_output = sum(r.output_tokens for r in recent)
        total_cost = sum(r.cost for r in recent)

        by_model = {}
        for r in recent:
            if r.model not in by_model:
                by_model[r.model] = {"requests": 0, "tokens": 0, "cost": 0.0}
            by_model[r.model]["requests"] += 1
            by_model[r.model]["tokens"] += r.input_tokens + r.output_tokens
            by_model[r.model]["cost"] += r.cost

        return {
            "total_requests": len(recent),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost": round(total_cost, 4),
            "by_model": by_model,
        }


model_router = ModelRouter(default_provider="glm")
