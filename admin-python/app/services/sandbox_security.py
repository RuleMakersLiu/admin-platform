"""沙箱安全：生成的代码（LLM 产出，不可信）在 admin-python 内以子进程执行时，
剔除敏感环境变量，防止生成代码 getenv 越权获取 admin 凭据
（DATABASE_URL / JWT_SECRET / *_API_KEY 等）。

适用于 backend_runner（mvn 构建 / java -jar）与 sandbox_preview（git clone / npm install /
vite dev）触发的所有子进程。这是「进程级 env 隔离」——更彻底的隔离（独立容器 / 独立网络 /
非 root 降权）见长期方案，本模块只兜底最直接的凭据泄露面。
"""
from __future__ import annotations

import asyncio
import os

# 敏感关键词（大小写不敏感，key 含任一即剔除）——生成的子进程绝不应继承 admin 凭据。
# 用「包含」而非「前缀」，避免 CLAUDE_API_KEY / X_API_KEY 这类前缀不在列表里的漏网。
SENSITIVE_ENV_KEYWORDS = (
    "DATABASE_URL", "JWT", "REDIS", "API_KEY", "SECRET", "PASSWORD", "TOKEN",
    "_KEY", "POSTGRES", "MYSQL", "PG_", "ZAI", "OPENAI", "ANTHROPIC", "CLAUDE",
    "GOOGLE", "DEEPSEEK", "GEMINI", "CREDENTIAL", "PRIVATE",
)


def sanitized_env(base: dict | None = None) -> dict:
    """返回剔除敏感 key 后的环境变量副本，供生成的子进程使用。

    用「关键词包含」匹配（大小写不敏感），覆盖各种 *_API_KEY / *_SECRET / 提供商前缀。
    backend_runner 另在白名单里单独注入指向 mysql-sandbox 的沙箱凭据。
    宁严勿松：误剔某个非敏感 env，好过泄露凭据给不可信的生成代码。
    """
    src = base if base is not None else os.environ
    return {
        k: v for k, v in src.items()
        if not any(kw in k.upper() for kw in SENSITIVE_ENV_KEYWORDS)
    }


# 不可信（LLM 生成）子进程降权到的非 root 身份。Dockerfile 建同名用户（uid/gid 1500）。
# 容器仍以 root 运行（保源码热更新 / chromium / build 期 pip），仅子进程降权。
SANDBOX_UID = 1500
SANDBOX_GID = 1500


def drop_privilege_kwargs(drop_privs: bool = True) -> dict:
    """返回传给 create_subprocess_exec 的降权 kwargs（user/group/extra_groups）。

    仅当当前进程为 root（os.geteuid()==0）时降权；本地 pytest 等非 root 环境返回空 dict（no-op），
    避免无权限降权报错。用 Popen 原生 user=/group=/extra_groups=（Python 3.9+）：内部按
    setgid→setgroups→setuid 安全顺序执行，规避手写 preexec_fn 的 async-signal-safety 顾虑。
    extra_groups=[] 清空残留 root 附加组，防越权。
    """
    if drop_privs and hasattr(os, "geteuid") and os.geteuid() == 0:
        return {"user": SANDBOX_UID, "group": SANDBOX_GID, "extra_groups": []}
    return {}


async def spawn_sandboxed(
    args,
    *,
    cwd=None,
    env=None,
    drop_privs=True,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
    **kw,
):
    """统一安全子进程原语（底层）：执行不可信/生成代码的子进程一律走这里，杜绝漏防护。

    - env=None → 用 sanitized_env() 剔除 admin 凭据；env=dict → 原样使用（调用方自建的白名单，
      如 backend_runner 注入的沙箱 MySQL 凭据，不二次剔除）。
    - 始终（root 时）降权到 uid 1500（drop_privilege_kwargs）。
    - 降权时强制 HOME=/tmp：uid 1500 无法访问 700 的 /root，若仍带 HOME=/root（sanitized_env 透传
      父进程 HOME），npm/pnpm/maven/git 等读 $HOME 的工具会 EACCES（pnpm 实测 WARN 读 /root/.npmrc）。
      指向可写的 /tmp 一并消除该类越权尝试；maven 镜像配置走全局 /usr/share/maven/conf（见 Dockerfile）。
    返回 asyncio.subprocess.Process 句柄，供长驻进程（vite/java 服务）持有与回收。
    """
    final_env = sanitized_env() if env is None else dict(env)
    drop = drop_privilege_kwargs(drop_privs)  # 仅 root 时非空
    if drop:
        final_env["HOME"] = "/tmp"
    return await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=final_env,
        stdout=stdout,
        stderr=stderr,
        **drop,
        **kw,
    )


async def run_sandboxed(args, *, cwd=None, env=None, timeout: int = 180, drop_privs=True):
    """统一安全子进程原语（高层）：spawn + wait_for(communicate) + 超时 kill。

    返回 (returncode, stdout 文本)；超时则 kill 进程并 await 回收后抛 asyncio.TimeoutError
    （调用方按需捕获转换为各自的超时语义）。覆盖所有「跑完即取输出」形状的不可信命令执行。
    """
    proc = await spawn_sandboxed(args, cwd=cwd, env=env, drop_privs=drop_privs)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, (out or b"").decode("utf-8", "ignore")
