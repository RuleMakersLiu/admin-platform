"""后端沙箱 runner（Phase 4b-2）：把生成的 Java Spring Boot 工程在 admin-python 内本地构建并启动。

与前端 sandbox_preview_service 同构（原生子进程，非 docker）：
1. ``mvn -B package -DskipTests`` 打包（依赖缓存在工作区内的 .m2-backend，跨流水线复用）；
2. ``java -jar target/*.jar --server.port=<动态端口>`` 起服务，env 指向 mysql-sandbox；
3. 轮询 TCP 端口就绪；
4. 用完即 ``stop``（terminate + 摘除）。

前置：admin-python 镜像含 JDK17+maven（Dockerfile），mysql-sandbox 服务可达（compose）。
未满足时 ``start`` 抛清晰错误，调用方 fail-open。当前版本只保证「能构建+能起」；DB/schema
灌入与端点契约探针留给 4b-3/4c。
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackendRunnerService:
    """每个 pipeline_id 对应一个本地 Java 进程 + 动态端口。"""

    def __init__(self) -> None:
        self._processes: Dict[str, Dict[str, Any]] = {}
        self._reserved_ports: set[int] = set()
        self._lock = asyncio.Lock()
        # 后端构建（mvn）重，限并发
        self._start_semaphore = asyncio.Semaphore(2)

    # ---------------- 端口分配 ----------------

    def _allocate_port(self) -> int:
        used = {int(e["port"]) for e in self._processes.values() if e.get("port")} | self._reserved_ports
        for port in range(settings.pipeline_backend_port_start, settings.pipeline_backend_port_end + 1):
            if port in used:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((settings.pipeline_backend_host, port))
                    self._reserved_ports.add(port)
                    return port
                except OSError:
                    continue
        raise RuntimeError(
            f"无可用后端端口（{settings.pipeline_backend_port_start}-{settings.pipeline_backend_port_end}）"
        )

    # ---------------- 查询 ----------------

    def is_running(self, pipeline_id: str) -> bool:
        entry = self._processes.get(pipeline_id)
        return bool(entry and entry["process"].returncode is None)

    def direct_backend_url(self, pipeline_id: str) -> Optional[str]:
        """已就绪后端的容器内直连 URL，未就绪返回 None（供 4c 契约探针直接命中）。"""
        entry = self._processes.get(pipeline_id)
        if not entry or entry["process"].returncode is not None or not entry.get("ready"):
            return None
        entry["last_active"] = time.time()
        return f"http://{settings.pipeline_backend_host}:{entry['port']}"

    async def reap_idle(self, ttl_seconds: int) -> int:
        """回收超过 ttl 无活动的后端沙箱进程（释放 Java 进程 + 端口），返回回收数。

        防长跑泄漏：pipeline 未显式 stop 时，start 后无 direct_backend_url 查询（4c 探针）
        超过 ttl 即由后台 reaper 自动 stop。
        """
        now = time.time()
        stale = [
            pid for pid, e in self._processes.items()
            if e.get("ready") and now - float(e.get("last_active", 0)) > ttl_seconds
        ]
        for pid in stale:
            await self.stop(pid)
        return len(stale)

    # ---------------- 构建 ----------------

    def _find_jar(self, root: Path) -> Optional[Path]:
        target = root / "target"
        if not target.exists():
            return None
        # 优先非 -plain 的可执行 jar（spring-boot-maven-plugin 产物）
        jars = sorted(target.glob("*.jar"), key=lambda p: ("-plain" in p.name, p.name))
        return jars[0] if jars else None

    async def _run(self, args: list[str], cwd: Path, timeout: int = 900) -> Tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, (out or b"").decode("utf-8", "ignore")
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "构建超时"

    async def _wait_tcp_ready(self, host: str, port: int, timeout: int = 90) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=2.0
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:  # noqa: BLE001
                    pass
                return
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(1.0)
        raise RuntimeError(f"后端服务就绪超时（{host}:{port}）")

    # ---------------- 生命周期 ----------------

    async def start(self, pipeline_id: str, workspace_path: str) -> Dict[str, Any]:
        if not shutil.which("java") or not shutil.which("mvn"):
            raise RuntimeError(
                "admin-python 容器未安装 JDK/maven（需 rebuild 含 openjdk-17 + maven 的镜像后生效）"
            )
        root = Path(workspace_path)
        if not (root / "pom.xml").exists():
            raise RuntimeError("工作区无 pom.xml（backend_scaffolder 未运行或非 Java 工程）")

        async with self._start_semaphore:
            # 复用已就绪的同 pipeline 后端
            existing = self._processes.get(pipeline_id)
            if existing and existing["process"].returncode is None and existing.get("ready"):
                return self._response(pipeline_id, existing)

            # 1) mvn 打包（依赖缓存在工作区内，跨次复用）
            repo_local = str(root / ".m2-backend")
            code, out = await self._run(
                ["mvn", "-B", "package", "-DskipTests", f"-Dmaven.repo.local={repo_local}"],
                root,
                timeout=900,
            )
            if code != 0:
                raise RuntimeError(f"mvn 构建失败（exit {code}）: {out[-800:]}")

            jar = self._find_jar(root)
            if not jar:
                raise RuntimeError("构建成功但未找到 target/*.jar")

            # 2) 起服务：env 指向 mysql-sandbox；每流水线独立 DB 名
            port = self._allocate_port()
            env = os.environ.copy()
            env.update(
                {
                    "MYSQL_HOST": settings.pipeline_backend_mysql_host,
                    "MYSQL_PORT": str(settings.pipeline_backend_mysql_port),
                    "MYSQL_DB": f"sandbox_{pipeline_id[:12].replace('-', '')}"[:63],
                    "MYSQL_USER": settings.pipeline_backend_mysql_user,
                    "MYSQL_PASSWORD": settings.pipeline_backend_mysql_password,
                }
            )
            process = await asyncio.create_subprocess_exec(
                "java", "-jar", str(jar), f"--server.port={port}",
                cwd=str(root),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            entry: Dict[str, Any] = {
                "process": process,
                "port": port,
                "ready": False,
                "root": str(root),
                "last_active": time.time(),
            }
            async with self._lock:
                self._processes[pipeline_id] = entry
                self._reserved_ports.discard(port)

        try:
            await self._wait_tcp_ready(settings.pipeline_backend_host, port, timeout=90)
        except Exception:
            await self._teardown(pipeline_id, entry)
            raise
        entry["ready"] = True
        logger.info("backend_runner: started %s on port %s", pipeline_id, port)
        return self._response(pipeline_id, entry)

    def _response(self, pipeline_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "pipeline_id": pipeline_id,
            "status": "running",
            "port": entry["port"],
            "backend_url": self.direct_backend_url(pipeline_id),
        }

    async def _teardown(self, pipeline_id: str, entry: Dict[str, Any]) -> None:
        process = entry.get("process")
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        async with self._lock:
            if self._processes.get(pipeline_id) is entry:
                self._processes.pop(pipeline_id, None)

    async def stop(self, pipeline_id: str) -> bool:
        async with self._lock:
            entry = self._processes.get(pipeline_id)
            if not entry or entry["process"].returncode is not None:
                return False
        await self._teardown(pipeline_id, entry)
        return True


backend_runner_service = BackendRunnerService()
