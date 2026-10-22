"""AutoGLM WebSearch 联网搜索工具。

封装 AutoGLM Web Search API：
- token 从本地服务自动获取
- 每次请求动态生成签名 Headers
- 对外暴露 LangChain tool，供 Agent 调用
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx
from langchain_core.tools import tool

from app.config import get_settings

_settings = get_settings()


def _get_token() -> str:
    """从本地服务获取 Bearer token。"""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(_settings.websearch_token_url)
        resp.raise_for_status()
        token = resp.text.strip()
    if not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    return token


def _build_headers(token: str) -> dict[str, str]:
    """动态生成签名请求头。"""
    timestamp = str(int(time.time()))
    sign_data = f"{_settings.websearch_app_id}&{timestamp}&{_settings.websearch_app_key}"
    sign = hashlib.md5(sign_data.encode("utf-8")).hexdigest()
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "X-Auth-Appid": _settings.websearch_app_id,
        "X-Auth-TimeStamp": timestamp,
        "X-Auth-Sign": sign,
    }


def search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    """执行一次联网搜索，返回 [{name, url, snippet}] 列表。

    Args:
        query: 搜索关键词。
        max_results: 最多返回的结果条数。
    """
    token = _get_token()
    payload = {"queries": [{"query": query}]}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            _settings.websearch_api_url,
            json=payload,
            headers=_build_headers(token),
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    results: list[dict[str, str]] = []
    if data.get("code") != 0:
        raise RuntimeError(f"搜索失败: {data.get('msg')}")

    for group in data.get("data", {}).get("results", []):
        for page in group.get("webPages", {}).get("value", []):
            results.append(
                {
                    "name": page.get("name", ""),
                    "url": page.get("url", ""),
                    "snippet": page.get("snippet", ""),
                }
            )
            if len(results) >= max_results:
                return results
    return results


def _format_results(results: list[dict[str, str]]) -> str:
    """将搜索结果格式化为 LLM 可读文本。"""
    if not results:
        return "未搜索到相关内容。"
    lines = []
    for i, item in enumerate(results, 1):
        lines.append(f"[{i}] {item['name']}\n    URL: {item['url']}\n    摘要: {item['snippet']}")
    return "\n\n".join(lines)


@tool
def web_search(query: str) -> str:
    """联网搜索指定关键词，返回相关网页的标题、链接与摘要。

    当需要获取某公司的最新新闻、财务数据、估值、行业动态等实时信息时调用此工具。
    """
    try:
        results = search(query)
        return _format_results(results)
    except Exception as e:  # noqa: BLE001 - 工具需保证不抛出致命异常
        return f"搜索出错: {e}"