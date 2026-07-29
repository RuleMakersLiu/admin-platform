"""Phase 3：eval 显式阶段 + 折入报告的离线单测。

覆盖：
- _format_eval_report：功能/幻觉/视觉结构化 → markdown（含分数、虚构项、跳过提示）
- _run_eval_stage：注入假 judge，验调用 + 透传 + 视觉 best-effort 跳过不崩
- _render_prompt_template：{{eval_result}} 注入 + 缺省文案
- STAGE_DEFINITIONS：eval 在 report 之前
"""
import asyncio
import json
from types import SimpleNamespace

from app.ai import flow_manager


def _run(coro):
    return asyncio.run(coro)


# ---------- _format_eval_report ----------

def test_format_eval_report_basic():
    structured = {
        "judge": {"overall_score": 85, "per_criterion": [
            {"criterion": "需求覆盖", "score": 90, "passed": True, "reason": "ok"}], "summary": "good"},
        "hallucination": {"hallucination_score": 100, "flagged": [], "summary": "clean"},
    }
    md = flow_manager._format_eval_report(structured)
    assert "85" in md
    assert "需求覆盖" in md
    assert "✅" in md
    assert "幻觉分：100" in md
    assert "虚构嫌疑：无" in md


def test_format_eval_report_flagged_and_vision():
    structured = {
        "judge": {"overall_score": 60, "per_criterion": [], "summary": ""},
        "hallucination": {"hallucination_score": 40, "flagged": ["虚构 API /api/foo"], "summary": ""},
        "vision": {"overall_score": 75, "summary": "rendered"},
    }
    md = flow_manager._format_eval_report(structured)
    assert "虚构 API /api/foo" in md
    assert "渲染分：75" in md


def test_format_eval_report_vision_skipped():
    structured = {
        "judge": {"overall_score": 70, "per_criterion": [], "summary": ""},
        "hallucination": {"hallucination_score": 90, "flagged": [], "summary": ""},
        "vision_error": "no renderable html",
    }
    md = flow_manager._format_eval_report(structured)
    assert "视觉评审" in md
    assert "跳过" in md


# ---------- _run_eval_stage（注入假 judge） ----------

def test_run_eval_stage_calls_judges(monkeypatch):
    async def fake_judge_output(inp, out, crit, llm=None):
        assert crit == flow_manager.DEFAULT_EVAL_CRITERIA
        return {"overall_score": 88, "per_criterion": [
            {"criterion": "需求覆盖", "score": 88, "passed": True, "reason": "ok"}], "summary": "s"}

    async def fake_judge_hallucination(req, out, llm=None):
        return {"hallucination_score": 95, "flagged": [], "summary": "clean"}

    monkeypatch.setattr("app.ai.eval_judge.judge_output", fake_judge_output)
    monkeypatch.setattr("app.ai.eval_judge.judge_hallucination", fake_judge_hallucination)

    pipe = SimpleNamespace(
        pipeline_id="pipe_x", user_request="做一个登录页",
        stages_data=json.dumps({"requirement": {"output": "需求..."}}), tenant_id=1,
    )
    mgr = flow_manager.DevPipelineManager.__new__(flow_manager.DevPipelineManager)
    md, structured = _run(mgr._run_eval_stage(pipe, {"requirement": {"output": "需求..."}}))
    assert structured["judge"]["overall_score"] == 88
    assert structured["hallucination"]["hallucination_score"] == 95
    assert "88" in md
    # 视觉 best-effort：无真实 pipeline artifact → 报错跳过，不崩
    assert structured.get("vision_error") or "vision" not in structured


def test_run_eval_stage_survives_judge_error(monkeypatch):
    async def boom(inp, out, crit, llm=None):
        raise RuntimeError("judge exploded")
    async def fake_halluc(req, out, llm=None):
        return {"hallucination_score": 100, "flagged": [], "summary": ""}
    monkeypatch.setattr("app.ai.eval_judge.judge_output", boom)
    monkeypatch.setattr("app.ai.eval_judge.judge_hallucination", fake_halluc)
    pipe = SimpleNamespace(
        pipeline_id="pipe_x", user_request="x",
        stages_data=json.dumps({"requirement": {"output": "x"}}), tenant_id=1,
    )
    mgr = flow_manager.DevPipelineManager.__new__(flow_manager.DevPipelineManager)
    # judge_output 抛错会冒泡（调用方 execute_stage 兜底为 error 文案，不阻塞报告）
    try:
        _run(mgr._run_eval_stage(pipe, {}))
        raised = False
    except RuntimeError:
        raised = True
    assert raised


# ---------- _render_prompt_template：{{eval_result}} 注入 ----------

def test_render_prompt_template_injects_eval_result():
    template = "测评:\n{{eval_result}}\n报告"
    ctx = {"stage_outputs": {"eval": {"output": "# 自动测评报告\n总分 90"}}}
    rendered = flow_manager._render_prompt_template(template, ctx)
    assert "总分 90" in rendered
    assert "{{eval_result}}" not in rendered


def test_render_prompt_template_eval_missing_default():
    rendered = flow_manager._render_prompt_template("{{eval_result}}", {"stage_outputs": {}})
    assert "自动测评未运行" in rendered


# ---------- STAGE_DEFINITIONS 顺序 ----------

def test_eval_stage_before_report():
    keys = [s["key"] for s in flow_manager.STAGE_DEFINITIONS]
    assert "eval" in keys
    assert keys.index("eval") < keys.index("report")
