"""4a stretch：eval 视觉/E2E 接真实沙箱预览的生命周期 + 直连 URL 单测。

覆盖 sandbox_preview_service 新增的 direct_preview_url / stop / _teardown_entry，
以及 vision_eval_service.acquire_live_preview 的「复用不 stop / 起停 / 失败回退 None」三态。
"""
import pytest

import app.ai.flow_manager as fm
import app.services.sandbox_preview_service as sps
import app.services.vision_eval_service as ves
from app.services.sandbox_preview_service import SandboxPreviewService


class _FakeProc:
    """最小进程替身：returncode=None 表示存活；terminate/wait/kill 可调用。"""

    def __init__(self, returncode=None):
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


def _entry(proc=None, ready=True, port=43001):
    return {
        "process": proc or _FakeProc(),
        "port": port,
        "ready": ready,
        "output_task": None,
        "root": "/tmp/x",
    }


# ---------------- direct_preview_url ----------------

def test_direct_preview_url_none_when_not_running():
    assert SandboxPreviewService().direct_preview_url("p1") is None


def test_direct_preview_url_none_when_not_ready():
    svc = SandboxPreviewService()
    svc._processes["p1"] = _entry(ready=False)
    assert svc.direct_preview_url("p1") is None


def test_direct_preview_url_when_ready():
    svc = SandboxPreviewService()
    svc._processes["p1"] = _entry(ready=True)
    url = svc.direct_preview_url("p1")
    assert url is not None
    assert ":43001" in url
    assert "/api/flow/pipeline/p1/sandbox-preview/" in url


# ---------------- stop ----------------

@pytest.mark.asyncio
async def test_stop_returns_false_when_not_running():
    assert (await SandboxPreviewService().stop("p1")) is False


@pytest.mark.asyncio
async def test_stop_terminates_and_deregisters():
    svc = SandboxPreviewService()
    proc = _FakeProc()
    svc._processes["p1"] = _entry(proc=proc, ready=True)
    assert (await svc.stop("p1")) is True
    assert proc.terminated is True
    assert "p1" not in svc._processes


# ---------------- _teardown_entry ----------------

@pytest.mark.asyncio
async def test_teardown_cancels_output_task_and_pops():
    from unittest.mock import MagicMock

    svc = SandboxPreviewService()
    proc = _FakeProc()
    task = MagicMock()
    entry = _entry(proc=proc, ready=True)
    entry["output_task"] = task
    svc._processes["p1"] = entry
    await svc._teardown_entry("p1", entry)
    assert proc.terminated is True
    task.cancel.assert_called_once()
    assert "p1" not in svc._processes


# ---------------- acquire_live_preview ----------------

@pytest.mark.asyncio
async def test_acquire_reuses_running_preview_without_stop(monkeypatch):
    svc = SandboxPreviewService()
    svc._processes["p1"] = _entry(ready=True)
    monkeypatch.setattr(sps, "sandbox_preview_service", svc)
    stops = {"n": 0}

    async def fake_stop(pid):
        stops["n"] += 1
        return True

    monkeypatch.setattr(svc, "stop", fake_stop)

    async with ves.acquire_live_preview("p1") as url:
        assert url is not None and ":43001" in url
    # 复用（非本上下文启动）→ 退出不得 stop
    assert stops["n"] == 0


@pytest.mark.asyncio
async def test_acquire_starts_then_stops_when_owned(monkeypatch):
    svc = SandboxPreviewService()
    monkeypatch.setattr(sps, "sandbox_preview_service", svc)

    async def fake_start(pid, files, info):
        svc._processes[pid] = _entry(ready=True)
        return {"preview_url": "x"}

    stopped = {"pid": None}

    async def fake_stop(pid):
        stopped["pid"] = pid
        svc._processes.pop(pid, None)
        return True

    monkeypatch.setattr(svc, "start", fake_start)
    monkeypatch.setattr(svc, "stop", fake_stop)

    async def fake_art(pid):
        return {"frontend_files": {"src/App.vue": "x"}}

    async def fake_snap(pid):
        return {}

    monkeypatch.setattr(fm.pipeline_manager, "get_pipeline_artifact", fake_art)
    monkeypatch.setattr(fm.pipeline_manager, "get_pipeline_frontend_project_snapshot", fake_snap)

    async with ves.acquire_live_preview("p1") as url:
        assert url is not None
        assert "p1" in svc._processes  # 运行中
    # owned → 退出已 stop
    assert stopped["pid"] == "p1"
    assert "p1" not in svc._processes


@pytest.mark.asyncio
async def test_acquire_yields_none_on_start_failure(monkeypatch):
    from unittest.mock import AsyncMock

    svc = SandboxPreviewService()
    monkeypatch.setattr(sps, "sandbox_preview_service", svc)

    async def fake_start(pid, files, info):
        raise RuntimeError("npm install failed")

    monkeypatch.setattr(svc, "start", fake_start)
    monkeypatch.setattr(fm.pipeline_manager, "get_pipeline_artifact", AsyncMock(return_value={"frontend_files": {}}))
    monkeypatch.setattr(fm.pipeline_manager, "get_pipeline_frontend_project_snapshot", AsyncMock(return_value={}))

    async with ves.acquire_live_preview("p1") as url:
        assert url is None  # 失败 → 回退桩
    assert "p1" not in svc._processes


# ---------------- _format_eval_report E2E 段 ----------------

def test_format_eval_report_includes_e2e_section():
    from app.ai.flow_manager import _format_eval_report

    md = _format_eval_report({
        "judge": {"overall_score": 80, "per_criterion": [], "summary": ""},
        "e2e": {"passed": False, "issues": ["缺少期望控件：登录"], "source": "live"},
    })
    assert "E2E 浏览器断言" in md
    assert "❌ 未通过" in md
    assert "真实预览" in md
    assert "缺少期望控件：登录" in md


def test_format_eval_report_e2e_passed():
    from app.ai.flow_manager import _format_eval_report

    md = _format_eval_report({"e2e": {"passed": True, "issues": [], "source": "stub"}})
    assert "✅ 通过" in md
    assert "渲染桩" in md
