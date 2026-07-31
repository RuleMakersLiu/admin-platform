"""沙箱安全：生成的代码（LLM 产出，不可信）在 admin-python 内以子进程执行时，
剔除敏感环境变量，防止生成代码 getenv 越权获取 admin 凭据
（DATABASE_URL / JWT_SECRET / *_API_KEY 等）。

适用于 backend_runner（mvn 构建 / java -jar）与 sandbox_preview（git clone / npm install /
vite dev）触发的所有子进程。这是「进程级 env 隔离」——更彻底的隔离（独立容器 / 独立网络 /
非 root 降权）见长期方案，本模块只兜底最直接的凭据泄露面。
"""
from __future__ import annotations

import asyncio
import json
import os
import socket

from app.core.config import settings

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

    container 模式（Phase A）：命令跑在仅挂 sandbox-net 的隔离 docker 容器里（不可达 admin 内网），
    走 _run_sandboxed_container；process 模式（默认/本地 pytest）走原子进程。
    """
    if settings.sandbox_execution_mode == "container":
        code, out, _ = await _run_sandboxed_container(args, cwd=cwd, env=env, timeout=timeout)
        return code, out.decode("utf-8", "ignore")
    proc = await spawn_sandboxed(args, cwd=cwd, env=env, drop_privs=drop_privs)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, (out or b"").decode("utf-8", "ignore")


# ==================== Phase A：容器后端（隔离网络执行） ====================
#
# container 模式下不可信命令在独立 docker 容器内执行（仅挂 sandbox-net）。admin-python 经挂载的
# docker.sock + docker-cli 编排（同 admin-deploy）。镜像复用 admin-python 自身镜像（含全部 toolchain +
# uid1500 + 全局 maven settings）；工作区经 --volumes-from 共享 admin-python 的 pipeline_data 挂载
# （自动继承正确卷名，免依赖 compose project 前缀）。容器以 uid 1500 跑，镜像 env 本身无 admin 密钥
# （DB/JWT 是 admin-python 运行期 compose env，不烤进镜像），故 env=None 不注入任何 -e 即天然脱敏。

_self_container_id: str | None = None


def _sandbox_self_container_id() -> str:
    """admin-python 自身容器 ID（短）——用于 --volumes-from 共享工作区卷。懒缓存（socket.gethostname）。"""
    global _self_container_id
    if not _self_container_id:
        _self_container_id = socket.gethostname() or ""
    return _self_container_id


async def _docker_exec(args: list[str], *, timeout: float | None = None) -> tuple[int, bytes, bytes]:
    """跑一条 docker CLI 命令，返回 (returncode, stdout, stderr)。"""
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out or b"", err or b""


def _docker_run_argv(args, *, cwd, env) -> list[str]:
    """组装 `docker run` 参数（共用前台/-d）：--network sandbox-net --user 1500 --volumes-from 自身
    -w cwd -e KEY=VAL... <image> <args>。镜像 CMD(uvicorn) 被 args 整体覆盖；镜像无 ENTRYPOINT。"""
    argv = [
        "docker", "run",
        "--network", settings.sandbox_network_name,
        "--user", f"{SANDBOX_UID}:{SANDBOX_GID}",
        "--volumes-from", _sandbox_self_container_id(),
    ]
    if cwd:
        argv += ["-w", str(cwd)]
    for k, v in (env or {}).items():
        argv += ["-e", f"{k}={v}"]
    argv.append(settings.sandbox_image_name)
    argv += list(args)
    return argv


async def _run_sandboxed_container(
    args, *, cwd=None, env=None, timeout: int = 180, separate_stderr: bool = False,
) -> tuple[int, bytes, bytes]:
    """run_sandboxed 的容器后端：docker run -d 拿容器 ID → docker logs -f 取输出（容器退出即 EOF）
    → docker wait 取退出码 → docker rm -f 清理；超时 docker stop -t 2 后回收再抛 TimeoutError。

    用 -d + logs + wait 而非 `docker run` 前台：前台超时 kill CLI 客户端会孤儿容器（SIGKILL 不转发），
    detached 能可靠按 ID stop/rm。返回 (returncode, stdout_bytes, stderr_bytes)：
    - separate_stderr=False：docker logs 的 stderr 合并进 stdout（stderr=STDOUT，保到达顺序），stderr_bytes=b""。
    - separate_stderr=True：docker logs 天然分离容器 stdout/stderr（各自 PIPE），保留分离（如 git clone 错误流）。
    """
    run_argv = _docker_run_argv(args, cwd=cwd, env=env) + ["-d"]
    rc, cid_b, err = await _docker_exec(run_argv, timeout=60)
    if rc != 0:
        raise RuntimeError(
            f"docker run 失败（exit {rc}）: {(err or b'').decode('utf-8', 'ignore')[:500]}"
        )
    cid = cid_b.decode("utf-8", "ignore").strip()
    if not cid:
        raise RuntimeError("docker run 未返回容器 ID")

    logs_stderr = asyncio.subprocess.PIPE if separate_stderr else asyncio.subprocess.STDOUT
    log_proc = await asyncio.create_subprocess_exec(
        "docker", "logs", "-f", cid,
        stdout=asyncio.subprocess.PIPE, stderr=logs_stderr,
    )
    try:
        out, err = await asyncio.wait_for(log_proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        # 超时：容器仍在跑 → 强停（SIGTERM 2s→SIGKILL）→ wait 收尸 → rm 清理，再抛
        await _docker_exec(["docker", "stop", "-t", "2", cid], timeout=20)
        await _docker_exec(["docker", "wait", cid], timeout=30)
        await _docker_exec(["docker", "rm", "-f", cid], timeout=30)
        raise
    # 容器已退出（logs -f EOF）：docker wait 取退出码（须容器仍存在），再 rm -f 清理
    rc = _decode_exit(await _docker_exec(["docker", "wait", cid], timeout=30))
    await _docker_exec(["docker", "rm", "-f", cid], timeout=30)
    return rc, out or b"", err or b""


async def run_sandboxed_with_stderr(args, *, cwd=None, env=None, timeout: int = 180, drop_privs=True):
    """run_sandboxed 的「stdout/stderr 分离」变体：返回 (returncode, stdout_bytes, stderr_bytes)。

    供需单独取 stderr 的调用点（flow_manager git clone 的错误提示）。container 模式走
    _run_sandboxed_container(separate_stderr=True)——docker logs 天然分离容器 stdout/stderr，比合并流保真。
    """
    if settings.sandbox_execution_mode == "container":
        return await _run_sandboxed_container(args, cwd=cwd, env=env, timeout=timeout, separate_stderr=True)
    proc = await spawn_sandboxed(args, cwd=cwd, env=env, drop_privs=drop_privs, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out or b"", err or b""


def _decode_exit(wait_out: tuple[int, bytes, bytes]) -> int:
    """解析 `docker wait` 输出（容器退出码，可能负数=信号）。非数字/异常返回 1。"""
    try:
        return int((wait_out[1] or b"").decode("utf-8", "ignore").strip())
    except (ValueError, AttributeError):
        return 1


# ==================== Phase A：长驻服务句柄（java / vite） ====================
#
# 长驻沙箱服务（后端 java -jar、前端 vite dev）需被持有、就绪探测、空闲回收。统一句柄屏蔽
# process vs container 后端，调用方（backend_runner / sandbox_preview）的 is_running/_teardown/
# direct_*_url 经句柄操作，两种模式同构。容器名 = sandbox-net 上的 DNS 名（admin-python 经此连服务）。


class SandboxHandle:
    """长驻沙箱服务句柄。

    - returncode：None=运行中，int=已退出（进程码/负数信号）。process 模式实时读 proc.returncode；
      container 模式经 drain-EOF 或 acleanup 置位（故 container 模式须 start_log_drain 才能检测崩溃）。
    - acleanup(timeout)：优雅停（SIGTERM→timeout→SIGKILL；container: docker stop -t + rm -f），幂等。
    - start_log_drain(on_line)：启后台任务逐行读日志（process: stdout.readline；container: docker logs -f），
      返回该任务（teardown 时由 acleanup 取消）。on_line(text) 每行回调；container 退出(EOF)时置 returncode。
    """

    returncode: int | None = None

    async def acleanup(self, timeout: int = 5) -> None:  # pragma: no cover - 接口
        raise NotImplementedError

    async def start_log_drain(self, on_line) -> asyncio.Task:  # pragma: no cover - 接口
        raise NotImplementedError


class ProcessHandle(SandboxHandle):
    """process 模式句柄：包 asyncio.subprocess.Process。语义等同历史（terminate→5s→kill）。"""

    def __init__(self, proc: asyncio.subprocess.Process):
        self._proc = proc
        self._drain_task: asyncio.Task | None = None

    @property
    def returncode(self):
        return self._proc.returncode

    async def acleanup(self, timeout: int = 5) -> None:
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        if self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()

    async def start_log_drain(self, on_line) -> asyncio.Task:
        async def _drain():
            if not self._proc.stdout:
                return
            try:
                while True:
                    line = await self._proc.stdout.readline()
                    if not line:
                        break
                    if on_line:
                        on_line(line.decode("utf-8", "ignore").strip())
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                pass

        self._drain_task = asyncio.create_task(_drain())
        return self._drain_task


class ContainerHandle(SandboxHandle):
    """container 模式句柄：包 detached docker 容器（cid + name）。name 同时是 sandbox-net DNS 名。"""

    def __init__(self, cid: str, name: str):
        self.cid = cid
        self.name = name
        self._rc: int | None = None
        self._drain_task: asyncio.Task | None = None

    @property
    def returncode(self):
        return self._rc

    async def start_log_drain(self, on_line) -> asyncio.Task:
        async def _drain():
            log_proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "-f", self.cid,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            try:
                while True:
                    line = await log_proc.stdout.readline()
                    if not line:
                        break
                    if on_line:
                        on_line(line.decode("utf-8", "ignore").strip())
            except asyncio.CancelledError:
                try:
                    log_proc.kill()
                    await log_proc.wait()
                except Exception:  # noqa: BLE001
                    pass
                raise
            except Exception:  # noqa: BLE001
                pass
            # 容器退出（logs -f EOF）：取退出码，returncode 由 None→码（is_running 即转 False）
            try:
                self._rc = _decode_exit(await _docker_exec(["docker", "wait", self.cid], timeout=30))
            except Exception:  # noqa: BLE001
                self._rc = 1

        self._drain_task = asyncio.create_task(_drain())
        return self._drain_task

    async def acleanup(self, timeout: int = 5) -> None:
        # 先取消 logs-follow 任务（免它挂在即将删除的容器上）
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await asyncio.wait_for(self._drain_task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        if self._rc is None:  # 仍在跑 → stop（SIGTERM timeout→SIGKILL）
            await _docker_exec(["docker", "stop", "-t", str(timeout), self.cid], timeout=timeout + 15)
            try:
                self._rc = _decode_exit(await _docker_exec(["docker", "wait", self.cid], timeout=30))
            except Exception:  # noqa: BLE001
                self._rc = 1
        await _docker_exec(["docker", "rm", "-f", self.cid], timeout=30)


async def spawn_sandboxed_service(args, *, cwd=None, env=None, name: str, drop_privs: bool = True) -> SandboxHandle:
    """长驻沙箱服务（java/vite）统一启动：返回 SandboxHandle。

    - container 模式：先 docker rm -f <name>（幂等防名称碰撞）→ docker run -d --name <name> ...
      返回 ContainerHandle。name 即 sandbox-net DNS 名（admin-python 经此连服务）。
    - process 模式：走 spawn_sandboxed 原子进程，返回 ProcessHandle；name 被忽略（用 loopback）。
    env 语义同 spawn_sandboxed（None→sanitize；dict→原样）。仅 root 时降权（process 模式）/
      固定 --user 1500（container 模式）。
    """
    if settings.sandbox_execution_mode == "container":
        await _docker_exec(["docker", "rm", "-f", name], timeout=30)  # 幂等：清同名残留容器
        run_argv = _docker_run_argv(args, cwd=cwd, env=env) + ["--name", name, "-d"]
        rc, cid_b, err = await _docker_exec(run_argv, timeout=60)
        if rc != 0:
            raise RuntimeError(
                f"docker run 失败（exit {rc}）: {(err or b'').decode('utf-8', 'ignore')[:500]}"
            )
        cid = cid_b.decode("utf-8", "ignore").strip()
        if not cid:
            raise RuntimeError("docker run 未返回容器 ID")
        return ContainerHandle(cid, name)
    proc = await spawn_sandboxed(args, cwd=cwd, env=env, drop_privs=drop_privs)
    return ProcessHandle(proc)
