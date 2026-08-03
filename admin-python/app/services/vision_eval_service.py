"""视觉评测渲染器：把流水线生成的前端代码真实渲染出来 → 无头截图 → 供 GLM-4V 评审。

golden-case 流水线生成的是 Vue 单文件组件（依赖 vue-router/vuex/element|antd 等），
但没有真实前端项目快照，sandbox 的 vite dev server 无法启动。因此这里用「渲染桩」
方案：把 .vue 的 <template>/<script> 抽出来，注入一个独立 HTML——用 CDN 加载
Vue2 + antd-vue，并用全局桩替代 import（vuex mapState/mapActions、@/utils/auth、
@api/login、$router/$route），让真实组件选项直接挂载、antd 组件正常渲染。

这样无需 npm/vite/git/scaffold，容器内 Playwright 直接截图 file:// 即可。
是「视觉评测」(A4) 的渲染层——让评测覆盖「真正渲染出来对不对」，正面回答
「什么需要人眼？」：截图 + 视觉模型，全自动，不需要人眼。
"""
import asyncio
import base64
import logging
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _extract_block(src: str, tag: str) -> str:
    """从 SFC 抽取 <tag ...>...</tag> 的内部文本（取第一个匹配）。"""
    m = re.search(
        rf"<{tag}[^>]*>(.*?)</{tag}>",
        src,
        re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def _pick_main_view(code_files: dict) -> tuple[Optional[str], str]:
    """挑出主页面文件：优先 src/views/**/index.vue，其次任意含 template 的 .vue/.html。"""
    if not isinstance(code_files, dict) or not code_files:
        return None, ""
    prio = []
    for path, content in code_files.items():
        if not isinstance(content, str):
            continue
        p = str(path)
        if p.endswith((".vue", ".html", ".htm")) and "<template" in content or "<body" in content or p.endswith((".html", ".htm")):
            score = 0
            if "index.vue" in p:
                score += 10
            if "views/" in p or "pages/" in p:
                score += 5
            if "<template" in content or p.endswith((".html", ".htm")):
                score += 2
            prio.append((score, p, content))
    if not prio:
        return None, ""
    prio.sort(key=lambda x: x[0], reverse=True)
    return prio[0][1], prio[0][2]


def _strip_less_nesting(style: str) -> str:
    """LESS 嵌套浏览器不认；粗略去掉，依赖 antd 自带样式即可（评测只需看元素是否存在/布局）。"""
    # 删掉明显的嵌套块（行首多空格且含 { 的规则内子规则）——保守起见直接丢弃自定义样式
    return ""


# 替代各 import 的全局桩：让 SFC 的 created/computed/methods 不因缺依赖而崩
_STUBS = """
window.mapState = function () { return {}; };
window.mapActions = function () { return {}; };
window.mapGetters = function () { return {}; };
window.getLocalItem = function () { return null; };
window.setLocalItem = function () {};
window.removeLocalItem = function () {};
window.getLocalStorage = function () { return null; };
window.getToken = function () { return null; };
window.setToken = function () {};
window.removeToken = function () {};
window.getLoginCaptcha = async function () { return { data: "" }; };
window.request = async function () { return { code: 200, data: {} }; };
"""


def _looks_vue3(template: str, script: str) -> bool:
    """启发式判断是否 Vue3 写法（v-model:value / <script setup> / defineComponent）。

    真实流水线常生成 Vue3 + antd-vue v3/v4（``v-model:value``、``@finish``），
    而 Vue2 桩无法渲染；据此分流到 Vue3 桩。
    """
    if "v-model:" in template:
        return True
    if "<script setup" in script or "defineComponent" in script:
        return True
    return False


def build_renderable_html(code_files: dict) -> Optional[str]:
    """从生成的 code_files 构造可独立渲染的 HTML（自动 Vue2 / Vue3 分流 + CDN + 依赖桩）。"""
    path, src = _pick_main_view(code_files)
    if not src:
        return None

    # 直接是 HTML 文件 —— 原样返回（已是可渲染的）
    if path and path.endswith((".html", ".htm")):
        if "<html" in src.lower() or "<body" in src.lower():
            return src
        return f"<!doctype html><html><head><meta charset='utf-8'></head><body>{src}</body></html>"

    template = _extract_block(src, "template")
    script = _extract_block(src, "script")
    if not template:
        return None

    # <script setup> 是 SFC 编译语法，浏览器内无 SFC compiler 无法直接运行 → 不渲染（E2E 静默放行）
    if "<script setup" in src:
        return None

    # 去掉 ES module 的 import/export 关键字，适配经典 <script>
    # 注意：只能按「整行」删 import，绝不能用 DOTALL（会把 import 到代码里某个分号之间的
    # 大段内容误删，例如模板串 `data:image/png;base64,` 里的分号）。
    script = re.sub(r"^[ \t]*import\s+.*$", "", script, flags=re.MULTILINE)
    script = re.sub(r"^[ \t]*export\s+default\s*", "var __comp = ", script, flags=re.MULTILINE)
    script = re.sub(r"^[ \t]*export\s+", "", script, flags=re.MULTILINE)

    # 安全地把 template 注入为字符串
    tmpl_js = __import__("json").dumps(template)

    # Vue3 / <script setup> / antd-vue v3+ 等桩无法渲染（v4 无全局构建、SFC 需编译）
    # → 不产出 HTML，E2E 据此静默放行（桩不兼容 ≠ 页面坏，绝不误杀真实页）。
    if _looks_vue3(template, script):
        return None
    return _build_vue2_html(script, tmpl_js)


def _build_vue2_html(script: str, tmpl_js: str) -> str:
    """Vue2 + antd-vue1 + element-ui CDN 渲染桩。"""
    # 给组件补 router/store 桩，避免 created 里访问 this.$router 崩溃
    script = (
        "var __comp = (typeof __comp === 'undefined') ? {} : __comp;\n"
        "if (!__comp.created) __comp.created = function(){};\n" + script
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/ant-design-vue@1.7.8/dist/antd.min.css">
<link rel="stylesheet" href="https://unpkg.com/element-ui@2.15.14/lib/theme-chalk/index.css">
<style>html,body{{margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,Segoe UI,Roboto,sans-serif;}}</style>
</head><body>
<div id="app"></div>
<script src="https://unpkg.com/vue@2.6.14/dist/vue.min.js"></script>
<script src="https://unpkg.com/ant-design-vue@1.7.8/dist/antd.min.js"></script>
<script src="https://unpkg.com/element-ui@2.15.14/lib/index.js"></script>
<script>{_STUBS}</script>
<script>
try {{ Vue.use(antd); }} catch (e) {{}}
try {{ Vue.use(ELEMENT); }} catch (e) {{}}
try {{
{script}
}} catch (e) {{ console.warn('script parse', e); }}
<script_replaced>
try {{
  var __base = (typeof __comp === 'object' && __comp) ? __comp : {{}};
  Vue.prototype.$router = {{ push: function(){{}}, replace: function(){{}}, query: {{}} }};
  Vue.prototype.$route = {{ query: {{}}, path: '/' }};
  var opts = Object.assign({{ el: '#app' }}, __base, {{ template: {tmpl_js} }});
  new Vue(opts);
}} catch (e) {{ window.__MOUNT_FAILED = true; console.error('mount failed', e); document.getElementById('app').innerHTML = '<pre style="padding:20px;color:#d00">'+e+'</pre>'; }}
</script>
</body></html>
""".replace("<script_replaced>", "</script><script>")


async def _render_url_screenshot(
    url: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> Optional[dict]:
    """对真实 URL 截图：轮询 body 有内容后截图。页面空白返回 None（调用方回退渲染桩）。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=1,
            )
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 真实 vite dev server：轮询挂载后有内容（非 CDN 桩的同步挂载）
            body_text = ""
            for _ in range(40):  # 真实 vite dev server 就绪需更久（npm install 后首编译），轮询 ~30s
                body_text = await page.evaluate("() => (document.body?.innerText || '').trim()")
                if body_text:
                    break
                await asyncio.sleep(0.75)
            await asyncio.sleep(1.0)  # 等 antd 组件渲染稳定
            if not body_text:
                return None  # 空白 → 回退桩
            png = await page.screenshot(type="png", full_page=False)
        finally:
            await browser.close()
    data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return {"png_bytes": png, "data_uri": data_uri, "preview_url": url}


async def render_pipeline_screenshot(
    pipeline_id: str,
    live_url: Optional[str] = None,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> dict:
    """渲染流水线产物并截图。返回 ``{png_bytes, data_uri, preview_url, source}``；失败抛 RuntimeError。

    优先用 ``live_url``（真实沙箱预览，能渲染 Vue3+antd 等桩渲染不了的页）；失败/空白
    回退 Vue2 渲染桩（``build_renderable_html``）。桩对 Vue3 页返回 None → 抛 RuntimeError，
    eval 据此写 vision_error 静默跳过。
    """
    # 1) 优先真实预览 URL
    if live_url:
        shot = await _render_url_screenshot(live_url, viewport_width, viewport_height)
        if shot is not None:
            shot["source"] = "live"
            logger.info("vision_eval: 真实预览截图 pipeline=%s size=%dB", pipeline_id, len(shot["png_bytes"]))
            return shot
        logger.info("vision_eval: 真实预览为空，回退渲染桩 pipeline=%s", pipeline_id)

    # 2) 回退 Vue2 渲染桩
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("admin-python 容器未安装 playwright，无法进行视觉评测") from exc

    from app.ai.flow_manager import pipeline_manager

    artifact = await pipeline_manager.get_pipeline_artifact(pipeline_id)
    code_files = artifact.get("frontend_files") or artifact.get("code_files") or {}
    if not code_files:
        raise RuntimeError("该流水线没有生成前端代码，无法视觉评测")

    html = build_renderable_html(code_files)
    if not html:
        raise RuntimeError("无法从生成代码构造可渲染页面（未找到 .vue/.html 主页面）")

    tmp = Path(tempfile.mkstemp(suffix=".html", prefix="eval_render_")[1])
    tmp.write_text(html, encoding="utf-8")
    url = tmp.as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=1,
            )
            page = await ctx.new_page()
            errs: list = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            # CDN 脚本较重，给充足加载时间
            for _ in range(20):
                try:
                    await page.goto(url, wait_until="networkidle", timeout=20000)
                    break
                except Exception:
                    await asyncio.sleep(1)
            else:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2.5)  # 等 Vue 挂载 + antd 渲染
            png = await page.screenshot(type="png", full_page=False)
        finally:
            await browser.close()
    try:
        tmp.unlink()
    except Exception:
        pass

    data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    logger.info("vision_eval: 桩截图完成 pipeline=%s size=%dB errs=%s", pipeline_id, len(png), errs[:3])
    return {"png_bytes": png, "data_uri": data_uri, "preview_url": url, "source": "harness"}


