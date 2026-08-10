"""代码提交——Git commit message + 变更摘要。"""

COMMIT_PROMPT = """请整理以下前后端代码和测试结果，生成准确、边界清晰的提交方案。

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

测试结果:
{{testing_output}}

请输出:
1. 变更摘要：按后端、前端、API 契约、测试、配置分组。
2. 后端 Git commit message（Conventional Commits 格式，说明 scope 和主要行为变化）
3. 前端 Git commit message（Conventional Commits 格式，说明 scope 和主要行为变化）
4. 后端变更文件列表：路径、用途、是否新增/修改/删除。
5. 前端变更文件列表：路径、用途、是否新增/修改/删除。
6. 风险与回滚提示：哪些变更影响权限、接口、数据结构或兼容性。
7. 提交前检查清单：测试、lint、构建、迁移、权限配置。"""
