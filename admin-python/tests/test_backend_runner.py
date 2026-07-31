"""Phase 4b-2：后端沙箱 runner 的逻辑单测（mock 句柄，不打真实 mvn/java/container）。"""
from pathlib import Path

import pytest

from app.services.backend_runner_service import BackendRunnerService


class _FakeHandle:
    """模拟 SandboxHandle（process 模式 ProcessHandle 的形状）：returncode 属性 + acleanup 协程。"""

    def __init__(self, returncode=None):
        self._rc = returncode
        self.terminated = False

    @property
    def returncode(self):
        return self._rc

    async def acleanup(self, timeout: int = 5) -> None:
        if self._rc is None:  # 仍在跑 → 终止
            self.terminated = True
            self._rc = -15

    async def start_log_drain(self, on_line):
        return None


def _entry(handle=None, ready=True, port=44001, connect_host="127.0.0.1"):
    return {
        "handle": handle or _FakeHandle(),
        "port": port,
        "ready": ready,
        "root": "/tmp/x",
        "connect_host": connect_host,
    }


# ---------- _find_jar ----------

def test_find_jar_prefers_executable_over_plain(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "app-plain.jar").write_text("x")
    (target / "app.jar").write_text("x")
    svc = BackendRunnerService()
    jar = svc._find_jar(tmp_path)
    assert jar is not None and jar.name == "app.jar"


def test_find_jar_none_when_no_target(tmp_path):
    assert BackendRunnerService()._find_jar(tmp_path) is None


# ---------- _allocate_port ----------

def test_allocate_port_in_range_and_reserves():
    svc = BackendRunnerService()
    port = svc._allocate_port()
    from app.core.config import settings
    assert settings.pipeline_backend_port_start <= port <= settings.pipeline_backend_port_end
    assert port in svc._reserved_ports


# ---------- 查询 ----------

def test_direct_backend_url_none_when_not_running():
    assert BackendRunnerService().direct_backend_url("p1") is None


def test_direct_backend_url_none_when_not_ready():
    svc = BackendRunnerService()
    svc._processes["p1"] = _entry(ready=False)
    assert svc.direct_backend_url("p1") is None


def test_direct_backend_url_when_ready():
    svc = BackendRunnerService()
    svc._processes["p1"] = _entry(ready=True, port=44010, connect_host="sandbox-be-p1")
    url = svc.direct_backend_url("p1")
    assert url is not None and url == "http://sandbox-be-p1:44010"


def test_is_running():
    svc = BackendRunnerService()
    assert svc.is_running("p1") is False
    svc._processes["p1"] = _entry(ready=True)
    assert svc.is_running("p1") is True
    svc._processes["p1"] = _entry(handle=_FakeHandle(returncode=0), ready=True)
    assert svc.is_running("p1") is False


# ---------- teardown / stop ----------

@pytest.mark.asyncio
async def test_teardown_terminates_and_pops():
    svc = BackendRunnerService()
    handle = _FakeHandle()
    entry = _entry(handle=handle, ready=True)
    svc._processes["p1"] = entry
    await svc._teardown("p1", entry)
    assert handle.terminated is True
    assert "p1" not in svc._processes


@pytest.mark.asyncio
async def test_stop_returns_false_when_not_running():
    assert (await BackendRunnerService().stop("p1")) is False


@pytest.mark.asyncio
async def test_stop_stops_running():
    svc = BackendRunnerService()
    handle = _FakeHandle()
    svc._processes["p1"] = _entry(handle=handle, ready=True)
    assert (await svc.stop("p1")) is True
    assert handle.terminated is True
    assert "p1" not in svc._processes


# ---------- start 前置校验 ----------

@pytest.mark.asyncio
async def test_start_raises_without_jdk(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.backend_runner_service.shutil.which", lambda cmd: None)
    (tmp_path / "pom.xml").write_text("<project/>")
    svc = BackendRunnerService()
    with pytest.raises(RuntimeError, match="JDK/maven"):
        await svc.start("p1", str(tmp_path))


@pytest.mark.asyncio
async def test_start_raises_without_pom(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.backend_runner_service.shutil.which", lambda cmd: f"/usr/bin/{cmd}")
    svc = BackendRunnerService()
    with pytest.raises(RuntimeError, match="pom.xml"):
        await svc.start("p1", str(tmp_path))
