"""LangGraph Agent 状态定义。"""
from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    """分析流程中在各节点间传递的状态。"""

    company: str           # 输入：公司名称/代码
    skill_prompt: str      # 注入的 skills 规则文本
    queries: list[str]     # 规划出的搜索关键词列表
    search_results: str    # 汇总后的搜索结果文本
    report: str            # 最终 Markdown 报告