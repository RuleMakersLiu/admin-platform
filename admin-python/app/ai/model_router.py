"""模型路由 - 根据任务类型自动选择最优 LLM 模型

策略:
  - 复杂推理（需求分析、代码审查）→ 高性能模型
  - 常规开发（代码生成、测试）→ 均衡模型
  - 简单任务（报告、提交信息）→ 快速模型
"""
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


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


@dataclass
class UsageRecord:
    """Token 使用记录"""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    timestamp: float = 0.0


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

    def record_usage(self, model: str, input_tokens: int, output_tokens: int):
        """记录 token 使用量"""
        config = None
        for c in self._models.values():
            if c.model_name == model:
                config = c
                break

        cost = 0.0
        if config:
            cost = (input_tokens / 1000 * config.cost_per_1k_input +
                    output_tokens / 1000 * config.cost_per_1k_output)

        record = UsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            timestamp=time.time(),
        )

        with self._usage_lock:
            self._usage.append(record)
            if len(self._usage) > 10000:
                self._usage = self._usage[-5000:]

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
