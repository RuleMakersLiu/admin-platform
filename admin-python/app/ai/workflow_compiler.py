"""工作流 DSL → LangGraph 编译器。

DSL（JSON）:
  {"version": 1, "nodes": [{"id","type","name","config"}], "edges": [{"from","to","when"?}]}

编译产物是 LangGraph StateGraph，复用平台既有运行时语义：
- llm 节点经 AgentFactory 走多 Provider 模型路由
- human_input 节点用 langgraph interrupt()（与 pipeline_graph 的 needs_human 同机制），
  由 checkpointer 持久化，经 Command(resume=...) 恢复
- 条件出边（when）编译为 conditional_edges，表达式在受限环境求值
- 模板 {{#nodeId.field}} / {{#input.x}} 在节点执行时解析
"""
import re
from typing import Annotated, Any, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.ai.agents import AgentFactory
from app.ai.workflow_registry import get_node_type

_TEMPLATE_RE = re.compile(r"\{\{#([\w.]+)\}\}")

# 受限 eval 环境：DSL 是平台内部产物，仅暴露白名单内置函数
_SAFE_BUILTINS: dict[str, Any] = {
    "len": len, "str": str, "int": int, "float": float, "bool": bool,
    "min": min, "max": max, "abs": abs, "round": round,
    "true": True, "false": False,  # DSL 侧小写布尔字面量（Python 本身用 True/False）
}


class WorkflowState(TypedDict, total=False):
    """跨节点共享状态：inputs 为运行入参，variables 为各节点输出快照。"""

    inputs: dict
    variables: dict  # node_id -> dict
    visited: Annotated[list[str], lambda a, b: (a or []) + (b or [])]


class WorkflowValidationError(ValueError):
    """DSL 结构/引用不合法。"""


def validate_dsl(dsl: dict) -> list[dict]:
    """校验 DSL，返回规范化后的 nodes（非法直接抛 WorkflowValidationError）。"""
    if not isinstance(dsl, dict):
        raise WorkflowValidationError("dsl 必须是对象")
    nodes = dsl.get("nodes") or []
    edges = dsl.get("edges") or []
    if not nodes:
        raise WorkflowValidationError("nodes 不能为空")
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)) or any(not i for i in ids):
        raise WorkflowValidationError("节点 id 不能为空且不能重复")
    types = {n["id"]: n.get("type") for n in nodes}
    if list(types.values()).count("start") != 1 or list(types.values()).count("end") < 1:
        raise WorkflowValidationError("必须有恰好 1 个 start 节点和至少 1 个 end 节点")
    for n in nodes:
        if not get_node_type(n.get("type", "")):
            raise WorkflowValidationError(f"未知节点类型: {n.get('type')}（节点 {n['id']}）")
        for field_key in (n.get("config") or {}):
            spec = get_node_type(n["type"])
            if spec and field_key not in [f.key for f in spec.fields]:
                raise WorkflowValidationError(f"节点 {n['id']} 含未知配置项 {field_key}")
    for e in edges:
        if e.get("from") not in ids or e.get("to") not in ids:
            raise WorkflowValidationError(f"边引用了不存在的节点: {e}")
    return nodes


def resolve_template(value: Any, variables: dict, inputs: dict) -> Any:
    """解析 {{#nodeId.field}} / {{#input.x}} 引用；无占位符原样返回。

    整串恰为一个占位符时保留原类型（可引用 dict/list），否则做字符串拼接。
    """
    if not isinstance(value, str):
        return value

    def _lookup(path: str) -> Any:
        parts = path.split(".")
        root = parts[0]
        if root == "input":
            cur: Any = inputs
            parts = parts[1:]
        else:
            cur = (variables or {}).get(root)
            parts = parts[1:]
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return ""
        return cur if cur is not None else ""

    matches = _TEMPLATE_RE.findall(value)
    if not matches:
        return value
    if len(matches) == 1 and _TEMPLATE_RE.fullmatch(value.strip()):
        return _lookup(matches[0])
    return _TEMPLATE_RE.sub(lambda m: str(_lookup(m.group(1))), value)


class _AttrDict(dict):
    """dict 的点访问包装：让 DSL 表达式支持 input.topic / vars.llm1.text 风格。"""

    def __getattr__(self, name: str) -> Any:
        try:
            return _wrap_attr(self[name])
        except KeyError as exc:
            raise AttributeError(name) from exc


def _wrap_attr(value: Any) -> Any:
    return _AttrDict(value) if isinstance(value, dict) else value


