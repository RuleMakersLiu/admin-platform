"""PDF 扫描件视觉兜底（A2）+ 大文档截断（A3）测试。"""
import base64
import io

import fitz  # pymupdf

from app.ai.attachments import process_attachments


def _pdf_data_uri(pdf_bytes: bytes, name: str = "x.pdf") -> dict:
    return {"mime": "application/pdf", "filename": name,
            "data_uri": f"data:application/pdf;base64,{base64.b64encode(pdf_bytes).decode()}"}


def _make_text_pdf(text: str = "Hello real PDF text layer") -> bytes:
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((50, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_scanned_pdf() -> bytes:
    """图片型 PDF（无文本层）—— pypdf extract_text 返回空。"""
    doc = fitz.open()
    p = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 100))
    pix.clear_with(255)
    p.insert_image(fitz.Rect(20, 20, 280, 80), pixmap=pix)  # 仅图片，无文本层
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_scanned_pdf_falls_back_to_vision_images():
    """扫描件/图片 PDF（无可抽文本）→ 页转图喂视觉模型（image_urls 非空）。"""
    import asyncio

    extra, image_urls = asyncio.run(process_attachments([_pdf_data_uri(_make_scanned_pdf(), "scan.pdf")]))
    assert len(image_urls) > 0, "扫描件应触发视觉兜底（页转图）"
    assert all(u.startswith("data:image/png;base64,") for u in image_urls)
    assert "扫描件" in extra or "视觉模型" in extra


def test_normal_text_pdf_stays_text_path():
    """正常文本 PDF → 纯文本抽取（image_urls 空，extra 含原文）。"""
    import asyncio

    extra, image_urls = asyncio.run(process_attachments([_pdf_data_uri(_make_text_pdf(), "real.pdf")]))
    assert len(image_urls) == 0
    assert "Hello real PDF text layer" in extra


def test_large_document_truncated():
    """A3：大文档超 attachment_max_chars → 截断 + 提示。"""
    import asyncio

    big = "A" * 20000
    att = {"mime": "text/plain", "filename": "big.txt",
           "data_uri": "data:text/plain;base64," + base64.b64encode(big.encode()).decode()}
    extra, _ = asyncio.run(process_attachments([att]))
    assert "已截断" in extra
    assert "12000" in extra
