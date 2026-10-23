"""研究维度关键词 → 报告生成 skill 的映射。

前端在搜索页以 checkbox 形式展示这些维度关键词，用户可多选；后端据此：
1. 解析出需要执行的研究框架 skill（value / growth / platform）；
2. 把选中维度注入报告提示词与搜索关键词规划，实现「按维度搜索并生成对应报告」。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.skills.loader import build_skills_prompt, load_skills


@dataclass(frozen=True)
class DimensionGroup:
    """一层维度分组。skill 为空表示通用维度（不绑定具体框架）。"""

    key: str
    label: str
    skill: str | None
    keywords: tuple[str, ...]


# 四层维度（与前端勾选项一一对应，label/keyword 保持英文以对齐报告输出）
DIMENSION_GROUPS: tuple[DimensionGroup, ...] = (
    DimensionGroup(
        "universal",
        "Universal",
        None,
        (
            "Business model", "Competition", "Narrative", "Catalysts",
            "Debate", "Tracking", "Value band",
        ),
    ),
    DimensionGroup(
        "value",
        "Value leader",
        "value-leader-research",
        (
            "FCF", "Moat", "Margins", "Share", "PE/PB", "Risks",
        ),
    ),
    DimensionGroup(
        "growth",
        "Growth / tech",
        "growth-tech-research",
        (
            "Growth path", "TAM", "Product", "Dilution", "Runway",
            "Valuation route", "PEG/PS",
        ),
    ),
    DimensionGroup(
        "platform",
        "Platform / upside",
        "platform-leader-research",
        (
            "Segments", "Cash cow", "Disruption", "SOTP", "Option", "Capex",
        ),
    ),
)

# 关键词（小写）→ (分组 key, 原始关键词) 快速索引
_KEYWORD_INDEX: dict[str, tuple[str, str]] = {
    keyword.lower(): (group.key, keyword)
    for group in DIMENSION_GROUPS
    for keyword in group.keywords
}


def all_keywords() -> list[str]:
    """返回全部维度关键词（供前端/校验使用）。"""
    return [keyword for group in DIMENSION_GROUPS for keyword in group.keywords]


def resolve_frameworks(dimensions: list[str]) -> list[str]:
    """根据选中的维度关键词，返回需要执行的研究框架 skill 名列表（去重保序）。"""
    selected = {dim.strip().lower() for dim in dimensions if dim and dim.strip()}
    frameworks: list[str] = []
    for group in DIMENSION_GROUPS:
        if group.skill and any(kw.lower() in selected for kw in group.keywords):
            if group.skill not in frameworks:
                frameworks.append(group.skill)
    return frameworks


def build_dimensions_payload() -> list[dict]:
    """构建提供给前端渲染 checkbox 的分组数据。"""
    return [
        {
            "key": group.key,
            "label": group.label,
            "skill": group.skill,
            "keywords": list(group.keywords),
        }
        for group in DIMENSION_GROUPS
    ]


def recommend_dimensions(company: str) -> list[str]:
    """让 LLM 根据公司，从全部维度关键词中挑选最相关的几个（3~8 个）。

    返回值为合法关键词列表（去重保序，非法/自创项被过滤）。
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.llm import get_llm

    listing = "\n".join(
        f"[{group.label}] " + ", ".join(group.keywords) for group in DIMENSION_GROUPS
    )
    system = (
        "你是一名专业的股票研究分析师。根据给定的公司，判断它更适合用哪套研究框架，"
        "并从下方维度关键词中挑选 3 到 8 个最相关的关键词，用于指导后续报告生成。\n"
        "规则：只能从给定关键词里选，不得自创；只输出一个 JSON 数组，元素为关键词字符串，"
        "不要输出任何其他文字。\n\n"
        f"可选维度关键词：\n{listing}"
    )

    llm = get_llm()
    resp = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=f"公司：{company}")]
    )
    text = (resp.content or "").strip()

    parsed: list[str] = []
    try:
        import json as _json

        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        data = _json.loads(text)
        if isinstance(data, list):
            parsed = [str(item).strip() for item in data if str(item).strip()]
    except (ValueError, TypeError):
        return []

    valid = {keyword.lower(): keyword for keyword in all_keywords()}
    result: list[str] = []
    for item in parsed:
        canonical = valid.get(item.lower())
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def build_tailored_skills_prompt(dimensions: list[str]) -> str:
    """根据选中维度构建注入报告的系统提示。

    - 选中框架维度 → 注入对应框架 skill 的完整规则（真正「执行」该 skill）；
    - 未命中任何框架 → 退回全部框架概览，由 LLM 自行匹配；
    - 所有选中维度统一追加「重点覆盖维度」清单，指导搜索与报告落点。
    """
    dims = [dim.strip() for dim in dimensions if dim and dim.strip()]
    frameworks = resolve_frameworks(dims)
    skills = load_skills()
    by_name = {skill.name: skill for skill in skills}

    parts: list[str] = []

    if frameworks:
        parts.append(
            "你被要求按以下研究框架（skill）执行本次报告，"
            "必须严格遵循其全部规则、章节模板与下结论纪律："
        )
        for name in frameworks:
            skill = by_name.get(name)
            if skill:
                parts.append(f"\n\n===== SKILL: {name} =====\n{skill.content}")
    else:
        # 仅勾选通用维度（或未命中框架），保留全部框架概览供 LLM 自选
        parts.append(build_skills_prompt(skills))

    if dims:
        parts.append(
            "\n\n===== 本次分析重点维度（务必覆盖） =====\n"
            "请确保报告与联网搜索都充分覆盖以下维度，并在结论与跟踪清单中体现：\n- "
            + "\n- ".join(dims)
        )

    parts.append(
        "\n\n语言要求（强制）：遵循上述 skill 撰写报告时，输出必须全部为英文，"
        "且禁止出现任何中文字符（标题、正文、表格、图表标签、括号注释、来源标题均不得含中文）；"
        "公司名用官方英文名或拼音，股票代码保持原样；"
        "skill 规则本身为中文不影响，但落到报告里的每个字都必须是英文。"
    )
    return "\n".join(parts)
