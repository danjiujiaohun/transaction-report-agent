"""A股取数工具包：行情 / 财务三表 / 估值历史 / 研报 / 一致预期。"""
from app.tools.a_stock.financials import get_financial_statements
from app.tools.a_stock.quote import get_realtime_quote
from app.tools.a_stock.research import get_eps_forecast, get_research_reports
from app.tools.a_stock.valuation import get_valuation_history

# 供 Agent 组合使用的 LangChain 工具列表
A_STOCK_TOOLS = [
    get_realtime_quote,
    get_financial_statements,
    get_valuation_history,
    get_research_reports,
    get_eps_forecast,
]

__all__ = ["A_STOCK_TOOLS"]