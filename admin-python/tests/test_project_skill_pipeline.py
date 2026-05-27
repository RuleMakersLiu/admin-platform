import json

import pytest

from app.ai.flow_manager import (
    _build_pipeline_artifact,
    _build_pipeline_skill_snapshot,
    _init_stages_for_mode,
    _render_prompt_template,
    _validate_project_skill_ready,
    DEFAULT_STAGE_PROMPTS,
)
from app.services.knowledge_service import (
    _build_project_skill_content,
    _format_project_skill_context,
    select_backend_project_skill_match,
    select_backend_project_skill_matches,
    select_project_skill_match,
)


class DummyProjectKnowledge:
    project_id = 42
    project_name = "Admin Portal"
    repo_url = "https://example.com/admin.git"
    language = "typescript"
    framework = "react"
    project_brief = "企业后台，包含用户、角色、项目接入和开发流水线。"
    tech_summary = "React + Ant Design + Zustand"
    architecture = "Vite SPA, pages/services/stores 分层"
    component_patterns = "表格页使用 Ant Design Table，编辑使用 Modal Form"
    api_patterns = "通过 services/api.ts 统一请求 /api 前缀"
    permission_model = "RBAC，菜单和按钮均通过 permission key 控制"
    coding_style = "TypeScript strict，组件内使用 hooks"
    key_files = json.dumps(["src/App.tsx", "src/services/api.ts"])
    skill_content = ""
    skill_status = "draft"
    skill_version = 1


def test_project_skill_content_includes_brief_and_repo_patterns():
    skill = _build_project_skill_content(DummyProjectKnowledge())

    assert "# Project Skill: Admin Portal" in skill
    assert "企业后台" in skill
    assert "React + Ant Design + Zustand" in skill
    assert "src/App.tsx" in skill
    assert "Do not generate backend implementation" in skill


def test_project_skill_context_only_uses_confirmed_skill():
    draft = DummyProjectKnowledge()
    draft.skill_content = "draft skill"
    draft.skill_status = "draft"

    confirmed = DummyProjectKnowledge()
    confirmed.skill_content = "confirmed skill"
    confirmed.skill_status = "confirmed"

    assert _format_project_skill_context(draft) == ""
    assert "confirmed skill" in _format_project_skill_context(confirmed)


def test_frontend_contract_review_mode_skips_backend_and_deploy_steps():
    stages = _init_stages_for_mode("frontend_contract_review")

    assert "backend_dev" not in stages
    assert "testing" not in stages
    assert "commit" not in stages
    assert "deploy" not in stages
    assert list(stages.keys()) == [
        "requirement",
        "page_design",
        "prototype",
        "delivery",
        "frontend_dev",
        "code_review",
        "report",
    ]


def test_project_skill_must_be_confirmed_before_pipeline_creation():
    with pytest.raises(ValueError, match="confirmed"):
        _validate_project_skill_ready({"skill_status": "draft", "skill_content": "x"})

    _validate_project_skill_ready({"skill_status": "confirmed", "skill_content": "x"})


def test_pipeline_skill_snapshot_is_stable_and_minimal():
    snapshot = _build_pipeline_skill_snapshot(
        {
            "project_id": 42,
            "project_name": "Admin Portal",
            "skill_content": "confirmed content",
            "skill_version": 3,
            "confirmed_at": 1710000000000,
        }
    )

    assert snapshot == {
        "project_id": "42",
        "project_name": "Admin Portal",
        "skill_content": "confirmed content",
        "skill_version": 3,
        "confirmed_at": 1710000000000,
    }


def test_pipeline_artifact_collects_preview_frontend_contract_and_review():
    stages = _init_stages_for_mode("frontend_contract_review")
    stages["prototype"].update({"preview_html": "<html>preview</html>", "output": "preview raw"})
    stages["delivery"].update({"output": "# API Contract\nGET /api/users"})
    stages["frontend_dev"].update({"code_files": {"src/pages/users.tsx": "export default function Users() {}"}})
    stages["code_review"].update(
        {
            "status": "completed",
            "structured_output": {
                "review_passed": True,
                "fix_suggestions": "",
                "checks": ["preview", "contract"],
            },
            "output": "PASS",
        }
    )

    artifact = _build_pipeline_artifact(stages)

    assert artifact["preview_html"] == "<html>preview</html>"
    assert artifact["api_contract"] == "# API Contract\nGET /api/users"
    assert artifact["frontend_files"] == {"src/pages/users.tsx": "export default function Users() {}"}
    assert artifact["review"]["review_passed"] is True


