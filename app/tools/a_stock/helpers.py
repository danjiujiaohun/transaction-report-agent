"""A股取数共用 helper。

提取自 skills/a-stock-core：ticker 归一化、市场前缀路由、东财限流请求。
所有取数端点共用本模块的前置函数。
"""
from __future__ import annotations

import random
import re
import time
from typing import Optional

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 共享会话：复用 Keep-Alive 连接，且不信任系统代理（国内数据源直连更稳）
_session = requests.Session()
_session.trust_env = False
_session.headers.update({"User-Agent": UA})

# 沪市指数白名单：与深市 000xxx 个股同段，需白名单区分
SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}

_TICKER_RE = re.compile(
    r"^(?:(sh|sz|bj)(\d{6})|(\d{6})(?:\.(sh|sz|bj))?)$", re.IGNORECASE)


def get_prefix(code: str) -> str:
    """6 位代码 → 市场前缀（sh/sz/bj）；支持显式前缀/后缀透传。"""
    c = code.lower().strip()
    if c.endswith((".sh", ".sz", ".bj")):
        return c[-2:]
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    if c.startswith("92"):
        return "bj"
    if c.startswith(("5", "6", "9")):
        return "sh"
    if c.startswith(("4", "8")):
        return "bj"
    if c in SH_INDEX:
        return "sh"
    return "sz"


def _natural_market(digits: str) -> str:
    if digits.startswith(("4", "8", "92")):
        return "bj"
    if digits[0] in ("5", "6", "9"):
        return "sh"
    return "sz"


def norm_ticker(code: str, stock_only: bool = False) -> str:
    """任意受支持写法 → 纯 6 位数字代码；无法解析时抛 ValueError。"""
    raw = str(code).strip()
    m = _TICKER_RE.match(raw)
    if not m:
        raise ValueError(
            f"无法把 {code!r} 解析为 6 位股票代码；"
            f"支持格式：600519 / SH600519 / sh600519 / 600519.SH"
        )
    digits = m.group(2) or m.group(3)
    market = (m.group(1) or m.group(4) or "").lower()
    if market:
        if digits.startswith("000"):
            if market == "bj":
                raise ValueError(f"{code!r} 市场标识与号段矛盾：000xxx 不属北交所。")
            if stock_only and market == "sh":
                raise ValueError(
                    f"{code!r} 指向沪市指数而非个股（沪市无 000xxx 个股）。"
                )
        else:
            nat = _natural_market(digits)
            if market != nat:
                raise ValueError(
                    f"{code!r} 的市场标识与号段矛盾：{digits} 属 {nat} 市，而不是 {market} 市。"
                )
    return digits


# ---- 东财限流（东财系端点必须走 em_get）----
_EM_SESSION = requests.Session()
_EM_SESSION.trust_env = False
_EM_SESSION.headers.update({"User-Agent": UA})
try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    _em_adapter = HTTPAdapter(max_retries=Retry(
        total=3, connect=3, backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]))
    _EM_SESSION.mount("https://", _em_adapter)
    _EM_SESSION.mount("http://", _em_adapter)
except Exception:  # noqa: BLE001 - urllib3 老版本降级为无重试
    pass

EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def em_get(url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
           timeout: int = 15, **kwargs):
    """东财统一请求入口：串行限流 + 复用会话 + 默认 UA，避免高频被封 IP。"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return _EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


def direct_get(url: str, **kwargs):
    """非东财数据源（腾讯/新浪/同花顺等）的普通直连请求。"""
    return _session.get(url, timeout=kwargs.pop("timeout", 15), **kwargs)