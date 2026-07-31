"""沙箱安全原语回归测试（app.services.sandbox_security）：env 隔离 + 非 root 降权。

纯逻辑/本地子进程，无 DB/服务器依赖，快且确定。锁定：
  - sanitized_env 剔除敏感凭据 key（DATABASE_URL/JWT_SECRET/*_API_KEY/PASSWORD 等）
  - drop_privilege_kwargs：root 时返回 user/group/extra_groups=[]，非 root 时 no-op
  - spawn_sandboxed / run_sandboxed：env=None 自动 sanitize；env=dict 原样保留
    （backend_runner 注入的沙箱 MySQL 凭据含 PASSWORD 关键词，不被二次剔除）
  - 降权路径：root 环境下不可信子进程 uid==1500；非 root 环境（本地 pytest）不报错（no-op）

注意：asyncio 子进程 Process 绑定创建它的事件循环，不能跨 loop await；故用「同步测试 + 单个
asyncio.run 跑一个 spawn+communicate 闭环」的写法（非 pytest.mark.asyncio，免配 asyncio_mode）。
"""
import asyncio
import os
import sys

import pytest

from app.core.config import settings
from app.services.sandbox_security import (
    SANDBOX_GID,
    SANDBOX_UID,
    drop_privilege_kwargs,
    run_sandboxed,
    sanitized_env,
    spawn_sandboxed,
)

PY = sys.executable


async def _capture(args, **kw):
    """spawn + communicate 在同一事件循环内闭环（Process 绑定其创建 loop）。"""
    proc = await spawn_sandboxed(args, **kw)
    out, _ = await proc.communicate()
    return proc.returncode, out


# ---------- sanitized_env ----------

def test_sanitized_env_strips_credentials_keeps_benign():
    base = {
        "DATABASE_URL": "postgresql://postgres:secret@host/db",
        "JWT_SECRET": "topsecret",
        "ZAI_API_KEY": "sk-xxx",
        "MYSQL_PASSWORD": "p",
        "ANTHROPIC_API_KEY": "sk-ant",
        "PATH": "/usr/bin",
        "HOME": "/root",
        "LANG": "C.UTF-8",
        "FOO_BAR": "keep",
    }
    out = sanitized_env(base)
    for secret in ("DATABASE_URL", "JWT_SECRET", "ZAI_API_KEY", "MYSQL_PASSWORD", "ANTHROPIC_API_KEY"):
        assert secret not in out, f"{secret} should be stripped"
    assert out["PATH"] == "/usr/bin"
    assert out["HOME"] == "/root"
    assert out["FOO_BAR"] == "keep"


# ---------- drop_privilege_kwargs ----------

def test_drop_privilege_kwargs_matches_runtime_uid():
    """root 环境：返回降权三元组；非 root（本地 pytest/CI）：no-op 空字典，均不报错。"""
    if os.geteuid() == 0:
        assert drop_privilege_kwargs() == {"user": SANDBOX_UID, "group": SANDBOX_GID, "extra_groups": []}
    else:
        assert drop_privilege_kwargs() == {}
    assert drop_privilege_kwargs(drop_privs=False) == {}


# ---------- spawn_sandboxed env 行为 ----------

def test_spawn_sandboxed_sanitizes_when_env_none():
    """env=None 走 sanitized_env：注入敏感 env 到 os.environ，子进程不应看到。"""
    os.environ["ZAI_API_KEY_TEST"] = "should-not-leak"
    try:
        code, out = asyncio.run(_capture(
            [PY, "-c", "import os; print(os.environ.get('ZAI_API_KEY_TEST','EMPTY'))"], cwd="/tmp"))
    finally:
        del os.environ["ZAI_API_KEY_TEST"]
    assert code == 0
    assert out.strip() == b"EMPTY", "敏感 env 未被剔除（泄露到子进程）"


def test_spawn_sandboxed_preserves_caller_env_dict():
    """env=dict 原样用：含 PASSWORD 关键词的沙箱凭据不被二次剔除（backend_runner java 场景）。"""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": "/tmp",
        "SANDBOX_DB_PASSWORD": "sandbox-pw",  # 含 PASSWORD 关键词——sanitize 会剔，但 env=dict 不二次剔
    }
    code, out = asyncio.run(_capture(
        [PY, "-c", "import os; print(os.environ.get('SANDBOX_DB_PASSWORD','EMPTY'))"], cwd="/tmp", env=env))
    assert code == 0
    assert out.strip() == b"sandbox-pw", "调用方自建 env（含沙箱凭据）被错误地二次剔除"


# ---------- 降权路径 ----------

def test_spawn_sandboxed_uid_dropped_when_root():
    """root 环境：不可信子进程 uid==1500；非 root：no-op，uid 不变，均不报错。"""
    code, out = asyncio.run(_capture(
        [PY, "-c", "import os; print(os.getuid())"], cwd="/tmp"))
    assert code == 0
    uid = int(out.strip())
    if os.geteuid() == 0:
        assert uid == SANDBOX_UID, f"降权失败：期望 uid={SANDBOX_UID}，实际 uid={uid}"
    else:
        assert uid == os.geteuid()  # 非 root no-op


