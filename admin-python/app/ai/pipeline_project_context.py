"""项目上下文加载：git clone + 关键文件筛选 + 现有页面候选匹配（进程级缓存）。

从 flow_manager 拆出（原 zone 9）。从 Generator 拉项目 Git 地址 → 沙箱安全原语浅克隆
→ file_reader skill 读关键文件 → 按需求关键词匹配现有前端页面候选。失败一律 fail-open
返回空，不阻塞主流程。git clone 走 sandbox_security（剔除 admin 凭据 + 非 root 降权 /
容器隔离），SSRF 由 _is_safe_git_url 拦截。
"""
import os
import re
import logging
from typing import Any, Dict, List, Tuple

from app.core.config import settings
from app.core.database import async_session_maker
from app.ai.skills import SkillStatus, skill_registry
from app.ai.pipeline_helpers import (
    _is_frontend_page_path,
    _is_existing_feature_change_request,
)

logger = logging.getLogger(__name__)

# 项目文件缓存（进程级，避免重复克隆）
_project_cache: Dict[str, Dict[str, str]] = {}


async def _cleanup_temp_path(path: str) -> None:
    if not path:
        return
    root_path = os.path.dirname(path)
    basename = os.path.basename(path)
    if not root_path or not basename:
        return
    try:
        await skill_registry.execute(
            "file_cleaner",
            root_path=root_path,
            paths=[basename],
        )
    except Exception as exc:
        logger.warning("Failed to cleanup temp path %s: %s", path, exc)


async def _load_project_files_cached(project_id: str, project_type: str) -> Dict[str, str]:
    """进程级缓存：避免同一 project_id 多阶段重复克隆 git 仓库。"""
    if not project_id:
        return {}
    cache_key = f"{project_id}:{project_type}"
    if cache_key not in _project_cache:
        _project_cache[cache_key] = await _fetch_project_files_from_git(project_id)
    return _project_cache[cache_key]


def _requirement_match_terms(requirement: str) -> List[str]:
    """从需求文本提取匹配用关键词（英文 token + 中文 2-4 字片段），剔除停用词。"""
    terms = set(re.findall(r"[A-Za-z0-9_]{2,}", (requirement or "").lower()))
    cjk_chunks = re.findall(r"[\u4e00-\u9fff]+", requirement or "")
    for chunk in cjk_chunks:
        if len(chunk) <= 4:
            terms.add(chunk)
            continue
        for size in (2, 3, 4):
            for index in range(0, len(chunk) - size + 1):
                terms.add(chunk[index:index + size])
    stop_terms = {"现有", "已有", "增加", "新增", "添加", "一个", "功能", "页面", "字段", "筛选", "查询", "搜索"}
    return sorted(term for term in terms if term not in stop_terms)


def _business_synonyms_for_terms(terms: List[str]) -> List[str]:
    """为业务词扩展同义词（商品→product/goods/sku/spu 等），提高代码文件检索召回率。"""
    synonyms = set(terms)
    mapping = {
        "商品": ["product", "goods", "commodity", "commdity", "sku", "spu"],
        "零售": ["retail"],
        "商城": ["mall", "shop", "store"],
        "列表": ["list"],
        "活动": ["activity"],
    }
    for term in terms:
        for key, values in mapping.items():
            if key in term:
                synonyms.update(values)
        for key, values in mapping.items():
            if term in values:
                synonyms.add(key)
    return sorted(synonyms)


def _requirement_strong_business_terms(requirement: str) -> List[str]:
    """提取需求中的强业务词（剔除通用词如「管理/平台/列表」），并扩展同义词。"""
    terms = _requirement_match_terms(requirement)
    generic = {
        "管理", "平台", "系统", "列表", "筛选", "查询", "搜索", "字段", "id",
        "商品id", "增加", "新增", "现有", "已有",
    }
    known_business_terms = ("商品", "零售", "活动", "营销", "订单", "用户", "酒店", "分类")
    strong = []
    for term in terms:
        if term.lower() in generic or len(term) < 2:
            continue
        if re.fullmatch(r"[a-z0-9_]+", term.lower()):
            strong.append(term)
            continue
        strong.extend(known for known in known_business_terms if known in term)
    return _business_synonyms_for_terms(strong)


