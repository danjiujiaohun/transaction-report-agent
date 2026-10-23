"""异步分析任务管理：进程内任务存储 + 后台线程执行。

注意：任务存储在进程内存中，服务重启后任务即清空；若需持久化/多实例，可将此模块替换为 Redis/DB。
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from app.agent.graph import generate_report
from app.agent.report_cache import save_report

# 状态常量
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class AnalysisTask:
    """一次分析任务的状态。"""

    id: str
    company: str
    status: str = PENDING
    phase: str = "排队中"
    report: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """序列化为接口返回的字典。"""
        return {
            "task_id": self.id,
            "company": self.company,
            "status": self.status,
            "phase": self.phase,
            "report": self.report,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_tasks: dict[str, AnalysisTask] = {}
_lock = threading.Lock()


def _update(task_id: str, **kwargs) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        for key, value in kwargs.items():
            setattr(task, key, value)
        task.updated_at = time.time()


def submit(company: str, skill_prompt: str, dimensions: list[str] | None = None) -> AnalysisTask:
    """创建任务并启动后台线程执行，立即返回任务对象。"""
    task = AnalysisTask(id=uuid.uuid4().hex[:12], company=company)
    with _lock:
        _tasks[task.id] = task

    threading.Thread(
        target=_run, args=(task.id, company, skill_prompt, dimensions or []), daemon=True
    ).start()
    return task


def submit_cached(company: str, report: str) -> AnalysisTask:
    """用已缓存的报告创建一个「已完成」任务，立即返回（命中缓存时不走生成流程）。"""
    task = AnalysisTask(
        id=uuid.uuid4().hex[:12],
        company=company,
        status=DONE,
        phase="完成",
        report=report,
    )
    with _lock:
        _tasks[task.id] = task
    return task


def _run(task_id: str, company: str, skill_prompt: str, dimensions: list[str]) -> None:
    """后台线程：跑完整分析流程，实时更新任务状态与阶段。"""
    _update(task_id, status=RUNNING, phase="规划检索关键词")

    def on_progress(phase: str) -> None:
        _update(task_id, phase=phase)

    try:
        report = generate_report(
            company, skill_prompt, dimensions=dimensions, on_progress=on_progress
        )
        # 仅默认（未勾选维度）报告写入本地缓存，供后续同名输入直接命中
        if not dimensions:
            save_report(company, report)
        _update(task_id, status=DONE, phase="完成", report=report)
    except Exception as e:  # noqa: BLE001 - 任务线程需兜底，避免静默退出
        _update(task_id, status=FAILED, phase="失败", error=str(e))


def get(task_id: str) -> AnalysisTask | None:
    """按 task_id 查询任务状态；不存在返回 None。"""
    with _lock:
        return _tasks.get(task_id)