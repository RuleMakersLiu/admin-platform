"""Run generated frontend artifacts in an isolated local dev server."""
import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)


class SandboxPreviewService:
    def __init__(self) -> None:
        self._processes: Dict[str, Dict[str, Any]] = {}
        self._reserved_ports: set[int] = set()
        self._process_lock = asyncio.Lock()
        self._pipeline_locks: Dict[str, asyncio.Lock] = {}
        self._start_semaphore = asyncio.Semaphore(3)
        self._token_ttl_seconds = 8 * 60 * 60
        self._max_tokens_per_pipeline = 80

    async def _pipeline_lock(self, pipeline_id: str) -> asyncio.Lock:
        async with self._process_lock:
            lock = self._pipeline_locks.get(pipeline_id)
            if lock is None:
                lock = asyncio.Lock()
                self._pipeline_locks[pipeline_id] = lock
            return lock

    def _prune_tokens(self, entry: Dict[str, Any]) -> None:
        tokens = entry.setdefault("tokens", {})
        now = time.time()
        for token, expires_at in list(tokens.items()):
            if expires_at <= now:
                tokens.pop(token, None)
        if len(tokens) <= self._max_tokens_per_pipeline:
            return
        for token, _ in sorted(tokens.items(), key=lambda item: item[1])[:-self._max_tokens_per_pipeline]:
            tokens.pop(token, None)

    def _issue_token(self, entry: Dict[str, Any]) -> str:
        self._prune_tokens(entry)
        token = secrets.token_urlsafe(32)
        entry.setdefault("tokens", {})[token] = time.time() + self._token_ttl_seconds
        entry["token"] = token
        entry["started_at"] = int(time.time() * 1000)
        return token

    def _preview_root(self, pipeline_id: str) -> Path:
        return Path(settings.pipeline_workspace_root) / pipeline_id / "real-frontend-preview"

    async def _allocate_port(self) -> int:
        async with self._process_lock:
            return self._allocate_port_locked()

    def _allocate_port_locked(self) -> int:
        used = {int(item["port"]) for item in self._processes.values() if item.get("port")} | self._reserved_ports
        for port in range(settings.pipeline_preview_port_start, settings.pipeline_preview_port_end + 1):
            if port in used:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind((settings.pipeline_preview_host, port))
                except OSError:
                    continue
                self._reserved_ports.add(port)
                return port
        raise RuntimeError("没有可用的预览端口")

    def _safe_write_files(self, root: Path, files: Dict[str, str]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        root_resolved = root.resolve()
        for raw_path, content in files.items():
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            parts = [part for part in safe_path.split("/") if part not in ("", ".", "..")]
            if not parts:
                continue
            target = (root / Path(*parts)).resolve()
            if not str(target).startswith(str(root_resolved)):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            text_content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
            if safe_path.startswith("src/views/") and safe_path.endswith(".vue"):
                text_content = self._patch_generated_vue_content(text_content)
            target.write_text(text_content, encoding="utf-8")

    def _patch_generated_vue_content(self, content: str) -> str:
        patched = self._patch_stable_contract(content)
        if "JDictSelectTag" not in patched:
            return patched
        replacements = {
            "import { STable, JDictSelectTag } from '@/components'": (
                "import { STable } from '@/components'\n"
                "import JDictSelectTag from '@/components/dict/JDictSelectTag.vue'"
            ),
            "import { JDictSelectTag, STable } from '@/components'": (
                "import { STable } from '@/components'\n"
                "import JDictSelectTag from '@/components/dict/JDictSelectTag.vue'"
            ),
            "import { JDictSelectTag } from '@/components'": (
                "import JDictSelectTag from '@/components/dict/JDictSelectTag.vue'"
            ),
        }
        for source, target in replacements.items():
            patched = patched.replace(source, target)
        return patched

    def _patch_stable_contract(self, content: str) -> str:
        from app.ai.flow_manager import _patch_stable_table_contract_content

        return _patch_stable_table_contract_content(content)

    def _files_hash(self, frontend_files: Dict[str, str]) -> str:
        payload = json.dumps(frontend_files, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _miniapp_html_preview_content(self, frontend_files: Dict[str, str]) -> Optional[str]:
        has_miniapp_page = any(
            str(path).replace("\\", "/").lstrip("/").startswith("pages/")
            and str(path).replace("\\", "/").lstrip("/").endswith(".wxml")
            for path in frontend_files
        )
        if not has_miniapp_page:
            return None
        html_candidates = [
            "public/sandbox-miniapp-preview.html",
            "sandbox-miniapp-preview.html",
            "preview/sandbox-miniapp-preview.html",
        ]
        normalized = {str(path).replace("\\", "/").lstrip("/"): content for path, content in frontend_files.items()}
        for path in html_candidates:
            content = normalized.get(path)
            if isinstance(content, str) and content.strip():
                return content
        for path, content in normalized.items():
            if path.endswith("/sandbox-miniapp-preview.html") and isinstance(content, str) and content.strip():
                return content
        return None

    def _install_miniapp_html_preview(self, root: Path, frontend_files: Dict[str, str]) -> Optional[str]:
        content = self._miniapp_html_preview_content(frontend_files)
        if not content:
            return None
        public_dir = root / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        preview_name = "sandbox-miniapp-preview.html"
        public_dir.joinpath(preview_name).write_text(content, encoding="utf-8")
        return preview_name

    def _generated_api_probe_specs(self, frontend_files: Dict[str, str]) -> list[Dict[str, Any]]:
        specs: Dict[str, Dict[str, Any]] = {}

        def strip_js_comments(content: str) -> str:
            content = re.sub(r"/\*.*?\*/", "", content, flags=re.S)
            return "\n".join(
                line for line in content.splitlines()
                if not line.lstrip().startswith("//")
            )

        def add_path(raw_path: str) -> None:
            path = raw_path.strip("/")
            if not path or path.startswith(("http://", "https://")):
                return
            if not re.search(r"(?:^|/)(?:list|page|detail|info|get)(?:/|$|-)", path):
                return
            probe_path = path if path.startswith("api/") else f"api/{path}"
            expects_list = bool(re.search(r"(?:^|/)(?:list|page)(?:/|$|-)", path))
            existing = specs.get(probe_path)
            specs[probe_path] = {
                "path": probe_path,
                "expects_list": expects_list or bool(existing and existing.get("expects_list")),
            }

        for raw_path, content in frontend_files.items():
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            if not safe_path.startswith("src/api/") or not safe_path.endswith((".js", ".ts")):
                continue
            if not isinstance(content, str):
                continue
            content = strip_js_comments(content)

            prefixes: Dict[str, str] = {}
            for match in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*['\"]([^'\"]+)['\"]", content):
                prefixes[match.group(1)] = match.group(2).strip("/")

            for match in re.finditer(r"url\s*:\s*`?\$\{([A-Za-z_$][\w$]*)\}/([^`'\"]*list[^`'\"]*)`?", content):
                prefix = prefixes.get(match.group(1), "").strip("/")
                suffix = match.group(2).strip("/")
                if prefix and suffix:
                    add_path(f"{prefix}/{suffix}")

            for match in re.finditer(r"url\s*:\s*`?\$\{([A-Za-z_$][\w$]*)\}/([^`'\"]*(?:detail|info|get)[^`'\"]*)`?", content):
                prefix = prefixes.get(match.group(1), "").strip("/")
                suffix = match.group(2).strip("/")
                if prefix and suffix:
                    add_path(f"{prefix}/{suffix}")

            for match in re.finditer(r"url\s*:\s*([A-Za-z_$][\w$]*)\s*\+\s*['\"]/?([^'\"]*(?:list|page|detail|info|get)[^'\"]*)['\"]", content):
                prefix = prefixes.get(match.group(1), "").strip("/")
                suffix = match.group(2).strip("/")
                if prefix and suffix:
                    add_path(f"{prefix}/{suffix}")

            for match in re.finditer(r"url\s*:\s*['\"]([^'\"]*(?:list|page|detail|info|get)[^'\"]*)['\"]", content):
                add_path(match.group(1))
        return [specs[path] for path in sorted(specs)]

    async def _smoke_test_generated_apis(self, pipeline_id: str, frontend_files: Dict[str, str]) -> None:
        specs = self._generated_api_probe_specs(frontend_files)
        if not specs:
            return
        for spec in specs[:5]:
            path = spec["path"]
            response = await self.proxy(
                pipeline_id,
                path,
                "id=1&tracebackId=sandbox-smoke&p=1&page=1&pageNo=1&pageSize=1&page_size=1",
                {},
                "GET",
                b"",
            )
            if response.status_code >= 400:
                raise RuntimeError(f"预览接口预检失败: {path} 返回 HTTP {response.status_code}")
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                raise RuntimeError(f"预览接口预检失败: {path} 未返回 JSON")
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"预览接口预检失败: {path} JSON 无法解析") from exc
            result = payload.get("result") if isinstance(payload, dict) else None
            data = payload.get("data") if isinstance(payload, dict) else None
            if spec.get("expects_list") and (not isinstance(result, dict) or not isinstance(result.get("list"), list)):
                raise RuntimeError(f"预览接口预检失败: {path} 未返回 result.list 数组")
            if not spec.get("expects_list") and not isinstance(result or data or payload, dict):
                raise RuntimeError(f"预览接口预检失败: {path} 未返回详情对象")

    def _detect_first_component(self, root: Path, suffixes: tuple[str, ...]) -> Optional[str]:
        for path in sorted((root / "src").rglob("*")) if (root / "src").exists() else []:
            if path.suffix.lower() in suffixes and path.name.lower() not in ("main.tsx", "main.jsx", "main.ts", "main.js"):
                return path.relative_to(root / "src").as_posix()
        return None

    def _ensure_vite_scaffold(self, root: Path, pipeline_id: str) -> None:
        has_vue = any(path.suffix.lower() == ".vue" for path in root.rglob("*"))
        has_react = any(path.suffix.lower() in (".tsx", ".jsx") for path in root.rglob("*"))

        if not (root / "package.json").exists():
            if has_vue:
                package = {
                    "scripts": {"dev": "vite"},
                    "dependencies": {
                        "@vitejs/plugin-vue2": "^2.3.3",
                        "ant-design-vue": "^1.7.8",
                        "vite": "^5.4.21",
                        "vue": "^2.7.16",
                    },
                    "devDependencies": {},
                }
            else:
                package = {
                    "scripts": {"dev": "vite"},
                    "dependencies": {
                        "@vitejs/plugin-react": "^4.3.4",
                        "antd": "^5.27.0",
                        "vite": "^5.4.21",
                        "react": "^18.3.1",
                        "react-dom": "^18.3.1",
                        "lucide-react": "^0.468.0",
                    },
                    "devDependencies": {"typescript": "^5.9.3"},
                }
            (root / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

        if not (root / "index.html").exists():
            (root / "index.html").write_text(
                '<!doctype html><html><head><meta charset="UTF-8" />'
                '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
                f"<title>{pipeline_id} preview</title></head><body><div id=\"root\"></div>"
                '<script type="module" src="/src/main.jsx"></script></body></html>',
                encoding="utf-8",
            )

        if has_vue and not (root / "vite.config.js").exists():
            (root / "vite.config.js").write_text(
                "import { defineConfig } from 'vite'\n"
                "import vue from '@vitejs/plugin-vue2'\n\n"
                "export default defineConfig({ plugins: [vue()] })\n",
                encoding="utf-8",
            )

        src = root / "src"
        src.mkdir(exist_ok=True)
        if has_vue and not any((src / name).exists() for name in ("main.js", "main.ts")):
            component = self._detect_first_component(root, (".vue",)) or "App.vue"
            if not (src / component).exists():
                (src / "App.vue").write_text("<template><div id=\"preview-root\">Preview</div></template>\n", encoding="utf-8")
                component = "App.vue"
            (src / "main.js").write_text(
                "import Vue from 'vue'\n"
                "import Antd from 'ant-design-vue'\n"
                "import 'ant-design-vue/dist/antd.css'\n"
                f"import App from './{component}'\n\n"
                "Vue.use(Antd)\nnew Vue({ render: h => h(App) }).$mount('#root')\n",
                encoding="utf-8",
            )
            index = root / "index.html"
            index.write_text(index.read_text(encoding="utf-8").replace("/src/main.jsx", "/src/main.js"), encoding="utf-8")
        elif has_react and not any((src / name).exists() for name in ("main.jsx", "main.tsx")):
            component = self._detect_first_component(root, (".tsx", ".jsx", ".js")) or "App.jsx"
            if not (src / component).exists():
                (src / "App.jsx").write_text("export default function App(){return <div id=\"preview-root\">Preview</div>}\n", encoding="utf-8")
                component = "App.jsx"
            (src / "main.jsx").write_text(
                "import React from 'react'\n"
                "import { createRoot } from 'react-dom/client'\n"
                f"import App from './{component}'\n\n"
                "createRoot(document.getElementById('root')).render(<App />)\n",
                encoding="utf-8",
            )

    async def _wait_ready(self, pipeline_id: str, port: int, timeout: int = 120, preview_path: str = "") -> None:
        deadline = time.time() + timeout
        url = f"http://{settings.pipeline_preview_host}:{port}{self._preview_base(pipeline_id)}{preview_path}"
        async with httpx.AsyncClient(timeout=2.0) as client:
            while time.time() < deadline:
                try:
                    response = await client.get(url)
                    body = response.text[:10000] if "text/html" in response.headers.get("content-type", "") else ""
                    is_uncompiled_template = (
                        "htmlWebpackPlugin.options" in body
                        or "<%=" in body
                        or "<% for" in body
                    )
                    if response.status_code < 500 and not is_uncompiled_template:
                        return
                except Exception:
                    pass
                await asyncio.sleep(0.5)
        raise RuntimeError("前端预览服务启动超时")

    async def _drain_process_output(self, pipeline_id: str, process: asyncio.subprocess.Process) -> None:
        if not process.stdout:
            return
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text_line = line.decode("utf-8", errors="ignore").strip()
                if (
                    "ERROR" in text_line
                    or "Error:" in text_line
                    or "Failed" in text_line
                    or "Compiled" in text_line
                    or "App running at" in text_line
                ):
                    logger.info("[SandboxPreview:%s] %s", pipeline_id, text_line[:1000])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Failed to drain preview output for %s: %s", pipeline_id, exc)

    async def _run(self, args: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"{' '.join(args)} 超时")
        return proc.returncode or 0, output.decode("utf-8", errors="ignore")

    async def _node_version(self) -> str:
        code, output = await self._run(["node", "-v"], Path("/tmp"), timeout=10)
        if code != 0:
            return ""
        return output.strip()

    def _load_env_file(self, root: Path, filename: str) -> Dict[str, str]:
        env_path = root / filename
        values: Dict[str, str] = {}
        if not env_path.exists():
            return values
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
        return values

    async def _project_git_info(self, project_id: str, fallback_repo_url: str = "") -> Dict[str, Any]:
        repo_url = fallback_repo_url or ""
        branch = "main"
        git_config_id = None
        try:
            async with async_session_maker() as session:
                if project_id and str(project_id).isdigit():
                    result = await session.execute(
                        text("SELECT repo_url, branch, git_config_id FROM gen_project WHERE id = :id"),
                        {"id": int(project_id)},
                    )
                    row = result.fetchone()
                    if row:
                        repo_url = row[0] or repo_url
                        branch = row[1] or branch
                        git_config_id = row[2]

                token = ""
                if git_config_id:
                    result = await session.execute(
                        text("SELECT access_token FROM sys_git_config WHERE id = :id AND status = 1"),
                        {"id": int(git_config_id)},
                    )
                    row = result.fetchone()
                    token = row[0] if row and row[0] else ""
                if not token and repo_url:
                    result = await session.execute(
                        text("SELECT platform, access_token, base_url FROM sys_git_config WHERE status = 1 LIMIT 20")
                    )
                    for platform, access_token, base_url in result.fetchall():
                        if not access_token:
                            continue
                        if base_url and base_url in repo_url:
                            token = access_token
                            break
                        if platform and platform.lower() in repo_url.lower():
                            token = access_token
                            break
        except Exception as exc:
            logger.warning("Failed to load project git info for preview: %s", exc)
            token = ""

        clone_url = repo_url
        if token and repo_url.startswith("http://"):
            clone_url = repo_url.replace("http://", f"http://oauth2:{token}@", 1)
        elif token and repo_url.startswith("https://"):
            clone_url = repo_url.replace("https://", f"https://oauth2:{token}@", 1)
        return {"repo_url": repo_url, "clone_url": clone_url, "branch": branch}

    def _canonical_git_url(self, url: str) -> str:
        url = (url or "").strip()
        url = re.sub(r"^(https?://)[^/@]+@", r"\1", url)
        url = url.removesuffix(".git").rstrip("/")
        return url

    async def _clone_project(self, root: Path, project_info: Dict[str, Any]) -> None:
        git_info = await self._project_git_info(
            str(project_info.get("project_id") or ""),
            str(project_info.get("repo_url") or ""),
        )
        if not git_info["repo_url"]:
            raise RuntimeError("匹配到的前端项目没有配置 Git 仓库，无法启动真实项目预览")

        args = ["git", "clone", "--depth", "1", "--branch", git_info["branch"], git_info["clone_url"], str(root)]
        code, output = await self._run(args, root.parent, timeout=180)
        if code != 0:
            args = ["git", "clone", "--depth", "1", git_info["clone_url"], str(root)]
            code, output = await self._run(args, root.parent, timeout=180)
        if code != 0:
            raise RuntimeError(f"克隆前端项目失败: {output[-500:]}")
        (root / ".sandbox-preview-project.json").write_text(
            json.dumps({
                "project_id": project_info.get("project_id") or "",
                "project_name": project_info.get("project_name") or "",
                "repo_url": git_info["repo_url"],
                "branch": git_info["branch"],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _prepare_project_root(self, root: Path, project_info: Dict[str, Any]) -> None:
        if not project_info.get("project_id") and not project_info.get("repo_url"):
            raise RuntimeError("流水线没有匹配到前端项目快照，无法启动真实前端项目预览")
        git_info = await self._project_git_info(
            str(project_info.get("project_id") or ""),
            str(project_info.get("repo_url") or ""),
        )
        if root.exists() and (root / ".git").exists() and (root / "package.json").exists():
            code, remote_output = await self._run(["git", "remote", "get-url", "origin"], root, timeout=20)
            current_repo = remote_output.strip() if code == 0 else ""
            expected_repo = git_info.get("repo_url") or project_info.get("repo_url") or ""
            if expected_repo and self._canonical_git_url(current_repo) != self._canonical_git_url(expected_repo):
                shutil.rmtree(root)
                root.parent.mkdir(parents=True, exist_ok=True)
                await self._clone_project(root, project_info)
                return
            code, output = await self._run(["git", "reset", "--hard", "HEAD"], root, timeout=60)
            if code != 0:
                raise RuntimeError(f"重置前端项目失败: {output[-500:]}")
            code, output = await self._run(["git", "clean", "-fd", "-e", "node_modules"], root, timeout=60)
            if code != 0:
                raise RuntimeError(f"清理前端项目失败: {output[-500:]}")
            marker = root / ".sandbox-preview-project.json"
            if marker.exists():
                try:
                    previous = json.loads(marker.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    previous = {}
                expected_project_id = str(project_info.get("project_id") or "")
                if expected_project_id and str(previous.get("project_id") or "") != expected_project_id:
                    shutil.rmtree(root)
                    root.parent.mkdir(parents=True, exist_ok=True)
                    await self._clone_project(root, project_info)
                    return
            else:
                marker.write_text(
                    json.dumps({
                        "project_id": project_info.get("project_id") or "",
                        "project_name": project_info.get("project_name") or "",
                        "repo_url": expected_repo,
                        "branch": git_info.get("branch") or "",
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            return

        if root.exists():
            shutil.rmtree(root)
        root.parent.mkdir(parents=True, exist_ok=True)
        await self._clone_project(root, project_info)

    def _dev_command(self, root: Path, port: int) -> list[str]:
        package_json = root / "package.json"
        if not package_json.exists():
            raise RuntimeError("匹配到的前端项目没有 package.json，无法启动真实项目预览")
        package = json.loads(package_json.read_text(encoding="utf-8"))
        scripts = package.get("scripts") or {}
        if "serve" in scripts:
            script = "serve"
        elif "dev" in scripts:
            script = "dev"
        elif "start" in scripts:
            script = "start"
        elif "preview" in scripts:
            script = "preview"
        else:
            raise RuntimeError("前端项目没有 dev/serve/start/preview 启动脚本")

        script_command = str(scripts.get(script, ""))
        args = ["npm", "run", script, "--", "--host", settings.pipeline_preview_host, "--port", str(port)]
        if (root / "vite.config.js").exists() or "vite" in script_command:
            args.extend(["--strictPort", "--base", f"/api/flow/pipeline/{root.parent.name}/sandbox-preview/"])
        return args

    def _preview_base(self, pipeline_id: str) -> str:
        return f"/api/flow/pipeline/{pipeline_id}/sandbox-preview/"

    def _patch_vue_cli_preview_base(self, root: Path) -> None:
        vue_config = root / "vue.config.js"
        if not vue_config.exists():
            return

        marker = "SANDBOX_PREVIEW_PUBLIC_PATH_PATCH_V4"
        content = vue_config.read_text(encoding="utf-8")
        if marker in content:
            return

        vue_config.write_text(
            content.rstrip()
            + "\n\n"
            + "// SANDBOX_PREVIEW_PUBLIC_PATH_PATCH_V4\n"
            + "if (process.env.VUE_APP_SANDBOX_PREVIEW_BASE) {\n"
            + "  vueConfig.publicPath = process.env.VUE_APP_SANDBOX_PREVIEW_BASE\n"
            + "  vueConfig.configureWebpack = vueConfig.configureWebpack || {}\n"
            + "  vueConfig.configureWebpack.output = vueConfig.configureWebpack.output || {}\n"
            + "  vueConfig.configureWebpack.output.publicPath = process.env.VUE_APP_SANDBOX_PREVIEW_BASE\n"
            + "  vueConfig.devServer = vueConfig.devServer || {}\n"
            + "  vueConfig.devServer.public = process.env.VUE_APP_SANDBOX_PREVIEW_PUBLIC || 'localhost'\n"
            + "  vueConfig.devServer.sockPath = process.env.VUE_APP_SANDBOX_PREVIEW_BASE + 'sockjs-node'\n"
            + "  if (vueConfig.devServer.proxy) {\n"
            + "    delete vueConfig.devServer.proxy['sockjs-node']\n"
            + "    delete vueConfig.devServer.proxy['/sockjs-node']\n"
            + "    if (vueConfig.devServer.proxy['/api']) {\n"
            + "      delete vueConfig.devServer.proxy['/api'].pathRewrite\n"
            + "    }\n"
            + "  }\n"
            + "  vueConfig.devServer.disableHostCheck = true\n"
            + "  vueConfig.devServer.historyApiFallback = vueConfig.devServer.historyApiFallback || { disableDotRule: true }\n"
            + "  vueConfig.devServer.hot = false\n"
            + "  vueConfig.devServer.liveReload = false\n"
            + "  vueConfig.devServer.inline = false\n"
            + "  vueConfig.devServer.clientLogLevel = 'silent'\n"
            + "  if (process.env.VUE_APP_SANDBOX_PREVIEW_SOCK_HOST) {\n"
            + "    vueConfig.devServer.sockHost = process.env.VUE_APP_SANDBOX_PREVIEW_SOCK_HOST\n"
            + "  }\n"
            + "  if (process.env.VUE_APP_SANDBOX_PREVIEW_SOCK_PORT) {\n"
            + "    vueConfig.devServer.sockPort = process.env.VUE_APP_SANDBOX_PREVIEW_SOCK_PORT\n"
            + "  }\n"
            + "}\n",
            encoding="utf-8",
        )

    def _patch_vue_cli_service_no_hmr(self, root: Path) -> None:
        serve_js = root / "node_modules" / "@vue" / "cli-service" / "lib" / "commands" / "serve.js"
        if not serve_js.exists():
            return

        marker = "SANDBOX_PREVIEW_DISABLE_WDS_CLIENT_PATCH"
        content = serve_js.read_text(encoding="utf-8")
        if marker in content:
            return

        patched = content.replace(
            "// inject dev & hot-reload middleware entries\n    if (!isProduction) {",
            "// SANDBOX_PREVIEW_DISABLE_WDS_CLIENT_PATCH\n"
            "    // inject dev & hot-reload middleware entries\n"
            "    if (!isProduction && !process.env.VUE_APP_SANDBOX_PREVIEW_DISABLE_WDS_CLIENT) {",
            1,
        )
        if patched == content:
            logger.warning("Failed to patch Vue CLI dev client injection in %s", serve_js)
            return
        serve_js.write_text(patched, encoding="utf-8")

    def _api_base_url_for_preview(self, root: Path, project_env: Dict[str, str], pipeline_id: str) -> str:
        configured = project_env.get("VUE_APP_API_BASE_URL") or ""
        if configured.rstrip("/") != "/api":
            return configured

        api_dir = root / "src" / "api"
        if not api_dir.exists():
            return configured
        for api_file in api_dir.rglob("*.js"):
            try:
                content = api_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"['\"]\/api\/", content):
                return self._preview_base(pipeline_id).rstrip("/")
        return configured

    def _preview_proxy_targets(self, project_env: Dict[str, str]) -> Dict[str, str]:
        test_proxy = (settings.pipeline_preview_api_proxy or project_env.get("VUE_APP_PROXY") or "").rstrip("/")
        if not test_proxy:
            raise RuntimeError("前端项目缺少 VUE_APP_PROXY，且系统未配置 PIPELINE_PREVIEW_API_PROXY，无法确定真实 API 测试域名")
        return {
            "api": test_proxy,
            "java": project_env.get("VUE_APP_JAVA_PROXY") or test_proxy,
            "log": project_env.get("VUE_APP_PROXY_LOG") or test_proxy,
        }

    async def start(self, pipeline_id: str, frontend_files: Dict[str, str], project_info: Dict[str, Any]) -> Dict[str, Any]:
        if not frontend_files:
            raise RuntimeError("当前流水线还没有生成前端代码，无法启动真实预览")
        if not shutil.which("npm"):
            raise RuntimeError("admin-python 容器未安装 npm，无法启动真实前端预览")
        if not shutil.which("git"):
            raise RuntimeError("admin-python 容器未安装 git，无法克隆真实前端项目")

        pipeline_lock = await self._pipeline_lock(pipeline_id)
        async with pipeline_lock:
            files_hash = self._files_hash(frontend_files)
            existing = self._processes.get(pipeline_id)
            if existing and existing["process"].returncode is None:
                if existing.get("ready") and existing.get("files_hash") == files_hash:
                    self._issue_token(existing)
                    return self._response(pipeline_id, existing)
                existing["process"].terminate()
                try:
                    await asyncio.wait_for(existing["process"].wait(), timeout=5)
                except asyncio.TimeoutError:
                    existing["process"].kill()
                    await existing["process"].wait()
                output_task = existing.get("output_task")
                if output_task:
                    output_task.cancel()
                async with self._process_lock:
                    if self._processes.get(pipeline_id) is existing:
                        self._processes.pop(pipeline_id, None)

            port: Optional[int] = None
            async with self._start_semaphore:
                root = self._preview_root(pipeline_id)
                try:
                    await self._prepare_project_root(root, project_info)
                    self._safe_write_files(root, frontend_files)
                    html_preview_path = self._install_miniapp_html_preview(root, frontend_files)
                    self._patch_vue_cli_preview_base(root)

                    port = await self._allocate_port()
                    node_version = await self._node_version()
                    node_marker = root / ".preview-node-version"
                    if (root / "node_modules").exists() and (
                        not node_marker.exists() or node_marker.read_text(encoding="utf-8").strip() != node_version
                    ):
                        shutil.rmtree(root / "node_modules", ignore_errors=True)
                    if not (root / "node_modules").exists():
                        install_cmd = [
                            "npm",
                            "install",
                            "--registry=https://registry.npmmirror.com",
                            "--no-audit",
                            "--no-fund",
                            "--legacy-peer-deps",
                            "--progress=false",
                            "--cache",
                            str(Path(settings.pipeline_workspace_root) / ".npm-cache"),
                        ]
                        code, output = await self._run(install_cmd, root, timeout=1200)
                        if code != 0:
                            raise RuntimeError(f"npm install 失败: {output[-500:]}")
                        node_marker.write_text(node_version, encoding="utf-8")

                    self._patch_vue_cli_service_no_hmr(root)
                    dev_cmd = self._dev_command(root, port)
                    env = os.environ.copy()
                    project_env = self._load_env_file(root, ".env.development")
                    proxy_targets = self._preview_proxy_targets(project_env)
                    api_base_url = self._api_base_url_for_preview(root, project_env, pipeline_id)
                    env.update({
                        "VUE_APP_PROXY": proxy_targets["api"],
                        "VUE_APP_JAVA_PROXY": proxy_targets["java"],
                        "VUE_APP_PROXY_LOG": proxy_targets["log"],
                        "VUE_APP_API_BASE_URL": api_base_url,
                        "VUE_APP_SANDBOX_PREVIEW_BASE": self._preview_base(pipeline_id),
                        "VUE_APP_SANDBOX_PREVIEW_PUBLIC": env.get("VUE_APP_SANDBOX_PREVIEW_PUBLIC") or "localhost",
                        "VUE_APP_SANDBOX_PREVIEW_DISABLE_WDS_CLIENT": "1",
                    })
                    process = await asyncio.create_subprocess_exec(
                        *dev_cmd,
                        cwd=str(root),
                        env=env,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    entry = {
                        "process": process,
                        "port": port,
                        "root": str(root),
                        "ready": False,
                        "files_hash": files_hash,
                        "tokens": {},
                        "html_preview_path": html_preview_path or "",
                        "project_info": project_info,
                        "proxy_targets": proxy_targets,
                    }
                    self._issue_token(entry)
                    entry["output_task"] = asyncio.create_task(self._drain_process_output(pipeline_id, process))
                    async with self._process_lock:
                        self._processes[pipeline_id] = entry
                        self._reserved_ports.discard(port)
                except Exception:
                    if port is not None:
                        async with self._process_lock:
                            self._reserved_ports.discard(port)
                    raise

            try:
                await self._wait_ready(pipeline_id, port, preview_path=entry.get("html_preview_path") or "")
            except Exception:
                if entry["process"].returncode is None:
                    entry["process"].terminate()
                async with self._process_lock:
                    if self._processes.get(pipeline_id) is entry:
                        self._processes.pop(pipeline_id, None)
                raise
            entry["ready"] = True
            return self._response(pipeline_id, entry)

    def _response(self, pipeline_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        project_info = entry.get("project_info") or {}
        marker_info: Dict[str, Any] = {}
        marker = Path(str(entry.get("root") or "")) / ".sandbox-preview-project.json"
        if marker.exists():
            try:
                marker_info = json.loads(marker.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                marker_info = {}
        return {
            "pipeline_id": pipeline_id,
            "status": "running",
            "port": entry["port"],
            "root": entry["root"],
            "preview_url": self._preview_base(pipeline_id),
            "preview_token": entry["token"],
            "started_at": entry["started_at"],
            "project": {
                "project_id": project_info.get("project_id") or marker_info.get("project_id") or "",
                "project_name": project_info.get("project_name") or marker_info.get("project_name") or "",
                "repo_url": project_info.get("repo_url") or marker_info.get("repo_url") or "",
                "branch": project_info.get("branch") or project_info.get("git_branch") or marker_info.get("branch") or "",
            },
            "proxy_targets": entry.get("proxy_targets") or {},
        }

    def validate_token(self, pipeline_id: str, token: str) -> bool:
        entry = self._processes.get(pipeline_id)
        if not entry or not token:
            return False
        self._prune_tokens(entry)
        return any(secrets.compare_digest(issued, token) for issued in entry.get("tokens", {}))

    def is_running(self, pipeline_id: str) -> bool:
        entry = self._processes.get(pipeline_id)
        return bool(entry and entry["process"].returncode is None)

    async def proxy(
        self,
        pipeline_id: str,
        path: str,
        query_string: str,
        request_headers: Dict[str, str],
        method: str = "GET",
        body: bytes = b"",
    ) -> httpx.Response:
        entry = self._processes.get(pipeline_id)
        if not entry or entry["process"].returncode is not None:
            raise RuntimeError("真实预览服务未启动")
        if path.startswith("sockjs-node/"):
            target = f"http://{settings.pipeline_preview_host}:{entry['port']}{self._preview_base(pipeline_id)}{path}"
        elif path.startswith("__webpack_dev_server__/"):
            target = f"http://{settings.pipeline_preview_host}:{entry['port']}/{path}"
        elif path.startswith(("api/", "javaApi/", "logApi/", "socket.io/")):
            target = f"http://{settings.pipeline_preview_host}:{entry['port']}/{path}"
        else:
            preview_path = entry.get("html_preview_path") if not path else ""
            target = f"http://{settings.pipeline_preview_host}:{entry['port']}{self._preview_base(pipeline_id)}{path or preview_path or ''}"
        if query_string:
            target = f"{target}?{query_string}"
        headers = {k: v for k, v in request_headers.items() if k.lower() not in {"host", "connection", "content-length"}}
        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
            response = await client.request(method, target, headers=headers, content=body)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            prefix = f"/api/flow/pipeline/{pipeline_id}/sandbox-preview/"
            text_body = response.text
            text_body = text_body.replace('src="/', f'src="{prefix}')
            text_body = text_body.replace("src='/", f"src='{prefix}")
            text_body = text_body.replace('href="/', f'href="{prefix}')
            text_body = text_body.replace("href='/", f"href='{prefix}")
            text_body = text_body.replace(prefix + prefix.lstrip("/"), prefix)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=text_body.encode("utf-8"),
            )
        return response


sandbox_preview_service = SandboxPreviewService()