def _select_relevant_project_files(files: Dict[str, str], requirement: str, limit: int = 8) -> List[Tuple[str, str]]:
    """按需求关键词对项目代码文件打分，挑出 top-N 相关文件作 prompt 上下文。"""
    terms = _requirement_match_terms(requirement)
    if not terms:
        return []

    candidates = []
    for path, content in files.items():
        normalized = str(path).replace("\\", "/")
        if not normalized.startswith(("src/views/", "src/pages/", "pages/", "src/api/")):
            continue
        if not normalized.endswith((".vue", ".tsx", ".jsx", ".js", ".ts", ".wxml")):
            continue
        haystack = f"{normalized}\n{content}".lower()
        matched_terms = [term for term in terms if term.lower() in haystack]
        if not matched_terms:
            continue
        page_bonus = 2 if _is_frontend_page_path(normalized) else 0
        score = len(matched_terms) + page_bonus
        candidates.append((score, len(content or ""), normalized, content))

    candidates.sort(key=lambda item: (item[0], -item[1], item[2]), reverse=True)
    return [(path, content) for _, _, path, content in candidates[:limit]]


def _frontend_existing_page_paths(files: Dict[str, str]) -> List[str]:
    """列出项目里所有可预览的前端页面路径（排序去重）。"""
    return sorted(
        str(path).replace("\\", "/").lstrip("/")
        for path in files
        if _is_frontend_page_path(str(path).replace("\\", "/").lstrip("/"))
    )


def _frontend_relevant_existing_page_paths(files: Dict[str, str], requirement: str, limit: int = 12) -> List[str]:
    """挑出与需求强相关的现有前端页面路径（供 prototype 改造时锁定目标文件）。"""
    return [item["path"] for item in _frontend_existing_page_candidates(files, requirement, limit)]


def _requirement_anchor_groups(requirement: str) -> List[List[str]]:
    """从需求抽取业务锚点组（零售/商品/活动），用于过滤无关页面候选。"""
    requirement_text = requirement or ""
    anchor_groups: List[List[str]] = []
    if "零售" in requirement_text:
        anchor_groups.append(["零售", "retail"])
    if "商品" in requirement_text:
        anchor_groups.append(["商品", "product", "goods", "sku", "spu"])
    if "活动" in requirement_text:
        anchor_groups.append(["活动", "activity"])
    return anchor_groups


def _is_product_pool_context(path: str, content: str) -> bool:
    """判定页面是否为商品池/池相关（与「商品列表」需求区分，避免误选池管理页）。"""
    text = f"{path}\n{content or ''}".lower()
    return "pool" in text or "商品池" in (content or "") or "池" in path


def _is_primary_product_list_context(path: str, content: str) -> bool:
    """判定页面是否为「主商品列表」上下文（排除商品池、订单列表、详情、操作页）。"""
    normalized = str(path).replace("\\", "/").lstrip("/")
    lower_path = normalized.lower()
    text = f"{lower_path}\n{content or ''}".lower()
    if _is_product_pool_context(normalized, content):
        return False
    if any(segment in lower_path for segment in ("/orderlist/", "refundorderlist", "/modules/", "/detail")):
        return False
    if lower_path.endswith("/operate.vue"):
        return False
    if "commoditylist" in lower_path or "commodity/list" in lower_path:
        return True
    if ("productlist" in lower_path or lower_path.endswith("/list.vue")) and (
        "商品名称" in (content or "") or "productname" in text
    ):
        return True
    return False


def _matches_requirement_anchor_groups(path: str, content: str, requirement: str) -> bool:
    """判定页面是否覆盖需求里所有业务锚点（缺任何一个锚点都不算相关）。"""
    anchor_groups = _requirement_anchor_groups(requirement)
    if not anchor_groups:
        return True
    if "商品" in (requirement or "") and _is_product_pool_context(path, content) and "池" not in (requirement or ""):
        return False
    primary_product_list = _is_primary_product_list_context(path, content)
    combined_text = f"{path}\n{content or ''}".lower()
    for group in anchor_groups:
        if any(anchor.lower() in combined_text for anchor in group):
            continue
        # Some admin systems expose "零售商品列表" in the menu/URL, while the
        # source file is named as a generic commodity/product list.
        if "零售" in group and primary_product_list and "商品" in (requirement or ""):
            continue
        return False
    return True


