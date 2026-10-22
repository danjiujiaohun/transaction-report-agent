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


def generate_report(company: str, skill_prompt: str = "") -> str:
    """执行完整分析流程，返回 Markdown 报告全文。"""
    result = _graph.invoke(
        {"company": company, "skill_prompt": skill_prompt}
    )
    return result.get("report", "")