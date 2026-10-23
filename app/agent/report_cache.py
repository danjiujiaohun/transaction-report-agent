"""本地报告缓存。

生成完成的报告会按规范化后的公司/代码键写入本地文件；后续相同输入命中缓存时，
直接返回已生成的报告，跳过重复生成。
"""
from __future__ import annotations

from pathlib import Path

# 项目根目录下的 cache 目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = _PROJECT_ROOT / "cache"


def normalize_key(company: str) -> str:
    """把输入归一化为缓存键：去首尾空白、合并内部空白、转大写。"""
    return " ".join(company.strip().split()).upper()


def _path(key: str) -> Path:
    return CACHE_DIR / f"{key}.md"


def get_cached_report(company: str) -> str | None:
    """命中缓存返回报告全文，否则返回 None。"""
    path = _path(normalize_key(company))
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def save_report(company: str, report: str) -> Path:
    """把报告写入本地缓存，返回写入路径。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(normalize_key(company))
    path.write_text(report, encoding="utf-8")
    return path
