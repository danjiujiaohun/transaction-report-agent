"""FastAPI 入口：为前端提供股票公司分析报告的 HTTP 接口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import generate_report
from app.config import get_settings
from app.llm import get_llm_info
from app.models.schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse
from app.skills.loader import build_skills_prompt, load_skills
from app.tools.web_search import search as raw_search

settings = get_settings()

# 进程内缓存 skills（启动时加载一次，运行期不变）
_skills_prompt = ""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用启动/关闭钩子：预加载 skills。"""
    global _skills_prompt
    skills = load_skills()
    _skills_prompt = build_skills_prompt(skills)
    yield


app = FastAPI(
    title="Transaction Report Agent",
    description="股票市场公司分析报告 Agent",
    version="0.1.0",
    lifespan=lifespan,
)

# 允许前端跨域访问（预留前端获取数据的能力）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """健康检查，返回 LLM、skills、搜索等运行状态。"""
    provider, model = get_llm_info()
    search_ok = False
    try:
        raw_search("测试")
        search_ok = True
    except Exception:  # noqa: BLE001
        search_ok = False
    return HealthResponse(
        status="ok",
        llm_provider=provider,
        llm_model=model,
        skills_loaded=len(load_skills()),
        search_available=search_ok,
    )


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """分析指定公司，返回 Markdown 报告。"""
    try:
        report = generate_report(req.company, _skills_prompt)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"分析失败: {e}") from e
    return AnalyzeResponse(company=req.company, report=report)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)