"""上下文 token 预算：粗估 token 数 + 按模型输入窗口裁剪 message，防超窗失败。

GLM 无公开 tokenizer，用 CJK-friendly 的 len/2 粗估（够做预算 guard-rail，非精确计费）。
流水线 prompt = memory + fix + contract + stage_prompt（核心需求在尾部），故裁剪保尾部、丢头部
（memory/fix 这种「上下文」优先丢，保 stage_prompt + 契约）。
"""
from __future__ import annotations

CHARS_PER_TOKEN = 2  # CJK-heavy 粗估（中文 ~1.5-2 字/token，英文 ~4 字符/token，取中）
DEFAULT_INPUT_WINDOW = 128000


def estimate_tokens(text: str | None) -> int:
    """粗估 token 数（len/2）。"""
    return max(1, len(text or "") // CHARS_PER_TOKEN)


def model_input_window(model: str) -> int:
    """模型的输入上下文窗口（token）。未知模型默认 128k。"""
    try:
        from app.ai.glm_provider import MODEL_INPUT_WINDOWS

        return MODEL_INPUT_WINDOWS.get(model or "", DEFAULT_INPUT_WINDOW)
    except Exception:  # noqa: BLE001
        return DEFAULT_INPUT_WINDOW


def trim_message_for_window(message: str, model: str, keep_ratio: float = 0.6) -> str:
    """把 message 裁到「模型输入窗口 × keep_ratio」估算字符内（保尾部核心，丢头部上下文）。

    未超则原样返回；超则取尾部 + 头部加截断标记。用于 LLM 报「context length exceeded」时截断重试。
    """
    if not message:
        return message
    budget_chars = int(model_input_window(model) * keep_ratio) * CHARS_PER_TOKEN
    if len(message) <= budget_chars:
        return message
    return "\n\n...[上下文超出模型窗口，已截断头部 context]...\n\n" + message[-budget_chars:]
