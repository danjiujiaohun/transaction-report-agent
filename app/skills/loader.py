"""Skills 加载器。

支持两类 skill：
1. Cursor 目录格式：skills/<skill-name>/SKILL.md（frontmatter 含 name / description）
2. 单文件格式：skills/<name>.md

本模块负责扫描、解析这些 skill，并在生成报告时把它们的概览注入系统提示；
取数类 skill 的完整代码在后续封装为工具时按需加载。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

_settings = get_settings()


@dataclass
class Skill:
    """单个 skill：名称、职责描述、正文内容。"""

    name: str
    content: str
    description: str = ""


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# YAML 折叠/字面量块标记（description: >- 等）
_BLOCK_MARKERS = (">-", ">", "|", "|-")


def _strip_block_marker(value: str) -> str:
    """去掉 YAML block scalar 标记（如 `>-`）。"""
    value = value.strip()
    for marker in _BLOCK_MARKERS:
        if value.startswith(marker):
            value = value[len(marker):].strip()
            break
    return value


def _parse_frontmatter(text: str) -> tuple[str, str, str]:
    """解析 frontmatter，返回 (name, description, 正文)。"""
    name, description, body = "", "", text
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return name, description, body.strip()

    header = m.group(1)
    fields: dict[str, str] = {}
    current: str | None = None
    for line in header.splitlines():
        if not line:
            continue
        if not line[0].isspace():  # 顶层 key: value
            if ":" in line:
                key, val = line.split(":", 1)
                current = key.strip()
                fields[current] = val.strip()
        elif current:  # 续行（折叠块），拼接到上一个 key
            fields[current] = f"{fields.get(current, '')} {line.strip()}".strip()

    name = fields.get("name", "").strip()
    description = _strip_block_marker(fields.get("description", ""))
    body = text[m.end():].strip()
    return name, description, body


def load_skills(skills_dir: Path | None = None) -> list[Skill]:
    """扫描 skills 目录，加载所有 skill。"""
    path = skills_dir or _settings.skills_path
    if not path.exists():
        return []

    skills: list[Skill] = []
    # 目录格式：skills/*/SKILL.md
    for skill_file in sorted(path.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        name, description, body = _parse_frontmatter(text)
        if not name:
            name = skill_file.parent.name
        skills.append(Skill(name=name, content=body, description=description))
    # 单文件格式：skills/*.md
    for file in sorted(path.glob("*.md")):
        text = file.read_text(encoding="utf-8")
        name, description, body = _parse_frontmatter(text)
        if not name:
            name = file.stem
        skills.append(Skill(name=name, content=body, description=description))
    return skills


def build_skills_prompt(skills: list[Skill] | None = None) -> str:
    """把 skills 的概览（名称 + 职责）拼接为可注入系统提示的文本。

    仅注入 name + description，避免把取数类 skill 的大段代码塞进上下文。
    完整正文在需要时通过 skill 名按需加载。
    """
    skills = skills if skills is not None else load_skills()
    if not skills:
        return ""

    parts = [
        "以下是已加载的报告/研究 skills 概览，撰写报告时请遵循与目标公司类型匹配的框架：\n"
    ]
    for i, skill in enumerate(skills, 1):
        desc = skill.description.strip() or skill.content[:200]
        parts.append(f"{i}. {skill.name}：{desc}")
    parts.append(
        "语言要求（强制）：遵循上述 skill 撰写报告时，输出必须全部为英文，"
        "且**禁止出现任何中文字符**（标题、正文、表格、图表标签、括号注释、来源标题均不得含中文）；"
        "公司名用官方英文名或拼音，股票代码保持原样；"
        "skill 规则本身为中文不影响，但落到报告里的每个字都必须是英文。"
    )
    return "\n".join(parts)