import json
from pathlib import Path

import pytest

from app.ai.flow_manager import (
    _build_auto_repair_summary,
    _build_pipeline_artifact,
    _build_pipeline_skill_snapshot,
    _fix_loop_stage_for_mode,
    _has_code_review_fix_loop,
    _init_stages_for_mode,
    _is_existing_feature_change_request,
    _is_new_feature_page_request,
    _patch_time_range_split_markers,
    _render_prompt_template,
    _should_pause_for_stage,
    _validate_page_design_frontend_coverage,
    _validate_project_skill_ready,
    DEFAULT_STAGE_PROMPTS,
)
from app.ai.pipeline_skills import file_cleaner, file_reader, file_writer
from app.services.knowledge_service import (
    _build_project_skill_content,
    _classify_requirement_for_knowledge,
    _format_project_skill_context,
    _parse_knowledge_tags,
    select_backend_project_skill_match,
    select_backend_project_skill_matches,
    select_project_skill_match,
)


@pytest.mark.asyncio
async def test_file_writer_restricts_writes_to_root(tmp_path: Path):
    outside = tmp_path.parent / "outside.txt"

    result = await file_writer(
        str(tmp_path),
        {
            "src/pages/UserList.vue": "<template>User</template>",
            "../outside.txt": "blocked",
            "/absolute.txt": "normalized",
        },
    )

    assert sorted(result["files_written"]) == [
        "absolute.txt",
        "outside.txt",
        "src/pages/UserList.vue",
    ]
    assert (tmp_path / "src/pages/UserList.vue").read_text(encoding="utf-8") == "<template>User</template>"
    assert (tmp_path / "absolute.txt").read_text(encoding="utf-8") == "normalized"
    assert (tmp_path / "outside.txt").read_text(encoding="utf-8") == "blocked"
    assert not outside.exists()


@pytest.mark.asyncio
async def test_file_reader_scans_with_excludes_and_path_limits(tmp_path: Path):
    page = tmp_path / "src/views/user/UserList.vue"
    page.parent.mkdir(parents=True)
    page.write_text("x" * 120, encoding="utf-8")
    normal = tmp_path / "README.md"
    normal.write_text("y" * 120, encoding="utf-8")
    binary = tmp_path / "logo.png"
    binary.write_bytes(b"\x89PNG\r\n")
    excluded = tmp_path / "node_modules/pkg/index.js"
    excluded.parent.mkdir(parents=True)
    excluded.write_text("z" * 120, encoding="utf-8")

    result = await file_reader(
        str(tmp_path),
        max_bytes=10,
        path_limits=[
            {
                "prefixes": ["src/views/"],
                "suffixes": [".vue"],
                "max_bytes": 50,
            }
        ],
    )

    assert result["files"]["src/views/user/UserList.vue"] == "x" * 50
    assert result["files"]["README.md"] == "y" * 10
    assert "logo.png" not in result["files"]
    assert "node_modules/pkg/index.js" not in result["files"]


@pytest.mark.asyncio
async def test_file_cleaner_removes_only_paths_under_root(tmp_path: Path):
    temp_dir = tmp_path / ".pipeline-temp"
    temp_dir.mkdir()
    (temp_dir / "repair.json").write_text("{}", encoding="utf-8")
    (tmp_path / "outside-cleaner.txt").write_text("delete", encoding="utf-8")
    outside = tmp_path.parent / "outside-cleaner.txt"
    outside.write_text("keep", encoding="utf-8")

    result = await file_cleaner(str(tmp_path), [".pipeline-temp", "../outside-cleaner.txt"])

    assert result["files_deleted"] == [".pipeline-temp", "outside-cleaner.txt"]
    assert not temp_dir.exists()
    assert not (tmp_path / "outside-cleaner.txt").exists()
    assert outside.read_text(encoding="utf-8") == "keep"


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