def _humanize_frontend_page_path(path: str, content: str = "") -> Dict[str, str]:
    """把代码路径转成人类可读的展示名/菜单提示/路由提示，给前端候选页选择器用。"""
    normalized = str(path).replace("\\", "/").lstrip("/")
    text = f"{normalized}\n{content or ''}".lower()
    name_parts: List[str] = []
    if re.search(r"selfoperate|self_operate|self-operated|自营", text):
        name_parts.append("自营")
    if "selfoperatecommodity/commoditylist/list.vue" in normalized.lower():
        name_parts.append("零售")
    if re.search(r"retail|零售", text):
        name_parts.append("零售")
    if re.search(r"goods|product|commodity|sku|spu|商品", text):
        name_parts.append("商品")
    if re.search(r"pool|商品池", text):
        name_parts.append("池")
    if re.search(r"activity|活动", text):
        name_parts.append("活动")
    if re.search(r"order|订单", text):
        name_parts.append("订单")
    if re.search(r"category|分类|类目", text):
        name_parts.append("分类")
    if re.search(r"list|列表", text):
        name_parts.append("列表")
    if not name_parts:
        file_name = normalized.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        display_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", file_name).strip() or "现有页面"
    else:
        display_name = "".join(dict.fromkeys(name_parts))
        if not display_name.endswith(("页", "列表", "管理")):
            display_name = f"{display_name}页"

    route_parts = []
    if "selfoperatecommodity/commoditylist/list.vue" in normalized.lower():
        route_parts.append("商城管理 / 商品管理 / 零售商品列表")
        route_parts.append("/product/goods/list")
    elif "product" in text and "list" in text:
        route_parts.append("商品相关列表页")
    elif "activity" in text:
        route_parts.append("活动管理相关页面")
    elif "order" in text:
        route_parts.append("订单相关页面")

    return {
        "display_name": display_name,
        "menu_hint": "；".join(route_parts[:2]) if route_parts else display_name,
        "route_hint": route_parts[-1] if route_parts and route_parts[-1].startswith("/") else "",
        "developer_hint": normalized,
    }


def _frontend_existing_page_candidates(files: Dict[str, str], requirement: str, limit: int = 12) -> List[Dict[str, Any]]:
    """强业务词匹配：从项目前端文件挑出与需求高置信度相关的候选页面（含展示名/置信度/命中词）。"""
    strong_terms = _requirement_strong_business_terms(requirement)
    if not strong_terms:
        return []

    scored: List[Tuple[int, str, List[str], List[str]]] = []
    for path, content in files.items():
        normalized = str(path).replace("\\", "/").lstrip("/")
        if not _is_frontend_page_path(normalized):
            continue
        if not _matches_requirement_anchor_groups(normalized, content or "", requirement):
            continue
        path_text = normalized.lower()
        content_text = (content or "").lower()
        path_hits = [term for term in strong_terms if term.lower() in path_text]
        content_hits = [term for term in strong_terms if term.lower() in content_text]
        if not path_hits and len(content_hits) < 2:
            continue
        score = len(path_hits) * 4 + len(content_hits)
        if _is_primary_product_list_context(normalized, content or "") and "商品" in (requirement or ""):
            score += 12
        if (
            "商城" in (requirement or "")
            and ("零售" in (requirement or "") or "自营" in (requirement or ""))
            and "selfoperatecommodity/commoditylist/list.vue" in normalized.lower()
        ):
            score += 18
        if "supplychainmidplatform/" in normalized.lower() and "供应链" not in (requirement or ""):
            score -= 6
        if "platformcommodity/" in normalized.lower() and "平台商品" not in (requirement or ""):
            score -= 4
        scored.append((score, normalized, path_hits, content_hits))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not scored:
        return []
    top_score = max(score for score, _, _, _ in scored)
    candidates = []
    for score, path, path_hits, content_hits in scored[:limit]:
        confidence = round(min(0.98, max(0.35, score / max(top_score, 1) * 0.92)), 2)
        matched_terms = sorted(set(path_hits + content_hits))
        content = files.get(path, "")
        candidates.append({
            "path": path,
            "confidence": confidence,
            "matched_terms": matched_terms[:8],
            "reason": f"命中业务词：{', '.join(matched_terms[:6])}" if matched_terms else "命中项目页面路径",
            **_humanize_frontend_page_path(path, content),
        })
    return candidates


