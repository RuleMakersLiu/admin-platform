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
        if "JDictSelectTag" not in content:
            return content
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
        patched = content
        for source, target in replacements.items():
            patched = patched.replace(source, target)
        return patched

    def _files_hash(self, frontend_files: Dict[str, str]) -> str:
        payload = json.dumps(frontend_files, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _route_segment(self, component_path: str) -> str:
        stem = Path(component_path).stem
        words = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", stem).replace("_", "-")
        return re.sub(r"[^a-zA-Z0-9-]+", "-", words).strip("-").lower() or "page"

    def _page_title(self, component_path: str, content: str) -> str:
        if "getFlashSaleList" in content or "flash_sale" in content or "秒杀" in content:
            return "秒杀活动"
        if "getGroupBuyingRecordList" in content or "group_record" in content or "拼团详情" in content:
            return "拼团记录"
        if "getGroupBuyingList" in content or "group_buying_status" in content or "新增拼团" in content:
            return "拼团活动"
        explicit_title = re.search(r"meta\s*:\s*\{[^}]*title\s*:\s*['\"]([^'\"]*[\u4e00-\u9fff][^'\"]*)['\"]", content)
        if explicit_title:
            return explicit_title.group(1)

        name_match = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", content)
        name = name_match.group(1) if name_match else Path(component_path).stem
        return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).strip()

    def _generated_vue_views(self, frontend_files: Dict[str, str]) -> list[Dict[str, str]]:
        views: list[Dict[str, str]] = []
        used_routes: set[str] = set()
        for raw_path, content in sorted(frontend_files.items()):
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            if not safe_path.startswith("src/views/") or not safe_path.endswith(".vue"):
                continue
            component_path = safe_path[len("src/views/"):-len(".vue")]
            route = self._route_segment(component_path)
            base_route = route
            index = 2
            while route in used_routes:
                route = f"{base_route}-{index}"
                index += 1
            used_routes.add(route)
            views.append({
                "component_path": component_path,
                "route": route,
                "name": re.sub(r"[^a-zA-Z0-9_]", "", Path(component_path).stem) or "SandboxPage",
                "title": self._page_title(component_path, content if isinstance(content, str) else ""),
            })
        return views

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

    def _generated_list_api_paths(self, frontend_files: Dict[str, str]) -> list[str]:
        return [
            spec["path"]
            for spec in self._generated_api_probe_specs(frontend_files)
            if spec.get("expects_list")
        ]

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

    async def _prepare_project_root(self, root: Path, project_info: Dict[str, Any]) -> None:
        if root.exists() and (root / ".git").exists() and (root / "package.json").exists():
            code, output = await self._run(["git", "reset", "--hard", "HEAD"], root, timeout=60)
            if code != 0:
                raise RuntimeError(f"重置前端项目失败: {output[-500:]}")
            code, output = await self._run(["git", "clean", "-fd", "-e", "node_modules"], root, timeout=60)
            if code != 0:
                raise RuntimeError(f"清理前端项目失败: {output[-500:]}")
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

        args = ["npm", "run", script, "--", "--host", settings.pipeline_preview_host, "--port", str(port)]
        if (root / "vite.config.js").exists() or "vite" in str(scripts.get(script, "")):
            args.extend(["--strictPort", "--base", f"/api/flow/pipeline/{root.parent.name}/sandbox-preview/"])
        return args

    def _preview_base(self, pipeline_id: str) -> str:
        return f"/api/flow/pipeline/{pipeline_id}/sandbox-preview/"

    def _patch_vue_cli_preview_base(self, root: Path) -> None:
        vue_config = root / "vue.config.js"
        if not vue_config.exists():
            return

        marker = "SANDBOX_PREVIEW_PUBLIC_PATH_PATCH"
        content = vue_config.read_text(encoding="utf-8")
        if marker in content:
            return

        vue_config.write_text(
            content.rstrip()
            + "\n\n"
            + "// SANDBOX_PREVIEW_PUBLIC_PATH_PATCH\n"
            + "if (process.env.VUE_APP_SANDBOX_PREVIEW_BASE) {\n"
            + "  vueConfig.publicPath = process.env.VUE_APP_SANDBOX_PREVIEW_BASE\n"
            + "  vueConfig.configureWebpack = vueConfig.configureWebpack || {}\n"
            + "  vueConfig.configureWebpack.output = vueConfig.configureWebpack.output || {}\n"
            + "  vueConfig.configureWebpack.output.publicPath = process.env.VUE_APP_SANDBOX_PREVIEW_BASE\n"
            + "  vueConfig.devServer = vueConfig.devServer || {}\n"
            + "  vueConfig.devServer.public = process.env.VUE_APP_SANDBOX_PREVIEW_PUBLIC || 'localhost'\n"
            + "  vueConfig.devServer.sockPath = process.env.VUE_APP_SANDBOX_PREVIEW_BASE + 'sockjs-node'\n"
            + "  vueConfig.devServer.disableHostCheck = true\n"
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

    def _patch_vue2_sandbox_preview_entry(self, root: Path, frontend_files: Dict[str, str]) -> None:
        pages = self._generated_vue_views(frontend_files)
        router_config = root / "src" / "config" / "router.config.js"
        permission_file = root / "src" / "permission.js"
        if not pages or not router_config.exists() or not permission_file.exists():
            return

        layout_dir = root / "src" / "views" / "SandboxPreview"
        layout_dir.mkdir(parents=True, exist_ok=True)
        layout_dir.joinpath("SandboxPreviewLayout.vue").write_text(
            "<template>\n"
            "  <a-layout class=\"sandbox-preview-layout\">\n"
            "    <a-layout-sider width=\"220\" theme=\"light\" class=\"sandbox-preview-sider\">\n"
            "      <div class=\"sandbox-preview-title\">生成页面</div>\n"
            "      <a-menu mode=\"inline\" :selectedKeys=\"[selectedKey]\">\n"
            "        <a-menu-item v-for=\"item in pages\" :key=\"item.path\" @click=\"go(item.path)\">\n"
            "          {{ item.title }}\n"
            "        </a-menu-item>\n"
            "      </a-menu>\n"
            "    </a-layout-sider>\n"
            "    <a-layout-content class=\"sandbox-preview-content\">\n"
            "      <router-view />\n"
            "    </a-layout-content>\n"
            "  </a-layout>\n"
            "</template>\n"
            "<script>\n"
            f"const pages = {json.dumps([{'title': page['title'], 'path': '/sandbox-generated-preview/' + page['route']} for page in pages], ensure_ascii=False)}\n"
            "export default {\n"
            "  name: 'SandboxPreviewLayout',\n"
            "  data () { return { pages } },\n"
            "  computed: {\n"
            "    selectedKey () {\n"
            "      const active = this.pages.find(item => this.$route.path === item.path)\n"
            "      return active ? active.path : this.pages[0].path\n"
            "    }\n"
            "  },\n"
            "  methods: {\n"
            "    go (path) { if (this.$route.path !== path) this.$router.push(path) }\n"
            "  }\n"
            "}\n"
            "</script>\n"
            "<style scoped>\n"
            ".sandbox-preview-layout { min-height: 100vh; background: #f0f2f5; }\n"
            ".sandbox-preview-sider { border-right: 1px solid #e8e8e8; }\n"
            ".sandbox-preview-title { height: 48px; line-height: 48px; padding: 0 16px; font-weight: 600; color: #1f2329; }\n"
            ".sandbox-preview-content { padding: 16px; overflow: auto; }\n"
            "</style>\n",
            encoding="utf-8",
        )

        route_marker = "SANDBOX_PREVIEW_ROUTE_PATCH"
        router_content = router_config.read_text(encoding="utf-8")
        if route_marker not in router_content:
            children = []
            for page in pages:
                children.append(
                    "      {\n"
                    f"        path: '{page['route']}',\n"
                    f"        name: 'SandboxGenerated{page['name']}',\n"
                    f"        component: () => import(/* webpackChunkName: \"sandbox-preview\" */ '@/views/{page['component_path']}'),\n"
                    f"        meta: {{ title: {json.dumps(page['title'], ensure_ascii=False)}, keepAlive: false }}\n"
                    "      }"
                )
            route_block = (
                "  // SANDBOX_PREVIEW_ROUTE_PATCH\n"
                "  {\n"
                "    path: '/sandbox-generated-preview',\n"
                "    name: 'SandboxGeneratedPreview',\n"
                "    component: () => import(/* webpackChunkName: \"sandbox-preview\" */ '@/views/SandboxPreview/SandboxPreviewLayout'),\n"
                f"    redirect: '/sandbox-generated-preview/{pages[0]['route']}',\n"
                "    meta: { title: '预览页面', keepAlive: false },\n"
                "    children: [\n"
                + ",\n".join(children)
                + "\n"
                "    ]\n"
                "  },\n"
            )
            anchor = "export const constantRouterMap = ["
            if anchor in router_content:
                router_content = router_content.replace(anchor, anchor + "\n" + route_block, 1)
                router_config.write_text(router_content, encoding="utf-8")

        permission_marker = "SANDBOX_PREVIEW_AUTH_PATCH"
        permission_content = permission_file.read_text(encoding="utf-8")
        if permission_marker in permission_content:
            return

        guard_anchor = "router.beforeEach(async (to, from, next) => {"
        guard_patch = (
            "router.beforeEach(async (to, from, next) => {\n"
            "  // SANDBOX_PREVIEW_AUTH_PATCH\n"
            "  if (process.env.VUE_APP_SANDBOX_PREVIEW_BASE) {\n"
            "    if (to.path === '/' || to.path === '/user/login') {\n"
            "      next({ path: '/sandbox-generated-preview', replace: true })\n"
            "      return\n"
            "    }\n"
            "    if (to.path === '/sandbox-generated-preview' || to.path.indexOf('/sandbox-generated-preview/') === 0) {\n"
            "      next()\n"
            "      return\n"
            "    }\n"
            "  }\n"
        )
        if guard_anchor in permission_content:
            permission_content = permission_content.replace(guard_anchor, guard_patch, 1)
            permission_file.write_text(permission_content, encoding="utf-8")

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
                    self._patch_vue2_sandbox_preview_entry(root, frontend_files)

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

                    dev_cmd = self._dev_command(root, port)
                    env = os.environ.copy()
                    project_env = self._load_env_file(root, ".env.development")
                    test_proxy = (
                        env.get("VUE_APP_SANDBOX_TEST_PROXY")
                        or project_env.get("VUE_APP_PROXY")
                        or project_env.get("VUE_APP_SOCKET_HOST")
                        or "http://dzg-dev_wma.gemantic.com"
                    )
                    java_proxy = env.get("VUE_APP_SANDBOX_TEST_JAVA_PROXY") or project_env.get("VUE_APP_JAVA_PROXY") or test_proxy
                    log_proxy = env.get("VUE_APP_SANDBOX_TEST_LOG_PROXY") or project_env.get("VUE_APP_PROXY_LOG") or test_proxy
                    env.update({
                        "VUE_APP_PROXY": test_proxy,
                        "VUE_APP_JAVA_PROXY": java_proxy,
                        "VUE_APP_PROXY_LOG": log_proxy,
                        "VUE_APP_API_BASE_URL": self._preview_base(pipeline_id).rstrip("/") + "/api",
                        "VUE_APP_SANDBOX_PREVIEW_BASE": self._preview_base(pipeline_id),
                        "VUE_APP_SANDBOX_PREVIEW_PUBLIC": env.get("VUE_APP_SANDBOX_PREVIEW_PUBLIC") or "localhost",
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
                await self._smoke_test_generated_apis(pipeline_id, frontend_files)
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
        return {
            "pipeline_id": pipeline_id,
            "status": "running",
            "port": entry["port"],
            "root": entry["root"],
            "preview_url": self._preview_base(pipeline_id),
            "preview_token": entry["token"],
            "started_at": entry["started_at"],
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

    def _mock_marketing_response(self, path: str, query_string: str) -> Optional[httpx.Response]:
        if not path.startswith("api/marketing/"):
            return None

        params = dict(item.split("=", 1) for item in query_string.split("&") if "=" in item)
        page = int(params.get("p") or params.get("pageNo") or params.get("page") or 1)
        page_size = int(params.get("pageSize") or params.get("page_size") or 10)

        if path == "api/marketing/flash-sale/list":
            items = [
                {
                    "id": 10001,
                    "activityName": "夏季会员秒杀",
                    "status": 1,
                    "timeRange": "2026-05-28 10:00 - 2026-05-31 22:00",
                    "skuCount": 12,
                    "stockInfo": "326/1000",
                    "creatorName": "运营部",
                },
                {
                    "id": 10002,
                    "activityName": "周末限时特惠",
                    "status": 0,
                    "timeRange": "2026-06-01 09:00 - 2026-06-03 23:00",
                    "skuCount": 8,
                    "stockInfo": "0/600",
                    "creatorName": "市场部",
                },
            ]
        elif path == "api/marketing/group-buying/list":
            items = [
                {
                    "id": 20001,
                    "activityName": "亲子酒店拼团",
                    "status": 1,
                    "timeRange": "2026-05-28 08:00 - 2026-06-05 23:59",
                    "groupSize": 3,
                    "groupInfo": "42/31",
                    "creatorName": "增长运营",
                },
                {
                    "id": 20002,
                    "activityName": "端午套餐拼团",
                    "status": 0,
                    "timeRange": "2026-06-02 08:00 - 2026-06-10 23:59",
                    "groupSize": 5,
                    "groupInfo": "0/0",
                    "creatorName": "市场部",
                },
            ]
        elif path == "api/marketing/group-buying/record/list":
            items = [
                {
                    "id": 30001,
                    "activityName": "亲子酒店拼团",
                    "leaderName": "张女士",
                    "groupProgress": "3/3",
                    "status": 1,
                    "createTime": "2026-05-28 09:32:18",
                },
                {
                    "id": 30002,
                    "activityName": "亲子酒店拼团",
                    "leaderName": "李先生",
                    "groupProgress": "2/3",
                    "status": 0,
                    "createTime": "2026-05-28 10:11:06",
                },
            ]
        elif path.startswith("api/marketing/group-buying/record/detail/"):
            items = []
            payload = {
                "activityName": "亲子酒店拼团",
                "leaderName": "张女士",
                "groupSize": 3,
                "currentSize": 3,
                "status": 1,
                "createTime": "2026-05-28 09:32:18",
                "endTime": "2026-05-28 12:20:03",
                "members": [
                    {"userId": 1, "nickName": "张女士", "joinTime": "2026-05-28 09:32:18", "statusText": "已参团"},
                    {"userId": 2, "nickName": "王同学", "joinTime": "2026-05-28 10:01:44", "statusText": "已参团"},
                    {"userId": 3, "nickName": "陈先生", "joinTime": "2026-05-28 12:20:03", "statusText": "已参团"},
                ],
            }
            body = {"code": 200, "message": "sandbox mock", "data": payload}
            return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(body, ensure_ascii=False).encode("utf-8"))
        else:
            return None

        payload = {
            "page": page,
            "pageNo": page,
            "pageSize": page_size,
            "count": len(items),
            "totalCount": len(items),
            "list": items,
        }
        body = {"code": 200, "message": "sandbox mock", "data": payload}
        return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def _table_payload(self, value: Any, fallback: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        fallback = fallback or {}
        if isinstance(value, list):
            items = value
            source = fallback
        elif isinstance(value, dict):
            if isinstance(value.get("list"), list):
                items = value["list"]
            elif isinstance(value.get("data"), list):
                items = value["data"]
            elif isinstance(value.get("records"), list):
                items = value["records"]
            elif isinstance(value.get("rows"), list):
                items = value["rows"]
            else:
                return None
            source = {**fallback, **value}
        else:
            return None

        page = source.get("page") or source.get("pageNo") or source.get("current") or source.get("currentPage") or 1
        page_size = source.get("pageSize") or source.get("page_size") or source.get("size") or len(items)
        total_count = (
            source.get("count")
            if source.get("count") is not None
            else source.get("totalCount")
            if source.get("totalCount") is not None
            else source.get("total")
            if source.get("total") is not None
            else len(items)
        )
        return {
            **source,
            "data": items,
            "list": items,
            "page": page,
            "pageNo": source.get("pageNo") or page,
            "pageSize": page_size,
            "count": total_count,
            "totalCount": source.get("totalCount") if source.get("totalCount") is not None else total_count,
        }

    def _normalize_api_response(self, path: str, response: httpx.Response) -> httpx.Response:
        if not path.startswith("api/"):
            return response
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type or response.status_code >= 400:
            return response
        try:
            payload = response.json()
        except ValueError:
            return response
        if not isinstance(payload, dict):
            return response

        table_payload = None
        if "result" in payload:
            table_payload = self._table_payload(payload.get("result"), payload)
        if table_payload is None and "data" in payload:
            table_payload = self._table_payload(payload.get("data"), payload)
        if table_payload is None:
            table_payload = self._table_payload(payload)
        if table_payload is None:
            return response

        normalized = dict(payload)
        normalized["result"] = {**table_payload, **(payload.get("result") if isinstance(payload.get("result"), dict) else {})}
        if isinstance(normalized.get("data"), dict):
            normalized["data"] = {**normalized["result"], **normalized["data"]}
        elif isinstance(normalized.get("data"), list):
            normalized["data"] = normalized["result"]

        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        try:
            request = response.request
        except RuntimeError:
            request = None
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
            content=json.dumps(normalized, ensure_ascii=False).encode("utf-8"),
            request=request,
        )

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
        mock_response = self._mock_marketing_response(path, query_string)
        if mock_response is not None:
            return mock_response
        if path.startswith(("api/", "javaApi/", "logApi/", "socket.io/")):
            target = f"http://{settings.pipeline_preview_host}:{entry['port']}/{path}"
        else:
            preview_path = entry.get("html_preview_path") if not path else ""
            target = f"http://{settings.pipeline_preview_host}:{entry['port']}{self._preview_base(pipeline_id)}{path or preview_path or ''}"
        if query_string:
            target = f"{target}?{query_string}"
        headers = {k: v for k, v in request_headers.items() if k.lower() not in {"host", "connection", "content-length"}}
        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
            response = await client.request(method, target, headers=headers, content=body)
        response = self._normalize_api_response(path, response)
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
