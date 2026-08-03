"""Tests for the 智能流水线 needs_human / review-gate additions (offline; LLM mocked).

Covers:
- _permission_keys_from_design: 收紧后只在「权限/permission」上下文行抽取权限码
- _generated_pages_look_auth_only: 登录/注册类页面判定
- _run_stage_review: 子智能体评审关卡（注入假 judge，验 passed/feedback 推导）
"""
import asyncio
from types import SimpleNamespace

from app.ai import flow_manager, eval_judge


def _run(coro):
    return asyncio.run(coro)


# ---------- 权限键抽取（收紧） ----------

def test_permission_keys_only_from_permission_context():
    doc = """
    # 页面设计
    接口：GET /api/login，字段 username/password。
    示例响应：{ "code": "0", "data": { "token:abc" } }
    权限：按钮 user:add、页面 user:list。
    """
    keys = flow_manager._permission_keys_from_design(doc)
    # 只应抽出权限行里的 user:add / user:list，而非 token:abc（在非权限行的示例里）
    assert "user:add" in keys
    assert "user:list" in keys
    assert "token:abc" not in keys


def test_permission_keys_empty_when_no_permission_section():
    # 登录页设计：完全没提权限 → 不应抽出任何权限码（修复前会误抽 ns:action）
    doc = """
    # 登录页
    接口 POST /api/auth/login。
    字段：username、password、captcha。
    路由：/login。
    """
    assert flow_manager._permission_keys_from_design(doc) == []


# ---------- auth 页判定 ----------

def test_generated_pages_look_auth_only_true_for_login():
    files = {"src/views/login/index.vue": "<template>login</template>"}
    assert flow_manager._generated_pages_look_auth_only(files) is True


def test_generated_pages_look_auth_only_false_for_mixed():
    files = {
        "src/views/login/index.vue": "x",
        "src/views/dashboard/index.vue": "y",
    }
    assert flow_manager._generated_pages_look_auth_only(files) is False


def test_generated_pages_look_auth_only_false_when_no_pages():
    assert flow_manager._generated_pages_look_auth_only({}) is False


# ---------- 子智能体评审关卡（注入假 judge） ----------

class _FakePipe:
    def __init__(self, user_request):
        self.user_request = user_request
        self.pipeline_id = "pipe_test"


def _patched_judge(result):
    async def _fake(input_spec, output, criteria, llm=None):
        return result
    return _fake


def test_review_gate_passes_when_score_high(monkeypatch):
    monkeypatch.setattr(eval_judge, "judge_output", _patched_judge({
        "overall_score": 90,
        "per_criterion": [
            {"criterion": "清晰", "score": 90, "passed": True, "reason": "ok"},
        ],
        "summary": "good",
    }))
    mgr = flow_manager.DevPipelineManager.__new__(flow_manager.DevPipelineManager)
    res = _run(mgr._run_stage_review(
        "requirement", _FakePipe("做一个登录页"), {"requirement": {"output": "需求..."}}, "需求..."
    ))
    assert res["passed"] is True
    assert res["score"] == 90


def test_review_gate_fails_with_feedback(monkeypatch):
    monkeypatch.setattr(eval_judge, "judge_output", _patched_judge({
        "overall_score": 30,
        "per_criterion": [
            {"criterion": "覆盖核心功能点", "score": 30, "passed": False, "reason": "缺少验证码"},
        ],
        "summary": "bad",
    }))
    mgr = flow_manager.DevPipelineManager.__new__(flow_manager.DevPipelineManager)
    res = _run(mgr._run_stage_review(
        "requirement", _FakePipe("做一个登录页"), {"requirement": {"output": ""}}, "简短需求"
    ))
    assert res["passed"] is False
    assert "缺少验证码" in res["feedback"]
    assert any("缺少验证码" in i for i in res["issues"])


def test_review_gate_passes_when_judge_errors(monkeypatch):
    # judge 本身报错 → 放行（不因评审故障卡死流水线）
    monkeypatch.setattr(eval_judge, "judge_output", _patched_judge({"error": "API 超时"}))
    mgr = flow_manager.DevPipelineManager.__new__(flow_manager.DevPipelineManager)
    res = _run(mgr._run_stage_review(
        "requirement", _FakePipe("x"), {"requirement": {"output": ""}}, "y"
    ))
    assert res["passed"] is True
    assert res.get("judge_error")


