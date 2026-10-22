"""财务三表工具：新浪财经（利润表 / 资产负债表 / 现金流量表）。"""
from __future__ import annotations

import json

from langchain_core.tools import tool

from app.tools.a_stock.helpers import direct_get, get_prefix, norm_ticker

_REPORT_TYPES = {
    "lrb": "利润表",
    "fzb": "资产负债表",
    "llb": "现金流量表",
}


def sina_financial_report(code: str, report_type: str = "lrb", num: int = 8) -> list[dict]:
    """新浪财报三表，按报告期倒序返回记录列表。

    Args:
        code: 6 位股票代码（支持 600519 / sh600519 / 600519.SH）。
        report_type: lrb(利润表) / fzb(资产负债表) / llb(现金流量表)。
        num: 取最近期数上限。
    """
    code = norm_ticker(code)
    paper_code = f"{get_prefix(code)}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": report_type,
        "type": "0",
        "page": "1",
        "num": str(num),
    }
    resp = direct_get(url, params=params, timeout=15)
    _j = resp.json() or {}
    report_list = ((_j.get("result") or {}).get("data") or {}).get("report_list") or {}

    rows: list[dict] = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period]
        rec = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for it in (obj.get("data") or []):
            title = it.get("item_title", "")
            if not title or it.get("item_value") is None:
                continue
            rec[title] = it.get("item_value")
            tongbi = it.get("item_tongbi")
            if tongbi not in (None, ""):
                rec[title + "_同比"] = tongbi
        rows.append(rec)
    return rows


@tool
def get_financial_statements(code: str, report_type: str = "lrb") -> str:
    """获取 A 股公司财报三表（新浪财经）。

    Args:
        code: 股票代码，如 '600519' 或 '300750'。
        report_type: 'lrb'(利润表) / 'fzb'(资产负债表) / 'llb'(现金流量表)。

    返回最近 8 期数据的 JSON 文本，含各科目数值与同比字段（形如 "<科目>_同比"）。
    """
    if report_type not in _REPORT_TYPES:
        return f"无效的 report_type: {report_type}（应为 {'/'.join(_REPORT_TYPES)}）"
    try:
        rows = sina_financial_report(code, report_type)
    except Exception as e:  # noqa: BLE001
        return f"财务数据获取失败: {e}"
    if not rows:
        return f"{_REPORT_TYPES[report_type]}暂无数据。"
    return json.dumps(rows, ensure_ascii=False)