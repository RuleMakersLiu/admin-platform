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
from urllib.parse import urlparse

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
        entry["last_active"] = time.time()
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

    def _safe_write_files(self, root: Path, files: Dict[str, str], skip_patches: bool = False) -> None:
        root.mkdir(parents=True, exist_ok=True)
        root_resolved = root.resolve()
        for raw_path, content in files.items():
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            parts = [part for part in safe_path.split("/") if part not in ("", ".", "..")]
            if not parts:
                continue
            target = (root / Path(*parts)).resolve()
            # Use Path.parents membership (not str.startswith) so a sibling dir
            # like /data/pipelines/abcde is not accepted under root /data/pipelines/abc,
            # and resolved symlinks pointing outside root are rejected.
            if target != root_resolved and root_resolved not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            text_content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
            if not skip_patches:
                if safe_path.startswith("src/views/") and safe_path.endswith(".vue"):
                    text_content = self._patch_generated_vue_content(text_content)
                if safe_path.startswith("src/") and safe_path.endswith((".js", ".ts", ".jsx", ".tsx")):
                    text_content = self._patch_generated_script_content(text_content)
            target.write_text(text_content, encoding="utf-8")

    def _patch_generated_script_content(self, content: str) -> str:
        patched = re.sub(r"<!--\s*(.*?)\s*-->", lambda match: f"// {match.group(1).strip()}", content, flags=re.S)
        patched = re.sub(
            r"^\s*import\s+\{\s*http\s*\}\s+from\s+['\"]@hc-agent/http['\"]\s*;?\s*$",
            (
                "const http = {\n"
                "  get: () => Promise.reject(new Error('sandbox preview mock http')),\n"
                "  post: () => Promise.reject(new Error('sandbox preview mock http')),\n"
                "}\n"
            ),
            patched,
            flags=re.M,
        )
        return patched

    def _patch_generated_vue_content(self, content: str) -> str:
        patched = self._patch_stable_contract(content)
        patched = self._patch_invalid_vue_dimension_bindings(patched)
        patched = self._patch_missing_moment_instance(patched)
        patched = self._patch_missing_permission_helper(patched)
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

    def _patch_invalid_vue_dimension_bindings(self, content: str) -> str:
        return re.sub(
            r":(width|height|min-width|min-height|max-width|max-height)=\"(\d+(?:\.\d+)?px)\"",
            lambda match: f'{match.group(1)}="{match.group(2)}"',
            content,
        )

    def _patch_missing_moment_instance(self, content: str) -> str:
        if "this.$moment" not in content:
            return content
        patched = content.replace("this.$moment", "moment")
        if re.search(r"import\s+moment\s+from\s+['\"]moment['\"]", patched):
            return patched
        script_match = re.search(r"<script[^>]*>", patched)
        if not script_match:
            return patched
        insert_at = script_match.end()
        return patched[:insert_at] + "\nimport moment from 'moment'\n" + patched[insert_at:]

    def _patch_missing_permission_helper(self, content: str) -> str:
        if "hasPermission(" not in content or re.search(r"\b(?:const|function)\s+hasPermission\b", content):
            return content
        script_match = re.search(r"<script\s+setup[^>]*>", content)
        if not script_match:
            return content
        insert_at = script_match.end()
        return content[:insert_at] + "\nconst hasPermission = () => true\n" + content[insert_at:]

    def _patch_stable_contract(self, content: str) -> str:
        from app.ai.flow_manager import _patch_stable_table_contract_content

        return _patch_stable_table_contract_content(content)

    def _generated_vue_route_specs(self, frontend_files: Dict[str, str]) -> list[Dict[str, str]]:
        specs: list[Dict[str, str]] = []

        for raw_path in sorted(frontend_files):
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            if not safe_path.startswith("src/views/") or not safe_path.endswith(".vue"):
                continue
            component_path = safe_path.removeprefix("src/views/").removesuffix(".vue")
            component_name = Path(component_path).name
            tokens = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", component_name)
            route_path = "/" + "/".join(token.lower() for token in tokens if token)
            if route_path == "/":
                route_path = "/" + component_path.replace("\\", "/").replace("_", "-").lower()
            specs.append({
                "path": route_path,
                "name": component_name,
                "componentPath": component_path,
                "title": component_name,
                "isNav": 1 if component_name.lower().endswith("list") else 0,
            })

        def route_rank(spec: Dict[str, str]) -> tuple[int, int, str]:
            name = spec.get("name", "").lower()
            path = spec.get("path", "")
            is_secondary_list = 1 if any(word in name for word in ("team", "record", "log")) else 0
            is_list = 0 if name.endswith("list") else 1
            return (is_list, is_secondary_list, len(path), path)

        return sorted(specs, key=route_rank)

    def _install_generated_vue_routes(self, root: Path, frontend_files: Dict[str, str]) -> str:
        specs = self._generated_vue_route_specs(frontend_files)
        if not specs:
            return ""

        self._install_generated_static_routes(root, specs)
        self._patch_preview_permission_whitelist(root, specs)

        router_file = root / "src" / "router" / "generator-routers.js"
        if not router_file.exists():
            return specs[0]["path"]

        marker = "SANDBOX_PREVIEW_GENERATED_ROUTES_PATCH_V1"
        content = router_file.read_text(encoding="utf-8")
        if marker in content:
            return specs[0]["path"]

        route_items = []
        for index, spec in enumerate(specs, start=1):
            route_items.append({
                "id": 900000 + index,
                "fid": 900000,
                "type": 1,
                "isNav": spec["isNav"],
                "name": spec["path"],
                "path": spec["path"],
                "link": spec["path"],
                "componentPath": spec["componentPath"],
                "title": spec["title"],
                "key": spec["name"],
                "meta": {
                    "title": spec["title"],
                    "show": spec["isNav"] == 1,
                },
            })

        sandbox_routes = [{
            "id": 900000,
            "fid": 0,
            "type": 1,
            "isNav": 1,
            "name": "sandbox-generated-preview",
            "path": "/sandbox-generated-preview",
            "component": "RouteView",
            "componentPath": "RouteView",
            "title": "生成预览",
            "redirect": specs[0]["path"],
            "meta": {
                "title": "生成预览",
                "icon": "experiment",
                "redirectPath": specs[0]["path"],
            },
            "son": route_items,
        }]

        declaration = (
            f"\n// {marker}\n"
            f"const sandboxPreviewGeneratedRoutes = {json.dumps(sandbox_routes, ensure_ascii=False, indent=2)}\n"
        )
        root_marker = "const rootRouter = {"
        insert_at = content.find(root_marker)
        if insert_at == -1:
            return specs[0]["path"]
        dynamic_marker = "/**\n * 动态生成菜单"
        dynamic_at = content.find(dynamic_marker, insert_at)
        if dynamic_at == -1:
            return specs[0]["path"]
        content = content[:dynamic_at] + declaration + "\n" + content[dynamic_at:]

        old = "      // rootRouter.children = childrenNav\n      rootRouter.children = rootRouter.children.concat(childrenNav)\n"
        new = (
            "      // rootRouter.children = childrenNav\n"
            "      if (sandboxPreviewGeneratedRoutes.length) {\n"
            "        rootRouter.redirect = sandboxPreviewGeneratedRoutes[0].redirect || sandboxPreviewGeneratedRoutes[0].path\n"
            "        childrenNav.unshift(...sandboxPreviewGeneratedRoutes)\n"
            "      }\n"
            "      rootRouter.children = rootRouter.children.concat(childrenNav)\n"
        )
        if old not in content:
            return specs[0]["path"]
        router_file.write_text(content.replace(old, new, 1), encoding="utf-8")
        return specs[0]["path"]

    def _install_generated_static_routes(self, root: Path, specs: list[Dict[str, str]]) -> None:
        router_config = root / "src" / "config" / "router.config.js"
        if not router_config.exists() or not specs:
            return
        marker = "SANDBOX_PREVIEW_STATIC_ROUTES_PATCH_V1"
        content = router_config.read_text(encoding="utf-8")
        if marker in content:
            return

        routes_source = ",\n".join(
            "  {\n"
            f"    path: {json.dumps(spec['path'])},\n"
            f"    name: {json.dumps(spec['name'])},\n"
            f"    component: () => import('@/views/{spec['componentPath']}.vue'),\n"
            f"    meta: {{ title: {json.dumps(spec['title'])}, keepAlive: false }}\n"
            "  }"
            for spec in specs
        )
        declaration = (
            f"// {marker}\n"
            "const sandboxPreviewGeneratedRoutes = [\n"
            f"{routes_source}\n"
            "]\n\n"
        )
        export_marker = "export const constantRouterMap = ["
        if export_marker not in content:
            return
        content = content.replace(export_marker, declaration + export_marker + "\n  ...sandboxPreviewGeneratedRoutes,", 1)
        router_config.write_text(content, encoding="utf-8")

    def _patch_preview_permission_whitelist(self, root: Path, specs: list[Dict[str, str]]) -> None:
        permission_file = root / "src" / "permission.js"
        if not permission_file.exists() or not specs:
            return
        marker = "SANDBOX_PREVIEW_WHITELIST_PATCH_V1"
        content = permission_file.read_text(encoding="utf-8")
        if marker in content:
            return
        names = [spec["name"] for spec in specs]
        names_source = ", ".join(json.dumps(name) for name in names)
        content = content.replace(
            "const whiteList = [",
            f"// {marker}\nconst whiteList = [{names_source}, ",
            1,
        )
        permission_file.write_text(content, encoding="utf-8")

    def _files_hash(self, frontend_files: Dict[str, str]) -> str:
        payload = json.dumps(frontend_files, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _miniapp_html_preview_content(self, frontend_files: Dict[str, str]) -> Optional[str]:
        normalized_paths = [str(path).replace("\\", "/").lstrip("/") for path in frontend_files]
        has_miniapp_page = any(
            (
                path.startswith("pages/")
                or path.startswith("src/pages/")
                or re.match(r"^apps/[^/]+/pages/", path)
            )
            and path.endswith((".wxml", ".vue"))
            for path in normalized_paths
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

    def _redact_sensitive_output(self, output: str) -> str:
        redacted = re.sub(r"(https?://[^:/@\s]+:)[^@\s]+@", r"\1***@", output or "")
        redacted = re.sub(r"(oauth2:)[^@\s]+@", r"\1***@", redacted)
        return redacted

    def _install_miniapp_html_preview(self, root: Path, frontend_files: Dict[str, str]) -> Optional[str]:
        content = self._miniapp_html_preview_content(frontend_files)
        if not content:
            return None
        public_dir = root / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        preview_name = "sandbox-miniapp-preview.html"
        public_dir.joinpath(preview_name).write_text(content, encoding="utf-8")
        return preview_name

    def _install_uniapp_monorepo_preview_files(self, root: Path, frontend_files: Dict[str, str]) -> str:
        first_page = ""
        pages_by_app: Dict[str, list[str]] = {}

        for raw_path, content in frontend_files.items():
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            match = re.match(r"^apps/([^/]+)/(pages|api)/(.+)$", safe_path)
            if not match:
                continue
            app_name, kind, relative = match.groups()
            app_root = root / "apps" / app_name
            if not (app_root / "src").exists():
                continue
            target = app_root / "src" / kind / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            text_content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
            if target.suffix == ".vue":
                text_content = self._patch_generated_vue_content(text_content)
            elif target.suffix in {".js", ".ts", ".jsx", ".tsx"}:
                text_content = self._patch_generated_script_content(text_content)
            target.write_text(text_content, encoding="utf-8")
            if kind == "pages" and target.suffix == ".vue":
                page_path = f"pages/{Path(relative).with_suffix('').as_posix()}"
                pages_by_app.setdefault(app_name, []).append(page_path)
                first_page = first_page or f"/{page_path}"

        for app_name, page_paths in pages_by_app.items():
            pages_json = root / "apps" / app_name / "src" / "pages.json"
            if not pages_json.exists():
                continue
            try:
                config = json.loads(pages_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            pages = config.setdefault("pages", [])
            if not isinstance(pages, list):
                continue
            existing = {
                str(item.get("path") or "")
                for item in pages
                if isinstance(item, dict)
            }
            new_pages = [
                {
                    "path": page_path,
                    "style": {
                        "navigationBarTitleText": "生成预览",
                        "navigationStyle": "custom",
                    },
                }
                for page_path in sorted(set(page_paths))
                if page_path not in existing
            ]
            if not new_pages:
                continue
            config["pages"] = new_pages + pages
            pages_json.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

        return first_page

    def _prepare_miniapp_html_fallback_root(
        self,
        root: Path,
        frontend_files: Dict[str, str],
        project_info: Dict[str, Any],
        reason: str,
    ) -> Optional[str]:
        content = self._miniapp_html_preview_content(frontend_files)
        if not content:
            return None
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        public_dir = root / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        preview_name = "sandbox-miniapp-preview.html"
        public_dir.joinpath(preview_name).write_text(content, encoding="utf-8")
        (root / "package.json").write_text(
            json.dumps({
                "name": "sandbox-miniapp-html-preview",
                "private": True,
                "scripts": {"start": "node server.js"},
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (root / "server.js").write_text(
            """
const http = require('http')
const fs = require('fs')
const path = require('path')

const args = process.argv.slice(2)
const valueAfter = (name, fallback) => {
  const index = args.indexOf(name)
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback
}
const host = valueAfter('--host', '127.0.0.1')
const port = Number(valueAfter('--port', process.env.PORT || '43000'))
const publicDir = path.join(__dirname, 'public')

const server = http.createServer((req, res) => {
  const requestPath = decodeURIComponent((req.url || '/').split('?')[0])
  const fileName = requestPath.endsWith('.html') ? path.basename(requestPath) : 'sandbox-miniapp-preview.html'
  const filePath = path.join(publicDir, fileName)
  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404, {'content-type': 'text/plain; charset=utf-8'})
      res.end('Not found')
      return
    }
    res.writeHead(200, {'content-type': 'text/html; charset=utf-8'})
    res.end(data)
  })
})

server.listen(port, host, () => {
  console.log(`sandbox miniapp preview ready at http://${host}:${port}/sandbox-miniapp-preview.html`)
})
""".lstrip(),
            encoding="utf-8",
        )
        (root / ".sandbox-preview-project.json").write_text(
            json.dumps({
                "project_id": project_info.get("project_id") or "",
                "project_name": project_info.get("project_name") or "",
                "repo_url": project_info.get("repo_url") or "",
                "fallback": "miniapp_html_preview",
                "fallback_reason": reason[-500:],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
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

    @staticmethod
    def _rel(path: str) -> str:
        return str(path).replace("\\", "/").lstrip("/")

    def _generated_code_is_vue3(self, files: Dict[str, str]) -> bool:
        blob = "\n".join(c for c in files.values() if isinstance(c, str))
        return ("v-model:" in blob) or ("<script setup" in blob) or ("defineComponent" in blob)

    def _looks_like_web_vue(self, files: Dict[str, str]) -> bool:
        """无项目快照时，是否值得脚手架 vite 宿主（web Vue，排除 miniapp/原生小程序）。"""
        if self._miniapp_html_preview_content(files):
            return False
        return any(self._rel(p).endswith(".vue") for p in files)

    def _pick_main_vue_path(self, files: Dict[str, str]) -> Optional[str]:
        """从生成文件选主页面 .vue（优先 src/views/**/index.vue，再任意 views/pages 下 .vue）。"""
        best: Optional[tuple] = None  # (score, rel_path)
        for raw_path in files:
            p = self._rel(raw_path)
            if not p.endswith(".vue"):
                continue
            score = 0
            if "index.vue" in p:
                score += 10
            if "views/" in p or "pages/" in p:
                score += 5
            if best is None or score > best[0]:
                best = (score, p)
        return best[1] if best else None

    # 生成代码常用 npm 依赖的版本映射（脚手架 package.json 用；未命中用 "*" 让 npm 解析）
    NPM_VERSIONS_VUE3 = {
        "vue": "^3.4.38", "vue-router": "^4.4.0", "pinia": "^2.2.0", "vuex": "^4.1.0",
        "ant-design-vue": "^4.2.3", "@ant-design/icons-vue": "^7.0.1",
        "axios": "^1.7.0", "echarts": "^5.5.0", "moment": "^2.30.1", "dayjs": "^1.11.0",
        "lodash-es": "^4.17.21", "qs": "^6.13.0",
    }
    NPM_VERSIONS_VUE2 = {
        "vue": "^2.7.16", "vue-router": "^3.6.5", "vuex": "^3.6.2",
        "ant-design-vue": "^1.7.8", "axios": "^1.7.0", "echarts": "^5.5.0",
        "moment": "^2.30.1", "lodash-es": "^4.17.21", "qs": "^6.13.0",
    }

    def _scan_npm_deps(self, files: Dict[str, str], version_map: Dict[str, str]) -> Dict[str, str]:
        """扫描生成代码的 npm import（非 @/、非相对），按 version_map 补依赖（未命中用 *）。"""
        deps: Dict[str, str] = {}
        for content in files.values():
            if not isinstance(content, str):
                continue
            for m in re.finditer(r"""from\s+['"]([a-zA-Z@][^'"]+)['"]""", content):
                spec = m.group(1)
                if spec.startswith("@/") or spec.startswith(".") or spec.startswith("/"):
                    continue
                name = spec if spec.startswith("@") else spec.split("/")[0]
                if spec.startswith("@") and "/" in spec:
                    name = "/".join(spec.split("/")[:2])
                if name == "vue" or name.startswith("@vitejs"):
                    continue
                deps.setdefault(name, version_map.get(name, "*"))
        return deps

    def _scan_style_preprocessors(self, files: Dict[str, str]) -> Dict[str, str]:
        """扫描 <style lang=...>，返回需要的 CSS 预处理器（less/sass/stylus）及版本。"""
        blob = "\n".join(c for c in files.values() if isinstance(c, str))
        needed: Dict[str, str] = {}
        if re.search(r'<style[^>]*lang\s*=\s*["\']less["\']', blob):
            needed["less"] = "^4.2.0"
        if re.search(r'<style[^>]*lang\s*=\s*["\'](scss|sass)["\']', blob):
            needed["sass"] = "^1.77.0"
        if re.search(r'<style[^>]*lang\s*=\s*["\']stylus["\']', blob):
            needed["stylus"] = "^0.63.0"
        return needed

    def _ensure_vite_scaffold(self, root: Path, pipeline_id: str, frontend_files: Optional[Dict[str, str]] = None) -> None:
        """无项目快照时，从生成的 frontend_files 脚手架最小 vite 宿主（Vue3/Vue2/React 分流）。

        在 ``_safe_write_files`` 之前调用，故 root 为空——框架/主组件一律从 frontend_files 检测，
        不能 rglob root（那是旧死代码的 bug）。Vue3 用 vue@3+ant-design-vue@4+@vitejs/plugin-vue，
        让真实生成的 antd 页（v-model:value、<script setup>）能编译渲染。
        """
        files = frontend_files or {}
        is_vue3 = self._generated_code_is_vue3(files)
        has_vue = is_vue3 or any(self._rel(p).endswith(".vue") for p in files)
        has_react = (not has_vue) and any(self._rel(p).endswith((".tsx", ".jsx")) for p in files)

        (root / "src").mkdir(parents=True, exist_ok=True)
        if is_vue3:
            self._scaffold_vue3_host(root, pipeline_id, files)
        elif has_vue:
            self._scaffold_vue2_host(root, pipeline_id, files)
        elif has_react:
            self._scaffold_react_host(root, pipeline_id, files)

    def _scaffold_vue3_host(self, root: Path, pipeline_id: str, files: Dict[str, str]) -> None:
        main_path = self._pick_main_vue_path(files) or "src/App.vue"
        rel = main_path[len("src/"):] if main_path.startswith("src/") else main_path  # 相对 src/ 的导入路径
        deps = {
            "vue": self.NPM_VERSIONS_VUE3["vue"],
            "ant-design-vue": self.NPM_VERSIONS_VUE3["ant-design-vue"],
        }
        deps.update(self._scan_npm_deps(files, self.NPM_VERSIONS_VUE3))
        package = {
            "name": f"preview-{pipeline_id}",
            "scripts": {"dev": "vite", "build": "vite build"},
            "dependencies": deps,
            "devDependencies": {
                "@vitejs/plugin-vue": "^5.1.4",
                "vite": "^5.4.21",
                "typescript": "^5.6.3",
                **self._scan_style_preprocessors(files),
            },
        }
        (root / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        # 函数式 defineConfig，便于 _patch_vite_preview_config 注入 base/port/host
        (root / "vite.config.js").write_text(
            "import { defineConfig } from 'vite'\n"
            "import vue from '@vitejs/plugin-vue'\n"
            "import path from 'path'\n\n"
            "export default defineConfig(() => {\n"
            "  return {\n"
            "    plugins: [vue()],\n"
            "    resolve: { alias: { '@': path.resolve(__dirname, './src') } },\n"
            "    define: { 'process.env': {} },\n"
            "    server: { host: '0.0.0.0' },\n"
            "  }\n"
            "})\n",
            encoding="utf-8",
        )
        (root / "index.html").write_text(
            '<!doctype html><html><head><meta charset="UTF-8" />'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
            f"<title>{pipeline_id} preview</title>"
            "<style>html,body{margin:0;padding:0;}</style></head><body>"
            '<div id="app"></div>'
            '<script type="module" src="/src/main.ts"></script></body></html>',
            encoding="utf-8",
        )
        (root / "src" / "main.ts").write_text(
            "import { createApp } from 'vue'\n"
            "import Antd from 'ant-design-vue'\n"
            "import 'ant-design-vue/dist/reset.css'\n"
            f"import App from './{rel}'\n\n"
            "const app = createApp(App)\n"
            "app.use(Antd)\n"
            "app.mount('#app')\n",
            encoding="utf-8",
        )

    def _scaffold_vue2_host(self, root: Path, pipeline_id: str, files: Dict[str, str]) -> None:
        main_path = self._pick_main_vue_path(files) or "src/App.vue"
        rel = main_path[len("src/"):] if main_path.startswith("src/") else main_path
        deps = {
            "vue": self.NPM_VERSIONS_VUE2["vue"],
            "ant-design-vue": self.NPM_VERSIONS_VUE2["ant-design-vue"],
        }
        deps.update(self._scan_npm_deps(files, self.NPM_VERSIONS_VUE2))
        package = {
            "name": f"preview-{pipeline_id}",
            "scripts": {"dev": "vite"},
            "dependencies": deps,
            "devDependencies": {"@vitejs/plugin-vue2": "^2.3.3", "vite": "^5.4.21"},
        }
        (root / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "vite.config.js").write_text(
            "import { defineConfig } from 'vite'\n"
            "import vue from '@vitejs/plugin-vue2'\n"
            "import path from 'path'\n\n"
            "export default defineConfig(() => {\n"
            "  return { plugins: [vue()], resolve: { alias: { '@': path.resolve(__dirname, './src') } }, define: { 'process.env': {} }, server: { host: '0.0.0.0' } }\n"
            "})\n",
            encoding="utf-8",
        )
        (root / "index.html").write_text(
            '<!doctype html><html><head><meta charset="UTF-8" />'
            f"<title>{pipeline_id} preview</title></head><body>"
            '<div id="app"></div>'
            '<script type="module" src="/src/main.js"></script></body></html>',
            encoding="utf-8",
        )
        (root / "src" / "main.js").write_text(
            "import Vue from 'vue'\n"
            "import Antd from 'ant-design-vue'\n"
            "import 'ant-design-vue/dist/antd.css'\n"
            f"import App from './{rel}'\n\n"
            "Vue.use(Antd)\nnew Vue({ render: h => h(App) }).$mount('#app')\n",
            encoding="utf-8",
        )

    def _scaffold_react_host(self, root: Path, pipeline_id: str, files: Dict[str, str]) -> None:
        package = {
            "name": f"preview-{pipeline_id}",
            "scripts": {"dev": "vite"},
            "dependencies": {
                "@vitejs/plugin-react": "^4.3.4",
                "antd": "^5.27.0",
                "vite": "^5.4.21",
                "react": "^18.3.1",
                "react-dom": "^18.3.1",
            },
            "devDependencies": {"typescript": "^5.9.3"},
        }
        (root / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "index.html").write_text(
            '<!doctype html><html><head><meta charset="UTF-8" />'
            f"<title>{pipeline_id} preview</title></head><body>"
            '<div id="root"></div>'
            '<script type="module" src="/src/main.jsx"></script></body></html>',
            encoding="utf-8",
        )
        (root / "src" / "main.jsx").write_text(
            "import React from 'react'\n"
            "import { createRoot } from 'react-dom/client'\n"
            "import App from './App.jsx'\n\n"
            "createRoot(document.getElementById('root')).render(<App />)\n",
            encoding="utf-8",
        )

    # ---- import shim：为生成代码引用但未生成的 @/ 模块写最小 ESM 桩 ----

    def _write_import_shims(self, root: Path, files: Dict[str, str]) -> None:
        """扫描生成代码的 @/ 引用，对未生成的模块/资源在 src/ 对应路径写 ESM 桩。

        - 模块：按代码里实际用到的命名导入生成对应 no-op 导出（解决 ``import { getToken }``
          这类命名导入；ESM 无法代理任意命名导出，必须照单生成）。
        - 资源（.png/.svg/.css 等）：写占位文件让 vite 按 asset 解析。
        生成的 @/api/* 本就在 files 里，经 @→src alias 自然解析。
        """
        generated = {self._rel(p) for p in files}

        def resolves(spec_rel: str) -> bool:
            cands = []
            for prefix in ("src/", ""):
                base = prefix + spec_rel
                cands.extend([base, base + ".js", base + ".ts", base + ".jsx", base + ".tsx",
                              base + "/index.js", base + "/index.ts"])
            return any(c in generated for c in cands)

        module_clauses, asset_specs = self._collect_at_references(files)

        for spec in sorted(module_clauses):
            spec_rel = self._rel(spec[2:])
            if resolves(spec_rel):
                continue
            target_rel = spec_rel if spec_rel.endswith((".js", ".ts", ".vue")) else spec_rel + ".js"
            target = root / "src" / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._module_shim_content(spec, module_clauses[spec]), encoding="utf-8")

        for spec in sorted(asset_specs):
            spec_rel = self._rel(spec[2:])
            if resolves(spec_rel):
                continue
            self._write_asset_placeholder(root, spec_rel)

    def _collect_at_references(self, files: Dict[str, str]) -> tuple:
        """解析所有 @/ 引用，返回 (module_clauses, asset_specs)。

        module_clauses: {spec: {'named': set, 'default': bool, 'namespace': bool}}
        asset_specs: set of @/ 资源 spec（图片/svg/css）
        """
        asset_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svg", ".css")
        module_clauses: Dict[str, Dict[str, Any]] = {}
        asset_specs: set = set()
        for content in files.values():
            if not isinstance(content, str):
                continue
            for m in re.finditer(r"""import\s+([^'";]+?)\s+from\s+['"](@/[^'"]+)['"]""", content):
                clause, spec = m.group(1).strip(), m.group(2)
                if spec.lower().endswith(asset_exts):
                    asset_specs.add(spec)
                    continue
                entry = module_clauses.setdefault(spec, {"named": set(), "default": False, "namespace": False})
                if clause.startswith("*") and " as " in clause:
                    entry["namespace"] = True
                if re.match(r"^[A-Za-z_$][\w$]*", clause):
                    entry["default"] = True  # DefaultName 或 DefaultName, { ... }
                for nb in re.finditer(r"\{([^}]*)\}", clause):
                    for item in nb.group(1).split(","):
                        name = item.strip()
                        if not name or name == "*":
                            continue
                        name = name.split(" as ")[0].strip()
                        if name:
                            entry["named"].add(name)
            for m in re.finditer(r"""(?:src|href)\s*=\s*['"](@/[^'"]+)['"]""", content):
                asset_specs.add(m.group(1))
            for m in re.finditer(r"""url\(['"]?(@/[^'")]+)['"]?\)""", content):
                asset_specs.add(m.group(1))
        return module_clauses, asset_specs

    def _write_asset_placeholder(self, root: Path, spec_rel: str) -> None:
        lower = spec_rel.lower()
        target = root / "src" / spec_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp")):
            import base64
            target.write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            ))
        else:  # svg / css
            target.write_text("/* sandbox placeholder */\n", encoding="utf-8")

    def _module_shim_content(self, spec: str, clause: Dict[str, Any]) -> str:
        # 语义桩：@/utils/request（默认 request + get/post 等）
        if spec.endswith("utils/request") or spec == "@/utils/request":
            return (
                "/* sandbox shim: @/utils/request — 预览用 mock */\n"
                "export default async function request(config){ return { code: 200, data: {}, message: 'ok' } }\n"
                "export const get = async () => ({ code: 200, data: {} })\n"
                "export const post = async () => ({ code: 200, data: {} })\n"
                "export const put = async () => ({ code: 200, data: {} })\n"
                "export const del = async () => ({ code: 200, data: {} })\n"
                "export const DELETE = async () => ({ code: 200, data: {} })\n"
            )
        # 语义桩：@/components（常见占位组件 + 扫描到的命名导出）
        if spec == "@/components" or spec.startswith("@/components"):
            named = sorted(clause.get("named", set()))
            names = sorted(set(["STable", "JDictSelectTag", "JUpload", "JEditor"]) | set(named))
            lines = ["/* sandbox shim: @/components */", "import { defineComponent } from 'vue'",
                     "const Stub = defineComponent({ name: 'Stub', render: () => null })"]
            lines += [f"export const {n} = Stub" for n in names]
            lines.append("export default { " + ", ".join(names) + " }")
            return "\n".join(lines) + "\n"
        # 通用桩：按代码实际用到的命名导入生成 no-op 导出 + 默认空对象
        named = sorted(clause.get("named", set()))
        lines = [f"/* sandbox shim: {spec} */"]
        for n in named:
            lines.append(f"export const {n} = () => {{}}")
        if clause.get("default") or clause.get("namespace") or not named:
            lines.append("const __default = {}")
            lines.append("export default __default")
        return "\n".join(lines) + "\n"


    async def _wait_ready(self, pipeline_id: str, port: int, timeout: int = 120, preview_path: str = "", connect_host: str = "") -> None:
        deadline = time.time() + timeout
        host = connect_host or settings.pipeline_preview_host
        url = f"http://{host}:{port}{self._preview_base(pipeline_id)}{preview_path}"
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

    def _make_preview_log_cb(self, pipeline_id: str):
        """构造日志行回调（供 SandboxHandle.start_log_drain）：只记录关键行。
        process 模式读 stdout.readline；container 模式 docker logs -f——两者共用此回调。"""
        def _on_line(text_line: str) -> None:
            if (
                "ERROR" in text_line
                or "Error:" in text_line
                or "Failed" in text_line
                or "Compiled" in text_line
                or "App running at" in text_line
            ):
                logger.info("[SandboxPreview:%s] %s", pipeline_id, text_line[:1000])
        return _on_line

    async def _run(self, args: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str]:
        # 安全：git clone / npm install（postinstall 脚本）/ vite 都执行不可信代码——走统一安全原语
        # （剔除 admin 凭据 + 非 root 降权）；超时转为带脱敏命令的 RuntimeError。
        from app.services.sandbox_security import run_sandboxed
        try:
            code, output = await run_sandboxed(args, cwd=str(cwd), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(f"{self._redact_sensitive_output(' '.join(args))} 超时")
        return code, self._redact_sensitive_output(output)

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
        git_host = ""
        try:
            git_host = urlparse(repo_url).netloc
        except Exception:
            git_host = ""
        return {
            "repo_url": repo_url,
            "clone_url": clone_url,
            "branch": branch,
            "token": token,
            "git_host": git_host,
        }

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
            raise RuntimeError(await self._diagnose_clone_failure(git_info, output[-500:]))
        (root / ".sandbox-preview-project.json").write_text(
            json.dumps({
                "project_id": project_info.get("project_id") or "",
                "project_name": project_info.get("project_name") or "",
                "repo_url": git_info["repo_url"],
                "branch": git_info["branch"],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _probe_git_token(self, scheme: str, host: str, token: str) -> str:
        """Probe token validity against the Git host; return a human hint or '' if unknown."""
        if not host or not token:
            return ""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    f"{scheme}://{host}/api/v4/user",
                    headers={"PRIVATE-TOKEN": token},
                )
        except Exception:
            return ""
        if resp.status_code == 401:
            return "Git 令牌无效或已过期（账户开启 2FA 时须用个人访问令牌 PAT，不能用密码），请在「Git 配置」中更新 token。"
        if resp.status_code == 403:
            return "Git 令牌权限不足，请在「Git 配置」中改用具备 read_repository/api 权限的 token。"
        if resp.status_code == 200:
            return "令牌本身有效但克隆仍被拒，请检查目标仓库/分支是否存在，或令牌是否具备该仓库的读权限。"
        return ""

    async def _diagnose_clone_failure(self, git_info: Dict[str, Any], raw_output: str) -> str:
        repo_url = git_info.get("repo_url") or ""
        token = git_info.get("token") or ""
        if not token:
            return (
                f"克隆前端项目失败: 未匹配到该仓库（{repo_url}）的有效 Git 凭据，"
                f"请在「Git 配置」中为其绑定 access_token（或检查 git 配置记录是否启用）。原始错误: {raw_output}"
            )
        host = git_info.get("git_host") or ""
        scheme = "https" if repo_url.startswith("https://") else "http"
        hint = await self._probe_git_token(scheme, host, token)
        if hint:
            return f"克隆前端项目失败: {hint} 原始错误: {raw_output}"
        return f"克隆前端项目失败: {raw_output}"

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

    def _package_manager(self, root: Path) -> str:
        package_json = root / "package.json"
        package: Dict[str, Any] = {}
        if package_json.exists():
            try:
                package = json.loads(package_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                package = {}
        package_manager = str(package.get("packageManager") or "").lower()
        if (root / "pnpm-lock.yaml").exists() or (root / "pnpm-workspace.yaml").exists() or package_manager.startswith("pnpm@"):
            return "pnpm"
        if (root / "yarn.lock").exists() or package_manager.startswith("yarn@"):
            return "yarn"
        return "npm"

    def _install_command(self, root: Path) -> list[str]:
        package_manager = self._package_manager(root)
        cache_root = Path(settings.pipeline_workspace_root)
        if package_manager == "pnpm":
            return [
                "pnpm",
                "install",
                "--registry=https://registry.npmmirror.com",
                "--frozen-lockfile=false",
                "--store-dir",
                str(cache_root / ".pnpm-store"),
            ]
        if package_manager == "yarn":
            return [
                "yarn",
                "install",
                "--registry=https://registry.npmmirror.com",
                "--cache-folder",
                str(cache_root / ".yarn-cache"),
            ]
        return [
            "npm",
            "install",
            "--registry=https://registry.npmmirror.com",
            "--no-audit",
            "--no-fund",
            "--legacy-peer-deps",
            "--progress=false",
            "--cache",
            str(cache_root / ".npm-cache"),
        ]

    def _generated_apps(self, frontend_files: Dict[str, str]) -> list[str]:
        apps: set[str] = set()
        for raw_path in frontend_files:
            safe_path = str(raw_path).replace("\\", "/").lstrip("/")
            match = re.match(r"^apps/([^/]+)/", safe_path)
            if match:
                apps.add(match.group(1))
        return sorted(apps)

    def _select_dev_script(self, scripts: Dict[str, Any], frontend_files: Optional[Dict[str, str]] = None) -> str:
        app_names = self._generated_apps(frontend_files or {})
        for app in app_names:
            candidates = [
                f"dev:{app}:h5:sass",
                f"dev:{app}:h5",
                f"dev:{app}-h5",
                f"dev:{app}:h5:longting",
                f"dev:{app}:mp-weixin:sass",
                f"dev:{app}:mp-weixin",
            ]
            for script in candidates:
                if script in scripts:
                    return script
        for script in ("serve", "dev", "start", "preview"):
            if script in scripts:
                return script
        raise RuntimeError("前端项目没有 dev/serve/start/preview 启动脚本")

    def _dev_command(self, root: Path, port: int, frontend_files: Optional[Dict[str, str]] = None, bind_host: str = "") -> list[str]:
        package_json = root / "package.json"
        if not package_json.exists():
            raise RuntimeError("匹配到的前端项目没有 package.json，无法启动真实项目预览")
        package = json.loads(package_json.read_text(encoding="utf-8"))
        scripts = package.get("scripts") or {}
        script = self._select_dev_script(scripts, frontend_files)

        package_manager = self._package_manager(root)
        script_command = str(scripts.get(script, ""))
        host = bind_host or settings.pipeline_preview_host
        args = [package_manager, "run", script, "--", "--host", host, "--port", str(port)]
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

    def _patch_vite_preview_config(self, root: Path) -> None:
        config_files = [
            root / "vite.config.ts",
            root / "vite.config.js",
            root / "vite.config.mts",
            root / "vite.config.mjs",
        ]
        config_files.extend(sorted(root.glob("apps/*/vite.config.ts")))
        config_files.extend(sorted(root.glob("apps/*/vite.config.js")))
        marker = "SANDBOX_PREVIEW_VITE_CONFIG_PATCH_V1"
        for config_file in config_files:
            if not config_file.exists():
                continue
            content = config_file.read_text(encoding="utf-8")
            if marker not in content:
                patched = re.sub(
                    r"return\s*\{",
                    "return {\n"
                    f"    // {marker}\n"
                    "    base: process.env.VITE_SANDBOX_PREVIEW_BASE || '/',",
                    content,
                    count=1,
                )
            else:
                patched = content
            patched = re.sub(
                r"port\s*:\s*\d+",
                "port: Number(process.env.VITE_SANDBOX_PREVIEW_PORT || 3000)",
                patched,
                count=1,
            )
            patched = re.sub(
                r"host\s*:\s*['\"][^'\"]+['\"]",
                "host: process.env.VITE_SANDBOX_PREVIEW_HOST || '0.0.0.0'",
                patched,
                count=1,
            )
            if "hmr:" not in patched:
                patched = re.sub(r"server\s*:\s*\{", "server: {\n          hmr: false,", patched, count=1)
            if patched != content:
                config_file.write_text(patched, encoding="utf-8")

    def _patch_uniapp_manifest_preview_base(self, root: Path, pipeline_id: str) -> None:
        preview_base = self._preview_base(pipeline_id)
        manifest_files = [root / "src" / "manifest.json"]
        manifest_files.extend(sorted(root.glob("apps/*/src/manifest.json")))
        for manifest_file in manifest_files:
            if not manifest_file.exists():
                continue
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            h5 = manifest.setdefault("h5", {})
            if not isinstance(h5, dict):
                continue
            router = h5.setdefault("router", {})
            if not isinstance(router, dict):
                continue
            router["mode"] = "history"
            router["base"] = preview_base
            h5["publicPath"] = preview_base
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _patch_uniapp_runtime_api_config(self, root: Path, pipeline_id: str) -> None:
        preview_base = self._preview_base(pipeline_id).rstrip("/")
        replacements = {
            "javaUrl": f"{preview_base}/javaApi",
            "aiJavaUrl": f"{preview_base}/hotelAi/dify/hotel/v2",
            "h5Url": preview_base,
        }
        config_files = sorted(root.glob("apps/*/config/*.config.js"))
        config_files.extend(sorted((root / "config").glob("*.config.js")) if (root / "config").exists() else [])
        for config_file in config_files:
            content = config_file.read_text(encoding="utf-8")
            patched = content
            for key, value in replacements.items():
                patched = re.sub(
                    rf"({re.escape(key)}\s*:\s*)['\"][^'\"]*['\"]",
                    lambda match, replacement=value: f"{match.group(1)}{json.dumps(replacement)}",
                    patched,
                )
            if patched != content:
                config_file.write_text(patched, encoding="utf-8")
        src_config_files = [root / "src" / "config" / "index.ts"]
        src_config_files.extend(sorted(root.glob("apps/*/src/config/index.ts")))
        for config_file in src_config_files:
            if not config_file.exists():
                continue
            content = config_file.read_text(encoding="utf-8")
            patched = content
            patched = re.sub(r"javaUrl\s*:\s*['\"]/javaApi['\"]", f"javaUrl: {json.dumps(replacements['javaUrl'])}", patched)
            patched = re.sub(r"aiJavaUrl\s*:\s*['\"]/hotelAi['\"]", f"aiJavaUrl: {json.dumps(preview_base + '/hotelAi')}", patched)
            patched = re.sub(r"h5Url\s*:\s*window\.location\.origin", f"h5Url: {json.dumps(replacements['h5Url'])}", patched)
            if patched != content:
                config_file.write_text(patched, encoding="utf-8")

    def _clear_preview_vite_cache(self, root: Path, frontend_files: Dict[str, str]) -> None:
        candidates = [root / "node_modules" / ".vite"]
        for app_name in self._generated_apps(frontend_files):
            candidates.append(root / "apps" / app_name / "node_modules" / ".vite")
        for cache_dir in candidates:
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)

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
                await self._teardown_entry(pipeline_id, existing)

            port: Optional[int] = None
            async with self._start_semaphore:
                root = self._preview_root(pipeline_id)
                try:
                    preview_fallback_reason = ""
                    html_preview_path = ""
                    scaffolded = False
                    try:
                        await self._prepare_project_root(root, project_info)
                    except Exception as exc:
                        # 无项目快照：web Vue → 从生成代码脚手架 vite 宿主（走正常 install+dev 流程，
                        # is_html_fallback=False）；脚手架不适用或失败 → 退回 miniapp HTML fallback。
                        scaffolded = False
                        if self._looks_like_web_vue(frontend_files):
                            try:
                                self._ensure_vite_scaffold(root, pipeline_id, frontend_files)
                                self._write_import_shims(root, frontend_files)
                                logger.info("Scaffolded vite host from generated code for %s", pipeline_id)
                                scaffolded = True
                            except Exception as scaffold_exc:  # noqa: BLE001
                                logger.warning(
                                    "vite scaffold from generated code failed for %s: %s",
                                    pipeline_id, scaffold_exc,
                                )
                        if not scaffolded:
                            fallback_path = self._prepare_miniapp_html_fallback_root(
                                root,
                                frontend_files,
                                project_info,
                                str(exc),
                            )
                            if not fallback_path:
                                raise
                            preview_fallback_reason = str(exc)
                            html_preview_path = fallback_path
                            logger.warning(
                                "Falling back to miniapp HTML preview for %s after project clone/setup failed: %s",
                                pipeline_id,
                                exc,
                            )
                    self._safe_write_files(root, frontend_files, skip_patches=scaffolded)
                    html_preview_path = html_preview_path or self._install_miniapp_html_preview(root, frontend_files)
                    uniapp_preview_path = self._install_uniapp_monorepo_preview_files(root, frontend_files)
                    generated_preview_path = self._install_generated_vue_routes(root, frontend_files)
                    generated_preview_path = generated_preview_path or uniapp_preview_path
                    self._patch_vue_cli_preview_base(root)

                    port = await self._allocate_port()
                    node_version = await self._node_version()
                    node_marker = root / ".preview-node-version"
                    if (root / "node_modules").exists() and (
                        not node_marker.exists() or node_marker.read_text(encoding="utf-8").strip() != node_version
                    ):
                        shutil.rmtree(root / "node_modules", ignore_errors=True)
                    is_html_fallback = bool(preview_fallback_reason)
                    if not is_html_fallback and not (root / "node_modules").exists():
                        install_cmd = self._install_command(root)
                        package_manager = install_cmd[0]
                        if not shutil.which(package_manager):
                            raise RuntimeError(f"admin-python 容器未安装 {package_manager}，无法安装真实前端项目依赖")
                        code, output = await self._run(install_cmd, root, timeout=1200)
                        if code != 0:
                            raise RuntimeError(f"{package_manager} install 失败: {output[-500:]}")
                        node_marker.write_text(node_version, encoding="utf-8")

                    if not is_html_fallback:
                        self._patch_vue_cli_service_no_hmr(root)
                        self._patch_vite_preview_config(root)
                        self._patch_uniapp_manifest_preview_base(root, pipeline_id)
                        self._patch_uniapp_runtime_api_config(root, pipeline_id)
                        self._clear_preview_vite_cache(root, frontend_files)
                    # container 模式：vite 跑在 sandbox-fe-<pid12> 容器（仅 sandbox-net），须绑 0.0.0.0
                    # （admin-python 跨网桥连它），admin-python 经容器 DNS 名连；process 模式用 loopback。
                    container_mode = settings.sandbox_execution_mode == "container"
                    fe_name = f"{settings.sandbox_container_prefix_fe}-{pipeline_id[:12].replace('-', '')}"
                    bind_host = "0.0.0.0" if container_mode else settings.pipeline_preview_host
                    connect_host = fe_name if container_mode else settings.pipeline_preview_host
                    dev_cmd = self._dev_command(root, port, frontend_files, bind_host=bind_host)
                    # 安全（防越权）：剔除 admin-python 敏感 env，只留前端构建/运行所需 + 业务变量
                    from app.services.sandbox_security import sanitized_env, spawn_sandboxed_service
                    env = sanitized_env()
                    project_env = self._load_env_file(root, ".env.development")
                    proxy_targets = (
                        {"api": "", "java": "", "log": ""}
                        if is_html_fallback
                        else self._preview_proxy_targets(project_env)
                    )
                    api_base_url = self._preview_base(pipeline_id).rstrip("/") if is_html_fallback else self._api_base_url_for_preview(root, project_env, pipeline_id)
                    env.update({
                        "VUE_APP_PROXY": proxy_targets["api"],
                        "VUE_APP_JAVA_PROXY": proxy_targets["java"],
                        "VUE_APP_PROXY_LOG": proxy_targets["log"],
                        "VUE_APP_API_BASE_URL": api_base_url,
                        "VUE_APP_SANDBOX_PREVIEW_BASE": self._preview_base(pipeline_id),
                        "VUE_APP_SANDBOX_PREVIEW_DEFAULT_ROUTE": generated_preview_path,
                        "VUE_APP_SANDBOX_PREVIEW_PUBLIC": env.get("VUE_APP_SANDBOX_PREVIEW_PUBLIC") or "localhost",
                        "VUE_APP_SANDBOX_PREVIEW_DISABLE_WDS_CLIENT": "1",
                        "VITE_SANDBOX_PREVIEW_BASE": self._preview_base(pipeline_id),
                        "VITE_SANDBOX_PREVIEW_HOST": bind_host,
                        "VITE_SANDBOX_PREVIEW_PORT": str(port),
                    })
                    # env=已脱敏并注入业务变量（原样保留不被二次剔除）；降权/容器隔离由句柄负责
                    handle = await spawn_sandboxed_service(dev_cmd, cwd=str(root), env=env, name=fe_name)
                    entry = {
                        "handle": handle,
                        "port": port,
                        "root": str(root),
                        "connect_host": connect_host,
                        "ready": False,
                        "files_hash": files_hash,
                        "tokens": {},
                        "html_preview_path": html_preview_path or "",
                        "generated_preview_path": generated_preview_path,
                        "project_info": project_info,
                        "proxy_targets": proxy_targets,
                        "fallback_reason": preview_fallback_reason,
                        "last_active": time.time(),
                    }
                    self._issue_token(entry)
                    await handle.start_log_drain(self._make_preview_log_cb(pipeline_id))
                    async with self._process_lock:
                        self._processes[pipeline_id] = entry
                        self._reserved_ports.discard(port)
                except Exception:
                    if port is not None:
                        async with self._process_lock:
                            self._reserved_ports.discard(port)
                    raise

            try:
                await self._wait_ready(pipeline_id, port, preview_path=entry.get("html_preview_path") or "", connect_host=entry["connect_host"])
            except Exception:
                await self._teardown_entry(pipeline_id, entry)
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
            "generated_preview_path": entry.get("generated_preview_path") or "",
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
        return bool(entry and entry["handle"].returncode is None)

    def direct_preview_url(self, pipeline_id: str) -> Optional[str]:
        """已就绪预览的容器内直连 vite URL（http://host:port/preview_base），未就绪返回 None。

        供 eval 视觉截图 / E2E 直接命中真实渲染页（绕过 Vue2 渲染桩）。
        """
        entry = self._processes.get(pipeline_id)
        if not entry or entry["handle"].returncode is not None or not entry.get("ready"):
            return None
        return f"http://{entry['connect_host']}:{entry['port']}{self._preview_base(pipeline_id)}"

    async def _teardown_entry(self, pipeline_id: str, entry: Dict[str, Any]) -> None:
        """终止预览句柄（含取消日志 drain）、从注册表摘除（start/stop 共用）。"""
        handle = entry.get("handle")
        if handle:
            await handle.acleanup(timeout=5)
        async with self._process_lock:
            if self._processes.get(pipeline_id) is entry:
                self._processes.pop(pipeline_id, None)

    async def stop(self, pipeline_id: str) -> bool:
        """终止该流水线的运行中预览。返回是否确实停掉了一个活预览（供 eval 用完即停）。"""
        pipeline_lock = await self._pipeline_lock(pipeline_id)
        async with pipeline_lock:
            entry = self._processes.get(pipeline_id)
            if not entry or entry["handle"].returncode is not None:
                return False
            await self._teardown_entry(pipeline_id, entry)
            return True

    async def reap_idle(self, ttl_seconds: int) -> int:
        """回收超过 ttl 无访问的前端预览进程（释放 vite 进程 + 端口），返回回收数。

        防长跑泄漏：用户停止访问（无 token 签发 / 无 proxy 请求）超过 ttl 即自动 stop。
        """
        now = time.time()
        stale = [
            pid for pid, e in self._processes.items()
            if e.get("ready") and now - float(e.get("last_active", 0)) > ttl_seconds
        ]
        for pid in stale:
            await self.stop(pid)
        return len(stale)

    def generated_preview_path(self, pipeline_id: str) -> str:
        entry = self._processes.get(pipeline_id) or {}
        return str(entry.get("generated_preview_path") or "").lstrip("/")

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
        if not entry or entry["handle"].returncode is not None:
            raise RuntimeError("真实预览服务未启动")
        host = entry["connect_host"]
        entry["last_active"] = time.time()
        if path.startswith("sockjs-node/"):
            target = f"http://{host}:{entry['port']}{self._preview_base(pipeline_id)}{path}"
        elif path.startswith("__webpack_dev_server__/"):
            target = f"http://{host}:{entry['port']}/{path}"
        elif path.startswith(("api/", "javaApi/", "logApi/", "socket.io/")):
            target = f"http://{host}:{entry['port']}/{path}"
        else:
            generated_path = entry.get("generated_preview_path") if not path else ""
            is_uniapp_page = str(generated_path or "").lstrip("/").startswith("pages/")
            preview_path = entry.get("html_preview_path") if not path and not is_uniapp_page else ""
            generated_path = "" if is_uniapp_page else generated_path
            fallback_path = path or str(preview_path or generated_path or "").lstrip("/")
            target = f"http://{host}:{entry['port']}{self._preview_base(pipeline_id)}{fallback_path}"
        if query_string:
            target = f"{target}?{query_string}"
        headers = {k: v for k, v in request_headers.items() if k.lower() not in {"host", "connection", "content-length"}}
        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
            response = await client.request(method, target, headers=headers, content=body)
            if (
                method == "GET"
                and response.status_code == 404
                and path
                and not path.startswith(("api/", "javaApi/", "logApi/", "socket.io/", "sockjs-node/", "__webpack_dev_server__/"))
                and not re.search(
                    r"\.(?:js|css|map|json|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot)(?:$|\?)",
                    path,
                    flags=re.I,
                )
            ):
                fallback_target = f"http://{host}:{entry['port']}{self._preview_base(pipeline_id)}"
                response = await client.request("GET", fallback_target, headers=headers)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            prefix = f"/api/flow/pipeline/{pipeline_id}/sandbox-preview/"
            text_body = response.text
            runtime_proxy_script = (
                "<script>\n"
                "(function(){\n"
                f"  var sandboxPrefix = {json.dumps(prefix)};\n"
                "  function rewriteUrl(input) {\n"
                "    if (typeof input !== 'string') return input;\n"
                "    var url = input;\n"
                "    if (url.indexOf(window.location.origin + '/') === 0) {\n"
                "      url = url.slice(window.location.origin.length);\n"
                "    }\n"
                "    if (url.indexOf(sandboxPrefix) === 0) return input;\n"
                "    if (/^(\\/api\\/server-time|\\/javaApi\\/|\\/hotelAi\\/|\\/log\\/save)(?:\\?|\\/|$)/.test(url)) {\n"
                "      return sandboxPrefix + url.replace(/^\\//, '');\n"
                "    }\n"
                "    return input;\n"
                "  }\n"
                "  function installSandboxProxyPatch() {\n"
                "    if (window.fetch && !window.fetch.__sandboxPreviewPatched) {\n"
                "      var rawFetch = window.fetch.bind(window);\n"
                "      var patchedFetch = function(input, init) {\n"
                "        if (input instanceof Request) {\n"
                "          var normalized = input.url.replace(window.location.origin, '');\n"
                "          var rewritten = rewriteUrl(normalized);\n"
                "          if (rewritten !== normalized) input = new Request(rewritten, input);\n"
                "        } else {\n"
                "          input = rewriteUrl(input);\n"
                "        }\n"
                "        return rawFetch(input, init);\n"
                "      };\n"
                "      patchedFetch.__sandboxPreviewPatched = true;\n"
                "      window.fetch = patchedFetch;\n"
                "    }\n"
                "    if (window.XMLHttpRequest && !window.XMLHttpRequest.prototype.open.__sandboxPreviewPatched) {\n"
                "      var rawOpen = window.XMLHttpRequest.prototype.open;\n"
                "      var patchedOpen = function(method, url) {\n"
                "        arguments[1] = rewriteUrl(url);\n"
                "        return rawOpen.apply(this, arguments);\n"
                "      };\n"
                "      patchedOpen.__sandboxPreviewPatched = true;\n"
                "      window.XMLHttpRequest.prototype.open = patchedOpen;\n"
                "    }\n"
                "    if (navigator.sendBeacon && !navigator.sendBeacon.__sandboxPreviewPatched) {\n"
                "      var rawBeacon = navigator.sendBeacon.bind(navigator);\n"
                "      var patchedBeacon = function(url, data) { return rawBeacon(rewriteUrl(url), data); };\n"
                "      patchedBeacon.__sandboxPreviewPatched = true;\n"
                "      navigator.sendBeacon = patchedBeacon;\n"
                "    }\n"
                "  }\n"
                "  installSandboxProxyPatch();\n"
                "  setTimeout(installSandboxProxyPatch, 0);\n"
                "  setTimeout(installSandboxProxyPatch, 50);\n"
                "  setTimeout(installSandboxProxyPatch, 250);\n"
                "  setInterval(installSandboxProxyPatch, 1000);\n"
                "})();\n"
                "</script>\n"
            )
            if "sandboxPrefix" not in text_body:
                text_body = text_body.replace("</head>", runtime_proxy_script + "</head>", 1)
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
