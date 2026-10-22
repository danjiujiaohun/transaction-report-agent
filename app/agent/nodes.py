"""LangGraph 节点实现：plan -> search -> report 三段式流水线。"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.llm import get_llm
from app.tools.web_search import search as raw_search

_PLAN_SYSTEM = """你是一名专业的股票/公司研究助理。根据用户给出的公司名称或股票代码，\
规划出 3 到 5 个用于联网搜索的关键词，以便收集撰写分析报告所需的信息。

搜索关键词应覆盖以下维度（可从中挑选最相关的）：
1. 公司业务与主营业务概况
2. 最新财务数据（营收、利润、毛利率等）
3. 近期重大新闻与公告
4. 估值指标（市盈率、市净率等）与股价表现
5. 所属行业与竞争格局

只输出一个 JSON 数组，元素为字符串，不要输出任何其他文字。示例格式：["关键词1", "关键词2"]"""


def plan_queries(state: AgentState) -> AgentState:
    """节点 1：规划搜索关键词。"""
    llm = get_llm()
    resp = llm.invoke(
        [
            SystemMessage(content=_PLAN_SYSTEM),
            HumanMessage(content=state["company"]),
        ]
    )
    text = (resp.content or "").strip()

    queries: list[str] = []
    try:
        # 兼容 LLM 可能包裹在 markdown 代码块中的情况
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        parsed = json.loads(text)
        if isinstance(parsed, list):
            queries = [str(q) for q in parsed if str(q).strip()]
    except (json.JSONDecodeError, ValueError):
        # 解析失败时退化为两个通用查询
        queries = [f"{state['company']} 公司概况", f"{state['company']} 财务数据 最新"]

    if not queries:
        queries = [f"{state['company']} 公司概况", f"{state['company']} 财务数据 最新"]

    return {**state, "queries": queries}


def _resolve_code(company: str) -> str | None:
    """把公司名称/代码解析为纯 6 位 A 股代码；无法解析时返回 None。"""
    from app.tools.a_stock.helpers import norm_ticker
    from app.tools.a_stock.quote import search_stock_code

    try:
        return norm_ticker(company)
    except ValueError:
        pass

    candidates = search_stock_code(company)
    if not candidates:
        return None
    # 优先精确名称匹配，其次名称包含
    for c in candidates:
        if c["name"] == company or company in c["name"]:
            return c["code"]
    return candidates[0]["code"]


def _collect_a_stock_data(code: str) -> str:
    """拉取 A 股结构化数据，返回 Markdown 段落；失败的数据源写入错误提示。"""
    import json as _json

    from app.tools.a_stock.financials import sina_financial_report
    from app.tools.a_stock.quote import tencent_quote
    from app.tools.a_stock.research import eastmoney_reports, ths_eps_forecast
    from app.tools.a_stock.valuation import valuation_summary

    parts = [f"## A股结构化数据（代码 {code}）"]

    def dump(obj) -> str:
        return _json.dumps(obj, ensure_ascii=False)

    # 实时行情
    try:
        quote = tencent_quote([code])
        if quote:
            item = next(iter(quote.values()))
            if not item.get("is_stale"):
                parts.append("### 实时行情\n```json\n" + dump(item) + "\n```")
    except Exception as e:  # noqa: BLE001
        parts.append(f"### 实时行情\n获取失败: {e}")

    # 财务三表（利润表）
    try:
        parts.append("### 利润表（近8期）\n```json\n" + dump(sina_financial_report(code, "lrb")) + "\n```")
    except Exception as e:  # noqa: BLE001
        parts.append(f"### 利润表\n获取失败: {e}")

    # 估值历史摘要
    try:
        parts.append("### 估值历史（近5年）\n```json\n" + dump(valuation_summary(code)) + "\n```")
    except Exception as e:  # noqa: BLE001
        parts.append(f"### 估值历史\n获取失败: {e}")

    # 研报
    try:
        reports = eastmoney_reports(code)
        parts.append(f"### 研报（共{len(reports)}篇，展示前20）\n```json\n" + dump(reports[:20]) + "\n```")
    except Exception as e:  # noqa: BLE001
        parts.append(f"### 研报\n获取失败: {e}")

    # 一致预期 EPS
    try:
        parts.append("### 一致预期 EPS\n```json\n" + dump(ths_eps_forecast(code).to_dict(orient="records")) + "\n```")
    except Exception as e:  # noqa: BLE001
        parts.append(f"### 一致预期 EPS\n获取失败: {e}")

    return "\n\n".join(parts)


def do_search(state: AgentState) -> AgentState:
    """节点 2：执行 A 股取数 + 联网搜索并汇总结果。"""
    company = state.get("company", "")
    queries = state.get("queries", [])
    sections: list[str] = []

    # 1) 若能解析出股票代码，先拉结构化 A 股数据
    code = _resolve_code(company)
    if code:
        try:
            sections.append(_collect_a_stock_data(code))
        except Exception as e:  # noqa: BLE001
            sections.append(f"## A股结构化数据\n获取失败: {e}")

    # 2) 联网搜索补充定性信息
    for q in queries:
        try:
            results = raw_search(q)
        except Exception as e:  # noqa: BLE001 - 单次搜索失败不阻断整体流程
            sections.append(f"### 搜索词: {q}\n搜索失败: {e}")
            continue

        lines = [f"### 搜索词: {q}"]
        if not results:
            lines.append("（无结果）")
        for i, item in enumerate(results, 1):
            lines.append(
                f"{i}. {item['name']}\n   URL: {item['url']}\n   摘要: {item['snippet']}"
            )
        sections.append("\n".join(lines))

    return {**state, "search_results": "\n\n".join(sections)}


_REPORT_SYSTEM = """你是一名专业的股票市场分析师。请基于下方提供的搜索结果，为指定的公司撰写一份结构化、\
专业的 Markdown 分析报告。

要求：
1. 使用 Markdown 格式（标题、列表、表格等），便于前端直接渲染。
2. 报告应覆盖：公司概况、主营业务、财务表现、近期动态、估值与投资要点、风险提示、总结。
3. 只能基于搜索结果给出结论，不要编造数据；信息不足的部分如实说明“信息暂缺”。
4. 涉及关键数据或事实时，在文末附上参考来源链接。
5. 若提供了报告规则（skills），必须严格遵循其要求与模板。"""


def write_report(state: AgentState) -> AgentState:
    """节点 3：根据搜索结果与 skills 生成最终报告。"""
    llm = get_llm()

    system_parts = [_REPORT_SYSTEM]
    if state.get("skill_prompt"):
        system_parts.append("\n\n" + state["skill_prompt"])
    system = "\n".join(system_parts)

    user = (
        f"目标公司：{state['company']}\n\n"
        f"以下是收集到的资料：\n\n{state.get('search_results', '（无数据）')}\n\n"
        "请据此撰写完整的 Markdown 分析报告。"
    )

    resp = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
    )
    return {**state, "report": (resp.content or "").strip()}