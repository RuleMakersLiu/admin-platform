"""前端预览 Spec 模式——antd-vue PC 后台专用页面规格 JSON。"""

PROTOTYPE_SPEC_PROMPT = """根据需求文档和页面设计，输出页面规格 JSON（antd-vue 3.x PC 后台专用）。系统会用模板引擎自动渲染成完整 .vue 组件代码。

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

## 本次预览页面范围
{{prototype_focus}}

## 用户需求
{{user_request}}

## 输出格式
只允许输出 JSON 页面规格，不要输出完整代码文件、不要输出 Markdown 围栏、不要输出解释文字。

JSON 格式如下:
{
  "pages": [
    {
      "path": "src/views/product/List.vue",
      "title": "商品管理",
      "components": [
        {"type": "search_bar", "fields": [{"name": "keyword", "label": "关键词", "input": "text"}]},
        {"type": "data_table", "columns": [{"name": "id", "label": "ID"}, {"name": "name", "label": "名称"}], "row_actions": ["edit", "delete"], "toolbar": ["create"], "pagination": true}
      ]
    }
  ],
  "api_modules": [{"path": "src/api/product.js", "base_url": "/api/product", "endpoints": [{"name": "getList", "method": "GET", "url": "/list", "paginated": true}]}],
  "pm_quality": {"score": 85, "issues": []}
}

支持的组件类型：search_bar / data_table / modal_form / stats_cards / description / tabs。
要求：
- 必须包含 pages 数组，覆盖页面设计所有主页面
- 每个 page 有 path（.vue）和 components
- pm_quality.score 是自评（0-100）"""
