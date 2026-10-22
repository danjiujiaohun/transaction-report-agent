"""LLM 工厂：根据配置返回对应的 chat model。"""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings

_settings = get_settings()


def get_llm() -> BaseChatModel:
    """根据 LLM_PROVIDER 返回聊天模型实例。"""
    if _settings.llm_provider.lower() == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=_settings.openai_base_url,
            api_key=_settings.openai_api_key,
            model=_settings.openai_model,
            temperature=0.3,
        )

    # 默认 Ollama
    from langchain_ollama import ChatOllama

    return ChatOllama(
        base_url=_settings.ollama_base_url,
        model=_settings.ollama_model,
        temperature=0.3,
    )


def get_llm_info() -> tuple[str, str]:
    """返回 (provider, model) 用于健康检查展示。"""
    if _settings.llm_provider.lower() == "openai":
        return "openai", _settings.openai_model
    return "ollama", _settings.ollama_model