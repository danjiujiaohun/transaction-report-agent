"""美股取数共用底座：ticker 归一化、Yahoo 限流、JSON 安全化。

对应 skills/us-stock-core/SKILL.md。
"""
from __future__ import annotations

import os
import random
import re
import time
from typing import Optional

import requests

SEC_UA = os.environ.get(
    "SEC_USER_AGENT",
    "transaction-report-agent research bot contact@example.com",
)
YF_MIN_INTERVAL = 0.4
_yf_last = [0.0]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": SEC_UA,
    "Accept-Language": "en-US,en;q=0.9",
})

# 美股代码：1-5 位字母 + 可选类别后缀（BRK.B / BRK-B）
_US_TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:[.\-][A-Z])?)\b")


def norm_us_ticker(code: str) -> str:
    """归一化美股代码：AAPL / aapl / BRK.B / NYSE:AAPL → Yahoo 形式（BRK-B）。"""
    raw = str(code).strip().upper()
    if not raw:
        raise ValueError("empty ticker")
    raw = raw.replace("NYSE:", "").replace("NASDAQ:", "").replace("AMEX:", "")
    if raw.endswith(".US"):
        raw = raw[:-3]
    raw = raw.replace(".", "-")  # Yahoo 使用 BRK-B 形式
    if not re.fullmatch(r"[A-Z]{1,5}(?:-[A-Z])?", raw):
        raise ValueError(f"无法解析美股代码: {code!r}")
    return raw


def extract_us_ticker(text: str) -> Optional[str]:
    """从输入中提取美股代码（如 "苹果 AAPL" → "AAPL"）；无则返回 None。"""
    m = _US_TICKER_RE.search(text.upper())
    if not m:
        return None
    try:
        return norm_us_ticker(m.group(1))
    except ValueError:
        return None


def _resolve_proxy() -> str:
    """美股流量代理：优先 .env 的 US_STOCK_PROXY，其次环境变量，留空直连。"""
    from app.config import get_settings

    return (
        get_settings().us_stock_proxy
        or os.environ.get("US_STOCK_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or ""
    )


_proxy_applied = False


def apply_yf_proxy() -> str:
    """把代理配置应用到 yfinance 内部会话与共用 SESSION（幂等）。"""
    global _proxy_applied
    proxy = _resolve_proxy()
    if _proxy_applied:
        return proxy
    _proxy_applied = True
    if proxy:
        try:
            import yfinance as yf

            yf.config.network.proxy = proxy  # yfinance >= 1.0
        except AttributeError:
            try:
                import yfinance as yf

                yf.set_config(proxy=proxy)  # yfinance 0.2.x 兼容
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001 - 代理配置失败不阻断，回退直连
            pass
        SESSION.proxies.update({"http": proxy, "https": proxy})
    return proxy


def yf_throttle() -> None:
    """串行调用 Yahoo：最小间隔 + 随机抖动，避免限流。"""
    wait = YF_MIN_INTERVAL - (time.time() - _yf_last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.05, 0.25))
    _yf_last[0] = time.time()


def yf_get(url: str, params: Optional[dict] = None, timeout: int = 20):
    """带限流的 GET（Yahoo / 通用 JSON API）。"""
    yf_throttle()
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r


def sec_get(url: str, params: Optional[dict] = None, timeout: int = 30):
    """SEC EDGAR GET，必须带可识别 User-Agent。"""
    yf_throttle()
    r = SESSION.get(
        url, params=params,
        headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r


def json_safe(obj):
    """把 pandas/numpy 对象转成可 JSON 序列化的纯 Python 结构。"""
    import math

    import pandas as pd

    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(x) for x in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(obj, "item"):
        try:
            v = obj.item()
        except Exception:
            return str(obj)
        return json_safe(v)
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj
