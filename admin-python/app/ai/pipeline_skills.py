"""Pipeline v2 Skills — 可配置的流水线操作能力

每个 Skill 封装一个独立的操作（写文件、跑测试、Git 提交、部署），
通过 skill_registry 注册，flow_manager 按阶段调用。
"""
import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.ai.skills import skill_registry
from app.core.config import settings

logger = logging.getLogger(__name__)

# ==================== Workspace Helper ====================

WORKSPACE_ROOT = settings.pipeline_workspace_root


def get_workspace_path(pipeline_id: str) -> str:
    return os.path.join(WORKSPACE_ROOT, pipeline_id)


def ensure_workspace(pipeline_id: str) -> str:
    path = get_workspace_path(pipeline_id)
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_workspace(pipeline_id: str) -> None:
    path = get_workspace_path(pipeline_id)
    shutil.rmtree(path, ignore_errors=True)


# ==================== Skill: file_writer / file_reader / file_cleaner ====================

@skill_registry.register(
    skill_id="file_writer",
    name="文件写入",
    description="在指定根目录内安全写入文件映射",
    category="development",
    agent_type="SYSTEM",
    input_schema={
        "root_path": {"type": "string"},
        "files": {"type": "object", "description": "{relative_path: content}"},
    },
    output_schema={
        "files_written": {"type": "array"},
        "root_path": {"type": "string"},
    },
)
async def file_writer(root_path: str, files: Dict[str, str], **kwargs) -> Dict[str, Any]:
    """Write files under root_path without allowing path traversal."""
    root = Path(root_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    written = []

    for filepath, content in (files or {}).items():
        relative = str(filepath).replace("\\", "/").lstrip("/")
        parts = [part for part in relative.split("/") if part not in ("", ".", "..")]
        if not parts:
            continue
        target = (root / Path(*parts)).resolve()
        if root not in target.parents and target != root:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        written.append("/".join(parts))

    logger.info(f"file_writer: wrote {len(written)} files to {root}")
    return {"files_written": written, "root_path": str(root)}


_DEFAULT_READ_EXCLUDE_DIRS = {
    ".git", "node_modules", "dist", ".nuxt", ".next", "__pycache__",
    "vendor", "target", "build",
}
_DEFAULT_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".zip", ".tar", ".gz",
}


