"""美股结构化取数：行情快照、三表、分析师预期、K 线摘要（yfinance）。

对应 skills/us-stock-quote 与 us-stock-fundamentals。
"""
from __future__ import annotations

import yfinance as yf

from app.tools.us_stock.helpers import apply_yf_proxy, json_safe

# 财报关注的关键行（GAAP）
_INCOME_ROWS = [
    "Total Revenue", "Gross Profit", "Operating Income",
    "Net Income", "Diluted EPS",
]
_BALANCE_ROWS = [
    "Total Assets", "Total Liabilities Net Minority Interest",
    "Stockholders Equity", "Cash And Cash Equivalents", "Total Debt",
]
_CASHFLOW_ROWS = [
    "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
]

_QUOTE_KEYS = [
    "shortName", "currentPrice", "previousClose", "marketCap",
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda",
    "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "beta", "dividendYield",
    "profitMargins", "returnOnEquity", "revenueGrowth",
    "targetMeanPrice", "targetMedianPrice", "recommendationKey",
    "numberOfAnalystOpinions", "sector", "industry", "currency",
]


def us_quote_snapshot(ticker: str) -> dict:
    """行情与估值快照（含分析师目标价摘要）。"""
    t = yf.Ticker(ticker)
    info = t.info or {}
    snap = {k: info.get(k) for k in _QUOTE_KEYS if info.get(k) is not None}
    snap["ticker"] = ticker
    return snap


def us_financials(ticker: str, periods: int = 4) -> dict:
    """年报三表关键行（近 N 期），GAAP 口径。"""
    t = yf.Ticker(ticker)

    def rows(frame, keys: list[str]) -> dict:
        if frame is None or frame.empty:
            return {}
        frame = frame.iloc[:, :periods]  # 最近 N 期（列倒序为最新在前）
        out: dict = {}
        for key in keys:
            if key in frame.index:
                col = frame.loc[key].dropna()
                if not col.empty:
                    out[key] = {
                        str(c.date()) if hasattr(c, "date") else str(c): float(v)
                        for c, v in col.items()
                    }
        return out

    return {
        "income_annual": rows(t.income_stmt, _INCOME_ROWS),
        "balance_annual": rows(t.balance_sheet, _BALANCE_ROWS),
        "cashflow_annual": rows(t.cashflow, _CASHFLOW_ROWS),
    }


def us_history_summary(ticker: str, period: str = "1y") -> dict:
    """近 1 年 K 线摘要：区间收益、回撤、52 周高低点、近 10 日收盘。"""
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return {}
    close = hist["Close"]
    high = float(hist["High"].max())
    low = float(hist["Low"].min())
    last = float(close.iloc[-1])

    def ret(days: int) -> float | None:
        if len(close) <= days:
            return None
        base = float(close.iloc[-1 - days])
        return round((last / base - 1) * 100, 2) if base else None

    recent = {
        str(c.date()): round(float(v), 2)
        for c, v in close.tail(10).items()
    }
    return {
        "last_close": round(last, 2),
        "period_high": round(high, 2),
        "period_low": round(low, 2),
        "drawdown_from_high_pct": round((last / high - 1) * 100, 2),
        "return_1m_pct": ret(21),
        "return_3m_pct": ret(63),
        "return_6m_pct": ret(126),
        "return_1y_pct": ret(252) if len(close) > 126 else None,
        "recent_10d_close": recent,
    }


def collect_us_stock_data(ticker: str) -> dict:
    """汇总单只美股的结构化数据，供报告生成使用。"""
    apply_yf_proxy()
    parts: dict = {"ticker": ticker}
    for name, fn in (
        ("quote", us_quote_snapshot),
        ("financials", us_financials),
        ("history", us_history_summary),
    ):
        try:
            parts[name] = json_safe(fn(ticker))
        except Exception as e:  # noqa: BLE001 - 单个数据源失败不阻断整体
            parts[name] = {"error": str(e)}
    return parts