def test_parse_knowledge_tags_accepts_legacy_plain_text():
    assert _parse_knowledge_tags('["拼团", "营销"]') == ["拼团", "营销"]
    assert _parse_knowledge_tags("拼团,营销；活动") == ["拼团", "营销", "活动"]
    assert _parse_knowledge_tags("auto-analysis") == ["auto-analysis"]
    assert _parse_knowledge_tags("") == []


def test_requirement_knowledge_classification_handles_page_location_suggestions():
    request = """
需求名称
供应链中台-渠道初始权限配置
页面位置建议
供应链中台 → 系统管理 → 渠道初始权限配置
页面功能
查询、新增/编辑、启用/停用渠道权限模板。
按当前后端实现要用表单参数提交。
"""

    assert _classify_requirement_for_knowledge(request) == "new_page"
    assert _classify_requirement_for_knowledge("在现有订单列表页面新增渠道筛选字段") == "existing_page_change"


def test_new_feature_page_request_does_not_require_existing_page_selection():
    request = "做一个拼团/团购活动管理功能。这是新功能页面，不是现有页面加字段。"

    assert _is_existing_feature_change_request(request) is False
    assert _is_new_feature_page_request(request) is True


def test_new_management_page_request_with_query_words_stays_new_page():
    requests = [
        "新增优惠券批次配置管理页面，运营可以创建满减券/折扣券批次，支持列表查询、编辑、启停、复制和导出。",
        "新增售后退款审核工作台，客服可以按订单号、用户手机号、退款状态筛选，查看退款申请详情，支持通过、驳回、批量审核。",
        "新增营销活动数据看板，运营可以查看拼团、秒杀、优惠券的 GMV、订单数、转化率趋势，支持时间范围筛选、渠道筛选、导出。",
        """
需求名称
供应链中台-渠道初始权限配置
页面位置建议
供应链中台 → 系统管理 → 渠道初始权限配置
页面功能
查询渠道模板，新增/编辑渠道模板，启用/停用模板。
字段建议
channelNo、templateName、status。
""",
    ]

    for request in requests:
        assert _is_existing_feature_change_request(request) is False
        assert _is_new_feature_page_request(request) is True


def test_existing_page_field_request_still_requires_existing_page_selection():
    request = "在现有商品列表页面新增活动状态筛选字段"

    assert _is_existing_feature_change_request(request) is True
    assert _is_new_feature_page_request(request) is False


def test_preview_coverage_treats_entities_and_drawers_as_support_not_buttons():
    page_design_stage = {
        "output": """
# 优惠券批次配置 页面设计

## 数据对象
- `CouponBatch`: couponBatchNo、batchName、status

## 页面操作
| 操作名称 | 说明 |
| --- | --- |
| 新建按钮 | 打开新增/编辑批次抽屉 |
| 新增/编辑批次抽屉 | 支撑容器 |

## 字段
批次编码、批次名称
"""
    }
    files = {
        "src/views/couponBatch/CouponBatchList.vue": """
<template>
  <a-button type="primary" @click="handleAdd">新建</a-button>
  <a @click="handleEdit(record)">编辑</a>
  <a-drawer :visible="drawerVisible" :title="drawerTitle" />
</template>
<script>
export default {
  data () {
    return {
      drawerVisible: false,
      drawerTitle: '新建批次'
    }
  },
  methods: {
    handleAdd () {},
    handleEdit () {}
  }
}
</script>
""",
    }

    issues = _validate_page_design_frontend_coverage(files, page_design_stage)

    assert not any("项目组件" in issue for issue in issues)
    assert not any("新增/编辑批次抽屉" in issue for issue in issues)
    assert not any("新建按钮" in issue for issue in issues)


def test_time_range_auto_fix_normalizes_start_date_to_start_time():
    content = """
<template>
  <a-range-picker v-model="queryParam.dateRange" />
</template>
<script>
export default {
  computed: {
    queryParamsFormatted () {
      const p = { ...this.queryParam }
      if (Array.isArray(p.dateRange) && p.dateRange.length === 2) {
        p.startDate = p.dateRange[0].format('YYYY-MM-DD')
        p.endDate = p.dateRange[1].format('YYYY-MM-DD')
      }
      delete p.dateRange
      return p
    }
  }
}
</script>
"""

    patched = _patch_time_range_split_markers(content)

    assert "p.startTime" in patched
    assert "p.endTime" in patched
    assert "startDate" not in patched
    assert "endDate" not in patched
    assert "delete p.dateRange" in patched


