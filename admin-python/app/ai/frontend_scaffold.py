"""前端 Spec → 代码模板渲染（确定性，不调 LLM）。

LLM 只输出页面规格 JSON（~2000 token，30-60s），本模块将其渲染成完整 antd-vue 3.x .vue 文件 +
API .js 文件。取代旧模式「LLM 直接输出完整 .vue 文件」（~16000 token，>900s 超时）。

参照 backend_scaffold.py 的纯函数范式：输入 spec dict，输出 {path: content}。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def render_spec_to_code_files(spec: dict) -> Dict[str, str]:
    """页面规格 JSON → 完整 .vue + .js 文件。纯函数，确定性。

    输入 spec 形如：
      {"pages": [{path, title, components: [{type, ...}]}],
       "api_modules": [{path, base_url, endpoints: [{name, method, url}]}]}

    输出 {path: content}，可直接写入项目、被 sandbox 预览消费。
    """
    if not isinstance(spec, dict):
        return {}
    files: Dict[str, str] = {}
    for page in spec.get("pages") or []:
        if not isinstance(page, dict) or not page.get("path"):
            continue
        try:
            files[page["path"]] = _render_vue_page(page)
        except Exception as exc:
            logger.warning("frontend_scaffold: 渲染页面 %s 失败: %s", page.get("path"), exc)
    for api in spec.get("api_modules") or []:
        if not isinstance(api, dict) or not api.get("path"):
            continue
        try:
            files[api["path"]] = _render_api_module(api)
        except Exception as exc:
            logger.warning("frontend_scaffold: 渲染 API %s 失败: %s", api.get("path"), exc)
    logger.info("frontend_scaffold: 渲染 %d 页面 + %d API 模块 → %d 文件",
                len(spec.get("pages") or []), len(spec.get("api_modules") or []), len(files))
    return files


# ==================== 页面渲染 ====================

def _render_vue_page(page: dict) -> str:
    """单个页面 spec → 完整 .vue 文件（template + script setup + style）。"""
    components = page.get("components") or []
    title = page.get("title", page.get("path", "").split("/")[-1].replace(".vue", ""))
    api_path = _guess_api_import_path(page)

    # 渲染各组件的 template 段 + 收集 script 需要的 state/methods
    template_parts: List[str] = []
    state_lines: List[str] = []
    method_lines: List[str] = []
    import_lines: List[str] = []
    form_fields: List[dict] = []
    table_columns: List[dict] = []

    for comp in components:
        ctype = comp.get("type", "")
        if ctype == "search_bar":
            template_parts.append(_tpl_search_bar(comp))
            state_lines.extend(_state_search_bar(comp))
            method_lines.extend(_methods_search_bar())
        elif ctype == "data_table":
            template_parts.append(_tpl_data_table(comp))
            state_lines.extend(_state_data_table(comp))
            method_lines.extend(_methods_data_table(comp))
            table_columns = comp.get("columns") or []
        elif ctype == "modal_form":
            template_parts.append(_tpl_modal_form(comp))
            state_lines.extend(_state_modal_form(comp))
            method_lines.extend(_methods_modal_form(comp))
            form_fields = comp.get("fields") or []
        elif ctype == "stats_cards":
            template_parts.append(_tpl_stats_cards(comp))
            state_lines.extend(_state_stats_cards(comp))
        elif ctype == "description":
            template_parts.append(_tpl_description(comp))
            state_lines.extend(_state_description(comp))
        elif ctype == "tabs":
            template_parts.append(_tpl_tabs(comp))

    # API import
    if api_path:
        api_names = _collect_api_names(method_lines)
        if api_names:
            import_lines.append(f"import {{ {', '.join(api_names)} }} from '{api_path}'")

    # 组装 script
    script = _assemble_script(title, state_lines, method_lines, import_lines, table_columns, form_fields)
    template = f"""<template>
  <div class="page-container">
{''.join(t for t in template_parts)}
  </div>
</template>"""
    style = """<style scoped>
