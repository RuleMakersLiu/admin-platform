"""Tests for the attachment normalizer + ASR (offline; httpx mocked)."""
import asyncio
import base64

from app.ai import asr, attachments


def _run(coro):
    return asyncio.run(coro)


def _b64(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def test_image_attachment_collects_image_url():
    extra, images = _run(attachments.process_attachments([
        {"type": "image", "mime": "image/png", "filename": "a.png", "data_uri": _b64("image/png", b"PNG")},
    ]))
    assert extra == ""
    assert images == [_b64("image/png", b"PNG")]


def test_document_attachment_extracts_text():
    extra, images = _run(attachments.process_attachments([
        {"type": "document", "mime": "text/plain", "filename": "req.txt",
         "data_uri": _b64("text/plain", "需求：登录页".encode())},
    ]))
    assert images == []
    assert "需求：登录页" in extra
    assert "req.txt" in extra


def test_audio_unconfigured_returns_placeholder(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "asr_base_url", "")
    monkeypatch.setattr(settings, "asr_api_key", "")
    monkeypatch.setattr(settings, "zai_api_key", None)  # 连 zai key 也没有才视为未配置
    extra, images = _run(attachments.process_attachments([
        {"type": "audio", "mime": "audio/mpeg", "filename": "v.mp3", "data_uri": _b64("audio/mpeg", b"AUDIO")},
    ]))
    assert images == []
    assert "语音转写未配置" in extra


def test_mixed_attachments_image_plus_document():
    extra, images = _run(attachments.process_attachments([
        {"type": "image", "data_uri": _b64("image/png", b"X")},
        {"mime": "text/plain", "filename": "n.txt", "data_uri": _b64("text/plain", "笔记内容".encode())},
    ]))
    assert len(images) == 1
    assert "笔记内容" in extra


def test_auto_category_by_extension_when_type_missing():
    extra, images = _run(attachments.process_attachments([
        {"filename": "pic.jpg", "data_uri": _b64("image/jpeg", b"JPG")},
        {"filename": "doc.pdf", "data_uri": _b64("application/pdf", b"%PDF-1.4 invalid")},
    ]))
    assert len(images) == 1  # the jpg recognized by ext
    assert "doc.pdf" in extra  # invalid pdf -> graceful note


def test_category_helpers():
    assert attachments._category("image/png", "") == "image"
    assert attachments._category("", "song.mp3") == "audio"
    assert attachments._category("application/pdf", "r.pdf") == "document"


def test_oversized_attachment_is_skipped():
    big = "data:text/plain;base64," + "A" * (attachments.MAX_DATA_URI_LEN + 10)
    extra, images = _run(attachments.process_attachments([
        {"type": "document", "mime": "text/plain", "filename": "huge.txt", "data_uri": big},
    ]))
    assert images == []
    assert "超过大小限制" in extra


def test_too_many_attachments_capped():
    atts = [{"type": "image", "data_uri": _b64("image/png", b"X")} for _ in range(attachments.MAX_ATTACHMENTS + 5)]
    _extra, images = _run(attachments.process_attachments(atts))
    assert len(images) == attachments.MAX_ATTACHMENTS


def test_asr_unconfigured(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "asr_base_url", "")
    monkeypatch.setattr(settings, "asr_api_key", "")
    monkeypatch.setattr(settings, "zai_api_key", None)
    out = _run(asr.transcribe_audio(b"AUDIO", "audio/mpeg", "v.mp3"))
    assert "未配置" in out


def test_asr_defaults_to_glm_when_only_zai_key(monkeypatch):
    """只有 ZAI_API_KEY 时，ASR 应默认走智谱 GLM-ASR（开箱即用）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "asr_base_url", "")
    monkeypatch.setattr(settings, "asr_api_key", "")
    monkeypatch.setattr(settings, "zai_api_key", "zai-test-key")

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"text": "你好世界"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["data"] = data
            return _Resp()

    monkeypatch.setattr("app.ai.asr.httpx.AsyncClient", _Client)
    out = _run(asr.transcribe_audio(b"AUDIO", "audio/mpeg", "v.mp3"))
    assert out == "你好世界"
    assert "open.bigmodel.cn" in captured["url"]  # 默认智谱端点
    assert captured["url"].endswith("/audio/transcriptions")
    assert captured["headers"]["Authorization"] == "Bearer zai-test-key"  # 复用 zai key
    assert captured["data"]["model"] == "glm-asr-2512"  # 默认模型


def test_asr_configured_calls_endpoint(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "asr_base_url", "https://whisper.example.com")
    monkeypatch.setattr(settings, "asr_api_key", "k")
    monkeypatch.setattr(settings, "asr_model", "whisper-1")

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"text": "转写文本"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def post(self, url, headers=None, files=None, data=None):
            captured["url"] = url
            captured["files"] = files
            captured["data"] = data
            return _Resp()

    monkeypatch.setattr("app.ai.asr.httpx.AsyncClient", _Client)
    out = _run(asr.transcribe_audio(b"AUDIO", "audio/mpeg", "v.mp3"))
    assert out == "转写文本"
    assert captured["url"] == "https://whisper.example.com/audio/transcriptions"
    assert captured["data"]["model"] == "whisper-1"
