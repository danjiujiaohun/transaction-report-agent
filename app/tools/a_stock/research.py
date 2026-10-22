"""研报与一致预期工具：东财研报列表 + 同花顺一致预期 EPS。"""
from __future__ import annotations

import json
from io import StringIO

import pandas as pd
from langchain_core.tools import tool

from app.tools.a_stock.helpers import direct_get, em_get, norm_ticker

REPORT_API = "https://reportapi.eastmoney.com/report/list"

_RECORD_FIELDS = (
    "title", "publishDate", "orgSName", "emRatingName",
    "predictThisYearEps", "predictNextYearEps", "predictNextTwoYearEps",
    "indvInduName",
)


def eastmoney_reports(code: str, max_pages: int = 3) -> list[dict]:
    """拉取指定股票的研报列表（东财，限流访问）。

    返回 [] 表示东财确无该标的研报覆盖；格式错误已在上游抛 ValueError。
    """
    code = norm_ticker(code, stock_only=True)
    all_records: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2000-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        r = em_get(REPORT_API, params=params,
                   headers={"Referer": "https://data.eastmoney.com/"}, timeout=30)
        d = r.json()
        rows = d.get("data") or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get("TotalPage", 1) or 1):
            break
    return all_records


def ths_eps_forecast(code: str) -> pd.DataFrame:
    """同花顺机构一致预期 EPS，返回 DataFrame（年度/预测机构数/最小值/均值/最大值）。"""
    code = norm_ticker(code, stock_only=True)
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    r = direct_get(url, headers={"Referer": "https://basic.10jqka.com.cn/"}, timeout=15)
    r.encoding = "gbk"
    dfs = pd.read_html(StringIO(r.text))
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    return dfs[0] if dfs else pd.DataFrame()


@tool
def get_research_reports(code: str) -> str:
    """获取 A 股个股研报列表（东财），含机构评级与盈利预测。

    Args:
        code: 股票代码，如 '600519'。

    返回 JSON 文本（最多 20 条）：标题、发布日期、机构、评级、年度 EPS 预测、行业。
    """
    try:
        records = eastmoney_reports(code)
    except Exception as e:  # noqa: BLE001
        return f"研报获取失败: {e}"
    if not records:
        return "未找到该标的的研报。"
    out = [
        {k: r[k] for k in _RECORD_FIELDS if r.get(k) not in (None, "")}
        for r in records[:20]
    ]
    return json.dumps(out, ensure_ascii=False)


@tool
def get_eps_forecast(code: str) -> str:
    """获取同花顺机构一致预期 EPS 预测。

    Args:
        code: 股票代码，如 '600519'。

    返回 JSON 文本：年度、预测机构数、最小值、均值（即一致预期 EPS）、最大值。
    """
    try:
        df = ths_eps_forecast(code)
    except Exception as e:  # noqa: BLE001
        return f"一致预期获取失败: {e}"
    if df is None or df.empty:
        return "未获取到一致预期 EPS 数据。"
    return df.to_json(orient="records", force_ascii=False)