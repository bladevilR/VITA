from __future__ import annotations

import re
from typing import Any

from .text_utils import normalize_text


PHENOMENON_GROUPS: dict[str, dict[str, Any]] = {
    "黑屏": {
        "neighbors": ["无显示", "显示异常", "白屏", "花屏"],
        "mechanisms": ["显示链路", "工控机", "电源"],
    },
    "白屏": {
        "neighbors": ["黑屏", "无显示", "显示异常", "花屏"],
        "mechanisms": ["显示链路", "工控机", "显卡"],
    },
    "花屏": {
        "neighbors": ["黑屏", "白屏", "显示异常"],
        "mechanisms": ["显卡", "视频线", "显示屏"],
    },
    "无显示": {
        "neighbors": ["黑屏", "白屏", "显示异常"],
        "mechanisms": ["显示链路", "显示器", "工控机"],
    },
    "显示异常": {
        "neighbors": ["黑屏", "白屏", "花屏", "无显示"],
        "mechanisms": ["显示链路", "工控机", "软件"],
    },
    "频繁死机": {
        "neighbors": ["死机", "卡死", "无响应", "重启无效"],
        "mechanisms": ["工控机", "操作系统", "散热"],
    },
    "死机": {
        "neighbors": ["频繁死机", "卡死", "无响应", "重启无效"],
        "mechanisms": ["工控机", "软件", "内存"],
    },
    "卡死": {
        "neighbors": ["死机", "无响应", "卡顿"],
        "mechanisms": ["软件", "内存", "资源占满"],
    },
    "无响应": {
        "neighbors": ["卡死", "死机", "无反应"],
        "mechanisms": ["软件", "通信", "设备驱动"],
    },
    "无反应": {
        "neighbors": ["无响应", "卡死", "无法启动"],
        "mechanisms": ["电源", "工控机", "通信"],
    },
    "重启无效": {
        "neighbors": ["死机", "频繁死机", "无法启动", "白屏"],
        "mechanisms": ["系统损坏", "工控机", "电源"],
    },
    "无法启动": {
        "neighbors": ["重启无效", "无反应", "黑屏"],
        "mechanisms": ["电源", "主板", "系统损坏"],
    },
    "离线": {
        "neighbors": ["通信中断", "中断", "网络异常"],
        "mechanisms": ["交换机", "网络链路", "设备通信"],
    },
    "中断": {
        "neighbors": ["离线", "通信中断", "网络异常"],
        "mechanisms": ["网络链路", "接口板", "通信"],
    },
    "通信中断": {
        "neighbors": ["离线", "中断", "网络异常"],
        "mechanisms": ["交换机", "光电转换", "网络链路"],
    },
    "网络异常": {
        "neighbors": ["离线", "通信中断", "中断"],
        "mechanisms": ["交换机", "网线", "网络链路"],
    },
    "故障停止": {
        "neighbors": ["停止", "失电停止", "紧急停止"],
        "mechanisms": ["安全回路", "异物卡阻", "电气保护"],
    },
    "停止": {
        "neighbors": ["故障停止", "失电停止", "紧急停止"],
        "mechanisms": ["安全回路", "异物卡阻", "控制回路"],
    },
    "失电停止": {
        "neighbors": ["停止", "故障停止", "无法启动"],
        "mechanisms": ["供电", "控制回路", "空开"],
    },
    "报警": {
        "neighbors": ["告警", "报错"],
        "mechanisms": ["传感器", "保护逻辑", "通信"],
    },
    "告警": {
        "neighbors": ["报警", "报错"],
        "mechanisms": ["传感器", "保护逻辑", "通信"],
    },
    "报错": {
        "neighbors": ["告警", "报警"],
        "mechanisms": ["软件", "接口", "参数配置"],
    },
}

PHENOMENON_ORDER = sorted(PHENOMENON_GROUPS.keys(), key=len, reverse=True)


def split_fault_terms(value: str | None) -> list[str]:
    if not value:
        return []

    text = normalize_text(value)
    matched: list[str] = []
    remaining = text
    for term in PHENOMENON_ORDER:
        if term in remaining:
            matched.append(term)
            remaining = remaining.replace(term, " ")

    for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fa5]{2,16}", remaining):
        if token not in matched:
            matched.append(token)
    return matched


def get_neighbor_terms(value: str | None) -> list[str]:
    neighbors: list[str] = []
    for term in split_fault_terms(value):
        for neighbor in PHENOMENON_GROUPS.get(term, {}).get("neighbors", []):
            if neighbor not in neighbors:
                neighbors.append(neighbor)
    return neighbors


def get_mechanism_terms(value: str | None) -> list[str]:
    mechanisms: list[str] = []
    for term in split_fault_terms(value):
        for mechanism in PHENOMENON_GROUPS.get(term, {}).get("mechanisms", []):
            if mechanism not in mechanisms:
                mechanisms.append(mechanism)
    return mechanisms


def has_exact_fault_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    return normalize_text(term) in normalize_text(text)
