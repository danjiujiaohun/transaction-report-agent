"""信号层工具：龙虎榜席位（东财数据中心）。"""
from __future__ import annotations

import json
from datetime import date, timedelta

from langchain_core.tools import tool

from app.tools.a_stock.helpers import eastmoney_datacenter, norm_ticker


def dragon_tiger_board(code: str, trade_date: str | None = None,
                       look_back: int = 30) -> dict:
    """龙虎榜聚合：近 look_back 天上榜记录 + 最近上榜买卖席位 + 机构统计。"""
    code = norm_ticker(code)
    end = trade_date or date.today().isoformat()
    start = (date.fromisoformat(end) - timedelta(days=look_back)).isoformat()

    records = []
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{end}')(SECURITY_CODE=\"{code}\")",
        page_size=50,
        sort_columns="TRADE_DATE", sort_types="-1",
    )
    for row in data:
        records.append({
            "date": str(row.get("TRADE_DATE", ""))[:10],
            "reason": row.get("EXPLANATION", ""),
            "net_buy": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
            "turnover": round(float(row.get("TURNOVERRATE") or 0), 2),
        })

    buy_data, sell_data = [], []
    seats = {"buy": [], "sell": []}
    if records:
        latest_date = records[0]["date"]
        def _seat_rows(report_name: str, sort_col: str) -> list[dict]:
            return eastmoney_datacenter(
                report_name,
                filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                page_size=10,
                sort_columns=sort_col, sort_types="-1",
            )

        buy_data = _seat_rows("RPT_BILLBOARD_DAILYDETAILSBUY", "BUY")
        for row in buy_data[:5]:
            seats["buy"].append({
                "name": row.get("OPERATEDEPT_NAME", ""),
                "buy_amt": round((row.get("BUY") or 0) / 10000, 1),
                "sell_amt": round((row.get("SELL") or 0) / 10000, 1),
                "net": round((row.get("NET") or 0) / 10000, 1),
            })
        sell_data = _seat_rows("RPT_BILLBOARD_DAILYDETAILSSELL", "SELL")
        for row in sell_data[:5]:
            seats["sell"].append({
                "name": row.get("OPERATEDEPT_NAME", ""),
                "buy_amt": round((row.get("BUY") or 0) / 10000, 1),
                "sell_amt": round((row.get("SELL") or 0) / 10000, 1),
                "net": round((row.get("NET") or 0) / 10000, 1),
            })

    institution = {"buy_amt": 0, "sell_amt": 0, "net_amt": 0}
    for detail_data, side in [(buy_data, "buy"), (sell_data, "sell")]:
        for row in detail_data:
            if str(row.get("OPERATEDEPT_CODE", "")) == "0":
                if side == "buy":
                    institution["buy_amt"] += (row.get("BUY") or 0)
                else:
                    institution["sell_amt"] += (row.get("SELL") or 0)
    institution["buy_amt"] = round(institution["buy_amt"] / 10000, 1)
    institution["sell_amt"] = round(institution["sell_amt"] / 10000, 1)
    institution["net_amt"] = round(institution["buy_amt"] - institution["sell_amt"], 1)

    return {"code": code, "records": records, "seats": seats, "institution": institution}


@tool
def get_dragon_tiger(code: str) -> str:
    """获取 A 股个股龙虎榜数据（近 30 天）。

    Args:
        code: 股票代码，如 '002475'。

    返回 JSON 文本：上榜记录（日期/原因/净买额/换手率）、最近上榜买卖席位 TOP5、
    机构专用席位买卖统计（单位：万元）。大市值/低换手率标的可能无上榜记录。
    """
    try:
        result = dragon_tiger_board(code)
    except Exception as e:  # noqa: BLE001
        return f"龙虎榜获取失败: {e}"
    return json.dumps(result, ensure_ascii=False)