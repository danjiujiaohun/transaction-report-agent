"""行情工具：名称→代码搜索、腾讯实时行情（价格/PE/PB/市值/换手率）。"""
from __future__ import annotations

import json
import re
import urllib.parse

from langchain_core.tools import tool

from app.tools.a_stock.helpers import direct_get, get_prefix, norm_ticker


def search_stock_code(name: str) -> list[dict[str, str]]:
    """按公司名称/代码搜索，返回 A 股候选 [{market, code, name}]。"""
    url = f"https://smartbox.gtimg.cn/s3/?q={urllib.parse.quote(name)}&t=all"
    resp = direct_get(url, timeout=10)
    text = resp.content.decode("utf-8", errors="ignore")
    m = re.search(r'v_hint="([^"]*)"', text)
    if not m:
        return []
    try:
        hint = json.loads(f'"{m.group(1)}"')  # 解析 \uXXXX 转义
    except json.JSONDecodeError:
        hint = m.group(1)

    results: list[dict[str, str]] = []
    for item in hint.split("^"):
        parts = item.split("~")
        if len(parts) >= 3 and parts[0] in ("sh", "sz", "bj"):
            results.append({"market": parts[0], "code": parts[1], "name": parts[2]})
    return results


def _parse_quote_line(key: str, vals: list[str], key_of: dict[str, str]) -> dict:
    code = key_of.get(key, key[2:])
    def f(i: int) -> float:
        try:
            return float(vals[i]) if vals[i] else 0.0
        except (ValueError, IndexError):
            return 0.0

    q = {
        "code": code,
        "name": vals[1] if len(vals) > 1 else "",
        "price": f(3),
        "last_close": f(4),
        "open": f(5),
        "change_amt": f(31),
        "change_pct": f(32),
        "high": f(33),
        "low": f(34),
        "amount_wan": f(37),
        "turnover_pct": f(38),
        "pe_ttm": f(39),
        "amplitude_pct": f(43),
        "float_mcap_yi": f(44),   # 流通市值(亿)
        "mcap_yi": f(45),         # 总市值(亿)
        "pb": f(46),
        "limit_up": f(47),
        "limit_down": f(48),
        "vol_ratio": f(49),
        "pe_static": f(52),
    }
    q["is_stale"] = (q["amount_wan"] == 0 and q["price"] == q["last_close"] and q["price"] > 0)
    return q


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """批量获取腾讯实时行情，key 为纯 6 位代码。"""
    prefixed: list[str] = []
    key_of: dict[str, str] = {}
    for c in codes:
        c = norm_ticker(c)
        p = f"{get_prefix(c)}{c}"
        prefixed.append(p)
        key_of[p] = c

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    resp = direct_get(url, timeout=12)
    data = resp.content.decode("gbk")

    result: dict[str, dict] = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        result[key_of.get(key, key[2:])] = _parse_quote_line(key, vals, key_of)
    return result


@tool
def get_realtime_quote(code: str) -> str:
    """获取 A 股实时行情快照：最新价、涨跌幅、PE(TTM)、PB、总市值、流通市值、换手率、成交额等。

    参数 code 为股票代码（如 '600519'、'300750'，也可以是 sh600519 / 600519.SH 形式）。
    返回 JSON 文本。
    """
    try:
        data = tencent_quote([code])
    except Exception as e:  # noqa: BLE001
        return f"行情获取失败: {e}"
    if not data:
        return "未获取到该代码的行情数据。"
    item = next(iter(data.values()))
    if item.get("is_stale"):
        return f"{item['name']}({item['code']}) 为停牌/未开盘/北交所老号段废码，报价非当日真实成交。"
    return json.dumps(item, ensure_ascii=False)