def test_project_skill_content_includes_brief_and_repo_patterns():
    skill = _build_project_skill_content(DummyProjectKnowledge())

    assert "# Project Skill: Admin Portal" in skill
    assert "企业后台" in skill
    assert "React + Ant Design + Zustand" in skill
    assert "src/App.tsx" in skill
    assert "Do not generate backend implementation" in skill
    assert "## Pipeline Execution Contract" in skill
    assert "### Project Analysis Checklist" in skill
    assert "### Frontend Generation Contract" in skill
    assert "### API And Data Contract" in skill
    assert "### Permission And State Contract" in skill
    assert "## AGENTS.md Handoff Notes" in skill
    assert "## Structured Project Analysis Schema" in skill
    assert "## Structured Generation Contract" in skill
    assert "## Structured Verification Contract" in skill
    assert "Every primary page from page design must have a corresponding page file" in skill
    assert "Never relax the project response envelope" in skill
    assert "页面位置建议" in skill
    assert "Existing page candidates are target files only for explicit existing/current/original page changes" in skill
    assert "Do not reuse an unrelated order/product/activity list page" in skill
    assert "Do not turn \"新增/编辑\" wording into separate primary create and edit route pages" in skill
    assert "one list page plus create/edit modal/drawer support" in skill
    assert "Do not make drawer/modal/component names" in skill


def test_frontend_preview_skills_encode_new_page_selection_boundary():
    root = Path(__file__).resolve().parents[1]
    real_preview = (root / "skills/real-frontend-preview/SKILL.md").read_text(encoding="utf-8")
    scaffold = (root / "skills/backoffice-page-scaffold/SKILL.md").read_text(encoding="utf-8")

    assert "page location suggestion" in real_preview
    assert "unrelated existing list page" in real_preview
    assert "combined \"新增/编辑\" action" in real_preview
    assert "Required visible actions are user commands" in real_preview
    assert "页面位置建议" in scaffold
    assert "order list, product list, activity list" in scaffold
    assert "Do not promote create and edit into separate primary route pages" in scaffold
    assert "Do not require visible controls named" in scaffold


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
        "code_review",
        "report",
    ]


def test_fix_loop_stage_falls_back_to_prototype_without_frontend_dev():
    assert _fix_loop_stage_for_mode(["requirement", "prototype", "delivery", "code_review"]) == "prototype"
    assert _fix_loop_stage_for_mode(["requirement", "frontend_dev", "code_review"]) == "frontend_dev"


def test_frontend_contract_review_has_no_frontend_dev_fix_loop():
    stage_keys = _init_stages_for_mode("frontend_contract_review").keys()

    assert "frontend_dev" not in stage_keys
    assert "prototype" in stage_keys
    assert _has_code_review_fix_loop(list(stage_keys))


def test_code_review_self_repair_skips_intermediate_confirmations():
    assert _should_pause_for_stage("prototype") is True
    assert _should_pause_for_stage("delivery") is True
    assert _should_pause_for_stage("code_review") is True

    assert _should_pause_for_stage("prototype", auto_review_fix_active=True) is False
    assert _should_pause_for_stage("delivery", auto_review_fix_active=True) is False
    assert _should_pause_for_stage("code_review", auto_review_fix_active=True) is True