def test_review_gate_only_for_configured_stages():
    # backend_dev 不在 Phase1 顺序关卡里
    assert "requirement" in flow_manager.REVIEW_GATE_CRITERIA
    assert "delivery" in flow_manager.REVIEW_GATE_CRITERIA
    assert "backend_dev" not in flow_manager.REVIEW_GATE_CRITERIA


def test_needs_human_status_enum_exists():
    assert flow_manager.PipelineStatus.NEEDS_HUMAN.value == "needs_human"


# ---------- eval 阶段质量门控（低分 → NEEDS_HUMAN；judge 缺失 fail-open）----------

def test_eval_quality_gate_low_score_returns_reason(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "eval_quality_gate_enabled", True)
    monkeypatch.setattr(settings, "eval_quality_gate_score", 40)
    reason = flow_manager.DevPipelineManager._eval_quality_gate_reason(
        {"judge": {"overall_score": 30}}
    )
    assert reason is not None and "judge 30" in reason and "40" in reason


def test_eval_quality_gate_high_score_no_reason(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "eval_quality_gate_enabled", True)
    monkeypatch.setattr(settings, "eval_quality_gate_score", 40)
    assert flow_manager.DevPipelineManager._eval_quality_gate_reason(
        {"judge": {"overall_score": 80}}
    ) is None


def test_eval_quality_gate_failopen_when_judge_missing(monkeypatch):
    """judge 缺失/出错/None → 不 gate（评测故障不卡死流水线）。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "eval_quality_gate_enabled", True)
    monkeypatch.setattr(settings, "eval_quality_gate_score", 40)
    gate = flow_manager.DevPipelineManager._eval_quality_gate_reason
    assert gate({"error": "评测未完成"}) is None               # 整个 eval 出错
    assert gate({"judge": {"error": "API 超时"}}) is None       # judge 子项出错
    assert gate({"judge": {"overall_score": None}}) is None     # judge 分为 None


def test_eval_quality_gate_disabled_no_reason(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "eval_quality_gate_enabled", False)
    assert flow_manager.DevPipelineManager._eval_quality_gate_reason(
        {"judge": {"overall_score": 10}}
    ) is None


# ---------- eval 低分重修反馈构造（闭环 Stage 1）----------

def test_build_eval_fix_feedback_extracts_findings():
    """judge 未过项 + E2E 问题 + 幻觉 + 视觉摘要 → 可执行反馈，含保留约束。"""
    issues, fb = flow_manager._build_eval_fix_feedback({
        "judge": {"overall_score": 30, "summary": "缺登录校验", "per_criterion": [
            {"criterion": "需求覆盖", "score": 30, "passed": False, "reason": "无验证码"},
            {"criterion": "代码质量", "score": 90, "passed": True, "reason": "ok"}]},
        "e2e": {"passed": False, "issues": ["缺少密码框", "无登录按钮"]},
        "hallucination": {"hallucination_score": 50, "flagged": [{"claim": "虚构 /api/x", "why": "契约无此接口"}]},
        "vision": {"overall_score": 40, "summary": "布局错乱"},
    })
    # 未过项入选，通过的项不入
    assert any("需求覆盖" in i and "无验证码" in i for i in issues)
    assert not any("代码质量" in i for i in issues)
    # E2E / 幻觉 / 视觉
    assert any("缺少密码框" in i for i in issues)
    assert any("虚构 /api/x" in i for i in issues)
    # 反馈含话术约束（增量改造）
    assert "只修复评测指出的问题" in fb
    assert "保留现有页面" in fb
    assert "布局错乱" in fb  # 视觉摘要


def test_build_eval_fix_feedback_empty_struct():
    """空 eval_struct → 仍有话术框架（不崩），issues 为空。"""
    issues, fb = flow_manager._build_eval_fix_feedback({})
    assert issues == []
    assert "只修复评测指出的问题" in fb


def test_max_eval_fix_iterations_is_bounded():
    """eval 重修上限=2（独立于 code_review 的 3，控末段重跑成本）。"""
    assert flow_manager.MAX_EVAL_FIX_ITERATIONS == 2
    assert flow_manager.MAX_EVAL_FIX_ITERATIONS <= flow_manager.MAX_FIX_ITERATIONS
