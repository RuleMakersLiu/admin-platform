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


def _extract_code_files(code_files: Any) -> list:
    """从 code_files 抽取实际代码文本。

    支持三种形态（pipeline 不同阶段写法不一）：
    - dict: {path: content}（直接 key=路径、value=内容）
    - list[{path,content}]: 每项含 path 与 content/code
    - list[str]: 裸内容
    """
    parts: list = []
    if isinstance(code_files, dict):
        for path, content in code_files.items():
            if isinstance(content, str) and content.strip():
                parts.append(f"// {path}\n{content}")
            elif isinstance(content, dict):
                c = content.get("content") or content.get("code") or ""
                if isinstance(c, str) and c.strip():
                    parts.append(f"// {path}\n{c}")
    elif isinstance(code_files, list):
        for f in code_files:
            if isinstance(f, dict):
                path = f.get("path") or f.get("name") or ""
                content = f.get("content") or f.get("code") or ""
                if isinstance(content, str) and content.strip():
                    parts.append(f"// {path}\n{content}" if path else content)
            elif isinstance(f, str) and f.strip():
                parts.append(f)
    return parts


def _try_parse_code_array(text: str) -> list:
    """output 字段常是 JSON 数组字符串 [{path,content}, ...]；解析失败返回 []。"""
    s = text.strip()
    if not s or s[0] not in "[{":
        return []
    try:
        parsed = json.loads(s)
    except Exception:
        return []
    if isinstance(parsed, list):
        return _extract_code_files(parsed)
    if isinstance(parsed, dict):
        # 可能是 {path:content} 或单个 {path,content}
        if any(k in parsed for k in ("content", "code")):
            return _extract_code_files([parsed])
        return _extract_code_files(parsed)
    return []


def extract_pipeline_output(stages_data_str: Any) -> str:
    """尽力从 pipeline 的 stages_data 抽取可评审的产物文本（前端代码优先）。

    prototype 阶段把生成代码写在多个位置（实测：output 是 JSON 数组 [{path,content}]，
    code_files 是 dict {path:content}，preview_html 是裸 HTML），本函数逐一兜底，
    确保抽到的是「真实代码内容」而非「文件名清单」。
    """
    try:
        data = json.loads(stages_data_str or "{}")
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""

    # 优先前端产物阶段；取到即止（避免拼接过多无关阶段）
    for stage_key in ("prototype", "frontend_dev", "page_design", "delivery"):
        sd = data.get(stage_key)
        if not isinstance(sd, dict):
            continue
        parts: list = []
        # 1. code_files（dict 或 list）
        parts.extend(_extract_code_files(sd.get("code_files")))
        # 2. preview_html（裸 HTML）
        preview = sd.get("preview_html")
        if isinstance(preview, str) and preview.strip():
            parts.append(preview)
        # 3. output（常为 JSON 数组 [{path,content}]，也可能是纯文本/HTML）
        out = sd.get("output")
        if isinstance(out, str) and out.strip():
            parsed = _try_parse_code_array(out)
            if parsed:
                parts.extend(parsed)
            else:
                parts.append(out)
        # 4. structured_output.code_files（部分版本写这里）
        so = sd.get("structured_output")
        if isinstance(so, dict):
            parts.extend(_extract_code_files(so.get("code_files") or so.get("files")))
        if parts:
            return "\n\n".join(p for p in parts if p).strip()

    # 最终回退：各阶段的 output / raw_output 纯文本
    parts: list = []
    for stage_key, sd in data.items():
        if not isinstance(sd, dict):
            continue
        for field in ("raw_output", "output"):
            raw = sd.get(field)
            if isinstance(raw, str) and raw.strip():
                parts.append(f"## {stage_key}\n{raw}")
    return "\n\n".join(parts).strip()


def input_spec_to_request_text(input_spec: Any) -> str:
    """把 golden case 的 input_spec 归一化为可用于创建 pipeline 的需求文本。"""
    if input_spec is None:
        return ""
    if isinstance(input_spec, str):
        return input_spec.strip()
    if isinstance(input_spec, dict):
        for key in ("requirement", "user_request", "prompt", "需求", "description"):
            v = input_spec.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return json.dumps(input_spec, ensure_ascii=False)
    return json.dumps(input_spec, ensure_ascii=False)


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


def build_vision_judge_llm():
    """构造视觉评审用 LLM（GLM-4V，json mode，max_tokens 受限 2048）；未配置返回 None。"""
    try:
        from app.ai.glm_provider import ChatGLM

        vision_model = getattr(settings, "zai_vision_model", None) or "glm-4v"
        llm = ChatGLM(model=vision_model, temperature=0.2)
        # GLM-4V max_tokens 上限 2048（>2048 → 400 参数非法）
        try:
            llm.max_tokens = min(int(llm.max_tokens or 2048), 2048)
        except (TypeError, ValueError):
            llm.max_tokens = 2048
        llm.response_format = {"type": "json_object"}
        return llm
    except Exception:
        return None


async def judge_output_vision(
    image_data_uri: str,
    input_spec: Any,
    criteria: Any,
    llm: Optional[Any] = None,
) -> dict:
    """视觉评审：依据评判标准对【渲染后的前端页面截图】逐项打分。

    与 judge_output（读代码文本）互补——本函数让评测覆盖「真正渲染出来对不对」，
    而非仅「代码里有没有」。image_data_uri 为 data:image/png;base64,... 或可访问图片 URL。
    """
    if llm is None:
        llm = build_vision_judge_llm()
    if llm is None:
        return {"overall_score": None, "per_criterion": [], "summary": "", "error": "AI 视觉模型未配置（缺少 API Key）"}

    from app.ai.glm_provider import build_vision_messages

    output_desc = "【产物】见下方截图：这是流水线生成并真实渲染出的前端页面。请基于截图可见内容评审。"
    prompt = build_judge_prompt(input_spec, output_desc, criteria)
    messages = build_vision_messages(prompt, [image_data_uri])
    try:
        resp = await llm.ainvoke(messages)
    except Exception as exc:
        logger.warning("vision judge LLM call failed: %s", exc)
        return {"overall_score": None, "per_criterion": [], "summary": "", "error": f"视觉评审调用失败: {exc}"}

    result = parse_judgment(resp.content)
    result["model"] = getattr(llm, "model", None)
    result["mode"] = "vision"
    return result