def _frontend_fallback_page_candidates(files: Dict[str, str], requirement: str, limit: int = 8) -> List[Dict[str, Any]]:
    """低置信候选：强业务词没匹配上时，用同义词+宽松打分，标记 uncertain 供人工确认。"""
    terms = _business_synonyms_for_terms(_requirement_match_terms(requirement))
    scored = []
    for path, content in files.items():
        normalized = str(path).replace("\\", "/").lstrip("/")
        if not _is_frontend_page_path(normalized):
            continue
        if not _matches_requirement_anchor_groups(normalized, content or "", requirement):
            continue
        haystack = f"{normalized}\n{content or ''}".lower()
        hits = [term for term in terms if term.lower() in haystack]
        score = len(hits)
        path_lower = normalized.lower()
        if "list" in path_lower or "列表" in (content or ""):
            score += 1
        scored.append((score, normalized, sorted(set(hits))[:6]))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    candidates = []
    for score, path, hits in scored[:limit]:
        content = files.get(path, "")
        candidates.append({
            "path": path,
            "confidence": round(min(0.52, 0.18 + score * 0.08), 2),
            "matched_terms": hits,
            "reason": "低置信候选，需要人工确认" if not hits else f"低置信候选，命中：{', '.join(hits[:4])}",
            "uncertain": True,
            **_humanize_frontend_page_path(path, content),
        })
    return candidates


async def get_frontend_page_candidates_for_requirement(project_id: str, requirement: str) -> Dict[str, Any]:
    """对外暴露：根据需求返回现有前端页面候选（含 requires_selection/uncertain 标记）。"""
    files = await _load_project_files_cached(project_id, "frontend")
    candidates = _frontend_existing_page_candidates(files, requirement)
    fallback_candidates: List[Dict[str, Any]] = []
    if _is_existing_feature_change_request(requirement) and not candidates:
        fallback_candidates = _frontend_fallback_page_candidates(files, requirement)
    return {
        "project_id": str(project_id or ""),
        "requires_selection": _is_existing_feature_change_request(requirement),
        "candidates": candidates or fallback_candidates,
        "uncertain": bool(fallback_candidates and not candidates),
    }


async def _load_project_context(project_id: str, project_type: str, requirement: str = "") -> str:
    """从 Generator 获取项目信息，从 Git 拉取关键文件，返回上下文文本。
    project_type: "frontend" 或 "backend"
    """
    files = await _load_project_files_cached(project_id, project_type)
    if not files:
        return ""

    # 筛选关键文件
    key_patterns = _get_key_file_patterns(project_type)
    key_files = {}
    for path, content in files.items():
        if any(path.endswith(p) or path.endswith("/" + p) for p in key_patterns):
            key_files[path] = content
    for path, content in _select_relevant_project_files(files, requirement):
        key_files[path] = content
    if not key_files:
        # 没匹配到关键文件，取前 3 个非空文件
        for path, content in list(files.items())[:3]:
            if content.strip():
                key_files[path] = content[:2000]

    # 构建上下文文本（总长度限制 6000 字符）
    sections = []
    total = 0
    if project_type == "frontend":
        relevant_pages = _frontend_relevant_existing_page_paths(files, requirement)
        existing_pages = relevant_pages or _frontend_existing_page_paths(files)
        if existing_pages:
            title = "## 与本需求相关的已确认前端页面路径" if relevant_pages else "## 已确认存在的前端页面路径"
            path_block = title + "\n" + "\n".join(f"- `{path}`" for path in existing_pages[:30])
            sections.append(path_block)
            total += len(path_block)
    for path, content in sorted(key_files.items()):
        chunk = f"### {path}\n```\n{content[:1500]}\n```\n"
        if total + len(chunk) > 6000:
            break
        sections.append(chunk)
        total += len(chunk)

    return "\n".join(sections) if sections else ""


