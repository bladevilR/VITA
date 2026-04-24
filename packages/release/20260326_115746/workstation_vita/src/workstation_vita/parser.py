from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .ai_clients import AIClient
from .text_utils import expand_specialty_synonyms, infer_specialty_from_text, normalize_specialty, normalize_text


CHITCHAT_KEYWORDS = {"你好", "在吗", "你是谁", "你能做什么"}
STATISTICS_KEYWORDS = ["多少", "统计", "有几个", "有几起", "排名", "最多", "前十"]
RESPONSIBILITY_KEYWORDS = ["谁负责", "归谁管", "哪个班组", "找谁", "责任班组"]
DIAGNOSIS_KEYWORDS = ["怎么办", "怎么处理", "怎么修", "原因", "为什么", "排查", "故障", "异常"]
HISTORY_KEYWORDS = ["历史", "过往", "以往", "之前", "以前", "记录", "案例", "工单", "出过", "出现过"]
COMPARE_LINE_KEYWORDS = ["哪条线", "哪个线路", "线路最多"]
COMPARE_STATION_KEYWORDS = ["哪个站", "哪个车站", "车站最多"]
COMPARE_SPECIALTY_KEYWORDS = ["哪个专业", "专业最多"]

DEVICE_SUFFIXES = [
    "工作站",
    "工控机",
    "服务器",
    "显示器",
    "交换机",
    "主机",
    "终端",
    "控制柜",
    "控制箱",
    "机柜",
    "盘",
    "摄像机",
    "球机",
    "枪机",
    "闸机",
    "门机",
    "读写器",
    "检票机",
    "售票机",
    "配电柜",
    "扶梯",
    "电扶梯",
]

DEVICE_FAMILY_HINTS = [
    "TVM",
    "AGM",
    "BOM",
    "SC",
    "IBP盘",
    "工作站",
    "工控机",
    "显示器",
    "扶梯",
    "电扶梯",
    "闸机",
    "球机",
    "枪机",
    "摄像机",
]

EXACT_DEVICE_PATTERNS = [
    r"(?i)((?:TVM|AGM|BOM|SC|LCB|IBP|FEP|PLC|UPS|AP)\s*[-_]?\s*\d{1,4})",
    r"(?i)((?:TVM|AGM|BOM|SC)\s*[-_]?\s*[A-Z]?\d{1,4})",
]

FAULT_HINTS = [
    "重启无效",
    "无法启动",
    "无法登录",
    "无法显示",
    "频繁死机",
    "失电停止",
    "故障停止",
    "无显示",
    "无反应",
    "黑屏",
    "蓝屏",
    "花屏",
    "死机",
    "卡死",
    "离线",
    "中断",
    "告警",
    "报警",
    "报错",
    "闪退",
    "卡顿",
    "重启",
    "停止",
]

GENERIC_PHENOMENON_WORDS = {
    "怎么办",
    "怎么处理",
    "怎么修",
    "如何处理",
    "如何排查",
    "什么原因",
    "是什么原因",
    "是什么问题",
    "故障",
    "异常",
    "问题",
    "记录",
    "历史",
    "案例",
    "工单",
    "查询",
    "查看",
    "有哪些",
    "有什么",
    "情况",
    "了",
}


