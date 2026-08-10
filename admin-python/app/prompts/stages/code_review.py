"""代码审查——10 项必审 + 6 项必须 FAIL。"""

CODE_REVIEW_PROMPT = """请审查真实前端代码、后端/API 契约和两端字段对齐情况。不要只做泛泛的代码质量评价。

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

## 交付包/API 契约
{{delivery_output}}

## 前端预览/真实前端代码
{{prototype_output}}

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

## 必审清单
1. 真实前端代码审查：只审查实际生成的前端文件、预览代码和 API/service 文件；如果没有 frontend_dev，则审查 prototype 阶段的真实前端代码。
2. API 契约对齐：逐项核对接口路径、HTTP 方法、query/body 参数名、必填字段、分页字段、详情字段、状态码/错误结构、鉴权和权限 key。
3. 字段一致性：逐项核对页面表格列、详情字段、表单字段、搜索条件、mock 字段、API 请求字段、API 响应字段是否同名同类型；中英文 label 不算字段名一致。
   - 前端请求对象前缀不算字段名差异：例如 `queryParam.id`、`params.id`、`parameter.id` 与 API 契约请求参数 `id` 是同一字段，不得因此判定字段名不一致。
4. 页面形态一致性：列表页核对 list/page/count 等分页契约；详情页核对对象数据和空对象兜底；表单页核对校验规则、提交参数和错误提示；小程序核对源码和 HTML 预览是否表达同一字段和交互。
5. Mock 与真实契约一致性：mock 数据不能用一套字段、真实 API/service 读另一套字段；mock 不能掩盖字段缺失。
6. 代码合理性：组件拆分、状态管理、加载/空/异常态、错误处理、防 undefined、权限指令/按钮态、重复代码、不可达代码、硬编码、无效 import、未实现事件方法。
7. 可预览性：首屏是否可能运行时报错，接口失败是否可降级，预览代码是否依赖不存在的组件/插件/全局变量。
8. 安全和稳定性：token/密钥泄露、XSS、未校验输入、危险 HTML、越权按钮、并发重复提交、接口超时和幂等性。
9. 逻辑正确性：核对业务规则、状态流转、权限条件、数据范围、默认值、枚举映射和边界判断是否前后一致。
10. 可维护性：核对重复代码、命名不清、职责混乱、不可测试逻辑、过度硬编码和与项目规范不一致的实现。

## 输出要求
请输出:
1. 后端/API 契约评分 (A/B/C/D/F)
2. 前端代码评分 (A/B/C/D/F)
3. 契约对齐结论：列出接口级、字段级、权限级差异；每条必须指出"前端使用字段/接口"和"契约或后端提供字段/接口"
4. 代码合理性问题列表（含严重程度: critical/major/minor，标注前端/后端/API/契约）
5. 改进建议（每个问题给出具体修复方案）
6. 是否通过审查 (PASS/FAIL)

如果发现 critical 或 major 问题，标记为 FAIL 并给出详细修复指导。
以下情况必须 FAIL：
- 前端读取的响应字段与 API 契约不一致
- 前端提交参数名与 API 契约不一致
- 页面展示字段、mock 字段和 API 字段三者不一致
- 列表/详情/表单页面形态与接口响应结构不匹配
- 预览依赖不存在的组件、方法、权限指令或全局变量
- 缺少必要的加载/空/异常兜底导致客户现场首屏可能报错

请在输出末尾附带结构化 JSON（方便自动化解析）:
```json
{
  "review_passed": true/false,
  "backend_score": "A/B/C/D/F",
  "frontend_score": "A/B/C/D/F",
  "contract_alignment": "接口和字段对齐结论摘要",
  "field_mismatches": [
    {"severity": "critical/major/minor", "location": "文件或接口", "frontend_field": "前端字段", "contract_field": "契约字段", "fix": "修复方式"}
  ],
  "fix_suggestions": "修复建议摘要"
}
```"""
