import json

from app.ai.flow_manager import _normalize_stream_chunk
from app.api.flow import _sse_event


def test_normalize_stream_chunk_extracts_glm_content():
    chunk = json.dumps({"type": "chunk", "content": "hello", "done": False})

    content, done, error = _normalize_stream_chunk(chunk)

    assert content == "hello"
    assert done is False
    assert error is None


def test_normalize_stream_chunk_handles_sse_data_prefix():
    chunk = f"data: {json.dumps({'type': 'chunk', 'content': ' world'})}"

    content, done, error = _normalize_stream_chunk(chunk)

    assert content == " world"
    assert done is False
    assert error is None


def test_normalize_stream_chunk_marks_done():
    content, done, error = _normalize_stream_chunk("data: [DONE]")

    assert content == ""
    assert done is True
    assert error is None


def test_sse_event_uses_named_event_and_json_payload():
    frame = _sse_event({"type": "chunk", "stage": "requirement", "content": "a"})

    assert frame.startswith("event: chunk\n")
    assert '"stage": "requirement"' in frame
    assert frame.endswith("\n\n")