def _contains_any(text: str, keywords: list[str] | set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _extract_line_nums(query: str) -> str | None:
    matches = re.findall(r"(\d+)\s*号线", query)
    if matches:
        return ",".join(dict.fromkeys(matches))
    return None


def _extract_station_name(query: str) -> str | None:
    for match in re.finditer(r"([A-Za-z0-9\u4e00-\u9fa5]{2,12}?站)", query):
        candidate = match.group(1)
        if candidate.endswith("工作站"):
            continue
        if candidate in {"车站", "本站", "全站"}:
            continue
        return candidate
    return None


def _extract_time_range(query: str) -> dict[str, str] | None:
    today = datetime.now().date()
    if "今天" in query:
        day = today.strftime("%Y-%m-%d")
        return {"start_date": day, "end_date": day}
    if "昨天" in query:
        day = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        return {"start_date": day, "end_date": day}
    if "本周" in query:
        monday = today - timedelta(days=today.weekday())
        return {"start_date": monday.strftime("%Y-%m-%d"), "end_date": today.strftime("%Y-%m-%d")}
    if "本月" in query:
        month_start = today.replace(day=1)
        return {"start_date": month_start.strftime("%Y-%m-%d"), "end_date": today.strftime("%Y-%m-%d")}

    recent_match = re.search(r"(?:最近|近)\s*(\d{1,3})\s*天", query)
    if recent_match:
        days = int(recent_match.group(1))
        start_day = today - timedelta(days=days)
        return {"start_date": start_day.strftime("%Y-%m-%d"), "end_date": today.strftime("%Y-%m-%d")}
    return None


def _detect_compare_dimension(query: str) -> str | None:
    if _contains_any(query, COMPARE_LINE_KEYWORDS):
        return "line"
    if _contains_any(query, COMPARE_STATION_KEYWORDS):
        return "station"
    if _contains_any(query, COMPARE_SPECIALTY_KEYWORDS):
        return "specialty"
    return None


def _strip_context_words(text: str, station_name: str | None, line_num: str | None) -> str:
    stripped = normalize_text(text)
    if station_name:
        stripped = stripped.replace(station_name, "")
    if line_num:
        for item in line_num.split(","):
            stripped = stripped.replace(f"{item}号线", "")
    for keyword in ("今天", "昨天", "本周", "本月", "最近", "近7天", "近30天"):
        stripped = stripped.replace(keyword, "")
    return stripped


def _normalize_device_token(token: str) -> str:
    normalized = normalize_text(token)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _extract_exact_device(query: str) -> str | None:
    for pattern in EXACT_DEVICE_PATTERNS:
        match = re.search(pattern, query)
        if match:
            return _normalize_device_token(match.group(1))
    return None


def _extract_device(query: str, specialty: str | None, station_name: str | None, line_num: str | None) -> str | None:
    stripped = _strip_context_words(query, station_name, line_num)
    exact_device = _extract_exact_device(stripped)
    if exact_device:
        return exact_device

    aliases = expand_specialty_synonyms(specialty or "")
    candidates: list[str] = []

    for suffix in DEVICE_SUFFIXES:
        pattern = rf"([A-Za-z0-9\u4e00-\u9fa5\-]{{1,24}}?{re.escape(suffix)})"
        for match in re.finditer(pattern, stripped):
            candidate = normalize_text(match.group(1).strip())
            if station_name and candidate.startswith(station_name):
                candidate = candidate[len(station_name) :].strip()
            if not candidate or candidate == suffix:
                continue
            if not specialty or any(alias in candidate for alias in aliases) or suffix in {"扶梯", "电扶梯"}:
                candidates.append(candidate)

    for candidate in candidates:
        if candidate:
            return candidate

    for family_hint in DEVICE_FAMILY_HINTS:
        if family_hint in stripped:
            return family_hint

    return specialty if specialty else None


def _device_cleanup_terms(device: str | None) -> list[str]:
    if not device:
        return []

    terms = [normalize_text(device)]
    compact = re.sub(r"[\s_-]+", "", terms[0])
    if compact and compact not in terms:
        terms.append(compact)
    asset_prefix = re.match(r"(?i)([A-Z]+)\d{1,4}", compact)
    if asset_prefix:
        terms.append(asset_prefix.group(1).upper())
    return list(dict.fromkeys(term for term in terms if term))


def _clean_fault_phenomenon(
    text: str,
    specialty: str | None,
    device: str | None,
    station_name: str | None,
    line_num: str | None,
    query_type: str | None = None,
) -> str | None:
    if query_type == "history":
        return None

    cleaned = _strip_context_words(text, station_name, line_num)
    for alias in expand_specialty_synonyms(specialty or ""):
        cleaned = cleaned.replace(alias, "")
    for term in _device_cleanup_terms(device):
        cleaned = cleaned.replace(term, "")

    for phrase in sorted(GENERIC_PHENOMENON_WORDS, key=len, reverse=True):
        cleaned = cleaned.replace(phrase, "")

    cleaned = re.sub(r"[，。；、？！,.?：:\s]+", " ", cleaned).strip()
    if not cleaned:
        return None

    remaining = cleaned
    matches: list[str] = []
    for hint in sorted(FAULT_HINTS, key=len, reverse=True):
        if hint in remaining:
            matches.append(hint)
            remaining = remaining.replace(hint, " ")
    if matches:
        return " ".join(dict.fromkeys(matches[:4]))

    tokens = re.findall(r"[A-Za-z0-9\u4e00-\u9fa5]{2,16}", cleaned)
    filtered: list[str] = []
    for token in tokens:
        if token in GENERIC_PHENOMENON_WORDS:
            continue
        if token not in filtered:
            filtered.append(token)
    if filtered:
        return " ".join(filtered[:4])
    return None


def fast_parse_local(user_query: str) -> dict[str, Any] | None:
    query = normalize_text(user_query.strip())
    lower_query = query.lower()

    if _contains_any(query, CHITCHAT_KEYWORDS):
        return {"intent": "chitchat", "entities": {}, "confidence": 1.0, "_source": "local_fast_parse"}

    line_num = _extract_line_nums(query)
    station_name = _extract_station_name(query)
    specialty = infer_specialty_from_text(query)
    time_range = _extract_time_range(query)
    compare_dimension = _detect_compare_dimension(query)
    history_query = _contains_any(query, HISTORY_KEYWORDS)

    intent = None
    query_type = None
    if _contains_any(query, RESPONSIBILITY_KEYWORDS):
        intent = "responsibility"
    elif _contains_any(query, STATISTICS_KEYWORDS):
        intent = "statistics"
    elif history_query:
        intent = "diagnosis"
        query_type = "history"
    elif _contains_any(query, DIAGNOSIS_KEYWORDS):
        intent = "diagnosis"

    if intent is None:
        return None

    device = _extract_device(query, specialty, station_name, line_num)
    if intent == "statistics":
        if compare_dimension:
            query_type = "comparison"
        elif "排名" in query or "最多" in query or "top" in lower_query:
            query_type = "ranking"
        else:
            query_type = "count"

    fault_phenomenon = _clean_fault_phenomenon(
        query,
        specialty,
        device,
        station_name,
        line_num,
        query_type=query_type,
    )
    if intent != "diagnosis":
        fault_phenomenon = None

    entities: dict[str, Any] = {
        "line_num": line_num,
        "station_name": station_name,
        "specialty": specialty,
        "device": device,
        "fault_phenomenon": fault_phenomenon,
        "time_range": time_range,
    }

    if intent == "diagnosis" and not specialty and not device:
        return None

    if intent in {"statistics", "responsibility"} and not any([line_num, station_name, specialty, device, time_range]):
        return None

    return {
        "intent": intent,
        "entities": entities,
        "query_type": query_type,
        "compare_dimension": compare_dimension,
        "confidence": 0.92,
        "_source": "local_fast_parse",
    }


def parse_user_query(user_query: str, ai_client: AIClient) -> dict[str, Any]:
    fast_result = fast_parse_local(user_query)
    if fast_result is not None:
        return fast_result

    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""你是地铁运维查询解析器。当前日期：{today}

请从用户问题中提取结构化字段，只返回 JSON。
规则：
1. intent 只能是 diagnosis / statistics / responsibility / chitchat
2. query_type 允许 ranking / count / comparison / history / null
3. line_num 只保留数字，多条线路用英文逗号连接
4. time_range 只在明确提到时间时填写
5. compare_dimension 只在 statistics 且明确是线路/车站/专业对比时填写
6. specialty 优先标准化为 ISCS / 屏蔽门 / AFC / BAS / FAS / 门禁 / 电扶梯 / 给排水 / 通风空调 / 低压供电 / 高压供电 / 通信 / 信号 / 房建 / 安检
7. device 尽量提取到具体设备，例如 综合监控工作站、TVM5、显示器、工控机、闸机、球机
8. fault_phenomenon 只保留核心现象，不要带“怎么办”“怎么处理”这类字样
9. 如果用户是在问历史记录、过往工单、历史故障，把 intent 仍然设为 diagnosis，但 query_type 设为 history

JSON 格式：
{{
  "intent": "diagnosis/statistics/responsibility/chitchat",
  "entities": {{
    "line_num": "1,2 or null",
    "station_name": "车站名或 null",
    "specialty": "专业或 null",
    "device": "设备名称或 null",
    "fault_phenomenon": "故障现象或 null",
    "time_range": {{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}} 或 null
  }},
  "query_type": "ranking/count/comparison/history/null",
  "compare_dimension": "line/station/specialty/null",
  "confidence": 0.0
}}

用户问题：{user_query}
"""
    try:
        result = ai_client.call_llm_json(prompt=prompt, temperature=0.0, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return {"intent": "error", "error_message": str(exc), "original_query": user_query}

    entities = result.get("entities", {}) or {}
    if entities.get("station_name"):
        entities["station_name"] = normalize_text(entities["station_name"])
    if entities.get("specialty"):
        entities["specialty"] = normalize_specialty(entities["specialty"])
    if entities.get("device"):
        entities["device"] = normalize_text(entities["device"])
    if entities.get("fault_phenomenon"):
        entities["fault_phenomenon"] = normalize_text(entities["fault_phenomenon"])

    if entities.get("line_num"):
        nums = re.findall(r"\d+", str(entities["line_num"]))
        entities["line_num"] = ",".join(dict.fromkeys(nums)) if nums else None

    time_range = entities.get("time_range")
    if isinstance(time_range, dict):
        try:
            if time_range.get("start_date"):
                datetime.strptime(time_range["start_date"], "%Y-%m-%d")
            if time_range.get("end_date"):
                datetime.strptime(time_range["end_date"], "%Y-%m-%d")
        except ValueError:
            entities["time_range"] = None

    query_type = result.get("query_type")
    if query_type not in {"ranking", "count", "comparison", "history", None}:
        query_type = None

    if entities.get("fault_phenomenon"):
        entities["fault_phenomenon"] = _clean_fault_phenomenon(
            entities["fault_phenomenon"],
            entities.get("specialty"),
            entities.get("device"),
            entities.get("station_name"),
            entities.get("line_num"),
            query_type=query_type,
        )

    result["entities"] = entities
    result["query_type"] = query_type
    if result.get("intent") not in {"diagnosis", "statistics", "responsibility", "chitchat"}:
        result["intent"] = "diagnosis"
    if _contains_any(normalize_text(user_query), HISTORY_KEYWORDS) and result["intent"] == "diagnosis" and not result.get("query_type"):
        result["query_type"] = "history"
        result["entities"]["fault_phenomenon"] = None
    return result
