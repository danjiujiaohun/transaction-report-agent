"""构建并导出 LangGraph 图与统一入口函数。"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import do_search, plan_queries, write_report
from app.agent.state import AgentState


def build_graph():
    """构建 plan -> search -> report 三段式流水线图。"""
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_queries)
    graph.add_node("search", do_search)
    graph.add_node("report", write_report)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "report")
    graph.add_edge("report", END)

    return graph.compile()


# 编译一次，复用（图本身无状态，可安全并发调用）
_graph = build_graph()


# 各节点对应的进度阶段文案
_PHASES = {
    "plan": "规划检索关键词",
    "search": "采集结构化数据与联网搜索",
    "report": "生成分析报告",
}


def generate_report(
    company: str,
    skill_prompt: str = "",
    dimensions: list[str] | None = None,
    on_progress=None,
) -> str:
    """执行完整分析流程，返回 Markdown 报告全文。

    Args:
        company: 公司名称或股票代码。
        skill_prompt: 注入的 skills 规则文本。
        dimensions: 用户勾选的研究维度关键词（可选），用于定向检索与报告落点。
        on_progress: 可选回调 `fn(phase: str)`，用于把阶段进度透出给调用方（如异步任务状态）。
    """
    initial: AgentState = {
        "company": company,
        "skill_prompt": skill_prompt,
        "dimensions": dimensions or [],
    }
    final: dict = dict(initial)

    for chunk in _graph.stream(initial, stream_mode="updates"):
        for node, update in chunk.items():
            if isinstance(update, dict):
                final.update(update)
            if on_progress and node in _PHASES:
                on_progress(_PHASES[node])

    return final.get("report", "")