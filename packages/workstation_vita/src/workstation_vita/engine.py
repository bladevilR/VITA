from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import math
import re
from datetime import datetime
from typing import Any

import pandas as pd

from .ai_clients import AIClient
from .api_client import EndpointUnavailableError, MaximoApiClient
from .config import get_settings
from .parser import parse_user_query
from .phenomenon_rules import split_fault_terms
from .retrieval_planner import build_retrieval_plan
from .text_utils import expand_specialty_synonyms, infer_specialty_from_text, normalize_specialty, normalize_text
from .vector_store import VectorStore


logger = logging.getLogger("workstation_vita.engine")

STOP_TERMS = {
    "怎么办",
    "怎么处理",
    "怎么修",
    "如何处理",
    "如何排查",
    "故障",
    "异常",
    "问题",
    "设备",
    "系统",
    "历史",
    "记录",
    "案例",
    "工单",
}
TEXT_COLUMNS = [
    "DESCRIPTION",
    "PROBLEMCODE",
    "FAILURECODE",
    "FAULT_CAUSE",
    "SOLUTION",
    "ASSETNUM",
    "SPECIALTY",
]
DISPLAY_COLUMNS = [
    "TICKETID",
    "REPORTDATE",
    "LINENUM",
    "STATIONNAME",
    "DESCRIPTION",
    "STATUS",
    "SPECIALTY",
    "OWNERGROUP",
    "SOLUTION",
    "FAULT_CAUSE",
    "FAILURECODE",
    "PROBLEMCODE",
    "ASSETNUM",
    "PLAN_LABEL",
    "PLAN_EVIDENCE",
    "PLAN_PRIORITY",
    "RELEVANCE_SCORE",
    "RETRIEVAL_RANK",
]
DEVICE_SUFFIX_HINTS = [
    "工作站",
    "工控机",
    "显示器",
    "服务器",
    "交换机",
    "主机",
    "终端",
    "控制柜",
    "控制箱",
    "机柜",
    "盘",
    "扶梯",
    "电扶梯",
    "闸机",
    "门机",
    "球机",
    "枪机",
    "摄像机",
    "检票机",
    "售票机",
    "读写器",
    "配电柜",
]
NULL_TEXTS = {"", "NONE", "NULL", "NAN", "NAT"}
LAYER_PRIORITY_BONUS = {
    "direct_exact": 460,
    "station_same_device": 340,
    "station_same_specialty": 280,
    "line_same_fault": 220,
    "peer_same_device_fault": 180,
    "peer_same_device": 160,
    "peer_neighbor_fault": 110,
    "general_specialty": 60,
}
EVIDENCE_BONUS = {
    "direct": 160,
    "history": 120,
    "indirect": 70,
    "weak": 20,
}
BUCKET_ORDER = {
    "direct": 1,
    "station": 2,
    "line": 3,
    "supplemental": 4,
}


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    if not text or text.upper() in NULL_TEXTS:
        return default
    return text


def _compact_token(value: str) -> str:
    return re.sub(r"[\s_-]+", "", normalize_text(value)).upper()


