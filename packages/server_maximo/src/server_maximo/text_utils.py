from __future__ import annotations

import re
from typing import Any


LINE_NAME_MAP = {
    "一号线": "1号线",
    "二号线": "2号线",
    "三号线": "3号线",
    "四号线": "4号线",
    "五号线": "5号线",
    "六号线": "6号线",
    "七号线": "7号线",
    "八号线": "8号线",
    "九号线": "9号线",
    "十号线": "10号线",
    "十一号线": "11号线",
    "十二号线": "12号线",
    "十三号线": "13号线",
    "十四号线": "14号线",
    "十五号线": "15号线",
    "十六号线": "16号线",
    "十七号线": "17号线",
    "十八号线": "18号线",
    "十九号线": "19号线",
    "二十号线": "20号线",
}


def normalize_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    normalized = value.strip().replace("\u3000", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    for raw, standard in LINE_NAME_MAP.items():
        normalized = normalized.replace(raw, standard)
    normalized = re.sub(r"[A-Za-z]+", lambda match: match.group(0).upper(), normalized)
    return normalized


SPECIALTY_SYNONYMS = {
    "ISCS": ["ISCS", "ISCS设备", "综合监控", "综合监控系统", "IBP", "IBP盘"],
    "屏蔽门": ["屏蔽门", "站台门", "PSD", "屏蔽门设备", "屏蔽门控制器"],
    "AFC": ["AFC", "AFC设备", "自动售检票", "售检票", "闸机", "检票机", "售票机", "TVM", "AGM", "BOM"],
    "BAS": ["BAS", "BAS设备", "环境监控", "环境与设备监控"],
    "FAS": ["FAS", "FAS设备", "火灾报警", "消防系统", "火灾自动报警"],
    "门禁": ["门禁", "门禁设备", "门禁系统", "通道门"],
    "电扶梯": ["电扶梯", "扶梯", "自动扶梯", "扶手电梯", "电扶梯设备"],
    "给排水": ["给排水", "给排水设备", "给水排水"],
    "通风空调": ["通风空调", "通风空调设备", "空调通风", "暖通空调"],
    "低压供电": ["低压供电", "低压供电设备", "低压配电"],
    "高压供电": ["高压供电", "高压供电设备", "高压配电"],
    "通信": ["通信", "通信设备", "通讯设备", "通信系统"],
    "信号": ["信号", "信号设备", "信号系统"],
    "房建": ["房建", "房建结构", "建筑结构", "土建"],
    "安检": ["安检", "安检设备", "安检仪设备", "安全检查"],
}

SPECIALTY_ALIASES: list[tuple[str, str]] = []
for canonical_name, aliases in SPECIALTY_SYNONYMS.items():
    for alias in aliases:
        SPECIALTY_ALIASES.append((normalize_text(alias).lower(), canonical_name))
SPECIALTY_ALIASES.sort(key=lambda item: len(item[0]), reverse=True)


def infer_specialty_from_text(text: str) -> str | None:
    normalized = normalize_text(text or "")
    lower_text = normalized.lower()
    for alias, canonical_name in SPECIALTY_ALIASES:
        if alias and alias in lower_text:
            return canonical_name
    return None


def normalize_specialty(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    specialty = infer_specialty_from_text(value)
    return specialty or normalize_text(value)


def expand_specialty_synonyms(term: str) -> list[str]:
    if not term:
        return []

    normalized = normalize_text(term)
    lower_text = normalized.lower()
    for canonical_name, aliases in SPECIALTY_SYNONYMS.items():
        normalized_aliases = [normalize_text(alias) for alias in aliases]
        if canonical_name.lower() in lower_text:
            return list(dict.fromkeys([canonical_name, *normalized_aliases]))
        if any(alias.lower() in lower_text for alias in normalized_aliases):
            return list(dict.fromkeys([canonical_name, *normalized_aliases]))
    return [normalized]


def extract_fault_cause(long_description: Any) -> str | None:
    if not isinstance(long_description, str) or not long_description.strip():
        return None

    patterns = [
        r"故障原因[:：]\s*(.+?)(?:\n|$)",
        r"原因[:：]\s*(.+?)(?:\n|$)",
        r"分析[:：]\s*(.+?)(?:\n|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, long_description, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()[:120]
    return None
