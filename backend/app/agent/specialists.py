"""Specialist capabilities are enforced by separate tool registries and graph contexts."""

from dataclasses import replace
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import StructuredTool
from .state import AgentState
from .runtime_nodes import build_nodes


class Delegation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str = Field(
        min_length=1,
        max_length=2000,
        description="具体需要核实的问题，包含已知商品/订单线索；不传用户身份。",
    )


SPECIALISTS = {
    "product_agent": {
        "label": "商品咨询",
        "description": "调度商品咨询 Agent：搜索、推荐、比较商品，查询商品参数、售价、库存、当前用户最近浏览及购买偏好。",
        "tools": {
            "list_product_categories",
            "search_products",
            "get_product_details",
            "get_my_browsing_history",
            "search_my_chat_history",
        },
        "prompt": "你是商品咨询专员。根据用户需求查询商品、最近浏览与选购偏好。实时参数、库存和售价必须查询。涉及订单状态或退款条件，应明确交回 Manager 调度其他专员，不越权查询。",
    },
    "order_agent": {
        "label": "订单查询",
        "description": "调度订单查询 Agent：查询当前用户的订单、订单商品、支付/发货/物流状态和关联售后状态，定位订单编号。",
        "tools": {"list_my_orders", "get_my_order_details", "search_my_chat_history"},
        "prompt": "你是订单查询专员。只查当前用户订单、商品明细、状态和物流。订单不明确时先查列表并说明候选，不能擅自认定某笔订单。退款规则交回售后专员，不执行订单修改。",
    },
    "aftersales_agent": {
        "label": "售后服务",
        "description": "调度售后 Agent：核实订单和现行退款政策，解释自动退款/人工审核/退货条件、申请材料与售后进度，不执行退款。",
        "tools": {
            "get_refund_policy",
            "list_my_orders",
            "get_my_order_details",
            "search_my_chat_history",
        },
        "prompt": "你是售后服务专员。涉及退款条件必须调用 get_refund_policy；针对具体订单的结论还必须核实当前订单。结合规则说明自动处理、人工核验或退货流程及所需资料。存在歧义先让用户确认，不承诺审核结果或退款到账。",
    },
}


def delegation_tools():
    # These schemas describe graph routing only. They do not execute database queries.
    def schema_only(task):
        return task

    return [
        StructuredTool.from_function(
            func=schema_only,
            name=name,
            args_schema=Delegation,
            description=spec["description"],
        )
        for name, spec in SPECIALISTS.items()
    ]


def specialist_graph(name, settings, tools, prompt, budget, model_factory):
    spec = SPECIALISTS[name]
    nodes = build_nodes(
        replace(settings, max_steps=settings.max_worker_steps),
        [tool for tool in tools if tool.name in spec["tools"]],
        prompt
        + "\n"
        + spec["prompt"]
        + "\n用户明确要求搜索历史聊天时，必须实际调用 search_my_chat_history，不能只根据当前会话回忆。",
        budget.deadline,
        model_factory,
        budget=budget,
        actor=name,
    )
    graph = StateGraph(AgentState)
    graph.add_node("model", nodes[0])
    graph.add_node("tools", nodes[1])
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", nodes[2], {"tools": "tools", "end": END})
    graph.add_edge("tools", "model")
    return graph.compile()
