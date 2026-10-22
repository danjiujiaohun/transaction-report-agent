"""请求 / 响应数据模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """分析请求参数。"""

    company: str = Field(
        ...,
        description="公司名称或股票代码，如 '贵州茅台' 或 '600519' 或 'AAPL'",
        min_length=1,
    )
    # 预留：后续可扩展语言、市场、分析维度等
    # language: str = "zh"
    # dimensions: list[str] = []


class AnalyzeResponse(BaseModel):
    """分析响应结果。"""

    company: str = Field(..., description="查询的公司名称/代码")
    report: str = Field(..., description="Markdown 格式的分析报告全文")
    error: Optional[str] = Field(default=None, description="出错时的错误信息")


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "ok"
    llm_provider: str
    llm_model: str
    skills_loaded: int
    search_available: bool