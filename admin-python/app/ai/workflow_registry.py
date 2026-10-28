"""工作流节点类型注册表——编辑器面板与 DSL 校验共同依赖的协议层。

每个节点类型声明：类型名 / 显示名 / 分类 / 配置字段 schema（编辑器据此渲染表单、
编译器据此校验 DSL）。MVP 内置 5 种；code/knowledge 等节点按需在此追加。
"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class NodeFieldSpec(BaseModel):
    """单个配置字段的描述（antd Form 可直接按 type 渲染控件）。"""

    key: str
    label: str
    type: str = "string"  # string / text / select / number
    required: bool = False
    default: Any = None
    options: Optional[list[dict]] = None  # type=select 时的选项 [{value,label}]
    placeholder: str = ""


class NodeTypeSpec(BaseModel):
    """节点类型规格。"""

    type: str
    name: str
    category: str  # 基础 / 智能体 / 流程控制
    description: str = ""
    fields: list[NodeFieldSpec] = Field(default_factory=list)
    # 出边是否可带 when 条件（condition/human_input 节点为 True）
    supports_branch: bool = False
    allow_delete: bool = True  # start/end 节点画布上不允许删除


_REGISTRY: dict[str, NodeTypeSpec] = {}


def register(spec: NodeTypeSpec) -> None:
    _REGISTRY[spec.type] = spec


def get_node_type(type_name: str) -> Optional[NodeTypeSpec]:
    return _REGISTRY.get(type_name)


def list_node_types() -> list[NodeTypeSpec]:
    return list(_REGISTRY.values())


register(NodeTypeSpec(
    type="start",
    name="开始",
    category="基础",
    description="工作流入口，运行时的 inputs 从这里进入",
    allow_delete=False,
    fields=[NodeFieldSpec(key="note", label="说明", type="text", default="")],
))
register(NodeTypeSpec(
    type="llm",
    name="LLM 节点",
    category="智能体",
    description="调用平台 Agent（复用 AgentFactory 的模型路由与多 Provider 分发）",
    fields=[
        NodeFieldSpec(
            key="prompt", label="Prompt 模板", type="text", required=True,
            placeholder="支持 {{#节点ID.字段}} 与 {{#input.变量名}} 引用上游产物",
        ),
        NodeFieldSpec(
            key="agent_type", label="Agent 类型", type="select", default="PM",
            options=[{"value": v, "label": v} for v in ["PM", "PJM", "BE", "FE", "QA", "RPT"]],
        ),
    ],
))
register(NodeTypeSpec(
    type="condition",
    name="条件分支",
    category="流程控制",
    description="对表达式求值，按出边 when 路由（首条为真的出边生效）",
    supports_branch=True,
    fields=[
        NodeFieldSpec(
            key="expression", label="条件表达式", type="text", required=True,
            placeholder="如 len(llm1.text) > 10，可用变量见右侧说明",
        ),
    ],
))
register(NodeTypeSpec(
    type="human_input",
    name="人工输入",
    category="流程控制",
    description="暂停等待人工确认（interrupt），resume 的值写入 approved 字段",
    supports_branch=True,
    fields=[
        NodeFieldSpec(key="message", label="提示信息", type="text", required=True,
                      placeholder="展示给审批人的说明，支持模板引用"),
    ],
))
register(NodeTypeSpec(
    type="end",
    name="结束",
    category="基础",
    description="工作流出口，聚合最终产物",
    allow_delete=False,
    fields=[NodeFieldSpec(key="note", label="说明", type="text", default="")],
))
