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
    dimensions: list[str] = Field(
        default_factory=list,
        description="用户勾选的研究维度关键词（可选），用于定向检索与报告落点",
    )


class RecommendRequest(BaseModel):
    """维度推荐请求参数。"""

    company: str = Field(
        ...,
        description="公司名称或股票代码",
        min_length=1,
    )


class TaskResponse(BaseModel):
    """分析任务状态（提交与轮询复用）。"""
    task_id: str = Field(..., description="任务唯一 ID")
    company: str = Field(..., description="查询的公司名称/代码")
    status: str = Field(..., description="任务状态：pending/running/done/failed")
    phase: str = Field(..., description="当前阶段文案，如『生成分析报告』")
    report: Optional[str] = Field(default=None, description="Markdown 报告全文，仅 status=done 时有值")
    error: Optional[str] = Field(default=None, description="出错信息，仅 status=failed 时有值")


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "ok"
    llm_provider: str
    llm_model: str
    skills_loaded: int
    search_available: bool