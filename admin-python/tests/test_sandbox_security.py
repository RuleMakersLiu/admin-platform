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