def _get_key_file_patterns(project_type: str) -> list:
    """根据项目类型返回关键文件模式（前端：package.json/router/main.vue 等；后端：pom.xml/application.yml 等）。"""
    """根据项目类型返回关键文件模式"""
    if project_type == "frontend":
        return [
            "package.json",
            "src/main.js", "src/main.ts", "src/App.vue", "src/App.tsx",
            "src/router/index.js", "src/router/index.ts",
            "src/views/Home.vue", "src/pages/index.vue",
            "src/layouts/BasicLayout.vue", "src/layout/index.vue",
            "src/components/",
            "vite.config.js", "vue.config.js",
            ".env",
        ]
    else:
        return [
            "pom.xml", "build.gradle", "go.mod", "requirements.txt",
            "composer.json", "package.json",
            "src/main/resources/application.yml", "src/main/resources/application.properties",
            "src/main/java/",
            "config.yaml", "config.json",
        ]


def _project_file_read_limit(path: str) -> int:
    """按路径类型返回读取字节上限（业务页面给 30k，其余 5k）。"""
    normalized = str(path).replace("\\", "/").lstrip("/")
    if normalized.startswith(("src/views/", "src/pages/", "pages/")) and normalized.endswith((
        ".vue", ".tsx", ".jsx", ".js", ".ts", ".wxml"
    )):
        return 30000
    return 5000


async def _fetch_project_files_from_git(project_id: str) -> Dict[str, str]:
    """从 Generator 获取 Git 地址 → 浅克隆到工作区临时目录 → 用 file_reader skill 读文件。

    克隆走沙箱安全原语（剔除 admin 凭据 + 非 root 降权 / 容器隔离），失败返回 {}。
    """
    """从 Generator 获取项目 Git 地址，浅克隆并读取关键文件"""
    import httpx
    import tempfile

    tmp_dir = ""
    try:
        # 1. 从 Generator 获取项目信息
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://admin-generator:8082/generator/projects/{project_id}")
            if resp.status_code != 200:
                return {}
            proj_data = resp.json().get("data", {})

        repo_url = proj_data.get("repo_url", "")
        branch = proj_data.get("branch", "main")
        if not repo_url:
            return {}

        # 2. 浅克隆到临时目录（放共享工作区根，沙箱容器模式下 git clone 跑在隔离容器里，
        #    需与 admin-python 共享同一卷——/tmp 是每容器独立的，不可见）
        tmp_dir = tempfile.mkdtemp(prefix="pipe-ctx-", dir=settings.pipeline_workspace_root)
        token = await _get_git_token_for_project(project_id) or await _get_git_token_for_repo(repo_url)
        clone_url = _inject_git_credentials(repo_url, token)

        stdout, stderr, returncode = await _clone_project_repo(clone_url, branch, tmp_dir)
        if returncode != 0:
            logger.warning(f"Git clone failed for project {project_id}: {stderr.decode()[:200]}")
            return {}

        # 3. 读取项目文件必须通过 Skill，避免主流程直接碰文件内容。
        read_result = await skill_registry.execute(
            "file_reader",
            root_path=tmp_dir,
            max_bytes=5000,
            path_limits=[
                {
                    "prefixes": ["src/views/", "src/pages/", "pages/"],
                    "suffixes": [".vue", ".tsx", ".jsx", ".js", ".ts", ".wxml"],
                    "max_bytes": 30000,
                }
            ],
        )
        files = read_result.output.get("files", {}) if read_result.status == SkillStatus.COMPLETED else {}

        logger.info(f"Loaded {len(files)} files from project {project_id}")
        return files

    except Exception as e:
        logger.warning(f"Failed to load project context for {project_id}: {e}")
        return {}
    finally:
        if tmp_dir:
            await _cleanup_temp_path(tmp_dir)


