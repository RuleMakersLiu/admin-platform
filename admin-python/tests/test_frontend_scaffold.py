"""frontend_scaffold 模板渲染测试（Spec → antd-vue 代码）。"""
from app.ai.frontend_scaffold import render_spec_to_code_files


_SPEC = {
    "pages": [{
        "path": "src/views/product/List.vue",
        "title": "商品管理",
        "components": [
            {"type": "search_bar", "fields": [
                {"name": "keyword", "label": "关键词", "input": "text", "placeholder": "搜索商品"},
                {"name": "status", "label": "状态", "input": "select",
                 "options": [{"label": "全部", "value": ""}, {"label": "上架", "value": 1}]},
            ]},
            {"type": "data_table", "columns": [
                {"name": "id", "label": "ID", "width": 80},
                {"name": "name", "label": "商品名称"},
                {"name": "price", "label": "价格"},
            ], "row_actions": ["edit", "delete"], "toolbar": ["create"], "pagination": True},
        ],
    }],
    "api_modules": [{
        "path": "src/api/product.js",
        "base_url": "/api/product",
        "endpoints": [
            {"name": "getList", "method": "GET", "url": "/list", "paginated": True},
            {"name": "create", "method": "POST", "url": "/create"},
            {"name": "update", "method": "PUT", "url": "/update"},
            {"name": "remove", "method": "DELETE", "url": "/delete"},
        ],
    }],
}


def test_renders_vue_and_api_files():
    files = render_spec_to_code_files(_SPEC)
    assert len(files) == 2
    assert "src/views/product/List.vue" in files
    assert "src/api/product.js" in files


def test_vue_has_antd_components():
    vue = render_spec_to_code_files(_SPEC)["src/views/product/List.vue"]
    # antd-vue 组件
    assert "<a-table" in vue
    assert "<a-input" in vue
    assert "<a-select" in vue
    assert "<a-button" in vue
    assert "<a-modal" in vue
    assert "<a-popconfirm" in vue


def test_vue_has_script_setup_with_crud():
    vue = render_spec_to_code_files(_SPEC)["src/views/product/List.vue"]
    assert "<script setup>" in vue
    assert "onMounted" in vue
    # CRUD methods
    assert "fetchList" in vue
    assert "handleAdd" in vue
    assert "handleEdit" in vue
    assert "handleDelete" in vue
    assert "handleSubmit" in vue
    # reactive state
    assert "dataSource" in vue
    assert "columns" in vue
    assert "pagination" in vue
    assert "formState" in vue


def test_api_module_has_request_functions():
    js = render_spec_to_code_files(_SPEC)["src/api/product.js"]
    assert "import request" in js
    assert "export function getList" in js
    assert "export function create" in js
    assert "export function update" in js
    assert "export function remove" in js
    assert "/api/product/list" in js


def test_empty_spec_returns_empty():
    assert render_spec_to_code_files({}) == {}
    assert render_spec_to_code_files({"pages": []}) == {}


def test_select_options_rendered():
    vue = render_spec_to_code_files(_SPEC)["src/views/product/List.vue"]
    assert "全部" in vue
    assert "上架" in vue
