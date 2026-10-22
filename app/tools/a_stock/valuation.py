"""估值历史工具：baostock 日频 PE/PB/PS/PCF + 换手率 + 停牌 + ST。"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, timedelta

import baostock as bs
import pandas as pd
from langchain_core.tools import tool

from app.tools.a_stock.helpers import norm_ticker


@contextmanager
def _bs_session():
    """baostock 登录会话，异常路径也保证 logout。"""
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_code} {lg.error_msg}")
    try:
        yield
    finally:
        bs.logout()


def _rs_to_df(rs) -> pd.DataFrame:
    """baostock ResultData -> DataFrame；错误码转异常，不静默返回空表。"""
    if rs.error_code != "0":
        raise RuntimeError(f"baostock 查询失败: {rs.error_code} {rs.error_msg}")
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)


def _bs_code(code: str) -> str:
    """6 位代码 -> baostock 格式；北交所号段（4/8/92 等）在登录前拦掉。"""
    code = norm_ticker(code)
    if code[:2] in ("60", "68", "90"):
        return f"sh.{code}"
    if code[:2] in ("00", "30", "20"):
        return f"sz.{code}"
    raise ValueError(
        f"baostock 不支持该代码: {code}（北交所号段会被服务端拒绝）"
    )


def baostock_valuation_history(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """估值历史序列：PE/PB/PS/PCF + 换手率 + 停牌 + ST，日频。"""
    bs_code = _bs_code(code)
    fields = "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST"
    with _bs_session():
        rs = bs.query_history_k_data_plus(
            bs_code, fields, start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="3",
        )
        df = _rs_to_df(rs)
    for c in ("close", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "turn"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _num(x) -> float | None:
    """安全转 float，失败返回 None。"""
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return round(float(x), 3)
    except (TypeError, ValueError):
        return None


def valuation_summary(code: str, years: int = 5) -> dict:
    """估值历史摘要：最新快照 + 区间/当前分位 + 价格区间 + ST/停牌统计。"""
    end = date.today()
    start = end - timedelta(days=365 * years)
    df = baostock_valuation_history(code, start.isoformat(), end.isoformat())
    if df.empty:
        return {}

    latest = df.iloc[-1]
    result: dict = {
        "code": code,
        "最新日期": latest.get("date"),
        "最新收盘": _num(latest.get("close")),
        "PE_TTM": _num(latest.get("peTTM")),
        "PB_MRQ": _num(latest.get("pbMRQ")),
        "PS_TTM": _num(latest.get("psTTM")),
        "PCF_TTM": _num(latest.get("pcfNcfTTM")),
        "换手率_pct": _num(latest.get("turn")),
    }

    for col, label in (("peTTM", "PE_TTM"), ("pbMRQ", "PB_MRQ"), ("psTTM", "PS_TTM")):
        s = df[col].dropna()
        s = s[s > 0]
        if s.empty:
            continue
        result[f"{label}_{years}年最低"] = round(float(s.min()), 2)
        result[f"{label}_{years}年最高"] = round(float(s.max()), 2)
        cur = _num(latest.get(col))
        if cur is not None and cur > 0:
            result[f"{label}_当前分位"] = round(float((s <= cur).mean() * 100), 1)

    close = df["close"].dropna()
    if not close.empty:
        result[f"{years}年最低价"] = round(float(close.min()), 2)
        result[f"{years}年最高价"] = round(float(close.max()), 2)

    if "tradestatus" in df.columns:
        result["停牌天数"] = int((df["tradestatus"].astype(str) == "0").sum())
    if "isST" in df.columns:
        result["ST天数"] = int((df["isST"].astype(str) == "1").sum())
    return result


@tool
def get_valuation_history(code: str) -> str:
    """获取 A 股历史估值摘要（baostock，近 5 年日频）。

    Args:
        code: 股票代码，如 '600519'。

    返回 JSON 文本：最新 PE(TTM)/PB/PS/PCF/换手率，以及近 5 年估值区间、当前分位、
    价格区间、停牌与 ST 天数统计。
    """
    try:
        summary = valuation_summary(code)
    except Exception as e:  # noqa: BLE001
        return f"估值历史获取失败: {e}"
    if not summary:
        return "未获取到估值历史数据。"
    return json.dumps(summary, ensure_ascii=False)