# ---------- run_sandboxed ----------

def test_run_sandboxed_returns_code_and_decoded_output():
    code, out = asyncio.run(run_sandboxed([PY, "-c", "print('hello-sandbox')"], cwd="/tmp", timeout=15))
    assert code == 0
    assert "hello-sandbox" in out


def test_run_sandboxed_timeout_kills_and_raises():
    """超时 → kill 子进程并回收 → 抛 TimeoutError（调用方按需转换语义）。"""
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_sandboxed([PY, "-c", "import time; time.sleep(60)"], cwd="/tmp", timeout=1))


# ---------- Phase A：容器后端纯逻辑（不依赖 docker 守护进程；端到端走部署期 E2E） ----------

def test_docker_run_argv_shape():
    """_docker_run_argv 组装正确的 docker run 标志：network/user/volumes-from/cwd/env/HOME 覆盖/image/args。"""
    import socket as _socket
    from app.services.sandbox_security import _docker_run_argv
    argv = _docker_run_argv(
        ["mvn", "-B", "package"],
        cwd="/data/pipelines/p1",
        env={"MYSQL_HOST": "mysql-sandbox", "HOME": "/root"},
    )
    assert argv[0:2] == ["docker", "run"]
    assert argv[argv.index("--network") + 1] == settings.sandbox_network_name
    assert argv[argv.index("--user") + 1] == "1500:1500"
    assert argv[argv.index("--volumes-from") + 1] == _socket.gethostname()
    assert argv[argv.index("-w") + 1] == "/data/pipelines/p1"
    # 调用方 env 注入
    assert "MYSQL_HOST=mysql-sandbox" in argv
    # HOME=/tmp 强制覆盖：env 里的 HOME=/root 必须被末尾的 HOME=/tmp 压过（docker -e 后者赢）
    home_vals = [argv[i + 1] for i, a in enumerate(argv) if a == "-e" and argv[i + 1].startswith("HOME=")]
    assert home_vals[-1] == "HOME=/tmp"
    # 镜像 + 命令在末尾
    img = settings.sandbox_image_name
    assert argv[argv.index(img):] == [img, "mvn", "-B", "package"]


def test_docker_run_argv_env_none_injects_no_env_but_home():
    """env=None：不注入调用方 env，但仍强制 HOME=/tmp（uid 1500 不可访问 /root）。"""
    from app.services.sandbox_security import _docker_run_argv
    argv = _docker_run_argv(["node", "-v"], cwd="/tmp", env=None)
    e_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    assert e_args == ["HOME=/tmp"]  # 仅 HOME，无其它 -e


def test_docker_run_argv_detached_and_name_before_image():
    """-d / --name 必须在 <image> 之前（docker run [OPTS] IMAGE [CMD]）；放后面会被当命令参数，
    导致 docker run 跑成前台、cid 误取容器输出（E2E 实测曾因此 logs 404）。回归守护。"""
    from app.services.sandbox_security import _docker_run_argv
    argv = _docker_run_argv(
        ["python", "x.py"], cwd="/tmp", env=None, name="sandbox-be-p1", detached=True
    )
    img = settings.sandbox_image_name
    img_idx = argv.index(img)
    assert argv.index("--name") < img_idx
    assert argv.index("-d") < img_idx
    # 命令参数在 image 之后
    assert argv[img_idx + 1:] == ["python", "x.py"]


def test_decode_exit():
    """_decode_exit 解析 docker wait 退出码（含负数信号、垃圾兜底返 1）。"""
    from app.services.sandbox_security import _decode_exit
    assert _decode_exit((0, b"0\n", b"")) == 0
    assert _decode_exit((0, b"3\n", b"")) == 3
    assert _decode_exit((0, b"-15\n", b"")) == -15  # SIGTERM
    assert _decode_exit((0, b"137\n", b"")) == 137   # SIGKILL
    assert _decode_exit((0, b"garbage", b"")) == 1
    assert _decode_exit((0, b"", b"")) == 1


def test_spawn_sandboxed_service_process_mode_returns_process_handle():
    """process 模式（默认）：spawn_sandboxed_service 包 spawn_sandboxed 返回 ProcessHandle，
    returncode 随进程退出翻转；acleanup 对已退出进程幂等。"""
    from app.services.sandbox_security import spawn_sandboxed_service, ProcessHandle

    async def _run():
        h = await spawn_sandboxed_service([PY, "-c", "pass"], cwd="/tmp", name="ignored-in-process-mode")
        assert isinstance(h, ProcessHandle)
        assert h.returncode is None  # 刚起，仍在跑
        await asyncio.sleep(0.5)
        assert h.returncode == 0  # 进程已退出
        await h.acleanup()  # 已退出 → 幂等 no-op，不抛
        return h

    asyncio.run(_run())

