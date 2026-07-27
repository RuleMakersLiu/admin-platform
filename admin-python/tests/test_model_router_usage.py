"""Tests for model_router usage attribution + flush (offline)."""
import asyncio

from app.ai.model_router import (
    ModelRouter,
    bind_pipeline_context,
    reset_pipeline_context,
)


def _run(coro):
    return asyncio.run(coro)


def test_record_usage_basic():
    r = ModelRouter(default_provider="glm")
    r.record_usage("glm-4-flash", 100, 50)
    stats = r.get_usage_stats()
    assert stats["total_requests"] == 1
    assert stats["total_input_tokens"] == 100


def test_record_usage_backward_compat_no_pipeline():
    r = ModelRouter(default_provider="glm")
    r.record_usage("glm-4-flash", 10, 5)
    rec = r._usage[0]
    assert rec.pipeline_id is None
    assert rec.tenant_id is None


def test_record_usage_picks_up_context():
    r = ModelRouter(default_provider="glm")
    token = bind_pipeline_context("pipe-123", tenant_id=7)
    try:
        r.record_usage("glm-4-flash", 10, 5)
    finally:
        reset_pipeline_context(token)
    rec = r._usage[0]
    assert rec.pipeline_id == "pipe-123"
    assert rec.tenant_id == 7


def test_record_usage_explicit_overrides_context():
    r = ModelRouter(default_provider="glm")
    token = bind_pipeline_context("pipe-ctx", tenant_id=1)
    try:
        r.record_usage("glm-4-flash", 10, 5, pipeline_id="pipe-explicit")
    finally:
        reset_pipeline_context(token)
    assert r._usage[0].pipeline_id == "pipe-explicit"


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add_all(self, rows):
        self.added.extend(rows)

    async def commit(self):
        self.committed = True


def test_flush_usage_writes_and_clears():
    r = ModelRouter(default_provider="glm")
    r.record_usage("glm-4-flash", 100, 50, pipeline_id="p1")
    r.record_usage("glm-4-plus", 200, 80, pipeline_id="p1")
    sess = _FakeSession()
    n = _run(r.flush_usage(sess))
    assert n == 2
    assert sess.committed
    assert len(sess.added) == 2
    assert r._usage == []  # buffer cleared


def test_flush_usage_empty_noop():
    r = ModelRouter(default_provider="glm")
    sess = _FakeSession()
    assert _run(r.flush_usage(sess)) == 0
    assert not sess.committed


def test_flush_usage_failure_restores_buffer():
    r = ModelRouter(default_provider="glm")
    r.record_usage("glm-4-flash", 10, 5, pipeline_id="p1")

    class _BoomSession(_FakeSession):
        async def commit(self):
            raise RuntimeError("db down")

    sess = _BoomSession()
    n = _run(r.flush_usage(sess))
    assert n == 0
    assert len(r._usage) == 1  # 失败回灌
