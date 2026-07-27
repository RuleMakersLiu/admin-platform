"""语音转写（ASR）：OpenAI 兼容的 Whisper 端点。

智谱 BigModel 暂无通用 ASR，故采用 OpenAI 兼容协议，可指向任意 Whisper 实现
（OpenAI / Groq / 本地 whisper-server / faster-whisper 等）。未配置时返回占位提示，
绝不抛异常打断对话。
"""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def transcribe_audio(data: bytes, mime: str = "", filename: str = "audio") -> str:
    """把音频字节转写为文本。未配置 ASR 时返回明确的占位提示。"""
    base = (settings.asr_base_url or "").rstrip("/")
    key = settings.asr_api_key
    if not base or not key:
        return "[语音转写未配置：请在环境变量设置 ASR_BASE_URL 与 ASR_API_KEY（OpenAI 兼容 Whisper 端点）]"

    model = settings.asr_model or "whisper-1"
    files = {"file": (filename or "audio", data, mime or "audio/mpeg")}
    form = {"model": model}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files=files,
                data=form,
            )
            resp.raise_for_status()
            payload = resp.json()
            return (payload.get("text") or "").strip()
    except Exception as exc:
        logger.warning("ASR transcribe failed for %s: %s", filename, exc)
        return f"[语音转写失败：{exc}]"
