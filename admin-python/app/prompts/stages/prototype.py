"""前端预览（原模式）——直接生成 .vue 文件。"""

PROTOTYPE_PROMPT = """根据需求文档和页面设计，直接生成可写入匹配前端项目的前端预览代码。

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

## 本次预览页面范围
{{prototype_focus}}

## 前端技术栈
{{frontend_tech}}

## 用户需求
{{user_request}}

## 重要：参考项目
结合 Frontend Project Skill，优先复用现有项目的目录、组件库、路由、API 封装、权限判断、表格/表单模式和样式规范。不要展开解释。
如果没有匹配到前端项目或 Project Skill 信息不足，不要生成独立 demo 页面，应该让本阶段失败并说明缺少匹配项目依据。

## 生成目标
本阶段就是前端代码生成阶段。产物会直接写入项目并启动真实预览。
你生成的是前端页面代码文件（.vue / .tsx / .wxml+.js 等），根据目标项目技术栈选择。

## 实现要求
1. 根据目标技术栈生成真实项目代码：Vue 生成 `src/views/**/*.vue` + `src/api/*.js`；React 生成 `src/pages/**/*.tsx`；uni-app 生成 `pages/**/*.vue`；小程序生成 `pages/**/*.wxml` + `.js`。
2. 每个页面组件控制在 260 行以内，API/mock 服务模块 120 行以内。
3. 所有按钮必须有真实前端交互，不允许未定义函数或空 onclick。
4. 代码必须能在首屏无运行时报错。

## 输出格式
只允许输出 JSON 文件数组，不要输出 Markdown，不要输出代码块围栏，不要输出解释文字。

JSON 格式如下:
[
  {"path": "src/views/product/List.vue", "content": "完整文件内容"},
  {"path": "src/api/product.js", "content": "完整文件内容"}
]

要求：
- 必须是合法 JSON，最外层必须是数组
- 每项必须包含 path 和 content
- 禁止输出 ```json 或任何 Markdown 包裹"""