def _dedupe_strings(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = _safe_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _build_search_query(entities: dict[str, Any]) -> str:
    parts: list[str] = []
    station_name = _safe_text(entities.get("station_name"))
    device = _safe_text(entities.get("device"))
    fault = _safe_text(entities.get("fault_phenomenon"))
    specialty = _safe_text(entities.get("specialty"))
    line_num = _safe_text(entities.get("line_num"))

    if station_name:
        parts.append(station_name)
    if device:
        parts.append(device)
    if fault:
        parts.append(fault)
    if specialty and specialty not in device:
        parts.append(specialty)
    if line_num:
        parts.append(f"{line_num}号线")
    return " ".join(part for part in parts if part) or "故障诊断"


def _split_terms(text: str) -> list[str]:
    if not text:
        return []
    normalized = normalize_text(str(text))
    tokens = re.findall(r"[A-Za-z0-9\u4e00-\u9fa5]{2,20}", normalized)
    unique: list[str] = []
    for token in tokens:
        if token in STOP_TERMS:
            continue
        if token not in unique:
            unique.append(token)
    return unique


def _parse_report_date(value: Any) -> datetime | None:
    text = _safe_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(text).to_pydatetime()
    except Exception:  # noqa: BLE001
        return None


def _recency_bonus(value: Any) -> int:
    report_date = _parse_report_date(value)
    if report_date is None:
        return 0
    days = max((datetime.now() - report_date).days, 0)
    if days <= 7:
        return 120
    if days <= 30:
        return 90
    if days <= 90:
        return 55
    if days <= 180:
        return 20
    return 0


def _row_search_text(row: pd.Series) -> str:
    parts = [_safe_text(row.get(column, "")) for column in TEXT_COLUMNS]
    return normalize_text(" ".join(part for part in parts if part))


def _is_specific_device(device: str | None, specialty: str | None) -> bool:
    device_text = _safe_text(device)
    if not device_text:
        return False
    specialty_terms = set(expand_specialty_synonyms(specialty or ""))
    return device_text not in specialty_terms and device_text != normalize_specialty(specialty or "")


def _extract_device_features(device: str | None, specialty: str | None) -> dict[str, Any]:
    device_text = _safe_text(device)
    specialty_terms = set(expand_specialty_synonyms(specialty or ""))
    specific_device = _is_specific_device(device_text, specialty)
    exact_terms: list[str] = []
    family_terms: list[str] = []
    compact_terms: list[str] = []

    if not device_text:
        return {
            "specific_device": False,
            "exact_terms": [],
            "family_terms": [],
            "compact_terms": [],
        }

    asset_match = re.search(r"(?i)([A-Z]+)\d{1,4}", _compact_token(device_text))
    if asset_match:
        exact_terms.append(device_text)
        compact_terms.append(_compact_token(device_text))
        family_terms.append(asset_match.group(1).upper())
    else:
        if specific_device:
            exact_terms.append(device_text)
        for hint in DEVICE_SUFFIX_HINTS:
            if hint in device_text:
                family_terms.append(hint)
        for token in _split_terms(device_text):
            if token in specialty_terms or token in STOP_TERMS:
                continue
            if token != device_text:
                family_terms.append(token)

    if not specific_device and device_text:
        family_terms.append(device_text)

    return {
        "specific_device": specific_device,
        "exact_terms": _dedupe_strings(exact_terms),
        "family_terms": _dedupe_strings(family_terms),
        "compact_terms": _dedupe_strings(compact_terms),
    }


def _station_history_rows(station_history: list[dict[str, Any]], entities: dict[str, Any], layer: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    station_name = _safe_text(entities.get("station_name"))
    line_num = _safe_text(entities.get("line_num"))
    for item in station_history or []:
        description = _safe_text(item.get("desc"))
        solution = _safe_text(item.get("solution"))
        specialty = infer_specialty_from_text(f"{description} {solution}") or _safe_text(entities.get("specialty"))
        rows.append(
            {
                "TICKETID": _safe_text(item.get("ticket")),
                "REPORTDATE": _safe_text(item.get("date")),
                "LINENUM": line_num,
                "STATIONNAME": station_name,
                "DESCRIPTION": description,
                "SOLUTION": solution,
                "SPECIALTY": specialty,
                "CASE_SOURCE": "station_history",
                "PLAN_LAYER_ID": layer["layer_id"],
                "PLAN_LABEL": layer["label"],
                "PLAN_BUCKET": layer["bucket"],
                "PLAN_EVIDENCE": layer["evidence_level"],
                "PLAN_PRIORITY": layer["priority"],
                "PLAN_MUST_MATCH_FAULT": layer.get("must_match_fault", False),
                "PLAN_MUST_MATCH_DEVICE": layer.get("must_match_device", False),
                "RETRIEVAL_RANK": 0,
            }
        )
    return rows


def _prepare_case_pool(layer_outputs: list[dict[str, Any]]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for layer_output in layer_outputs:
        layer = layer_output["layer"]
        support = layer_output["support"]
        cases_df = pd.DataFrame(support.get("cases", []))
        if not cases_df.empty:
            support_df = cases_df.copy()
            support_df["CASE_SOURCE"] = "support"
            support_df["PLAN_LAYER_ID"] = layer["layer_id"]
            support_df["PLAN_LABEL"] = layer["label"]
            support_df["PLAN_BUCKET"] = layer["bucket"]
            support_df["PLAN_EVIDENCE"] = layer["evidence_level"]
            support_df["PLAN_PRIORITY"] = layer["priority"]
            support_df["PLAN_MUST_MATCH_FAULT"] = bool(layer.get("must_match_fault"))
            support_df["PLAN_MUST_MATCH_DEVICE"] = bool(layer.get("must_match_device"))
            if "RETRIEVAL_RANK" not in support_df.columns:
                support_df["RETRIEVAL_RANK"] = range(1, len(support_df) + 1)
            frames.append(support_df)

        history_rows = _station_history_rows(
            support.get("analytics", {}).get("station_history", []),
            layer["entities"],
            layer,
        )
        if history_rows:
            frames.append(pd.DataFrame(history_rows))

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "TICKETID" not in combined.columns:
        return combined.reset_index(drop=True)

    def dedupe_key(row: pd.Series) -> str:
        ticket_id = _safe_text(row.get("TICKETID"))
        fallback = ticket_id or f"{_safe_text(row.get('DESCRIPTION'))}:{_safe_text(row.get('REPORTDATE'))}"
        if _safe_text(row.get("CASE_SOURCE")) == "station_history":
            return f"station_history:{_safe_text(row.get('PLAN_BUCKET'))}:{fallback}"
        return fallback

    combined["__bucket_order"] = combined["PLAN_BUCKET"].map(BUCKET_ORDER).fillna(99)
    combined["__dedupe_key"] = combined.apply(dedupe_key, axis=1)
    combined = combined.sort_values(
        ["PLAN_PRIORITY", "__bucket_order", "CASE_SOURCE", "RETRIEVAL_RANK"],
        ascending=[True, True, True, True],
        na_position="last",
    )
    combined = combined.drop_duplicates(subset=["__dedupe_key"], keep="first").drop(columns=["__bucket_order", "__dedupe_key"])
    return combined.reset_index(drop=True)


def _aggregate_station_history(layer_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for layer_output in layer_outputs:
        for item in layer_output["support"].get("analytics", {}).get("station_history", []):
            key = _safe_text(item.get("ticket")) or _safe_text(item.get("desc"))
            if key and key not in seen:
                seen.add(key)
                merged.append(item)
    return merged[:6]


def _aggregate_support_metadata(layer_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    vector_ids: list[str] = []
    keyword_ids: list[str] = []
    fused_ids: list[str] = []
    for layer_output in layer_outputs:
        support = layer_output["support"]
        for collection, source in (
            (vector_ids, support.get("vector_candidate_ids", [])),
            (keyword_ids, support.get("keyword_candidate_ids", [])),
            (fused_ids, support.get("fused_ticket_ids", [])),
        ):
            for item in source:
                text = _safe_text(item)
                if text and text not in collection:
                    collection.append(text)
    return {
        "vector_candidate_ids": vector_ids,
        "keyword_candidate_ids": keyword_ids,
        "fused_ticket_ids": fused_ids,
    }


def _annotate_cases(case_pool: pd.DataFrame, entities: dict[str, Any], retrieval_plan: dict[str, Any]) -> pd.DataFrame:
    if case_pool.empty:
        return case_pool.copy()

    specialty = _safe_text(entities.get("specialty"))
    station_name = _safe_text(entities.get("station_name"))
    line_nums = [item.strip() for item in _safe_text(entities.get("line_num")).split(",") if item.strip()]
    specialty_terms = expand_specialty_synonyms(specialty)
    device_features = _extract_device_features(entities.get("device"), specialty)
    exact_fault_terms = _dedupe_strings(retrieval_plan.get("exact_fault_terms", []))
    neighbor_fault_terms = _dedupe_strings(retrieval_plan.get("neighbor_fault_terms", []))
    mechanism_terms = _dedupe_strings(retrieval_plan.get("mechanism_terms", []))
    has_exact_fault = bool(exact_fault_terms)

    annotated = case_pool.copy()
    annotated["SEARCH_TEXT"] = annotated.apply(_row_search_text, axis=1)
    annotated["SEARCH_TEXT_COMPACT"] = annotated["SEARCH_TEXT"].apply(_compact_token)
    annotated["SPECIALTY_MATCH"] = annotated.apply(
        lambda row: any(term and term in _safe_text(row.get("SPECIALTY")) for term in specialty_terms)
        or any(term and term in _safe_text(row.get("SEARCH_TEXT")) for term in specialty_terms),
        axis=1,
    )
    annotated["SAME_STATION"] = annotated.apply(
        lambda row: bool(station_name) and station_name in _safe_text(row.get("STATIONNAME")),
        axis=1,
    )
    annotated["SAME_LINE"] = annotated.apply(
        lambda row: bool(line_nums) and _safe_text(row.get("LINENUM")) in line_nums,
        axis=1,
    )
    annotated["EXACT_DEVICE_HITS"] = annotated.apply(
        lambda row: sum(int(term in _safe_text(row.get("SEARCH_TEXT"))) for term in device_features["exact_terms"])
        + sum(int(term in _safe_text(row.get("SEARCH_TEXT_COMPACT"))) for term in device_features["compact_terms"]),
        axis=1,
    )
    annotated["DEVICE_FAMILY_HITS"] = annotated["SEARCH_TEXT"].apply(
        lambda text: sum(int(term in text) for term in device_features["family_terms"])
    )
    annotated["EXACT_FAULT_HITS"] = annotated["SEARCH_TEXT"].apply(
        lambda text: sum(int(term in text) for term in exact_fault_terms)
    )
    annotated["NEIGHBOR_FAULT_HITS"] = annotated["SEARCH_TEXT"].apply(
        lambda text: sum(int(term in text) for term in neighbor_fault_terms)
    )
    annotated["MECHANISM_HITS"] = annotated["SEARCH_TEXT"].apply(
        lambda text: sum(int(term in text) for term in mechanism_terms)
    )
    annotated["ANY_DEVICE_HITS"] = annotated["EXACT_DEVICE_HITS"] + annotated["DEVICE_FAMILY_HITS"]
    annotated["FAULT_HITS"] = annotated["EXACT_FAULT_HITS"] + annotated["NEIGHBOR_FAULT_HITS"]
    annotated["RECENCY_BONUS"] = annotated["REPORTDATE"].apply(_recency_bonus)
    annotated["PLANNER_BONUS"] = annotated.apply(
        lambda row: LAYER_PRIORITY_BONUS.get(_safe_text(row.get("PLAN_LAYER_ID")), 0)
        + EVIDENCE_BONUS.get(_safe_text(row.get("PLAN_EVIDENCE")), 0),
        axis=1,
    )

    def constraint_ok(row: pd.Series) -> bool:
        if _safe_text(row.get("CASE_SOURCE")) == "station_history" and _safe_text(row.get("PLAN_BUCKET")) == "station":
            return True
        if bool(row.get("PLAN_MUST_MATCH_FAULT")) and int(row["EXACT_FAULT_HITS"]) <= 0:
            return False
        if bool(row.get("PLAN_MUST_MATCH_DEVICE")) and int(row["ANY_DEVICE_HITS"]) <= 0:
            return False
        if _safe_text(row.get("PLAN_LAYER_ID")) == "peer_neighbor_fault":
            return int(row["FAULT_HITS"]) > 0 and (not bool(row.get("PLAN_MUST_MATCH_DEVICE")) or int(row["ANY_DEVICE_HITS"]) > 0)
        if _safe_text(row.get("PLAN_LAYER_ID")) == "general_specialty":
            return bool(row["SPECIALTY_MATCH"])
        if _safe_text(row.get("PLAN_BUCKET")) == "station":
            return bool(row["SAME_STATION"])
        if _safe_text(row.get("PLAN_BUCKET")) == "line":
            return bool(row["SAME_LINE"])
        return True

    annotated["LAYER_CONSTRAINT_OK"] = annotated.apply(constraint_ok, axis=1)

    def direct_level(row: pd.Series) -> int:
        exact_device_hits = int(row["EXACT_DEVICE_HITS"])
        device_hits = int(row["ANY_DEVICE_HITS"])
        exact_fault_hits = int(row["EXACT_FAULT_HITS"])
        neighbor_fault_hits = int(row["NEIGHBOR_FAULT_HITS"])

        if exact_device_hits and exact_fault_hits:
            return 3
        if device_hits and exact_fault_hits:
            return 2
        if exact_fault_hits and (row["SPECIALTY_MATCH"] or row["SAME_STATION"]):
            return 2
        if device_hits and neighbor_fault_hits:
            return 1
        return 0

    annotated["DIRECT_LEVEL"] = annotated.apply(direct_level, axis=1)

    def score_row(row: pd.Series) -> int:
        score = 0
        if row["CASE_SOURCE"] == "station_history":
            score += 320
        if row["SPECIALTY_MATCH"]:
            score += 200
        if row["SAME_STATION"]:
            score += 320
        if row["SAME_LINE"]:
            score += 110
        score += int(row["EXACT_DEVICE_HITS"]) * 430
        score += int(row["DEVICE_FAMILY_HITS"]) * 160
        score += int(row["EXACT_FAULT_HITS"]) * 320
        score += int(row["NEIGHBOR_FAULT_HITS"]) * 140
        score += int(row["MECHANISM_HITS"]) * 35
        score += int(row["DIRECT_LEVEL"]) * 260
        score += int(row["PLANNER_BONUS"])
        score += int(row["RECENCY_BONUS"])
        if not row["LAYER_CONSTRAINT_OK"]:
            score -= 800
        if has_exact_fault and not row["EXACT_FAULT_HITS"] and _safe_text(row.get("PLAN_LAYER_ID")) == "direct_exact":
            score -= 220
        if device_features["specific_device"] and not row["ANY_DEVICE_HITS"] and bool(row.get("PLAN_MUST_MATCH_DEVICE")):
            score -= 260
        if specialty and not row["SPECIALTY_MATCH"] and row["CASE_SOURCE"] != "station_history":
            score -= 90
        return score

    annotated["RELEVANCE_SCORE"] = annotated.apply(score_row, axis=1)
    return annotated.sort_values(
        ["PLAN_PRIORITY", "RELEVANCE_SCORE", "RETRIEVAL_RANK"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)


def _apply_local_rerank(ai_client: AIClient, cases_df: pd.DataFrame, query: str, top_k: int = 20) -> tuple[pd.DataFrame, bool]:
    if cases_df.empty or len(cases_df) <= 1:
        return cases_df.head(top_k), False

    texts: list[str] = []
    for _, row in cases_df.iterrows():
        texts.append(
            f"层级:{_safe_text(row.get('PLAN_LABEL'))} "
            f"证据:{_safe_text(row.get('PLAN_EVIDENCE'))} "
            f"专业:{_safe_text(row.get('SPECIALTY'))} "
            f"车站:{_safe_text(row.get('STATIONNAME'))} "
            f"描述:{_safe_text(row.get('DESCRIPTION'))} "
            f"处理:{_safe_text(row.get('SOLUTION'))[:180]}"
        )

    try:
        ordered_indices = ai_client.rerank_results(query=query, texts=texts, top_k=min(top_k, len(texts)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local rerank failed: %s", exc)
        return cases_df.head(top_k), False

    ordered_indices = [index for index in ordered_indices if 0 <= index < len(cases_df)]
    if not ordered_indices:
        return cases_df.head(top_k), False
    return cases_df.reset_index(drop=True).iloc[ordered_indices[:top_k]].reset_index(drop=True), True


def _dedupe_cases(*frames: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    rows: list[pd.Series] = []
    seen: set[str] = set()
    for frame in frames:
        if frame.empty:
            continue
        for _, row in frame.iterrows():
            ticket_id = _safe_text(row.get("TICKETID"))
            key = ticket_id or f"{_safe_text(row.get('DESCRIPTION'))}:{_safe_text(row.get('REPORTDATE'))}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            if len(rows) >= limit:
                return pd.DataFrame(rows).reset_index(drop=True)
    return pd.DataFrame(rows).reset_index(drop=True) if rows else pd.DataFrame()


def _is_precise_scene(entities: dict[str, Any], query_type: str | None = None) -> bool:
    if query_type == "history":
        return True
    return bool(
        _safe_text(entities.get("station_name"))
        or _safe_text(entities.get("fault_phenomenon"))
        or _is_specific_device(entities.get("device"), entities.get("specialty"))
    )


def _prepare_case_groups(
    case_pool: pd.DataFrame,
    entities: dict[str, Any],
    retrieval_plan: dict[str, Any],
    user_query: str,
    ai_client: AIClient,
    query_type: str | None = None,
) -> tuple[dict[str, pd.DataFrame], bool]:
    annotated = _annotate_cases(case_pool, entities, retrieval_plan)
    empty_groups = {
        "直接相关案例": pd.DataFrame(),
        "本站历史案例": pd.DataFrame(),
        "同线同类案例": pd.DataFrame(),
        "补充参考案例": pd.DataFrame(),
        "最终引用案例": pd.DataFrame(),
    }
    if annotated.empty:
        return empty_groups, False

    candidate_df = annotated[annotated["LAYER_CONSTRAINT_OK"] & (annotated["RELEVANCE_SCORE"] > -200)].copy()
    if candidate_df.empty:
        candidate_df = annotated.copy()

    rerank_applied = False
    if not _is_precise_scene(entities, query_type=query_type):
        candidate_df, rerank_applied = _apply_local_rerank(ai_client, candidate_df.head(30), user_query, top_k=24)

    direct_cases = candidate_df[
        (candidate_df["PLAN_BUCKET"] == "direct")
        & candidate_df["LAYER_CONSTRAINT_OK"]
        & ((candidate_df["DIRECT_LEVEL"] >= 2) | (candidate_df["EXACT_FAULT_HITS"] > 0))
    ].head(5)

    station_cases = candidate_df[
        (candidate_df["PLAN_BUCKET"] == "station")
        & candidate_df["LAYER_CONSTRAINT_OK"]
    ].head(5)
    if station_cases.empty and _safe_text(entities.get("station_name")):
        station_cases = candidate_df[candidate_df["SAME_STATION"] & candidate_df["LAYER_CONSTRAINT_OK"]].head(5)

    line_cases = candidate_df[
        (candidate_df["PLAN_BUCKET"] == "line")
        & candidate_df["LAYER_CONSTRAINT_OK"]
    ].head(5)

    supplemental_cases = candidate_df[
        (candidate_df["PLAN_BUCKET"] == "supplemental")
        & candidate_df["LAYER_CONSTRAINT_OK"]
    ].head(5)

    if query_type == "history" and direct_cases.empty:
        direct_cases = candidate_df[
            (candidate_df["ANY_DEVICE_HITS"] > 0) & candidate_df["LAYER_CONSTRAINT_OK"]
        ].head(3)

    quoted_cases = _dedupe_cases(direct_cases, station_cases, line_cases, supplemental_cases, limit=8)
    return {
        "直接相关案例": direct_cases,
        "本站历史案例": station_cases,
        "同线同类案例": line_cases,
        "补充参考案例": supplemental_cases,
        "最终引用案例": quoted_cases,
    }, rerank_applied


def _risk_level_to_cn(level: str) -> str:
    return {
        "critical": "极高",
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(str(level).lower(), str(level) or "未知")


def _trend_to_cn(trend: str) -> str:
    return {
        "up": "上升",
        "down": "下降",
        "stable": "持平",
    }.get(str(trend).lower(), str(trend) or "未知")


def _evidence_to_cn(value: str) -> str:
    return {
        "direct": "直接证据",
        "history": "本站历史",
        "indirect": "间接参考",
        "weak": "弱参考",
    }.get(str(value).lower(), str(value) or "")


def _format_case_block(title: str, cases_df: pd.DataFrame) -> str:
    if cases_df.empty:
        return f"{title}：暂无"

    blocks: list[str] = [f"{title}："]
    for index, (_, row) in enumerate(cases_df.head(3).iterrows(), start=1):
        evidence = _evidence_to_cn(_safe_text(row.get("PLAN_EVIDENCE")))
        evidence_note = f"；证据：{evidence}" if evidence else ""
        blocks.append(
            f"{index}. 工单{_safe_text(row.get('TICKETID'), '未知')}，"
            f"{_safe_text(row.get('REPORTDATE')) or '时间不详'}，"
            f"{_safe_text(row.get('STATIONNAME'), '未知站点')}，"
            f"描述：{_safe_text(row.get('DESCRIPTION'), '暂无')[:70]}；"
            f"处理：{_safe_text(row.get('SOLUTION'), '暂无')[:90]}{evidence_note}"
        )
    return "\n".join(blocks)


def _format_station_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return "本站最近工单：暂无"
    lines = ["本站最近工单："]
    for index, item in enumerate(history[:3], start=1):
        lines.append(
            f"{index}. 工单{_safe_text(item.get('ticket'), '未知')}，{_safe_text(item.get('date'), '时间不详')}，"
            f"{_safe_text(item.get('desc'), '暂无')}；处理：{_safe_text(item.get('solution'), '暂无')}"
        )
    return "\n".join(lines)


def _clean_responsibility_answer(answer: str, entities: dict[str, Any]) -> str:
    cleaned = _safe_text(answer)
    if not cleaned:
        return "责任归属查询完成。"

    cleaned = re.sub(r"\*\*([一-龥A-Za-z])\1+([一-龥A-Za-z0-9]+)\*\*", r"**\1\2**", cleaned)
    cleaned = re.sub(r"([一-龥])\1{2,}", r"\1", cleaned)

    if cleaned.startswith("没有找到"):
        specialty = _safe_text(entities.get("specialty"))
        device = _safe_text(entities.get("device"))
        display = device if _is_specific_device(device, specialty) else specialty or device or "该设备"
        cleaned = f"没有找到与 **{display}** 直接对应的责任归属记录。"
        if specialty and specialty != display:
            cleaned += f"\n\n建议先按 **{specialty}** 专业继续核实责任班组。"
    return cleaned


def _query_knowledge_base(settings, specialty: str | None) -> dict[str, Any]:
    specialty = normalize_specialty(specialty or "") or specialty or ""
    if specialty in {"AFC", "屏蔽门", "电扶梯", "FAS", "BAS", "给排水", "通风空调", "低压供电", "高压供电"}:
        return {"level": "general_guide", "specialty": specialty, "link": settings.general_guide_link}
    return {"level": "no_standard", "specialty": specialty}


def _prepare_answer_analytics(
    primary_analytics: dict[str, Any],
    case_groups: dict[str, pd.DataFrame],
    entities: dict[str, Any],
    retrieval_plan: dict[str, Any],
    station_history: list[dict[str, Any]],
    query_type: str | None = None,
) -> dict[str, Any]:
    analytics = dict(primary_analytics or {})
    analytics["station_history"] = station_history
    analytics["retrieval_plan_notes"] = _safe_text(retrieval_plan.get("notes"))

    if query_type == "history":
        analytics["risk_assessment"] = {
            "level": "历史查询",
            "freq_text": f"本站历史案例 {len(case_groups['本站历史案例'])} 条，直接相关案例 {len(case_groups['直接相关案例'])} 条",
            "recommendation": "优先看本站最近记录，再看同线同类案例。",
        }
        return analytics

    has_specific_scene = bool(_safe_text(entities.get("fault_phenomenon"))) or _is_specific_device(entities.get("device"), entities.get("specialty"))
    if not has_specific_scene:
        return analytics

    direct_count = len(case_groups["直接相关案例"])
    station_count = len(case_groups["本站历史案例"])
    line_count = len(case_groups["同线同类案例"])
    supplemental_count = len(case_groups["补充参考案例"])

    analytics["total_cases"] = direct_count + supplemental_count
    analytics["line_cases"] = line_count
    analytics["station_cases"] = station_count

    if direct_count == 0:
        analytics["time_trend"] = {"recent_7d": 0, "recent_30d": 0, "prev_30d": 0, "recent_90d": 0, "trend": "依据不足"}
        analytics["risk_assessment"] = {
            "level": "待判定",
            "freq_text": "未找到与当前现象直接匹配的历史工单",
            "recommendation": "先按通用流程排查，再结合本站历史和现场日志继续定位。",
        }
        analytics["high_freq_stations"] = []
        analytics["cause_stats"] = []
        analytics["solution_stats"] = []
        return analytics

    analytics["time_trend"] = {
        "recent_7d": 0,
        "recent_30d": direct_count,
        "prev_30d": 0,
        "recent_90d": direct_count + supplemental_count,
        "trend": "依据样本",
    }
    analytics["risk_assessment"] = {
        "level": "中" if direct_count <= 2 else "高",
        "freq_text": f"直接相关案例 {direct_count} 条，补充参考案例 {supplemental_count} 条",
        "recommendation": "以直接相关案例为主，结合本站历史做现场排查。",
    }
    return analytics


def _build_diagnosis_prompt(
    user_query: str,
    entities: dict[str, Any],
    retrieval_plan: dict[str, Any],
    analytics: dict[str, Any],
    case_groups: dict[str, pd.DataFrame],
    knowledge_result: dict[str, Any],
) -> str:
    trend = analytics.get("time_trend", {})
    risk = analytics.get("risk_assessment", {})
    direct_cases = case_groups["直接相关案例"]
    station_cases = case_groups["本站历史案例"]
    line_cases = case_groups["同线同类案例"]
    supplemental_cases = case_groups["补充参考案例"]

    cause_stats = analytics.get("cause_stats", [])
    solution_stats = analytics.get("solution_stats", [])
    cause_text = "、".join(f"{item['cause']}({item['count']}次)" for item in cause_stats[:5]) or "暂无"
    solution_text = "、".join(f"{item['method']}({item['count']}次)" for item in solution_stats[:5]) or "暂无"
    high_freq_text = "、".join(
        f"{item['station']}({item['count']}次)" for item in analytics.get("high_freq_stations", [])[:5]
    ) or "暂无"

    guide_text = ""
    if knowledge_result.get("level") == "general_guide" and knowledge_result.get("link"):
        guide_text = f"\n通用指引：{knowledge_result['link']}"

    stats_lines = [
        f"- 直接相关案例数：{len(direct_cases)}",
        f"- 本站历史案例数：{len(station_cases)}",
        f"- 同线同类案例数：{len(line_cases)}",
        f"- 补充参考案例数：{len(supplemental_cases)}",
        f"- 风险等级：{_risk_level_to_cn(risk.get('level', '低'))}",
        f"- 风险说明：{risk.get('freq_text', '暂无')}",
    ]
    if trend.get("trend") not in {"依据不足", "依据样本"}:
        stats_lines.extend(
            [
                f"- 近7天：{trend.get('recent_7d', 0)}次",
                f"- 近30天：{trend.get('recent_30d', 0)}次",
                f"- 前30天：{trend.get('prev_30d', 0)}次",
                f"- 趋势：{_trend_to_cn(trend.get('trend', '持平'))}",
                f"- 高频站点：{high_freq_text}",
                f"- 原因分布：{cause_text}",
                f"- 处理方式分布：{solution_text}",
            ]
        )
    else:
        stats_lines.append("- 时间趋势：由于没有找到足够的直接匹配工单，趋势依据不足。")

    planner_lines = [
        f"- 精确现象：{'、'.join(retrieval_plan.get('exact_fault_terms', [])) or '未识别'}",
        f"- 相近现象：{'、'.join(retrieval_plan.get('neighbor_fault_terms', [])) or '无'}",
        f"- 设备别名：{'、'.join(retrieval_plan.get('device_aliases', [])) or '无'}",
    ]

    return f"""你是地铁设备维修专家。请根据“直接相关案例、本站历史、同线同类案例、统计数据”给出诊断建议。

用户问题：
{user_query}

识别结果：
- 车站：{_safe_text(entities.get('station_name'), '未指定')}
- 线路：{_safe_text(entities.get('line_num'), '未指定')}
- 专业：{_safe_text(entities.get('specialty'), '未识别')}
- 设备：{_safe_text(entities.get('device'), '未识别')}
- 现象：{_safe_text(entities.get('fault_phenomenon'), '未识别')}

检索规划：
{chr(10).join(planner_lines)}

统计信息：
{chr(10).join(stats_lines)}

{_format_case_block("直接相关案例", direct_cases)}

{_format_case_block("本站历史案例", station_cases)}

{_format_case_block("同线同类案例", line_cases)}

{_format_case_block("补充参考案例", supplemental_cases)}

{_format_station_history(analytics.get("station_history", []))}{guide_text}

回答要求：
1. 严格用中文作答，不要出现没有必要的英文词。
2. 直接相关案例只允许引用现象原词一致或极贴近的案例。
3. 补充参考案例必须明确标注为“相近现象”或“间接参考”，不能冒充直接证据。
4. 如果“直接相关案例”为空，要明确说“没有找到与该现象直接匹配的历史工单”。
5. “本站历史案例”即使现象不完全一致，也要说明它是本站设备或本站同专业的间接参考。
6. 回答结构固定为：
   一、现场判断
   二、最可能原因
   三、优先排查步骤
   四、本站与同类历史参考
   五、结论
7. 结论必须区分：
   - 直接证据
   - 间接参考
   - 依据不足的部分
"""


def _build_history_prompt(
    user_query: str,
    entities: dict[str, Any],
    retrieval_plan: dict[str, Any],
    analytics: dict[str, Any],
    case_groups: dict[str, pd.DataFrame],
) -> str:
    return f"""你是地铁运维历史工单分析助手。请根据给出的历史记录，总结指定车站、设备、现象最相关的过往工单。

用户问题：
{user_query}

识别结果：
- 车站：{_safe_text(entities.get('station_name'), '未指定')}
- 线路：{_safe_text(entities.get('line_num'), '未指定')}
- 专业：{_safe_text(entities.get('specialty'), '未识别')}
- 设备：{_safe_text(entities.get('device'), '未识别')}
- 现象：{_safe_text(entities.get('fault_phenomenon'), '未指定')}
- 设备别名：{'、'.join(retrieval_plan.get('device_aliases', [])) or '无'}

{_format_case_block("最贴近的历史记录", case_groups["直接相关案例"])}

{_format_case_block("本站历史案例", case_groups["本站历史案例"])}

{_format_case_block("同线同类案例", case_groups["同线同类案例"])}

{_format_case_block("补充参考案例", case_groups["补充参考案例"])}

{_format_station_history(analytics.get("station_history", []))}

回答要求：
1. 严格用中文。
2. 先列最贴近的历史记录，再列本站历史，再列同类参考。
3. 如果没有直接匹配，要明确说没有找到与该设备和现象直接一致的历史工单。
4. 回答结构固定为：
   一、最贴近的历史记录
   二、本站设备历史
   三、同类参考
   四、结论
"""


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    keep_columns = [column for column in DISPLAY_COLUMNS if column in frame.columns]
    cleaned = frame[keep_columns].copy()
    if "PLAN_EVIDENCE" in cleaned.columns:
        cleaned["PLAN_EVIDENCE"] = cleaned["PLAN_EVIDENCE"].apply(lambda value: _evidence_to_cn(_safe_text(value)))
    cleaned = cleaned.where(pd.notna(cleaned), None)
    return cleaned.to_dict(orient="records")


class WorkstationEngine:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.ai_client = AIClient()
        self.api_client = MaximoApiClient()
        self.vector_store = VectorStore()

    def server_health(self) -> dict[str, Any]:
        return self.api_client.healthz()

    def _vector_candidates_for_entities(self, entities: dict[str, Any], use_vector: bool) -> list[str]:
        if not use_vector:
            return []
        search_query = _build_search_query(entities)
        embedding = self.ai_client.get_embedding(search_query)
        return self.vector_store.search(embedding=embedding, top_k=self.settings.vector_top_k)

    def _build_layer_request(self, layer: dict[str, Any]) -> dict[str, Any]:
        limit = min(self.settings.max_cases_limit, 60 if layer["priority"] <= 2 else 40)
        return {
            **layer,
            "vector_candidate_ids": self._vector_candidates_for_entities(layer["entities"], layer.get("use_vector", False)),
            "limit": limit,
        }

    @staticmethod
    def _run_support_request(user_query: str, layer: dict[str, Any]) -> dict[str, Any]:
        api_client = MaximoApiClient()
        support = api_client.run_diagnosis_support(
            user_query=user_query,
            entities=layer["entities"],
            vector_candidate_ids=layer["vector_candidate_ids"],
            limit=layer["limit"],
        )
        return {"layer": layer, "support": support}

    def _execute_layered_support(self, user_query: str, retrieval_plan: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        requests = [self._build_layer_request(layer) for layer in retrieval_plan.get("layers", [])]
        if not requests:
            return [], "none"

        if self.settings.enable_batch_support:
            try:
                payload = self.api_client.run_diagnosis_support_batch(user_query=user_query, layers=requests)
                layer_outputs: list[dict[str, Any]] = []
                for item in payload.get("layers", []):
                    layer = next((req for req in requests if req["layer_id"] == item.get("layer_id")), None)
                    if not layer:
                        continue
                    layer_outputs.append({"layer": layer, "support": item.get("result", {})})
                if layer_outputs:
                    return layer_outputs, "batch"
            except EndpointUnavailableError:
                logger.info("Server batch diagnosis endpoint unavailable, fallback to sequential calls")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Batch diagnosis support failed, fallback to sequential calls: %s", exc)

        max_workers = min(max(1, self.settings.support_parallelism), len(requests))
        if max_workers > 1:
            layer_outputs: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._run_support_request, user_query, layer) for layer in requests]
                for future in as_completed(futures):
                    layer_outputs.append(future.result())
            layer_outputs.sort(key=lambda item: int(item["layer"].get("priority", 99)))
            return layer_outputs, f"parallel_{max_workers}"

        layer_outputs = []
        for layer in requests:
            support = self.api_client.run_diagnosis_support(
                user_query=user_query,
                entities=layer["entities"],
                vector_candidate_ids=layer["vector_candidate_ids"],
                limit=layer["limit"],
            )
            layer_outputs.append({"layer": layer, "support": support})
        return layer_outputs, "sequential"

    def process_query(self, user_query: str) -> dict[str, Any]:
        parsed = parse_user_query(user_query, self.ai_client)
        intent = parsed.get("intent")
        entities = parsed.get("entities", {})
        query_type = parsed.get("query_type")

        if intent == "chitchat":
            return {
                "intent": intent,
                "answer_markdown": "我是维保助手，可以帮你做故障诊断、故障统计和责任归属查询。",
                "details": {},
                "parsed": parsed,
            }

        if intent == "error":
            return {
                "intent": intent,
                "answer_markdown": f"问题解析失败：{parsed.get('error_message', '未知错误')}",
                "details": {},
                "parsed": parsed,
            }

        if intent == "statistics":
            payload = self.api_client.run_statistics(entities=entities, query_type=query_type or "count")
            return {
                "intent": intent,
                "answer_markdown": payload.get("summary_markdown", "统计完成。"),
                "details": payload,
                "parsed": parsed,
            }

        if intent == "responsibility":
            payload = self.api_client.run_responsibility(entities=entities)
            return {
                "intent": intent,
                "answer_markdown": _clean_responsibility_answer(payload.get("answer_markdown", "查询完成。"), entities),
                "details": payload,
                "parsed": parsed,
            }

        retrieval_plan = build_retrieval_plan(user_query, parsed, self.ai_client) if self.settings.planner_enabled else {
            "mode": query_type or intent,
            "main_scene": entities,
            "exact_fault_terms": split_fault_terms(_safe_text(entities.get("fault_phenomenon"))),
            "neighbor_fault_terms": [],
            "mechanism_terms": [],
            "device_aliases": [],
            "layers": [],
            "planner_source": "disabled",
            "notes": "",
        }
        layer_outputs, execution_mode = self._execute_layered_support(user_query, retrieval_plan)
        case_pool = _prepare_case_pool(layer_outputs)
        case_groups, rerank_applied = _prepare_case_groups(
            case_pool=case_pool,
            entities=entities,
            retrieval_plan=retrieval_plan,
            user_query=user_query,
            ai_client=self.ai_client,
            query_type=query_type,
        )

        primary_support = layer_outputs[0]["support"] if layer_outputs else {}
        primary_analytics = primary_support.get("analytics", {})
        station_history = _aggregate_station_history(layer_outputs)
        answer_analytics = _prepare_answer_analytics(
            primary_analytics=primary_analytics,
            case_groups=case_groups,
            entities=entities,
            retrieval_plan=retrieval_plan,
            station_history=station_history,
            query_type=query_type,
        )
        quoted_cases = case_groups["最终引用案例"]

        knowledge_specialty = (
            _safe_text(quoted_cases.iloc[0].get("SPECIALTY")) if not quoted_cases.empty else _safe_text(entities.get("specialty"))
        )
        knowledge_result = _query_knowledge_base(self.settings, knowledge_specialty)

        if query_type == "history":
            prompt = _build_history_prompt(
                user_query=user_query,
                entities=entities,
                retrieval_plan=retrieval_plan,
                analytics=answer_analytics,
                case_groups=case_groups,
            )
        else:
            prompt = _build_diagnosis_prompt(
                user_query=user_query,
                entities=entities,
                retrieval_plan=retrieval_plan,
                analytics=answer_analytics,
                case_groups=case_groups,
                knowledge_result=knowledge_result,
            )
        answer = self.ai_client.call_llm_text(
            prompt=prompt,
            temperature=0.2,
            timeout=90,
            max_completion_tokens=4096,
            enable_thinking=False,
        )

        layer_summaries = []
        for layer_output in layer_outputs:
            layer = layer_output["layer"]
            support = layer_output["support"]
            layer_summaries.append(
                {
                    "layer_id": layer["layer_id"],
                    "label": layer["label"],
                    "bucket": layer["bucket"],
                    "evidence_level": _evidence_to_cn(layer["evidence_level"]),
                    "priority": layer["priority"],
                    "case_count": len(support.get("cases", []) or []),
                    "station_history_count": len(support.get("analytics", {}).get("station_history", []) or []),
                }
            )

        metadata = _aggregate_support_metadata(layer_outputs)
        return {
            "intent": "diagnosis",
            "answer_markdown": answer,
            "details": {
                "user_query": user_query,
                "entities": entities,
                "analytics": answer_analytics,
                "server_analytics": primary_analytics,
                "top_cases": _frame_to_records(quoted_cases),
                "direct_cases": _frame_to_records(case_groups["直接相关案例"]),
                "station_cases": _frame_to_records(case_groups["本站历史案例"]),
                "line_cases": _frame_to_records(case_groups["同线同类案例"]),
                "supplemental_cases": _frame_to_records(case_groups["补充参考案例"]),
                "retrieval_plan": retrieval_plan,
                "retrieval_layers": layer_summaries,
                "planner_source": retrieval_plan.get("planner_source"),
                "execution_mode": execution_mode,
                "rerank_applied": rerank_applied,
                "knowledge_result": knowledge_result,
                "count": len(case_pool),
                "cases": _frame_to_records(case_pool),
                **metadata,
            },
            "parsed": parsed,
        }
