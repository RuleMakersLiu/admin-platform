"""Phase 4a：无项目快照时从生成代码脚手架 Vue3 vite 宿主 + import shim 的离线单测。"""
from pathlib import Path

from app.services.sandbox_preview_service import SandboxPreviewService


def _svc():
    return SandboxPreviewService()


# ---------- Vue3 检测 ----------

def test_generated_code_is_vue3_detects_v_model_value():
    files = {"src/views/login/index.vue": '<a-input v-model:value="form.u" />'}
    assert _svc()._generated_code_is_vue3(files) is True


def test_generated_code_is_vue3_detects_script_setup():
    files = {"src/views/x.vue": "<script setup>\nconst a = 1\n</script>"}
    assert _svc()._generated_code_is_vue3(files) is True


def test_generated_code_is_vue2_when_no_markers():
    files = {"src/views/x.vue": '<input v-model="x"/><script>export default {}</script>'}
    assert _svc()._generated_code_is_vue3(files) is False


# ---------- web Vue 判定 ----------

def test_looks_like_web_vue_true_for_vue():
    assert _svc()._looks_like_web_vue({"src/views/login/index.vue": "x"}) is True


def test_looks_like_web_vue_false_when_empty():
    assert _svc()._looks_like_web_vue({}) is False


# ---------- 主组件选取 ----------

def test_pick_main_vue_path_prefers_views_index():
    files = {
        "src/components/Foo.vue": "x",
        "src/views/login/index.vue": "y",
        "src/views/list/detail.vue": "z",
    }
    assert _svc()._pick_main_vue_path(files) == "src/views/login/index.vue"


# ---------- import shim ----------

def test_write_import_shims_for_missing_modules(tmp_path):
    files = {
        # 生成的（应靠 @→src 解析，不写 shim）
        "src/api/foo.js": "import request from '@/utils/request'\nexport const getList = () => request({url:'/list'})",
        # 引用未生成的项目内模块
        "src/views/login/index.vue": (
            "<template><div>{{ msg }}</div></template>\n"
            "<script>\n"
            "import { getList } from '@/api/foo'\n"
            "import request from '@/utils/request'\n"
            "import { STable } from '@/components'\n"
            "import { TOKEN } from '@/store/mutation-types'\n"
            "export default { data(){return {msg:'x'}} }\n"
            "</script>"
        ),
    }
    svc = _svc()
    svc._write_import_shims(tmp_path, files)

    # 未生成的 → 写了 shim
    assert (tmp_path / "src" / "utils" / "request.js").exists()
    assert "request" in (tmp_path / "src" / "utils" / "request.js").read_text(encoding="utf-8")
    assert (tmp_path / "src" / "components.js").exists()
    assert "STable" in (tmp_path / "src" / "components.js").read_text(encoding="utf-8")
    assert (tmp_path / "src" / "store" / "mutation-types.js").exists()
    # 生成的 @/api/foo → 不写 shim（靠 alias 解析）
    assert not (tmp_path / "src" / "api" / "foo.js").exists()


# ---------- Vue3 scaffold 端到端 ----------

def test_ensure_vite_scaffold_vue3(tmp_path):
    files = {"src/views/login/index.vue": '<a-input v-model:value="form.u" />\n<script>export default {}</script>'}
    svc = _svc()
    svc._ensure_vite_scaffold(tmp_path, "pipe_test", files)

    pkg = (tmp_path / "package.json").read_text(encoding="utf-8")
    assert '"vue": "^3.4.38"' in pkg
    assert '"ant-design-vue": "^4.2.3"' in pkg
    assert '"dev": "vite"' in pkg

    vite_cfg = (tmp_path / "vite.config.js").read_text(encoding="utf-8")
    assert "@vitejs/plugin-vue" in vite_cfg
    assert "alias" in vite_cfg

    main_ts = (tmp_path / "src" / "main.ts").read_text(encoding="utf-8")
    assert "createApp" in main_ts
    assert "app.use(Antd)" in main_ts
    assert "./views/login/index.vue" in main_ts  # 导入主组件相对路径

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "/src/main.ts" in index_html


def test_ensure_vite_scaffold_vue2_when_no_vue3_markers(tmp_path):
    files = {"src/views/x.vue": '<input v-model="x"/><script>export default {}</script>'}
    svc = _svc()
    svc._ensure_vite_scaffold(tmp_path, "pipe_test", files)
    pkg = (tmp_path / "package.json").read_text(encoding="utf-8")
    assert '"vue": "^2.7.16"' in pkg
    assert (tmp_path / "src" / "main.js").exists()
