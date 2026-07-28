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
import base64
import logging
import re
import tempfile
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


def build_renderable_html(code_files: dict) -> Optional[str]:
    """从生成的 code_files 构造可独立渲染的 HTML（Vue2 + antd-vue CDN + 依赖桩）。"""
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

    # 去掉 ES module 的 import/export 关键字，适配经典 <script>
    # 注意：只能按「整行」删 import，绝不能用 DOTALL（会把 import 到代码里某个分号之间的
    # 大段内容误删，例如模板串 `data:image/png;base64,` 里的分号）。
    script = re.sub(r"^[ \t]*import\s+.*$", "", script, flags=re.MULTILINE)
    script = re.sub(r"^[ \t]*export\s+default\s*", "var __comp = ", script, flags=re.MULTILINE)
    script = re.sub(r"^[ \t]*export\s+", "", script, flags=re.MULTILINE)

    # 给组件补 router/store 桩，避免 created 里访问 this.$router 崩溃
    comp_preamble = (
        "var __comp = (typeof __comp === 'undefined') ? {} : __comp;\n"
        "if (!__comp.created) __comp.created = function(){};\n"
    )

    # 安全地把 template 注入为字符串
    tmpl_js = __import__("json").dumps(template)

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
  // router/store 桩
  Vue.prototype.$router = {{ push: function(){{}}, replace: function(){{}}, query: {{}} }};
  Vue.prototype.$route = {{ query: {{}}, path: '/' }};
  var opts = Object.assign({{ el: '#app' }}, __base, {{ template: {tmpl_js} }});
  new Vue(opts);
}} catch (e) {{ console.error('mount failed', e); document.getElementById('app').innerHTML = '<pre style=padding:20px;color:#d00>'+e+'</pre>'; }}
</script>
</body></html>
""".replace("<script_replaced>", "</script><script>")


async def render_pipeline_screenshot(
    pipeline_id: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> dict:
    """渲染流水线产物并截图。返回 ``{png_bytes, data_uri, preview_url, source}``；失败抛 RuntimeError。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("admin-python 容器未安装 playwright，无法进行视觉评测") from exc

    from app.ai.eval_judge import extract_pipeline_output  # noqa: F401  (kept for parity)
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

    import asyncio

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
    logger.info("vision_eval: 截图完成 pipeline=%s size=%dB errs=%s", pipeline_id, len(png), errs[:3])
    return {"png_bytes": png, "data_uri": data_uri, "preview_url": url, "source": "harness"}