def test_requirement_prompt_names_frontend_and_backend_projects():
    prompt = _render_prompt_template(
        DEFAULT_STAGE_PROMPTS["requirement"],
        {
            "user_request": "新增费用明细系统",
            "frontend_project_name": "web-product-agent",
            "frontend_tech": "javascript/vue",
            "backend_project_name": "wealth-glsw-service",
            "backend_tech": "java/spring-boot",
            "stage_outputs": {},
        },
    )

    assert "前端项目: web-product-agent" in prompt
    assert "后端项目: wealth-glsw-service" in prompt
    assert "必须分别写明前端参考项目和后端参考项目" in prompt


def test_requirement_auto_match_prefers_relevant_confirmed_project_skill():
    candidates = [
        {
            "project_id": 11,
            "project_name": "Marketing CMS",
            "language": "typescript",
            "framework": "vue",
            "project_brief": "Content publishing and marketing landing pages.",
            "skill_content": "Use CMS blocks, landing page templates, and SEO metadata.",
            "skill_status": "confirmed",
            "skill_version": 2,
        },
        {
            "project_id": 42,
            "project_name": "Order Admin",
            "language": "typescript",
            "framework": "react",
            "project_brief": "订单、退款、审批、财务对账后台。",
            "skill_content": "Use Ant Design Table, refund approval modal, order APIs, and RBAC permission buttons.",
            "skill_status": "confirmed",
            "skill_version": 5,
        },
    ]

    match = select_project_skill_match(
        "新增退款审批页面，包含订单表格、审批弹窗、退款状态流转和按钮权限。",
        candidates,
    )

    assert match["skill"]["project_id"] == 42
    assert match["confidence"] > 0.2
    assert match["candidates_considered"] == 2
    assert "退款" in match["match_reason"]


def test_backend_match_prefers_service_layer_over_core_models():
    candidates = [
        {
            "project_id": 7,
            "project_name": "wealth-glsw-core",
            "language": "java",
            "framework": "maven",
            "project_brief": "酒店智能体管理平台、供应链中台、商品管理平台的java项目core层",
            "skill_content": "纯后端服务基础核心模块，主要包含 model、DTO、VO、Result 和数据模型定义。",
            "skill_status": "confirmed",
            "skill_version": 3,
        },
        {
            "project_id": 6,
            "project_name": "wealth-glsw-service",
            "language": "java",
            "framework": "spring-boot",
            "project_brief": "酒店智能体管理平台、供应链中台、商品管理平台的java项目service层",
            "skill_content": "Spring Boot 服务层，包含业务逻辑、MyBatis Mapper、Dubbo RPC、接口响应和数据处理。",
            "skill_status": "confirmed",
            "skill_version": 1,
        },
    ]

    match = select_backend_project_skill_match(
        "商城管理平台需要增一个费用明细系统",
        candidates,
    )

    assert match["skill"]["project_id"] == 6
    assert "后端实现层信号" in match["match_reason"]


def test_backend_match_returns_dubbo_related_project_group():
    candidates = [
        {
            "project_id": 2,
            "project_name": "wealth-admin-home",
            "language": "java",
            "framework": "spring-boot",
            "project_brief": "酒店智能体管理平台、供应链中台、商品管理平台接口项目，controller层",
            "skill_content": "Controller API 接口项目，负责接收管理后台请求并通过 Dubbo 调用 service。",
            "skill_status": "confirmed",
            "skill_version": 1,
        },
        {
            "project_id": 6,
            "project_name": "wealth-glsw-service",
            "language": "java",
            "framework": "spring-boot",
            "project_brief": "酒店智能体管理平台、供应链中台、商品管理平台的java项目service层",
            "skill_content": "Service 层实现业务逻辑，通过 Dubbo 暴露服务，使用 MyBatis Mapper。",
            "skill_status": "confirmed",
            "skill_version": 1,
        },
        {
            "project_id": 7,
            "project_name": "wealth-glsw-core",
            "language": "java",
            "framework": "maven",
            "project_brief": "酒店智能体管理平台、供应链中台、商品管理平台的java项目core层",
            "skill_content": "Core 层定义 model、DTO、VO、Result 等数据模型。",
            "skill_status": "confirmed",
            "skill_version": 1,
        },
    ]

    match = select_backend_project_skill_matches(
        "商城管理平台需要增一个费用明细系统",
        candidates,
    )

    assert [item["skill"]["project_id"] for item in match["matches"]] == [2, 6, 7]
    assert "Dubbo 分层后端项目组" in match["match_reason"]
