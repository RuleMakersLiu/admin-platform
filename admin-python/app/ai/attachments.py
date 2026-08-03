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
from app.core.config import settings

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
        effective_mime = real_mime or mime
        text = doc_extract.extract_text_from_bytes(raw, effective_mime, filename)
        is_pdf = doc_extract._kind(effective_mime, filename) == "pdf"
        if text.strip():
            # A3: 大文档截断上限（防全文进 prompt 超窗）
            max_chars = settings.attachment_max_chars
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n...[文档已截断，仅取前 {max_chars} 字符]"
            extra_parts.append(f"[文档 {filename}]\n{text}")
        elif is_pdf:
            # A2: PDF 文本空/极短 → 视觉兜底：页转图喂 GLM-4V（扫描件/图片 PDF）
            page_images = _pdf_pages_to_image_data_uris(raw, max_pages=4)
            if page_images:
                image_urls.extend(page_images)
                extra_parts.append(
                    f"[文档 {filename}] 为扫描件/图片 PDF（无可抽文本），已转 {len(page_images)} 页图交视觉模型识别"
                )
            else:
                extra_parts.append(f"[文档 {filename}] 无法抽取文本（空 PDF 且转图失败）")
        else:
            extra_parts.append(
                f"[文档 {filename}] 无法抽取文本（可能是旧版二进制 Office，建议转 PDF/截图上传）"
            )

    return ("\n\n".join(extra_parts), image_urls)


def _pdf_pages_to_image_data_uris(data: bytes, max_pages: int = 4, dpi: int = 130) -> list[str]:
    """PDF 前若干页渲染成 PNG data_uri（pymupdf/fitz）。用于扫描件/图片 PDF 的视觉兜底。

    自包含（pymupdf wheel 不依赖 poppler）；失败返回 []。dpi=130 平衡清晰度与 base64 体积。
    """
    try:
        import fitz  # pymupdf  # noqa: F401
    except ImportError:
        logger.info("pymupdf 未安装，PDF 扫描件视觉兜底跳过")
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        uris: list[str] = []
        for i in range(min(max_pages, doc.page_count)):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=dpi)
            png = pix.tobytes("png")
            b64 = base64.b64encode(png).decode("ascii")
            uris.append(f"data:image/png;base64,{b64}")
        doc.close()
        return uris
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF 页转图失败: %s", exc)
        return []