def _is_safe_git_url(repo_url: str) -> tuple:
    """SSRF guard: allow only http(s) and reject loopback/private/link-local/metadata hosts."""
    import ipaddress
    from urllib.parse import urlparse
    try:
        parsed = urlparse(repo_url)
    except Exception:
        return False, "invalid URL"
    if parsed.scheme not in ("https", "http"):
        return False, f"scheme '{parsed.scheme}' not allowed"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "missing host"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"private/loopback IP {host} not allowed"
    except ValueError:
        if host in ("localhost", "metadata.google.internal") or host.endswith(".internal"):
            return False, f"host '{host}' not allowed"
    return True, ""


async def _clone_project_repo(clone_url: str, branch: str, tmp_dir: str):
    """Clone a repo, falling back to the remote default branch when stored branch is stale."""
    ok, reason = _is_safe_git_url(clone_url)
    if not ok:
        logger.warning("Blocked git clone to unsafe host: %s", reason)
        return b"", reason.encode(errors="ignore")[:200], 128
    from app.services.sandbox_security import run_sandboxed_with_stderr
    # 安全（防越权）：git clone 跑不可信代码——走统一安全原语（剔除 admin 凭据 + 非 root 降权 / 容器隔离）。
    # 此前裸继承 os.environ（含 GIT_TOKEN）。容器模式下 docker logs 天然分离 stdout/stderr（保真错误流）。
    rc, stdout, stderr = await run_sandboxed_with_stderr(
        ["git", "clone", "--depth", "1", "--branch", branch, clone_url, tmp_dir],
        timeout=60,
    )
    if rc == 0 or not branch:
        return stdout, stderr, rc

    logger.warning(
        "Git clone branch %s failed, retrying default branch: %s",
        branch,
        stderr.decode(errors="ignore")[:200],
    )
    await _cleanup_temp_path(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)

    rc, stdout, stderr = await run_sandboxed_with_stderr(
        ["git", "clone", "--depth", "1", clone_url, tmp_dir],
        timeout=60,
    )
    return stdout, stderr, rc


def _inject_git_credentials(repo_url: str, token: str = "") -> str:
    """为 Git URL 注入凭证（支持 http/https）"""
    if not token:
        import os
        token = os.environ.get("GIT_TOKEN", "")
    if not token:
        return repo_url

    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://oauth2:{token}@", 1)
    elif repo_url.startswith("http://"):
        return repo_url.replace("http://", f"http://oauth2:{token}@", 1)
    return repo_url


async def _get_git_token_for_repo(repo_url: str) -> str:
    """根据仓库 URL 从数据库查找对应的 Git token"""
    from sqlalchemy import text
    async with async_session_maker() as session:
        # 先按 base_url 匹配
        result = await session.execute(
            text("SELECT platform, access_token, base_url FROM sys_git_config WHERE status = 1 LIMIT 10")
        )
        for row in result.fetchall():
            platform, access_token, base_url = row[0], row[1], row[2] or ""
            if not access_token:
                continue
            if base_url and base_url in repo_url:
                return access_token
            if platform == "gitlab" and "gitlab" in repo_url:
                return access_token
            if platform == "github" and "github" in repo_url:
                return access_token
    return ""


async def _get_git_token_for_project(project_id: str) -> str:
    """从项目的 git_config_id 获取 Git token"""
    import httpx
    from sqlalchemy import text
    try:
        # 先从 Generator 获取项目的 git_config_id
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://admin-generator:8082/generator/projects/{project_id}")
            if resp.status_code != 200:
                return ""
            proj = resp.json().get("data", {})
        git_config_id = proj.get("git_config_id")
        if not git_config_id:
            # fallback: 用 repo_url 匹配
            repo_url = proj.get("repo_url", "")
            if repo_url:
                return await _get_git_token_for_repo(repo_url)
            return ""

        # 从数据库取 token
        async with async_session_maker() as session:
            result = await session.execute(
                text("SELECT access_token FROM sys_git_config WHERE id = :id AND status = 1"),
                {"id": int(git_config_id)}
            )
            row = result.fetchone()
            return row[0] if row and row[0] else ""
    except Exception as e:
        logger.warning(f"Failed to get git token for project {project_id}: {e}")
        return ""