def test_auto_repair_summary_lists_fix_content():
    summary = _build_auto_repair_summary(
        2,
        "prototype",
        "自动审查未通过，请只修复审查指出的问题。\n- 当前: queryParam.productId\n- 应为: queryParam.id",
        ["已补充 queryParam.id", "已保留原 url.list 数据流"],
    )

    assert "系统已自动回到 前端预览代码 修复" in summary
    assert "修复轮次：2" in summary
    assert "当前: queryParam.productId" in summary
    assert "已补充 queryParam.id" in summary
    assert "本轮审查通过" in summary


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
            "project_analysis_schema": '{"routing":["routes"]}',
            "generation_contract": '{"tables":["STable"]}',
            "verification_contract": '{"commands":["npm run build"]}',
            "skill_version": 3,
            "confirmed_at": 1710000000000,
        }
    )

    assert snapshot == {
        "project_id": "42",
        "project_name": "Admin Portal",
        "repo_url": "",
        "skill_content": "confirmed content",
        "project_analysis_schema": '{"routing":["routes"]}',
        "generation_contract": '{"tables":["STable"]}',
        "verification_contract": '{"commands":["npm run build"]}',
        "skill_version": 3,
        "confirmed_at": 1710000000000,
    }


def test_pipeline_artifact_collects_preview_frontend_contract_and_review():
    stages = _init_stages_for_mode("frontend_contract_review")
    stages["prototype"].update({"preview_html": "<html>preview</html>", "output": "preview raw"})
    stages["prototype"].update({"code_files": {"src/pages/users.tsx": "export default function Users() {}"}})
    stages["delivery"].update({"output": "# API Contract\nGET /api/users"})
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


def test_requirement_prompt_requires_step_by_step_execution():
    prompt = _render_prompt_template(
        DEFAULT_STAGE_PROMPTS["requirement"],
        {
            "user_request": "新增费用明细系统",
            "stage_outputs": {},
        },
    )

    assert "## 需求分析执行步骤" in prompt
    assert "输入盘点" in prompt
    assert "流程建模" in prompt
    assert "验收标准落地" in prompt
    assert "每一步写清操作者、系统动作、数据变化和下一状态" in prompt


def test_page_design_prompt_requires_step_by_step_execution():
    prompt = _render_prompt_template(
        DEFAULT_STAGE_PROMPTS["page_design"],
        {
            "stage_outputs": {
                "requirement": {
                    "output": "P0: 新增费用明细列表，包含查询、导出和详情查看。",
                }
            },
        },
    )

    assert "## 页面设计执行步骤" in prompt
    assert "PRD 对齐" in prompt
    assert "页面拆分" in prompt
    assert "字段落表" in prompt
    assert "API 契约草案" in prompt
    assert "每个字段写清展示名、字段 key、类型、来源、校验、格式化" in prompt


def test_delivery_prompt_inherits_existing_frontend_contract():
    prompt = _render_prompt_template(
        DEFAULT_STAGE_PROMPTS["delivery"],
        {
            "requirement_output": "给现有零售商品列表增加商品ID筛选项",
            "page_design_output": "商品ID是新增筛选项，商品编号现有字段为 productCode",
            "prototype_output": "queryParam.productCode; queryParam.id; url: { list: '/api/product/glsw/product/selfOperatedList' }",
            "backend_project_name": "wealth-admin-home",
            "backend_tech": "java/spring-boot",
            "stage_outputs": {},
        },
    )

    assert "{{prototype_output}}" not in prompt
    assert "queryParam.productCode" in prompt
    assert "保留所有原筛选项及其请求字段" in prompt
    assert "新增字段按 API 契约使用 `id`" in prompt
    assert "不得把旧字段改名来冒充新增" in prompt
    assert "不得凭空写 `/goods/retail/list`" in prompt


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
    assert match["match_source"] == "backend_role_rule"
    assert "后端实现层信号" in match["match_reason"]
    assert "兜底" not in match["match_reason"]


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
    assert match["match_source"] == "backend_project_group"
    assert "Dubbo 分层后端项目组" in match["match_reason"]
    assert all(item["match_source"] == "backend_project_group" for item in match["matches"])
    assert [item["match_tags"][1] for item in match["matches"]] == ["controller/API层", "service层", "core/model层"]
    assert all("兜底" not in item["match_reason"] for item in match["matches"])
