"""资金面/筹码层工具：股东户数、分红送转、个股资金流（东财）。"""
from __future__ import annotations

import json

from langchain_core.tools import tool

from app.tools.a_stock.helpers import eastmoney_datacenter, em_get, em_secid, norm_ticker


def holder_num_change(code: str, page_size: int = 10) -> list[dict]:
    """股东户数变化（季度级）。"""
    code = norm_ticker(code)
    data = eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="END_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("END_DATE", ""))[:10],
            "holder_num": row.get("HOLDER_NUM", 0),
            "change_num": row.get("HOLDER_NUM_CHANGE", 0),
            "change_ratio": row.get("HOLDER_NUM_RATIO", 0),  # 环比%
            "avg_shares": row.get("AVG_FREE_SHARES", 0),     # 户均持股
        })
    return rows


def dividend_history(code: str, page_size: int = 20) -> list[dict]:
    """分红送转历史。"""
    code = norm_ticker(code)
    data = eastmoney_datacenter(
        "RPT_SHAREBONUS_DET",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("EX_DIVIDEND_DATE", ""))[:10],
            "bonus_rmb": row.get("PRETAX_BONUS_RMB", 0),    # 每股派息(税前)
            "transfer_ratio": row.get("TRANSFER_RATIO", 0),  # 每10股转增
            "bonus_ratio": row.get("BONUS_RATIO", 0),        # 每10股送股
            "plan": row.get("ASSIGN_PROGRESS", ""),           # 进度
        })
    return rows


def stock_fund_flow_120d(code: str) -> list[dict]:
    """个股资金流（日级，最近 120 个交易日），单位：元。"""
    code = norm_ticker(code)
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": em_secid(code),
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    headers = {
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
    }
    r = em_get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    klines = (d.get("data") or {}).get("klines") or []

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            def f(v: str) -> float:
                try:
                    return float(v) if v != "-" else 0.0
                except ValueError:
                    return 0.0
            rows.append({
                "date": parts[0],
                "main_net": f(parts[1]),   # 主力净流入
                "small_net": f(parts[2]),  # 小单净流入
                "mid_net": f(parts[3]),    # 中单净流入
                "large_net": f(parts[4]),  # 大单净流入
                "super_net": f(parts[5]),  # 超大单净流入
            })
    return rows


@tool
def get_holder_num(code: str) -> str:
    """获取 A 股股东户数变化（季度级）。

    Args:
        code: 股票代码，如 '600519'。

    返回 JSON 文本：报告期、股东户数、户数变化、环比%、户均持股。
    股东户数持续减少通常意味着筹码集中。
    """
    try:
        rows = holder_num_change(code)
    except Exception as e:  # noqa: BLE001
        return f"股东户数获取失败: {e}"
    if not rows:
        return "未获取到股东户数数据。"
    return json.dumps(rows, ensure_ascii=False)


@tool
def get_dividend_history(code: str) -> str:
    """获取 A 股分红送转历史。

    Args:
        code: 股票代码，如 '600519'。

    返回 JSON 文本：除权除息日、每股派息(税前)、每10股转增、每10股送股、进度。
    """
    try:
        rows = dividend_history(code)
    except Exception as e:  # noqa: BLE001
        return f"分红历史获取失败: {e}"
    if not rows:
        return "未获取到分红送转数据。"
    return json.dumps(rows, ensure_ascii=False)


@tool
def get_fund_flow(code: str) -> str:
    """获取 A 股个股资金流（日级，最近 120 个交易日，东财）。

    Args:
        code: 股票代码，如 '600519'。

    返回 JSON 文本：日期、主力/超大单/大单/中单/小单净流入（单位：元），
    并附最近 20 日主力累计净流入（单位：亿元）。
    """
    try:
        rows = stock_fund_flow_120d(code)
    except Exception as e:  # noqa: BLE001
        return f"资金流获取失败: {e}"
    if not rows:
        return "未获取到资金流数据。"
    recent_20 = rows[-20:]
    total_main = sum(r["main_net"] for r in recent_20)
    result = {
        "code": norm_ticker(code),
        "近20日主力累计净流入_亿": round(total_main / 1e8, 2),
        "最近20日": recent_20,
    }
    return json.dumps(result, ensure_ascii=False)