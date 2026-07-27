"""语音转写（ASR）。

默认走智谱 GLM-ASR（GLM-ASR-2512），复用 ZAI_API_KEY，开箱即用——无需额外配置。
也可通过 ASR_BASE_URL / ASR_API_KEY 指向任意 OpenAI 兼容 /audio/transcriptions 端点。
未配置（连 ZAI_API_KEY 都没有）时返回占位提示，绝不抛异常打断对话。
"""
import logging

import httpx

from app.ai.glm_provider import GLM_API_URL
from app.core.config import settings

logger = logging.getLogger(__name__)


async def transcribe_audio(data: bytes, mime: str = "", filename: str = "audio") -> str:
    """把音频字节转写为文本。默认智谱 GLM-ASR；无任何 key 时返回占位提示。"""
    base = (settings.asr_base_url or GLM_API_URL).rstrip("/")
    key = settings.asr_api_key or settings.zai_api_key
    if not key:
        return "[语音转写未配置：缺少 ZAI_API_KEY（智谱 GLM-ASR）或 ASR_API_KEY]"

    model = settings.asr_model or "glm-asr-2512"
    files = {"file": (filename or "audio", data, mime or "audio/mpeg")}
    form = {"model": model, "stream": "false"}
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
            text = payload.get("text")
            if text is None:
                # 容错：个别实现字段名不同
                text = payload.get("result") or payload.get("transcription") or ""
            return (text or "").strip()
    except Exception as exc:
        logger.warning("ASR transcribe failed for %s: %s", filename, exc)
        return f"[语音转写失败：{exc}]"