def _eval_condition(expression: str, variables: dict, inputs: dict) -> bool:
    """在受限环境对条件表达式求值。变量名直接用节点 id（如 llm1.text）。"""
    env: dict[str, Any] = dict(_SAFE_BUILTINS)
    env["input"] = _AttrDict(inputs or {})
    env["vars"] = _AttrDict(variables or {})
    for node_id, out in (variables or {}).items():
        env.setdefault(node_id, _wrap_attr(out))
    try:
        return bool(eval(expression, {"__builtins__": env}, env))  # noqa: S307 DSL 内部表达式
    except Exception as exc:
        raise WorkflowValidationError(f"条件表达式求值失败: {expression!r} -> {exc}") from exc


def _resolve_config(config: dict, variables: dict, inputs: dict) -> dict:
    return {k: resolve_template(v, variables, inputs) for k, v in (config or {}).items()}


def _make_node_executor(node: dict):
    """为单个 DSL 节点生成 LangGraph 节点函数（读取上游 variables → 写回自身输出）。"""
    node_id, node_type, config = node["id"], node["type"], node.get("config") or {}

    async def _run(state: WorkflowState) -> dict:
        variables = dict(state.get("variables") or {})
        inputs = dict(state.get("inputs") or {})
        cfg = _resolve_config(config, variables, inputs)

        if node_type == "start":
            output: dict = {"ok": True}
        elif node_type == "end":
            output = {"summary": {k: v for k, v in variables.items() if k != "start"}}
        elif node_type == "llm":
            agent = AgentFactory.get_agent(cfg.get("agent_type") or "PM")
            reply = await agent.process(str(cfg.get("prompt", "")), [])
            output = {"text": reply}
        elif node_type == "condition":
            expression = str(cfg.get("expression", "true"))
            output = {"result": _eval_condition(expression, variables, inputs)}
        elif node_type == "human_input":
            payload = interrupt({"node_id": node_id, "message": cfg.get("message", "")})
            output = {"approved": payload}
        else:  # registry 有、executor 未实现的类型（未来 code/knowledge 节点）
            raise WorkflowValidationError(f"节点类型 {node_type} 尚未实现执行器")

        variables[node_id] = output
        return {"variables": variables, "visited": [node_id]}

    _run.__name__ = f"wf_node_{node_id}"
    return _run


def _make_router(edges_from_node: list[dict]):
    """生成分支路由函数：when 求值（缺省 true），首条为真的出边生效。"""
    def _route(state: WorkflowState) -> str:
        variables = state.get("variables") or {}
        inputs = state.get("inputs") or {}
        for edge in edges_from_node:
            when = edge.get("when")
            if when is None or when == "" or _eval_condition(str(when), variables, inputs):
                return edge["to"]
        return END

    return _route


def compile_workflow(dsl: dict):
    """DSL → 已编译 LangGraph（带 MemorySaver checkpointer，支持 interrupt/resume）。

    返回 (compiled_graph, checkpointer)。调用方以 thread_id=run_id 驱动与恢复。
    """
    nodes = validate_dsl(dsl)
    edges = dsl.get("edges") or []
    edges_by_from: dict[str, list[dict]] = {}
    for e in edges:
        edges_by_from.setdefault(e["from"], []).append(e)

    graph = StateGraph(WorkflowState)
    for node in nodes:
        graph.add_node(node["id"], _make_node_executor(node))
        if node["type"] == "start":
            graph.add_edge(START, node["id"])

    for node in nodes:
        node_id, node_type = node["id"], node["type"]
        out_edges = edges_by_from.get(node_id, [])
        if node_type == "end" or not out_edges:
            graph.add_edge(node_id, END)
            continue
        spec = get_node_type(node_type)
        if spec and spec.supports_branch and len(out_edges) > 1:
            graph.add_conditional_edges(node_id, _make_router(out_edges), [e["to"] for e in out_edges])
        else:
            graph.add_edge(node_id, out_edges[0]["to"])

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer), checkpointer


def extract_waiting(result: dict) -> Optional[dict]:
    """从 ainvoke 结果中提取 interrupt 等待信息（LangGraph 以 __interrupt__ 键返回）。"""
    intr = result.get("__interrupt__") if isinstance(result, dict) else None
    if intr and len(intr) > 0:
        item = intr[0]
        value = getattr(item, "value", None) or (item.get("value") if isinstance(item, dict) else None)
        if isinstance(value, dict):
            return value
    return None
