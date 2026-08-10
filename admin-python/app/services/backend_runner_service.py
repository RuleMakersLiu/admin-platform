"""后端沙箱 runner（Phase 4b-2）：把生成的 Java Spring Boot 工程在 admin-python 内本地构建并启动。

与前端 sandbox_preview_service 同构（原生子进程，非 docker）：
1. ``mvn -B package -DskipTests`` 打包（依赖缓存在工作区内的 .m2-backend，跨流水线复用）；
2. ``java -jar target/*.jar --server.port=<动态端口>`` 起服务，env 指向 mysql-sandbox；
3. 轮询 TCP 端口就绪；
4. 用完即 ``stop``（terminate + 摘除）。

前置：admin-python 镜像含 JDK18+maven（Dockerfile），mysql-sandbox 服务可达（compose）。
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
        # 每个 pipeline_id → 后端进程句柄/端口/就绪状态等元数据
        self._processes: Dict[str, Dict[str, Any]] = {}
        # 已预留端口（start 中已分配但进程尚未登记），避免并发抢占同一端口
        self._reserved_ports: set[int] = set()
        self._lock = asyncio.Lock()
        # 后端构建（mvn）重，限并发
        self._start_semaphore = asyncio.Semaphore(2)

    # ---------------- 端口分配 ----------------

    def _allocate_port(self) -> int:
        """在配置端口区间内找一个可绑定端口并预留，找不到抛 RuntimeError。"""
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
        """后端沙箱进程是否在运行（进程句柄未结束）。"""
        entry = self._processes.get(pipeline_id)
        return bool(entry and entry["handle"].returncode is None)

    def direct_backend_url(self, pipeline_id: str) -> Optional[str]:
        """已就绪后端的容器内直连 URL，未就绪返回 None（供 4c 契约探针直接命中）。"""
        entry = self._processes.get(pipeline_id)
        if not entry or entry["handle"].returncode is not None or not entry.get("ready"):
            return None
        entry["last_active"] = time.time()
        return f"http://{entry['connect_host']}:{entry['port']}"

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
        """在 target/ 下找到可执行 jar（优先非 -plain 的 spring-boot 产物）。"""
        target = root / "target"
        if not target.exists():
            return None
        # 优先非 -plain 的可执行 jar（spring-boot-maven-plugin 产物）
        jars = sorted(target.glob("*.jar"), key=lambda p: ("-plain" in p.name, p.name))
        return jars[0] if jars else None

    async def _run(self, args: list[str], cwd: Path, timeout: int = 900) -> Tuple[int, str]:
        """以安全原语运行子进程（剔除 admin 凭据 + 降权），超时返回 124。"""
        # 安全：mvn 执行生成工程的 pom.xml（可能含恶意构建插件/依赖）——走统一安全原语
        # （剔除 admin 凭据 + 非 root 降权），超时返回 124。
        from app.services.sandbox_security import run_sandboxed
        try:
            return await run_sandboxed(args, cwd=str(cwd), timeout=timeout)
        except asyncio.TimeoutError:
            return 124, "构建超时"

    async def _wait_tcp_ready(self, host: str, port: int, timeout: int = 90) -> None:
        """轮询 TCP 端口直到可连（服务就绪），超时抛 RuntimeError。"""
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
        """构建并启动后端沙箱：建库→mvn 打包→起 jar→等端口就绪，返回直连地址。"""
        if not shutil.which("java") or not shutil.which("mvn"):
            raise RuntimeError(
                "admin-python 容器未安装 JDK/maven（需 rebuild 含 openjdk-18 + maven 的镜像后生效）"
            )
        root = Path(workspace_path)
        if not (root / "pom.xml").exists():
            raise RuntimeError("工作区无 pom.xml（backend_scaffolder 未运行或非 Java 工程）")

        async with self._start_semaphore:
            # 复用已就绪的同 pipeline 后端
            existing = self._processes.get(pipeline_id)
            if existing and existing["handle"].returncode is None and existing.get("ready"):
                return self._response(pipeline_id, existing)

            # 0) 建 per-pipeline DB + 灌 schema.sql（4b-3，fail-open，不阻塞构建）
            await self._prepare_database(pipeline_id, root)

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
            # 安全（防越权）：生成的 Java 进程只给最小必要 env，绝不继承 admin 凭据
            # （DATABASE_URL/JWT_SECRET/*_API_KEY 等）——否则生成代码 getenv 即可越权拿 admin 库凭据
            env = {
                "PATH": os.environ.get("PATH", ""),
                "JAVA_HOME": os.environ.get("JAVA_HOME", ""),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
                "HOME": "/tmp",
                "MYSQL_HOST": settings.pipeline_backend_mysql_host,
                "MYSQL_PORT": str(settings.pipeline_backend_mysql_port),
                "MYSQL_DB": f"sandbox_{pipeline_id[:12].replace('-', '')}"[:63],
                "MYSQL_USER": settings.pipeline_backend_mysql_user,
                "MYSQL_PASSWORD": settings.pipeline_backend_mysql_password,
            }
            from app.services.sandbox_security import spawn_sandboxed_service
            # env=自建白名单（含沙箱 MySQL 凭据，原样保留不被二次剔除）；降权/容器隔离由句柄负责。
            # container 模式：java 跑在 sandbox-be-<pid12> 容器（仅 sandbox-net），admin-python 经此 DNS 名连它。
            container_mode = settings.sandbox_execution_mode == "container"
            be_name = f"{settings.sandbox_container_prefix_be}-{pipeline_id[:12].replace('-', '')}"

            def _on_be_log(line: str) -> None:
                if any(k in line for k in ("ERROR", "Started", "Failed", "Exception", "Application")):
                    logger.info("[SandboxBE:%s] %s", pipeline_id, line[:1000])

            handle = await spawn_sandboxed_service(
                ["java", "-jar", str(jar), f"--server.port={port}"],
                cwd=str(root),
                env=env,
                name=be_name,
            )
            # container 模式启日志 drain：java 崩溃 → docker logs EOF → returncode 置位（is_running 转 False）
            if container_mode:
                await handle.start_log_drain(_on_be_log)
            entry: Dict[str, Any] = {
                "handle": handle,
                "port": port,
                "ready": False,
                "root": str(root),
                "connect_host": be_name if container_mode else settings.pipeline_backend_host,
                "last_active": time.time(),
            }
            async with self._lock:
                self._processes[pipeline_id] = entry
                self._reserved_ports.discard(port)

        try:
            await self._wait_tcp_ready(entry["connect_host"], port, timeout=90)
        except Exception:
            await self._teardown(pipeline_id, entry)
            raise
        entry["ready"] = True
        logger.info("backend_runner: started %s on port %s", pipeline_id, port)
        return self._response(pipeline_id, entry)

    def _response(self, pipeline_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """组装对外返回的沙箱状态（含直连 backend_url）。"""
        return {
            "pipeline_id": pipeline_id,
            "status": "running",
            "port": entry["port"],
            "backend_url": self.direct_backend_url(pipeline_id),
        }

    async def _teardown(self, pipeline_id: str, entry: Dict[str, Any]) -> None:
        """回收进程句柄并从进程表中摘除。"""
        handle = entry.get("handle")
        if handle:
            await handle.acleanup(timeout=5)
        async with self._lock:
            if self._processes.get(pipeline_id) is entry:
                self._processes.pop(pipeline_id, None)

    async def stop(self, pipeline_id: str) -> bool:
        """停止后端沙箱进程，返回是否实际停止（未在运行返回 False）。"""
        async with self._lock:
            entry = self._processes.get(pipeline_id)
            if not entry or entry["handle"].returncode is not None:
                return False
        await self._teardown(pipeline_id, entry)
        return True

    async def _prepare_database(self, pipeline_id: str, root: Path) -> None:
        """4b-3：在 mysql-sandbox 建 per-pipeline DB + 灌 schema.sql。fail-open（失败不阻塞）。"""
        import pymysql

        db_name = f"sandbox_{pipeline_id[:12].replace('-', '')}"[:63]
        # 防库名注入：只允许字母数字下划线
        if not db_name.replace("_", "").isalnum():
            logger.warning("invalid sandbox db_name %s, skip seeding", db_name)
            return
        host = settings.pipeline_backend_mysql_host
        port = settings.pipeline_backend_mysql_port
        root_pwd = settings.pipeline_backend_mysql_root_password

        # 1) root 建库（sandbox user 可能无 CREATE DATABASE 权限）
        try:
            conn = await asyncio.to_thread(
                pymysql.connect, host=host, port=port, user="root",
                password=root_pwd, autocommit=True,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
                    )
                    # 授权 sandbox user（生成的 Java 用它连；仅此 per-pipeline 库，
                    # 隔离 + 无 FILE/SHUTDOWN 等全局权限，危险 SQL 由 MySQL 权限兜底拒绝）
                    cur.execute(
                        f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO "
                        f"`{settings.pipeline_backend_mysql_user}`@`%`"
                    )
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("create sandbox DB %s failed (non-fatal): %s", db_name, exc)
            return

        # 2) 灌 schema.sql（扫工作区所有 *.sql）
        sql_files = sorted(root.rglob("*.sql"))
        if not sql_files:
            logger.info("backend_runner: 无 schema.sql，跳过灌入 %s", db_name)
            return
        try:
            conn = await asyncio.to_thread(
                pymysql.connect, host=host, port=port,
                user=settings.pipeline_backend_mysql_user,
                password=settings.pipeline_backend_mysql_password,
                database=db_name, autocommit=True,
            )
            try:
                with conn.cursor() as cur:
                    for sql_file in sql_files:
                        for stmt in _split_sql(sql_file.read_text(encoding="utf-8", errors="ignore")):
                            cur.execute(stmt)
                logger.info("backend_runner: 灌入 %s（%d 个 sql 文件）", db_name, len(sql_files))
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed sandbox DB %s failed (non-fatal): %s", db_name, exc)


def _split_sql(sql: str) -> list[str]:
    """简单按 ; 分割 SQL 语句、去 -- 注释行（够用 for CREATE TABLE/INSERT 等 DDL）。"""
    statements: list[str] = []
    for raw in sql.split(";"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


backend_runner_service = BackendRunnerService()
