"""自动化测试——测试用例生成。"""

TESTING_PROMPT = """基于以下需求、页面设计、API 契约和前后端代码，设计测试用例并生成可执行的测试脚本。

需求文档:
{{requirement_output}}

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

代码审查结果:
{{code_review_output}}

## 要求

请完成以下两部分输出:

### 第一部分：测试用例分析
1. 测试范围和不测范围：明确本次验证边界。
2. 测试用例列表：含优先级、前置条件、步骤、输入、预期结果。
3. 边界用例：空数据、无权限、非法输入、重复提交、分页越界、状态非法、接口超时。
4. 权限用例：菜单/页面/按钮/API/数据范围分别验证。
5. 契约用例：请求字段、响应字段、分页字段、错误结构、mock 与真实字段一致性。
6. 覆盖率评估：说明已覆盖和未覆盖风险。
7. 发现的 Bug 列表（标注严重程度: critical/major/minor）

### 第二部分：可执行测试脚本
请根据后端技术栈生成对应的自动化测试代码:
- Java: JUnit 5 + MockMvc 测试
- Go: testing 包 + httptest
- Python: pytest + httpx
- PHP: PHPUnit
- Node.js: Jest + supertest

如果后端有 REST API，请生成 API 接口测试脚本，包含:
- 正常流程测试（200 响应）
- 参数校验测试（400 响应）
- 权限测试（401/403 响应）
- 边界条件测试
- 并发/幂等测试（重复点击、重复提交、同一资源并发修改）
- 数据范围测试（不同租户/角色/部门只能访问授权数据）

每个代码块前用 `### 文件: 路径/文件名` 标注。

在输出末尾附带结构化 JSON:
```json
{
  "tests_passed": true/false,
  "bug_details": "发现的问题详情",
  "test_cases_total": 10,
  "test_cases_passed": 8,
  "coverage_estimate": "80%",
  "test_scripts": ["tests/TestController.java"]
}
```"""