.page-container { padding: 24px; }
.search-bar { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
.toolbar { margin-bottom: 16px; }
</style>"""
    return f"{template}\n\n{script}\n\n{style}"


# ==================== 组件模板渲染器 ====================

def _tpl_search_bar(comp: dict) -> str:
    fields = comp.get("fields") or []
    parts = []
    for f in fields:
        label = f.get("label", f.get("name", ""))
        name = f.get("name", "")
        placeholder = f.get("placeholder", f"请输入{label}")
        inp = f.get("input", "text")
        if inp == "select":
            opts = f.get("options") or []
            opt_tags = "\n              ".join(
                f'<a-select-option value="{o.get("value", o) if isinstance(o, dict) else o}">'
                f'{o.get("label", o) if isinstance(o, dict) else o}</a-select-option>'
                for o in opts
            )
            parts.append(f"""      <a-select v-model:value="searchForm.{name}" placeholder="{placeholder}" style="width: 160px" allowClear>
              {opt_tags}
            </a-select>""")
        elif inp == "date":
            parts.append(f'      <a-date-picker v-model:value="searchForm.{name}" placeholder="{placeholder}" />')
        else:
            parts.append(f'      <a-input v-model:value="searchForm.{name}" placeholder="{placeholder}" style="width: 200px" allowClear />')
    parts.append('      <a-button type="primary" @click="handleSearch">搜索</a-button>')
    parts.append('      <a-button @click="handleReset">重置</a-button>')
    return '\n    <div class="search-bar">\n' + "\n".join(parts) + '\n    </div>\n'


def _tpl_data_table(comp: dict) -> str:
    cols = comp.get("columns") or []
    row_actions = comp.get("row_actions") or []
    toolbar = comp.get("toolbar") or []
    pagination = comp.get("pagination", True)

    # toolbar 按钮
    toolbar_html = ""
    if "create" in toolbar:
        toolbar_html = '    <div class="toolbar">\n      <a-button type="primary" @click="handleAdd">新增</a-button>\n    </div>\n'

    # 行操作列
    action_tags = []
    if "edit" in row_actions:
        action_tags.append('<a-button type="link" size="small" @click="handleEdit(record)">编辑</a-button>')
    if "delete" in row_actions:
        action_tags.append('<a-popconfirm title="确认删除？" @confirm="handleDelete(record)">\n        <a-button type="link" size="small" danger>删除</a-button>\n      </a-popconfirm>')
    action_col = ""
    if action_tags:
        action_col = f"""
      <template #bodyCell="{{ column, record }}">
        <template v-if="column.key === 'action'">
          {''.join(action_tags)}
        </template>
      </template>"""

    pag = ':pagination="pagination"' if pagination else ':pagination="false"'
    return f"""{toolbar_html}
    <a-table
      :columns="columns"
      :data-source="dataSource"
      :loading="loading"
      {pag}
      rowKey="id"
    >{action_col}
    </a-table>
    <a-modal v-model:open="modalVisible" :title="modalTitle" @ok="handleSubmit" :confirmLoading="submitLoading">
      <a-form :model="formState" :label-col="{{ span: 6 }}" :wrapper-col="{{ span: 16 }}">
{_form_items(comp.get('_form_fields') or [])}
      </a-form>
    </a-modal>"""


def _tpl_modal_form(comp: dict) -> str:
    fields = comp.get("fields") or []
    title = comp.get("title", "编辑")
    return f"""
    <a-modal v-model:open="modalVisible" :title="modalTitle || '{title}'" @ok="handleSubmit" :confirmLoading="submitLoading">
      <a-form :model="formState" :label-col="{{ span: 6 }}" :wrapper-col="{{ span: 16 }}">
{_form_items(fields)}
      </a-form>
    </a-modal>"""


def _tpl_stats_cards(comp: dict) -> str:
    cards = comp.get("cards") or []
    cols = []
    for c in cards:
        title = c.get("label", c.get("title", ""))
        val = c.get("value", "0")
        suffix = c.get("suffix", "")
        cols.append(f"""      <a-col :span="6">
        <a-card><a-statistic title="{title}" value="{{ {val} }}" suffix="{suffix}" /></a-card>
      </a-col>""")
    return f'\n    <a-row gutter="{{ 16 }}" style="margin-bottom: 16px;">\n{chr(10).join(cols)}\n    </a-row>\n'


def _tpl_description(comp: dict) -> str:
    fields = comp.get("fields") or []
    items = "\n        ".join(
        f'<a-descriptions-item label="{f.get("label", f.get("name", ""))}">{{{{ record.{f.get("name", "")} }}}}</a-descriptions-item>'
        for f in fields
    )
    return f"""
    <a-descriptions title="{comp.get("title", "详情")}" bordered :column="2">
        {items}
    </a-descriptions>"""


def _tpl_tabs(comp: dict) -> str:
    tabs = comp.get("tabs") or []
    panes = "\n      ".join(
        f'<a-tab-pane key="{t.get("key", i)}" tab="{t.get("label", t.get("title", ""))}">{t.get("content", "")}</a-tab-pane>'
        for i, t in enumerate(tabs)
    )
    return f'\n    <a-tabs>\n      {panes}\n    </a-tabs>\n'


# ==================== 表单字段渲染（共用） ====================

def _form_items(fields: List[dict]) -> str:
    """渲染 a-form-item 列表（给 modal_form 和 data_table 内嵌表单共用）。"""
    items = []
    for f in fields:
        name = f.get("name", "")
        label = f.get("label", name)
        inp = f.get("input", "text")
        required = "required" if f.get("required") else ""
        placeholder = f.get("placeholder", f"请输入{label}")

        if inp == "number":
            control = f'<a-input-number v-model:value="formState.{name}" style="width: 100%" />'
        elif inp == "select":
            opts = f.get("options") or []
            opt_tags = "\n              ".join(
                f'<a-select-option value="{o.get("value", o) if isinstance(o, dict) else o}">'
                f'{o.get("label", o) if isinstance(o, dict) else o}</a-select-option>'
                for o in opts
            )
            control = f"""<a-select v-model:value="formState.{name}" placeholder="{placeholder}">
              {opt_tags}
            </a-select>"""
        elif inp == "textarea":
            control = f'<a-textarea v-model:value="formState.{name}" placeholder="{placeholder}" :rows="3" />'
        elif inp == "upload":
            control = f'<a-upload v-model:file-list="formState.{name}" :max-count="1" list-type="picture-card">\n          <div><span>上传</span></div>\n        </a-upload>'
        elif inp == "date":
            control = f'<a-date-picker v-model:value="formState.{name}" style="width: 100%" />'
        elif inp == "switch":
            control = f'<a-switch v-model:checked="formState.{name}" />'
        else:
            control = f'<a-input v-model:value="formState.{name}" placeholder="{placeholder}" />'

        rules = ' :rules="[{ required: true, message: \'请输入' + label + '\' }]"' if f.get("required") else ''
        items.append(f"        <a-form-item label=\"{label}\" name=\"{name}\"{rules}>\n          {control}\n        </a-form-item>")
    return "\n".join(items)


# ==================== State / Methods 生成 ====================

def _state_search_bar(comp: dict) -> List[str]:
    fields = comp.get("fields") or []
    defaults = ", ".join(f'{f.get("name", "")}: ""' for f in fields)
    return [f"const searchForm = reactive({{ {defaults} }})"]


def _methods_search_bar() -> List[str]:
    return [
        "const handleSearch = () => { pagination.current = 1; fetchList() }",
        "const handleReset = () => { Object.keys(searchForm).forEach(k => searchForm[k] = ''); fetchList() }",
    ]


def _state_data_table(comp: dict) -> List[str]:
    cols = comp.get("columns") or []
    col_defs = json.dumps([
        {"title": c.get("label", c.get("name", "")), "dataIndex": c.get("name", ""), "key": c.get("name", ""),
         "width": c.get("width"), "ellipsis": True}
        for c in cols
    ], ensure_ascii=False)
    return [
        f"const columns = ref({col_defs})",
        "const dataSource = ref([])",
        "const loading = ref(false)",
        "const pagination = reactive({ current: 1, pageSize: 10, total: 0 })",
        "const modalVisible = ref(false)",
        "const modalTitle = ref('')",
        "const formState = reactive({})",
        "const submitLoading = ref(false)",
        "const isEdit = ref(false)",
    ]


def _methods_data_table(comp: dict) -> List[str]:
    has_create = "create" in (comp.get("toolbar") or [])
    has_edit = "edit" in (comp.get("row_actions") or [])
    has_delete = "delete" in (comp.get("row_actions") or [])
    methods = [
        "const fetchList = async () => {\n"
        "  loading.value = true\n"
        "  try {\n"
        "    const res = await getList({ ...searchForm, page: pagination.current, pageSize: pagination.pageSize })\n"
        "    dataSource.value = res.data?.list || res.data?.records || []\n"
        "    pagination.total = res.data?.total || 0\n"
        "  } catch (e) { message.error('加载失败') } finally { loading.value = false }\n"
        "}",
    ]
    if has_create:
        methods.append(
            "const handleAdd = () => {\n"
            "  isEdit.value = false; modalTitle.value = '新增'\n"
            "  Object.keys(formState).forEach(k => delete formState[k])\n"
            "  modalVisible.value = true\n"
            "}")
    if has_edit:
        methods.append(
            "const handleEdit = (record) => {\n"
            "  isEdit.value = true; modalTitle.value = '编辑'\n"
            "  Object.assign(formState, record)\n"
            "  modalVisible.value = true\n"
            "}")
    return methods


def _state_modal_form(comp: dict) -> List[str]:
    fields = comp.get("fields") or []
    defaults = ", ".join(f'{f.get("name", "")}: undefined' for f in fields)
    return [f"const formState = reactive({{ {defaults} }})"] if defaults else []


def _methods_modal_form(comp: dict) -> List[str]:
    return [
        "const handleSubmit = async () => {\n"
        "  submitLoading.value = true\n"
        "  try {\n"
        "    if (isEdit.value) { await update(formState) } else { await create(formState) }\n"
        "    message.success(isEdit.value ? '更新成功' : '创建成功')\n"
        "    modalVisible.value = false; fetchList()\n"
        "  } catch (e) { message.error('操作失败') } finally { submitLoading.value = false }\n"
        "}",
    ]


def _state_stats_cards(comp: dict) -> List[str]:
    cards = comp.get("cards") or []
    lines = []
    for c in cards:
        name = c.get("name", c.get("label", "").replace(" ", "_"))
        val = c.get("value", 0)
        lines.append(f"const {name} = ref({val})")
    return lines


def _state_description(comp: dict) -> List[str]:
    return ["const record = ref({})"]


# ==================== API 模块渲染 ====================

def _render_api_module(api: dict) -> str:
    """API spec → 完整 .js 文件（axios request 封装）。"""
    base_url = api.get("base_url", "")
    endpoints = api.get("endpoints") or []
    lines = ["import request from '@/utils/request'\n"]
    for ep in endpoints:
        name = ep.get("name", "call")
        method = ep.get("method", "GET").lower()
        url = ep.get("url", "")
        full_url = f"'{base_url}{url}'" if base_url else f"'{url}'"
        if ep.get("paginated"):
            lines.append(f"export function {name}(params) {{ return request({{ url: {full_url}, method: '{method}', params }}) }}")
        elif method in ("post", "put"):
            lines.append(f"export function {name}(data) {{ return request({{ url: {full_url}, method: '{method}', data }}) }}")
        else:
            lines.append(f"export function {name}(params) {{ return request({{ url: {full_url}, method: '{method}', params }}) }}")
    return "\n".join(lines) + "\n"


# ==================== 辅助 ====================

def _guess_api_import_path(page: dict) -> str:
    """从页面路径推测 API 模块的 import 路径。"""
    path = page.get("path", "")
    # src/views/product/List.vue → @/api/product
    parts = path.replace("\\", "/").split("/")
    if "views" in parts:
        idx = parts.index("views")
        if idx + 1 < len(parts):
            module = parts[idx + 1].lower()
            return f"@/api/{module}"
    return "@/api/common"


def _collect_api_names(method_lines: List[str]) -> List[str]:
    """从 methods 里提取引用的 API 函数名。"""
    names = set()
    for known in ("getList", "create", "update", "remove", "getDetail"):
        if any(known in line for line in method_lines):
            names.add(known)
    return sorted(names)


def _assemble_script(title: str, state_lines: List[str], method_lines: List[str],
                     import_lines: List[str], table_columns: List[dict], form_fields: List[dict]) -> str:
    """组装 <script setup> 块。"""
    parts = ["<script setup>"]
    # imports
    parts.append("import { ref, reactive, onMounted } from 'vue'")
    parts.append("import { message } from 'ant-design-vue'")
    parts.extend(import_lines)
    parts.append("")
    # state
    if state_lines:
        parts.extend(state_lines)
        parts.append("")
    # methods
    if method_lines:
        parts.extend(method_lines)
        parts.append("")
    # lifecycle
    parts.append("onMounted(() => { fetchList && fetchList() })")
    parts.append("</script>")
    return "\n".join(parts)
