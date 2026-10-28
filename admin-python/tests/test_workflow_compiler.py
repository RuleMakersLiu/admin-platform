"""工作流编排编译器测试：DSL 校验 / 模板解析 / 线性执行 / 条件分支 / 人工中断恢复。"""
import pytest

from app.ai.agents import AgentFactory
from app.ai.workflow_compiler import (
    WorkflowValidationError,
    compile_workflow,
    extract_waiting,
    resolve_template,
    validate_dsl,
)


class _FakeAgent:
    def __init__(self, reply: str = "fake-reply"):
        self.reply = reply

    async def process(self, message, history=None, attachments=None):
        return f"{self.reply}:{message}"


def _linear_dsl() -> dict:
    return {
        "version": 1,
        "name": "linear",
        "nodes": [
            {"id": "start", "type": "start", "name": "开始", "config": {}},
            {"id": "llm1", "type": "llm", "name": "生成", "config": {"prompt": "你好 {{#input.topic}}", "agent_type": "PM"}},
            {"id": "end", "type": "end", "name": "结束", "config": {}},
        ],
        "edges": [
            {"from": "start", "to": "llm1"},
            {"from": "llm1", "to": "end"},
        ],
    }


def _branch_dsl() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "cond", "type": "condition", "config": {"expression": "len(input.topic) > 3"}},
            {"id": "end_long", "type": "end", "config": {}},
            {"id": "end_short", "type": "end", "config": {}},
        ],
        "edges": [
            {"from": "start", "to": "cond"},
            {"from": "cond", "to": "end_long", "when": "vars.cond.result == true"},
            {"from": "cond", "to": "end_short", "when": "vars.cond.result == false"},
        ],
    }


def _human_dsl() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "human", "type": "human_input", "config": {"message": "确认发布 {{#input.topic}}？"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"from": "start", "to": "human"},
            {"from": "human", "to": "end", "when": "vars.human.approved == True"},
        ],
    }


# ---------------- 校验 ----------------

def test_validate_dsl_rejects_bad_structure():
    with pytest.raises(WorkflowValidationError):
        validate_dsl({"nodes": [], "edges": []})
    with pytest.raises(WorkflowValidationError):
        validate_dsl({"nodes": [{"id": "a", "type": "llm"}], "edges": []})  # 无 start/end
    with pytest.raises(WorkflowValidationError):
        validate_dsl({
            "nodes": [{"id": "start", "type": "start"}, {"id": "start", "type": "end"}],
            "edges": [],
        })
    with pytest.raises(WorkflowValidationError):
        validate_dsl({
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "x", "type": "不存在的类型"},
                {"id": "end", "type": "end"},
            ],
            "edges": [{"from": "start", "to": "x"}, {"from": "x", "to": "end"}],
        })


def test_validate_dsl_rejects_unknown_edge_ref():
    with pytest.raises(WorkflowValidationError):
        validate_dsl({
            "nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}],
            "edges": [{"from": "start", "to": "ghost"}],
        })


# ---------------- 模板 ----------------

def test_resolve_template_interpolation_and_passthrough():
    variables = {"llm1": {"text": "世界"}, "start": {"ok": True}}
    assert resolve_template("你好 {{#llm1.text}}", variables, {}) == "你好 世界"
    # 整串单个占位符保留原类型
    assert resolve_template("{{#llm1}}", variables, {}) == {"text": "世界"}
    assert resolve_template("{{#llm1.text}}", variables, {}) == "世界"
    assert resolve_template("{{#input.topic}}", variables, {"topic": "T"}) == "T"
    assert resolve_template("plain text", variables, {}) == "plain text"
    assert resolve_template(42, variables, {}) == 42


# ---------------- 执行 ----------------

@pytest.mark.asyncio
async def test_linear_run_with_fake_agent(monkeypatch):
    monkeypatch.setattr(AgentFactory, "get_agent", classmethod(lambda cls, t: _FakeAgent("ok")))
    graph, _ = compile_workflow(_linear_dsl())
    result = await graph.ainvoke(
        {"inputs": {"topic": "登录页"}, "variables": {}},
        config={"configurable": {"thread_id": "t1"}},
    )
    variables = result["variables"]
    assert variables["llm1"]["text"] == "ok:你好 登录页"
    assert "llm1" in variables["end"]["summary"]


@pytest.mark.asyncio
async def test_condition_branch_routes_true_edge(monkeypatch):
    graph, _ = compile_workflow(_branch_dsl())
    result = await graph.ainvoke(
        {"inputs": {"topic": "四个字以上"}, "variables": {}},
        config={"configurable": {"thread_id": "t2"}},
    )
    assert result["variables"]["cond"]["result"] is True
    assert "end_long" in result["variables"]
    assert "end_short" not in result["variables"]


@pytest.mark.asyncio
async def test_condition_branch_routes_false_edge(monkeypatch):
    graph, _ = compile_workflow(_branch_dsl())
    result = await graph.ainvoke(
        {"inputs": {"topic": "短"}, "variables": {}},
        config={"configurable": {"thread_id": "t3"}},
    )
    assert result["variables"]["cond"]["result"] is False
    assert "end_short" in result["variables"]
    assert "end_long" not in result["variables"]


@pytest.mark.asyncio
async def test_human_input_interrupt_and_resume(monkeypatch):
    from langgraph.types import Command

    graph, _ = compile_workflow(_human_dsl())
    config = {"configurable": {"thread_id": "t4"}}
    result = await graph.ainvoke({"inputs": {"topic": "发布单"}, "variables": {}}, config=config)

    waiting = extract_waiting(result)
    assert waiting is not None
    assert waiting["node_id"] == "human"
    assert "发布单" in waiting["message"]

    result = await graph.ainvoke(Command(resume=True), config=config)
    assert result["variables"]["human"]["approved"] is True
    assert "human" in result["variables"]["end"]["summary"]


@pytest.mark.asyncio
async def test_bad_expression_fails_validation(monkeypatch):
    monkeypatch.setattr(AgentFactory, "get_agent", classmethod(lambda cls, t: _FakeAgent()))
    dsl = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "cond", "type": "condition", "config": {"expression": "undefined_name ~~ 3"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [{"from": "start", "to": "cond"}, {"from": "cond", "to": "end"}],
    }
    graph, _ = compile_workflow(dsl)
    with pytest.raises(Exception, match="条件表达式求值失败|invalid syntax"):
        await graph.ainvoke({"inputs": {}, "variables": {}},
                            config={"configurable": {"thread_id": "t5"}})
