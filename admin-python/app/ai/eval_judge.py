"""LLM-as-judge 评测：依据评判标准对产物逐项打分。

输入：需求(input_spec) + 产物(output) + 评判标准(criteria)。
输出：{overall_score, per_criterion:[{criterion,score,passed,reason}], summary, model?}。
用 GLM json mode 拿结构化结果；解析容错（直接 JSON / 抽取 {...} / 纯文本降级）。
"""
import json
import logging
import re
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_judge_prompt(input_spec: Any, output: str, criteria: Any) -> str:
    """构造评审 prompt（纯函数，便于测试）。"""
    return f"""你是严谨的软件产物评审官。请依据【评判标准】判断【产物】是否满足【需求】，逐条打分。

【需求】
{_stringify(input_spec)}

【产物】
{output}

【评判标准】（逐条评审）
{_stringify(criteria)}

严格按以下 JSON 结构输出（仅输出 JSON，不要额外文字）：
{{
  "overall_score": "0-100 的整数",
  "per_criterion": [
    {{"criterion": "标准原文", "score": "0-100 整数", "passed": "true/false", "reason": "简短理由"}}
  ],
  "summary": "总体评价"
}}

要求：per_criterion 必须覆盖每一条标准；passed 表示该条 score >= 60；overall_score 为综合分。"""


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def parse_judgment(content: Any) -> dict:
    """把模型输出解析为结构化评审结果（纯函数，容错）。"""
    empty = {"overall_score": None, "per_criterion": [], "summary": ""}
    if not content:
        return {**empty, "error": "空响应"}
    text = content.strip() if isinstance(content, str) else str(content)
    data = _extract_json(text)
    if not data:
        return {**empty, "error": "无法解析评审 JSON", "raw": text[:500]}

    norm = []
    for item in data.get("per_criterion") or []:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = None
        passed = item.get("passed")
        if not isinstance(passed, bool):
            passed = score is not None and score >= 60
        norm.append({
            "criterion": item.get("criterion", ""),
            "score": score,
            "passed": passed,
            "reason": item.get("reason", ""),
        })

    overall = data.get("overall_score")
    try:
        overall = int(overall)
    except (TypeError, ValueError):
        overall = None
    if overall is None and norm:
        scores = [n["score"] for n in norm if n["score"] is not None]
        if scores:
            overall = round(sum(scores) / len(scores))

    return {
        "overall_score": overall,
        "per_criterion": norm,
        "summary": data.get("summary", ""),
    }


def build_judge_llm():
    """构造评审用 LLM（json mode，低温）；未配置返回 None。"""
    try:
        from app.ai.glm_provider import ChatGLM

        llm = ChatGLM(model=settings.zai_default_model, temperature=0.2)
        llm.response_format = {"type": "json_object"}
        return llm
    except Exception:
        return None


async def judge_output(
    input_spec: Any, output: str, criteria: Any, llm: Optional[Any] = None
) -> dict:
    """对产物按标准评审。llm 可注入（测试用）；默认用 GLM json mode。"""
    if llm is None:
        llm = build_judge_llm()
    if llm is None:
        return {"overall_score": None, "per_criterion": [], "summary": "", "error": "AI 未配置（缺少 API Key）"}

    prompt = build_judge_prompt(input_spec, output, criteria)
    try:
        resp = await llm.ainvoke([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("judge LLM call failed: %s", exc)
        return {"overall_score": None, "per_criterion": [], "summary": "", "error": f"评审调用失败: {exc}"}

    result = parse_judgment(resp.content)
    result["model"] = getattr(llm, "model", None)
    return result
