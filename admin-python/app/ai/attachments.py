"""附件归一化：把 image / document / audio 附件统一转成 (extra_text, image_data_urls)。

- image → image_data_urls（交给视觉模型）
- document（pdf/word/excel/ppt/txt）→ 抽取文本 → extra_text
- audio → ASR 转写 → extra_text

agent 拿到后：把 extra_text 拼进 prompt，把 image_data_urls 作为多模态图像部分。
"""
import base64
import logging
import re
from typing import Any
from urllib.parse import unquote

from app.ai import asr, doc_extract

logger = logging.getLogger(__name__)

_DATA_URI_RE = re.compile(r"data:([^;,]+)?(;base64)?,(.*)", re.DOTALL)

_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/bmp"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_AUDIO_MIMES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/webm",
    "audio/ogg", "audio/m4a", "audio/x-m4a", "audio/mp4", "audio/aac", "audio/flac",
}
_AUDIO_EXTS = {".mp3", ".wav", ".webm", ".ogg", ".m4a", ".aac", ".flac"}

# 防滥用上限（后端独立于前端强制，客户端可绕过前端校验）
MAX_DATA_URI_LEN = 25_000_000  # ~25MB 字符串 ≈ ~18MB 解码后字节
MAX_ATTACHMENTS = 10


def _decode_data_uri(data_uri: str) -> tuple[str, bytes]:
    """拆解 data URI -> (mime, bytes)。非 data URI 时按原始 URL 处理（返回空 bytes）。"""
    data_uri = (data_uri or "").strip()
    m = _DATA_URI_RE.match(data_uri)
    if not m:
        return "", b""
    mime = (m.group(1) or "").lower()
    is_b64 = m.group(2) is not None
    payload = m.group(3)
    if is_b64:
        try:
            return mime, base64.b64decode(payload)
        except Exception:
            return mime, b""
    return mime, unquote(payload).encode("utf-8")


def _category(mime: str, filename: str) -> str:
    import os

    ext = os.path.splitext(filename or "")[1].lower()
    mime = (mime or "").split(";")[0].strip().lower()
    if mime in _IMAGE_MIMES or ext in _IMAGE_EXTS:
        return "image"
    if mime in _AUDIO_MIMES or ext in _AUDIO_EXTS:
        return "audio"
    if mime.startswith("text/") or ext:
        # 有扩展名或 text 都按文档尝试抽取（doc_extract 自身会判 kind）
        return "document"
    return "document"


async def process_attachments(attachments: list[Any]) -> tuple[str, list[str]]:
    """归一化附件 -> (extra_text, image_data_urls)。每个附件失败不阻断其余。"""
    extra_parts: list[str] = []
    image_urls: list[str] = []

    for att in (attachments or [])[:MAX_ATTACHMENTS]:
        if not isinstance(att, dict):
            continue
        mime = att.get("mime", "")
        filename = att.get("filename", "") or att.get("name", "")
        data_uri = att.get("data_uri", "") or att.get("url", "")
        if not data_uri:
            continue
        if len(data_uri) > MAX_DATA_URI_LEN:
            extra_parts.append(f"[附件 {filename}] 超过大小限制（约 18MB），已跳过")
            continue

        category = att.get("type") or _category(mime, filename)

        if category == "image":
            image_urls.append(data_uri)
            continue

        if category == "audio":
            _, raw = _decode_data_uri(data_uri)
            if not raw:
                continue
            transcript = await asr.transcribe_audio(raw, mime, filename)
            extra_parts.append(f"[语音 {filename}]\n{transcript}")
            continue

        # document
        real_mime, raw = _decode_data_uri(data_uri)
        if not raw:
            # 可能是公网 URL；此处只处理内联 data URI，URL 留待后续
            extra_parts.append(f"[文档 {filename}] 仅支持内联上传，外部链接未抓取")
            continue
        text = doc_extract.extract_text_from_bytes(raw, real_mime or mime, filename)
        if text.strip():
            extra_parts.append(f"[文档 {filename}]\n{text}")
        else:
            extra_parts.append(
                f"[文档 {filename}] 无法抽取文本（可能是扫描件/旧版二进制 Office，建议转 PDF 文字版或截图上传）"
            )

    return ("\n\n".join(extra_parts), image_urls)