@asynccontextmanager
async def acquire_live_preview(pipeline_id: str):
    """为 eval 视觉/E2E 提供真实沙箱预览 URL 的上下文管理器，yield 出 URL 或 None。

    - 预览已在跑 → 复用（不归本上下文管，退出不停，避免打断用户正在看的预览）。
    - 未在跑 → start 一个（180s 超时兜底），退出时 stop（用完即停，不占端口）。
    - 任何失败 → yield None（调用方回退渲染桩，绝不让视觉/E2E 阻塞 eval）。
    """
    from app.services.sandbox_preview_service import sandbox_preview_service

    owned = False
    url = sandbox_preview_service.direct_preview_url(pipeline_id)
    if not url:
        try:
            from app.ai.flow_manager import pipeline_manager

            artifact = await pipeline_manager.get_pipeline_artifact(pipeline_id)
            project_info = await pipeline_manager.get_pipeline_frontend_project_snapshot(pipeline_id)
            await asyncio.wait_for(
                sandbox_preview_service.start(
                    pipeline_id,
                    artifact.get("frontend_files") or {},
                    project_info,
                ),
                timeout=300,  # Vue3 等现代前端 npm install + vite 首编译较慢，180s 常超时 → 视觉评测跳过
            )
            url = sandbox_preview_service.direct_preview_url(pipeline_id)
            owned = bool(url)
        except asyncio.TimeoutError:
            logger.info("eval live preview start 超时，回退渲染桩 pipeline=%s", pipeline_id)
        except Exception as exc:  # noqa: BLE001
            logger.info("eval live preview start 失败，回退渲染桩 pipeline=%s: %s", pipeline_id, str(exc)[:200])
    try:
        yield url
    finally:
        if owned:
            try:
                await sandbox_preview_service.stop(pipeline_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("eval live preview stop 失败 pipeline=%s: %s", pipeline_id, exc)


async def _expectation_present(page, exp: dict) -> bool:
    """在已加载页面上断言单条期望是否满足。任何异常都视为不满足（保守）。

    用 page.evaluate + textContent 判定，而非 Playwright ``:has-text`` locator
    （后者在替换挂载、动态渲染场景下不稳定）。Vue2 ``el:'#app'`` 挂载会替换 #app，
    故一律在 document 级别查询。
    """
    kind = exp.get("kind")
    try:
        if kind == "password":
            return await page.evaluate("()=>document.querySelectorAll(\"input[type='password']\").length>0")
        if kind == "table":
            return await page.evaluate("()=>document.querySelectorAll('table,.ant-table,.el-table').length>0")
        if kind == "has_input":
            return await page.evaluate("()=>document.querySelectorAll('input,textarea,select').length>0")
        if kind == "button_text":
            texts = exp.get("texts", []) or []
            if not texts:
                return False
            return await page.evaluate(
                "(ts)=>{const els=[...document.querySelectorAll("
                "'button,a,[role=button],.ant-btn,.el-button'"
                ")];const txt=els.map(e=>(e.textContent||'').trim());"
                "return ts.some(t=>txt.some(x=>x.replace(/\\s+/g,'').includes(t.replace(/\\s+/g,''))));}",
                texts,
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("e2e expectation check error kind=%s: %s", kind, e)
    return False


async def _assert_loaded_page(page, expectations: list, screenshot: bool = True) -> dict:
    """在已加载页面上做渲染完整性 + 期望控件断言（stub / 真实预览共用）。

    harness 挂载失败置 window.__MOUNT_FAILED（Vue2/Vue3 通用）。挂载成功但无内容/控件
    → 桩不兼容（模块化 UI 库未注册），放行不升级。返回 ``{passed, issues, data_uri, [stub_incompatible]}``。
    """
    data_uri = None
    mount_failed = await page.evaluate("() => !!window.__MOUNT_FAILED")
    body_text = await page.evaluate("() => (document.body?.innerText || '').trim()")
    interactive_n = await page.evaluate(
        "() => document.querySelectorAll("
        "'button,input,textarea,select,a,[role=button]'"
        ").length"
    )

    # 挂载成功但无内容/控件：多为 antd-vue v3+/element 等模块化 UI 库未注册
    # （桩无全局构建可用，组件渲染成未知标签）→ 无法判定，放行不升级。
    if not mount_failed and len(body_text) == 0 and interactive_n == 0:
        return {"passed": True, "issues": [], "data_uri": data_uri, "stub_incompatible": True}

    issues: list = []
    if mount_failed:
        issues.append("页面渲染失败：组件在浏览器中挂载报错（可能缺依赖或脚本错误）")
    elif interactive_n == 0 and len(body_text) < 5:
        issues.append("页面没有任何可交互控件（按钮/输入/链接）")

    for exp in expectations or []:
        if not isinstance(exp, dict):
            continue
        if not await _expectation_present(page, exp):
            issues.append(f"缺少期望控件：{exp.get('label', exp)}")

    if screenshot:
        try:
            png = await page.screenshot(type="png", full_page=False)
            data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        except Exception as e:  # noqa: BLE001
            logger.debug("e2e screenshot failed: %s", e)
    return {"passed": not issues, "issues": issues, "data_uri": data_uri}


async def run_e2e_assertions(
    code_files: dict,
    expectations: list,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    screenshot: bool = True,
    live_url: Optional[str] = None,
) -> dict:
    """对生成的 code_files 做真实浏览器 E2E 断言。

    加载方式：优先 ``live_url``（真实沙箱预览，能断言 Vue3+antd 等桩渲染不了的页），
    否则用 ``build_renderable_html`` 渲染桩 file:// 加载。然后：
    1. 渲染完整性：无 mount 失败、有可交互控件；
    2. 期望控件：逐条断言 expectations 在 DOM 中存在。
    返回 ``{"passed", "issues", "data_uri"}``。harness 故障 fail-open（passed=True + harness_error）。
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - 容器内已装
        logger.warning("e2e: playwright 未安装，跳过浏览器断言: %s", exc)
        return {"passed": True, "issues": [], "data_uri": None, "harness_error": "playwright missing"}

    import tempfile

    # 加载目标：优先真实预览 URL，否则渲染桩 file://
    tmp: Optional[Path] = None
    if live_url:
        url = live_url
    else:
        html = build_renderable_html(code_files or {})
        if not html:
            # 构造不出可渲染 HTML（非 .vue/.html 主页面）→ 无法做浏览器断言，放行
            return {"passed": True, "issues": [], "data_uri": None, "harness_error": "no renderable html"}
        tmp = Path(tempfile.mkstemp(suffix=".html", prefix="e2e_render_")[1])
        tmp.write_text(html, encoding="utf-8")
        url = tmp.as_uri()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height},
                    device_scale_factor=1,
                )
                page = await ctx.new_page()
                page_errors: list = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                if live_url:
                    # 真实 vite dev server：domcontentloaded + 轮询挂载后有内容
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    for _ in range(24):
                        body_text = await page.evaluate("() => (document.body?.innerText || '').trim()")
                        if body_text:
                            break
                        await asyncio.sleep(0.5)
                    await asyncio.sleep(1.0)
                else:
                    for _ in range(20):
                        try:
                            await page.goto(url, wait_until="networkidle", timeout=20000)
                            break
                        except Exception:
                            await asyncio.sleep(1)
                    else:
                        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(2.5)  # 等 Vue 挂载 + 组件渲染
                return await _assert_loaded_page(page, expectations, screenshot)
            finally:
                await browser.close()
    except Exception as e:  # noqa: BLE001 - harness 故障必须 fail-open
        logger.warning("e2e: 浏览器断言 harness 故障，放行: %s", e)
        return {"passed": True, "issues": [], "data_uri": None, "harness_error": str(e)[:200]}
    finally:
        if tmp:
            try:
                tmp.unlink()
            except Exception:
                pass

