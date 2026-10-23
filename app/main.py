"""FastAPI 入口：为前端提供股票公司分析报告的 HTTP 接口。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent.tasks import get as get_task
from app.agent.tasks import submit as submit_task
from app.config import get_settings
from app.llm import get_llm_info
from app.models.schemas import AnalyzeRequest, HealthResponse, RecommendRequest, TaskResponse
from app.skills.dimensions import (
    build_dimensions_payload,
    build_tailored_skills_prompt,
    recommend_dimensions,
)
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


@app.get("/api/dimensions")
def dimensions() -> dict:
    """返回前端可勾选的研究维度分组（关键词 → 对应研究框架 skill）。"""
    return {"groups": build_dimensions_payload()}


@app.post("/api/recommend-dimensions")
def recommend_dimensions_endpoint(req: RecommendRequest) -> dict:
    """让模型根据公司匹配最相关的研究维度关键词（供前端「点亮」）。"""
    try:
        keywords = recommend_dimensions(req.company)
    except Exception:  # noqa: BLE001 - 推荐失败返回空，不阻断主流程
        keywords = []
    return {"keywords": keywords}


@app.post("/api/analyze", response_model=TaskResponse, status_code=202)
def analyze(req: AnalyzeRequest) -> TaskResponse:
    """提交分析任务，立即返回 task_id，后台异步生成报告。"""
    # 勾选了维度 → 定向注入对应框架 skill；否则沿用全部框架概览
    if req.dimensions:
        prompt = build_tailored_skills_prompt(req.dimensions)
    else:
        prompt = _skills_prompt
    task = submit_task(req.company, prompt, req.dimensions)
    return TaskResponse(**task.to_dict())


@app.get("/api/analyze/{task_id}", response_model=TaskResponse)
def analyze_status(task_id: str) -> TaskResponse:
    """轮询分析任务状态；status=done 时 report 有值。"""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return TaskResponse(**task.to_dict())


# ---- 前端静态资源（访问 / 即打开前端页面） ----
_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)