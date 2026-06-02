import json
import pytest
from unittest.mock import Mock

from app.ai.flow_manager import _normalize_stream_chunk
from app.api import flow
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


@pytest.mark.asyncio
async def test_pipeline_background_task_reuses_existing_task(monkeypatch):
    created = 0

    class RunningTask:
        def done(self):
            return False

    def fake_create_task(coro):
        nonlocal created
        created += 1
        coro.close()
        return RunningTask()

    monkeypatch.setattr(flow, "_pipeline_tasks", {"pipe_existing": RunningTask()})
    monkeypatch.setattr(flow.asyncio, "create_task", fake_create_task)

    await flow._ensure_pipeline_background_task("pipe_existing", "")

    assert created == 0


@pytest.mark.asyncio
async def test_pipeline_background_task_rejects_when_queue_full(monkeypatch):
    class RunningTask:
        def done(self):
            return False

    monkeypatch.setattr(flow.settings, "pipeline_execution_queue_limit", 1)
    monkeypatch.setattr(flow, "_pipeline_tasks", {"pipe_busy": RunningTask()})
    monkeypatch.setattr(flow.asyncio, "create_task", Mock())

    with pytest.raises(RuntimeError, match="开发流水线执行队列已满"):
        await flow._ensure_pipeline_background_task("pipe_new", "")
