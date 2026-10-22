"""全局配置模块。

从环境变量 / .env 文件加载配置，统一管理 LLM、搜索、skills 等服务参数。
"""
from __future__ import annotations

import os

# 关键修复：本机若开启系统代理（如 Clash 127.0.0.1:7890），httpx / ollama 客户端会
# 把对 localhost 的请求也交给代理，导致 Ollama(11434)、AutoGLM(53699) 等本地服务返回
# 502。此处将本地地址加入 NO_PROXY，确保直连。需在 httpx 创建客户端之前设置。
_no_proxy = os.environ.get("NO_PROXY", "")
for _host in ("127.0.0.1", "localhost"):
    if _host not in _no_proxy.split(","):
        _no_proxy = f"{_no_proxy},{_host}" if _no_proxy else _host
os.environ["NO_PROXY"] = _no_proxy
os.environ["no_proxy"] = _no_proxy

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM ----
    llm_provider: str = "ollama"  # ollama | openai
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"

    openai_base_url: str = "https://api.deepseek.com"
    openai_api_key: str = ""
    openai_model: str = "deepseek-chat"

    # ---- 联网搜索 ----
    # 首选：Tavily（标准 HTTP API，只需 key，跨环境可移植）
    tavily_api_key: str = ""
    tavily_api_url: str = "https://api.tavily.com/search"

    # 备选：AutoGLM WebSearch（依赖本地 53699 token 服务）
    websearch_token_url: str = "http://127.0.0.1:53699/get_token"
    websearch_api_url: str = (
        "https://autoglm-api.zhipuai.cn/agentdr/v1/assistant/skills/web-search"
    )
    websearch_app_id: str = "100003"
    websearch_app_key: str = "38d2391985e2369a5fb8227d8e6cd5e5"

    # ---- 美股取数 ----
    # Yahoo/SEC 对部分网络环境直连 403/限流，配置 HTTP 代理后仅美股流量走代理；
    # A 股数据源始终直连。留空表示直连。示例：http://127.0.0.1:7890
    us_stock_proxy: str = ""

    # ---- Skills 目录（markdown 规则文件）----
    skills_dir: str = "skills"

    # ---- 服务 ----
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def skills_path(self) -> Path:
        """skills 目录的绝对路径（相对项目根目录解析）。"""
        path = Path(self.skills_dir)
        if not path.is_absolute():
            # 项目根目录即本文件上两级
            path = Path(__file__).resolve().parent.parent / path
        return path


@lru_cache
def get_settings() -> Settings:
    """获取缓存的全局配置实例。"""
    return Settings()