@skill_registry.register(
    skill_id="file_reader",
    name="文件读取",
    description="在指定根目录内安全读取文件或扫描目录文件",
    category="development",
    agent_type="SYSTEM",
    input_schema={
        "root_path": {"type": "string"},
        "paths": {"type": "array", "description": "相对路径列表；为空则扫描 root_path"},
        "max_bytes": {"type": "integer", "default": 20000},
        "path_limits": {"type": "array", "description": "按路径前缀/后缀设置读取上限"},
        "exclude_dirs": {"type": "array"},
        "binary_extensions": {"type": "array"},
    },
    output_schema={
        "files": {"type": "object"},
        "files_read": {"type": "array"},
    },
)
async def file_reader(
    root_path: str,
    paths: Optional[List[str]] = None,
    max_bytes: int = 20000,
    path_limits: Optional[List[Dict[str, Any]]] = None,
    exclude_dirs: Optional[List[str]] = None,
    binary_extensions: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Read text files under root_path without allowing path traversal."""
    root = Path(root_path).resolve()
    if not root.exists() or not root.is_dir():
        return {"files": {}, "files_read": [], "error": "root_path does not exist or is not a directory"}

    excludes = set(exclude_dirs or _DEFAULT_READ_EXCLUDE_DIRS)
    binary_exts = set(binary_extensions or _DEFAULT_BINARY_EXTENSIONS)
    default_limit = max(0, int(max_bytes or 0))
    files: Dict[str, str] = {}

    def safe_relative_path(raw_path: str) -> Optional[Path]:
        relative = str(raw_path).replace("\\", "/").lstrip("/")
        parts = [part for part in relative.split("/") if part not in ("", ".", "..")]
        if not parts:
            return None
        candidate = (root / Path(*parts)).resolve()
        if root not in candidate.parents and candidate != root:
            return None
        return candidate

    def read_file(path: Path) -> None:
        if path.suffix.lower() in binary_exts or not path.is_file():
            return
        rel = path.relative_to(root).as_posix()
        limit = default_limit
        for rule in path_limits or []:
            prefixes = tuple(rule.get("prefixes") or [])
            suffixes = tuple(rule.get("suffixes") or [])
            if prefixes and not rel.startswith(prefixes):
                continue
            if suffixes and not rel.endswith(suffixes):
                continue
            try:
                limit = max(0, int(rule.get("max_bytes", limit)))
            except (TypeError, ValueError):
                pass
            break
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                files[rel] = handle.read(limit)
        except Exception:
            return

    if paths:
        for raw_path in paths:
            candidate = safe_relative_path(raw_path)
            if candidate:
                read_file(candidate)
    else:
        for current_root, dirs, filenames in os.walk(root):
            dirs[:] = [name for name in dirs if name not in excludes]
            for filename in filenames:
                read_file(Path(current_root) / filename)

    return {"files": files, "files_read": sorted(files)}


@skill_registry.register(
    skill_id="file_cleaner",
    name="文件清理",
    description="在指定根目录内安全删除临时文件或目录",
    category="development",
    agent_type="SYSTEM",
    input_schema={
        "root_path": {"type": "string"},
        "paths": {"type": "array", "description": "需要删除的相对路径列表"},
    },
    output_schema={
        "files_deleted": {"type": "array"},
        "root_path": {"type": "string"},
    },
)
async def file_cleaner(root_path: str, paths: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    """Delete files or directories under root_path without allowing path traversal."""
    root = Path(root_path).resolve()
    if not root.exists() or not root.is_dir():
        return {"files_deleted": [], "root_path": str(root)}

    deleted = []
    for raw_path in paths or []:
        relative = str(raw_path).replace("\\", "/").lstrip("/")
        parts = [part for part in relative.split("/") if part not in ("", ".", "..")]
        if not parts:
            continue
        target = (root / Path(*parts)).resolve()
        if root not in target.parents and target != root:
            continue
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            deleted.append("/".join(parts))
        elif target.exists():
            target.unlink()
            deleted.append("/".join(parts))

    return {"files_deleted": deleted, "root_path": str(root)}


# ==================== Skill: code_writer ====================

@skill_registry.register(
    skill_id="code_writer",
    name="代码写入",
    description="将 LLM 生成的代码文件写入工作区目录",
    category="development",
    agent_type="SYSTEM",
    input_schema={
        "pipeline_id": {"type": "string"},
        "code_files": {"type": "object", "description": "{filepath: content}"},
    },
    output_schema={
        "files_written": {"type": "array"},
        "workspace_path": {"type": "string"},
    },
)
async def code_writer(pipeline_id: str, code_files: Dict[str, str], **kwargs) -> Dict[str, Any]:
    """将 LLM 生成的代码写入工作区"""
    workspace = ensure_workspace(pipeline_id)
    result = await file_writer(workspace, code_files)
    written = result.get("files_written", [])
    logger.info(f"code_writer: wrote {len(written)} files to {workspace}")
    return {"files_written": written, "workspace_path": workspace}


# ==================== Skill: test_runner ====================

_FRAMEWORK_DETECTORS = {
    "pytest": lambda w: bool(
        (Path(w) / "pytest.ini").exists()
        or (Path(w) / "pyproject.toml").exists()
        or (Path(w) / "conftest.py").exists()
    ),
    "npm": lambda w: bool(
        (Path(w) / "package.json").exists()
    ),
    "go": lambda w: bool(
        (Path(w) / "go.mod").exists()
    ),
}

_FRAMEWORK_COMMANDS = {
    "pytest": ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"],
    "npm": ["npm", "test"],
    "go": ["go", "test", "./..."],
}


def _detect_frameworks(workspace: str, preferred: Optional[List[str]] = None) -> List[str]:
    if preferred:
        return [f for f in preferred if f in _FRAMEWORK_COMMANDS]
    return [name for name, detector in _FRAMEWORK_DETECTORS.items() if detector(workspace)]


def _parse_pytest_output(stdout: str) -> Dict[str, int]:
    """从 pytest 输出提取 passed/failed/errored"""
    import re
    m = re.search(r"(\d+) passed", stdout)
    passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) failed", stdout)
    failed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) error", stdout)
    errors = int(m.group(1)) if m else 0
    return {"passed": passed, "failed": failed, "errors": errors}


def _parse_npm_output(stdout: str) -> Dict[str, int]:
    import re
    m = re.search(r"Tests:\s+\d+\s+failed", stdout)
    failed = int(re.search(r"(\d+)", m.group(0)).group(1)) if m else 0
    m = re.search(r"(\d+)\s+passed", stdout)
    passed = int(m.group(1)) if m else 0
    return {"passed": passed, "failed": failed, "errors": 0}


@skill_registry.register(
    skill_id="test_runner",
    name="测试执行",
    description="检测并执行工作区中的测试框架（pytest/npm test/go test）",
    category="testing",
    agent_type="SYSTEM",
    input_schema={
        "workspace_path": {"type": "string"},
        "timeout": {"type": "integer", "default": 120},
        "frameworks": {"type": "array", "description": "指定框架，空则自动检测"},
    },
    output_schema={
        "success": {"type": "boolean"},
        "framework": {"type": "string"},
        "tests_passed": {"type": "integer"},
        "tests_failed": {"type": "integer"},
        "stdout": {"type": "string"},
        "duration_ms": {"type": "integer"},
    },
)
async def test_runner(
    workspace_path: str,
    timeout: int = 120,
    frameworks: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """执行测试框架"""
    if not os.path.isdir(workspace_path):
        return {"success": False, "framework": "none", "error": "工作区不存在", "skipped": False}

    detected = _detect_frameworks(workspace_path, frameworks)
    if not detected:
        return {"success": True, "framework": "none", "skipped": True, "message": "未检测到测试框架，跳过测试"}

    for fw in detected:
        cmd = _FRAMEWORK_COMMANDS[fw]
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            duration_ms = int((time.time() - start) * 1000)
            stdout = stdout_bytes.decode("utf-8", errors="replace")

            # 截断超长输出
            if len(stdout) > 10000:
                stdout = stdout[:5000] + "\n... (truncated) ...\n" + stdout[-5000:]

            if proc.returncode == 0:
                return {
                    "success": True,
                    "framework": fw,
                    "stdout": stdout,
                    "duration_ms": duration_ms,
                    "skipped": False,
                }
            else:
                # 解析失败详情
                if fw == "pytest":
                    counts = _parse_pytest_output(stdout)
                elif fw == "npm":
                    counts = _parse_npm_output(stdout)
                else:
                    counts = {"passed": 0, "failed": 1, "errors": 0}

                return {
                    "success": False,
                    "framework": fw,
                    "stdout": stdout,
                    "tests_passed": counts.get("passed", 0),
                    "tests_failed": counts.get("failed", 1),
                    "duration_ms": duration_ms,
                    "skipped": False,
                }

        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "framework": fw,
                "error": f"测试执行超时 ({timeout}s)",
                "skipped": False,
            }
        except FileNotFoundError:
            continue

    return {"success": True, "framework": "none", "skipped": True, "message": "所有测试命令不可用"}


# ==================== Skill: git_commit ====================

_SSH_KEY_DIR = "/tmp/pipeline_ssh"


async def _write_ssh_key_via_skill(git_config: Any) -> Optional[str]:
    """将 SSH key 通过文件写入 Skill 写入临时文件，返回路径。"""
    if not git_config or not git_config.ssh_key:
        return None
    filename = f"gitconfig_{git_config.id}.key"
    result = await file_writer(_SSH_KEY_DIR, {filename: git_config.ssh_key})
    if filename not in result.get("files_written", []):
        return None
    key_path = os.path.join(_SSH_KEY_DIR, filename)
    os.chmod(key_path, 0o600)
    return key_path


def _build_auth_url(repo_url: str, git_config: Any) -> str:
    """构建带认证的 Git URL"""
    if not git_config:
        return repo_url
    if git_config.ssh_key:
        # 转换 HTTPS → SSH
        if repo_url.startswith("https://"):
            parts = repo_url.replace("https://", "").split("/", 1)
            if len(parts) == 2:
                return f"git@{parts[0]}:{parts[1]}"
        return repo_url
    if git_config.access_token and repo_url.startswith("https://"):
        platform = (git_config.platform or "").lower()
        if platform in ("github", "gitea"):
            return repo_url.replace("https://", f"https://{git_config.access_token}@")
        elif platform == "gitlab":
            return repo_url.replace("https://", f"https://oauth2:{git_config.access_token}@")
        else:
            return repo_url.replace("https://", f"https://{git_config.access_token}@")
    return repo_url


def _do_git_operations(
    workspace_path: str,
    commit_message: str,
    repo_url: str,
    branch: str,
    git_config: Any,
    ssh_key_path: Optional[str] = None,
) -> Dict[str, Any]:
    """同步 Git 操作（在 asyncio.to_thread 中执行）"""
    import git as gitpython

    env = os.environ.copy()
    if ssh_key_path:
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no"

    if repo_url:
        auth_url = _build_auth_url(repo_url, git_config)
        # 如果工作区已有 .git，做 pull；否则 clone
        if os.path.isdir(os.path.join(workspace_path, ".git")):
            repo = gitpython.Repo(workspace_path)
            try:
                repo.remotes.origin.pull(branch)
            except Exception:
                pass
        else:
            repo = gitpython.Repo.clone_from(
                auth_url, workspace_path,
                branch=branch, env=env,
            )
    else:
        repo = gitpython.Repo.init(workspace_path)

    # 设置 git 用户信息
    config_writer = repo.config_writer()
    config_writer.set_value("user", "name", "AI Pipeline")
    config_writer.set_value("user", "email", "pipeline@admin-platform.local")
    config_writer.release()

    # 添加所有文件
    repo.index.add(repo.untracked_files)
    # 也添加已修改的文件
    for item in repo.index.diff(None):
        repo.index.add([item.a_path])
    for item in repo.index.diff("HEAD"):
        repo.index.add([item.a_path])

    # 提交
    commit = repo.index.commit(commit_message)
    commit_sha = commit.hexsha

    # 推送
    pushed = False
    if repo_url and "origin" in [r.name for r in repo.remotes]:
        for attempt in range(3):
            try:
                repo.remotes.origin.push(f"{branch}:{branch}", env=env)
                pushed = True
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(5)
                else:
                    return {"commit_sha": commit_sha, "pushed": False, "error": str(e)}

    return {"commit_sha": commit_sha, "pushed": pushed, "branch": branch}


@skill_registry.register(
    skill_id="git_commit",
    name="Git 提交推送",
    description="将工作区代码提交并推送到远程 Git 仓库",
    category="deployment",
    agent_type="SYSTEM",
    input_schema={
        "workspace_path": {"type": "string"},
        "commit_message": {"type": "string"},
        "repo_url": {"type": "string"},
        "branch": {"type": "string", "default": "main"},
        "git_config_id": {"type": "integer"},
        "db_session": {"type": "object", "description": "SQLAlchemy session (内部传递)"},
    },
    output_schema={
        "commit_sha": {"type": "string"},
        "pushed": {"type": "boolean"},
        "branch": {"type": "string"},
    },
)
async def git_commit(
    workspace_path: str,
    commit_message: str,
    repo_url: str = "",
    branch: str = "main",
    git_config_id: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Git 提交并推送"""
    db_session = kwargs.get("db_session")

    # 加载 Git 配置
    git_config = None
    if git_config_id and db_session:
        from sqlalchemy import select
        from app.models.models import SysGitConfig
        result = await db_session.execute(
            select(SysGitConfig).where(SysGitConfig.id == git_config_id)
        )
        git_config = result.scalar_one_or_none()

    if not git_config and db_session:
        from sqlalchemy import select
        from app.models.models import SysGitConfig
        result = await db_session.execute(
            select(SysGitConfig).where(
                SysGitConfig.is_default == 1,
                SysGitConfig.status == 1,
            )
        )
        git_config = result.scalar_one_or_none()

    if not repo_url and not git_config:
        return {"commit_sha": "local", "pushed": False, "skipped": True, "message": "无 Git 配置，仅本地提交"}

    try:
        ssh_key_path = await _write_ssh_key_via_skill(git_config)
        result = await asyncio.to_thread(
            _do_git_operations,
            workspace_path, commit_message, repo_url, branch, git_config, ssh_key_path,
        )
        return result
    except Exception as e:
        return {"commit_sha": "", "pushed": False, "error": str(e)}


# ==================== Skill: deployer ====================

@skill_registry.register(
    skill_id="deployer",
    name="部署发布",
    description="调用 Go Deploy 服务构建 Docker 镜像并部署",
    category="deployment",
    agent_type="SYSTEM",
    input_schema={
        "workspace_path": {"type": "string"},
        "repo_url": {"type": "string"},
        "branch": {"type": "string"},
        "tenant_id": {"type": "integer"},
        "admin_id": {"type": "integer"},
        "pipeline_id": {"type": "string"},
    },
    output_schema={
        "deploy_status": {"type": "string"},
        "task_id": {"type": "integer"},
        "logs": {"type": "string"},
    },
)
async def deployer(
    workspace_path: str,
    repo_url: str = "",
    branch: str = "main",
    tenant_id: int = 0,
    admin_id: int = 0,
    pipeline_id: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """调用 Go Deploy 服务"""
    base_url = settings.deploy_service_url
    project_code = f"pipeline-{pipeline_id[:12]}" if pipeline_id else "pipeline-unknown"

    # 检测项目类型（含 Java Spring Boot，避免误判为 python）
    project_type = _detect_project_type(workspace_path)

    dockerfile = _generate_dockerfile(project_type)
    image_name = project_code

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        headers = {"X-Tenant-Id": str(tenant_id), "X-Admin-Id": str(admin_id)}

        try:
            # 1. 查找或创建 deploy project
            resp = await client.get("/deploy/projects", headers=headers, params={"keyword": project_code})
            projects = resp.json().get("data", {}).get("list", []) if resp.status_code == 200 else []
            project = next((p for p in projects if p.get("code") == project_code), None)

            if not project:
                resp = await client.post("/deploy/projects", headers=headers, json={
                    "name": project_code,
                    "code": project_code,
                    "type": project_type,
                    "repo_url": repo_url,
                    "branch": branch,
                    "dockerfile": dockerfile,
                    "image_name": image_name,
                })
                if resp.status_code not in (200, 201):
                    return {"deploy_status": "failed", "error": f"创建部署项目失败: {resp.text}"}
                project = resp.json().get("data", {})

            # 2. 创建构建+部署任务
            resp = await client.post("/deploy/tasks", headers=headers, json={
                "project": project_code,
                "env": "dev",
                "type": 2,  # build+deploy
            })
            if resp.status_code not in (200, 201):
                return {"deploy_status": "failed", "error": f"创建部署任务失败: {resp.text}"}
            task = resp.json().get("data", {})
            task_id = task.get("id")

            # 3. 触发执行
            await client.post(f"/deploy/tasks/{task_id}/execute", headers=headers)

            # 4. 轮询状态
            for _ in range(60):  # 最多等 10 分钟
                await asyncio.sleep(10)
                resp = await client.get(f"/deploy/tasks/{task_id}", headers=headers)
                task_data = resp.json().get("data", {})
                status = task_data.get("status", 0)
                if status >= 3:  # 3=success, 4=failed, 5=cancelled
                    # 获取日志
                    logs_resp = await client.get(f"/deploy/tasks/{task_id}/logs", headers=headers)
                    logs = logs_resp.text if logs_resp.status_code == 200 else ""
                    return {
                        "deploy_status": "success" if status == 3 else "failed",
                        "task_id": task_id,
                        "logs": logs[-2000:] if logs else "",
                        "project_type": project_type,
                    }

            return {"deploy_status": "timeout", "task_id": task_id, "error": "部署超时"}

        except httpx.ConnectError:
            return {"deploy_status": "unreachable", "error": "Deploy 服务不可用，请检查是否启动"}
        except Exception as e:
            return {"deploy_status": "failed", "error": str(e)}


def _detect_project_type(workspace_path: str) -> str:
    """从工作区文件探测项目类型：java > go > node > python。

    修复「Java 工程因无 go.mod/package.json 被误判为 python」的 bug——识别 pom.xml/build.gradle
    及 src/main/java 下的 .java。
    """
    root = workspace_path or ""
    if os.path.isfile(os.path.join(root, "pom.xml")) or os.path.isfile(os.path.join(root, "build.gradle")):
        return "java"
    try:
        if any(Path(root).glob("src/main/java/**/*.java")):
            return "java"
    except (OSError, ValueError):
        pass
    if os.path.isfile(os.path.join(root, "go.mod")):
        return "go"
    if os.path.isfile(os.path.join(root, "package.json")):
        return "node"
    return "python"


def _generate_dockerfile(project_type: str) -> str:
    templates = {
        "python": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -e .\nCMD [\"python\", \"-m\", \"app.main\"]",
        "node": "FROM node:20-alpine\nWORKDIR /app\nCOPY . .\nRUN npm install && npm run build\nCMD [\"npm\", \"start\"]",
        "go": "FROM golang:1.21-alpine\nWORKDIR /app\nCOPY . .\nRUN go build -o main ./cmd\nCMD [\"./main\"]",
        # Java Spring Boot：多阶段构建（maven 打包 → JRE 运行），端口 8080
        "java": (
            "FROM maven:3.9-eclipse-temurin-17 AS build\n"
            "WORKDIR /app\n"
            "COPY pom.xml .\n"
            "RUN mvn -B dependency:go-offline\n"
            "COPY src ./src\n"
            "RUN mvn -B package -DskipTests\n"
            "FROM eclipse-temurin:17-jre\n"
            "WORKDIR /app\n"
            "COPY --from=build /app/target/*.jar app.jar\n"
            "EXPOSE 8080\n"
            'ENTRYPOINT ["java", "-jar", "app.jar"]\n'
        ),
    }
    return templates.get(project_type, templates["python"])


# ==================== Skill: dockerfile_generator ====================

@skill_registry.register(
    skill_id="dockerfile_generator",
    name="Dockerfile 生成",
    description="根据项目类型自动生成 Dockerfile",
    category="development",
    agent_type="SYSTEM",
    input_schema={
        "workspace_path": {"type": "string"},
        "project_type": {"type": "string"},
    },
    output_schema={
        "dockerfile": {"type": "string"},
        "project_type": {"type": "string"},
    },
)
async def dockerfile_generator(workspace_path: str, project_type: str = None, **kwargs) -> Dict[str, Any]:
    if not project_type:
        project_type = _detect_project_type(workspace_path)

    dockerfile = _generate_dockerfile(project_type)
    # 写入工作区
    df_path = os.path.join(workspace_path, "Dockerfile")
    if not os.path.isfile(df_path):
        await file_writer(workspace_path, {"Dockerfile": dockerfile})

    return {"dockerfile": dockerfile, "project_type": project_type}
