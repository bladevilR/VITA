from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from .ai_clients import AIClient
from .phenomenon_rules import get_mechanism_terms, get_neighbor_terms, split_fault_terms
from .text_utils import expand_specialty_synonyms, infer_specialty_from_text, normalize_text


logger = logging.getLogger("workstation_vita.retrieval_planner")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = normalize_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _copy_entities(base_entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    cloned = {
        "line_num": base_entities.get("line_num"),
        "station_name": base_entities.get("station_name"),
        "specialty": base_entities.get("specialty"),
        "device": base_entities.get("device"),
        "fault_phenomenon": base_entities.get("fault_phenomenon"),
        "time_range": base_entities.get("time_range"),
    }
    cloned.update(overrides)
    return cloned


def _device_aliases(entities: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    device = _safe_text(entities.get("device"))
    specialty = _safe_text(entities.get("specialty"))

    if device:
        aliases.append(device)
        compact = device.replace("综合监控", "").replace("设备", "").strip()
        if compact and compact != device:
            aliases.append(compact)
    if specialty:
        aliases.extend(expand_specialty_synonyms(specialty))
    return _dedupe(aliases)[:8]


def _build_layer(
    layer_id: str,
    label: str,
    bucket: str,
    evidence_level: str,
    priority: int,
    entities: dict[str, Any],
    use_vector: bool,
    must_match_fault: bool = False,
    must_match_device: bool = False,
) -> dict[str, Any]:
    return {
        "layer_id": layer_id,
        "label": label,
        "bucket": bucket,
        "evidence_level": evidence_level,
        "priority": priority,
        "entities": entities,
        "use_vector": use_vector,
        "must_match_fault": must_match_fault,
        "must_match_device": must_match_device,
    }


def _build_default_layers(parsed: dict[str, Any], main_fault_terms: list[str], neighbor_fault_terms: list[str]) -> list[dict[str, Any]]:
    entities = deepcopy(parsed.get("entities", {}) or {})
    query_type = parsed.get("query_type")
    layers: list[dict[str, Any]] = []
    station_name = _safe_text(entities.get("station_name"))
    line_num = _safe_text(entities.get("line_num"))
    specialty = _safe_text(entities.get("specialty"))
    device = _safe_text(entities.get("device"))
    fault = _safe_text(entities.get("fault_phenomenon"))
    has_specific_device = bool(device and device != specialty)

    if query_type == "history":
        if station_name and device:
            layers.append(
                _build_layer(
                    "station_same_device",
                    "本站同设备历史",
                    "station",
                    "history",
                    1,
                    _copy_entities(entities, fault_phenomenon=None, time_range=None),
                    use_vector=False,
                    must_match_device=True,
                )
            )
        if station_name and specialty:
            layers.append(
                _build_layer(
                    "station_same_specialty",
                    "本站同专业历史",
                    "station",
                    "history",
                    2,
                    _copy_entities(entities, device=None, fault_phenomenon=None, time_range=None),
                    use_vector=False,
                )
            )
        if device:
            layers.append(
                _build_layer(
                    "peer_same_device",
                    "同类设备历史",
                    "supplemental",
                    "indirect",
                    3,
                    _copy_entities(entities, station_name=None, line_num=None, fault_phenomenon=None, time_range=None),
                    use_vector=not has_specific_device,
                    must_match_device=has_specific_device,
                )
            )
        return layers

    if fault or device or specialty:
        layers.append(
            _build_layer(
                "direct_exact",
                "直接匹配",
                "direct",
                "direct",
                1,
                _copy_entities(entities),
                use_vector=not (fault or has_specific_device),
                must_match_fault=bool(main_fault_terms),
                must_match_device=has_specific_device,
            )
        )

    if station_name and device:
        layers.append(
            _build_layer(
                "station_same_device",
                "本站同设备历史",
                "station",
                "history",
                2,
                _copy_entities(entities, fault_phenomenon=None, time_range=None),
                use_vector=False,
                must_match_device=has_specific_device,
            )
        )

    if station_name and specialty:
        layers.append(
            _build_layer(
                "station_same_specialty",
                "本站同专业历史",
                "station",
                "history",
                3,
                _copy_entities(entities, device=None if has_specific_device else entities.get("device"), fault_phenomenon=None, time_range=None),
                use_vector=False,
            )
        )

    if line_num and (fault or device or specialty):
        layers.append(
            _build_layer(
                "line_same_fault",
                "同线同类案例",
                "line",
                "indirect",
                4,
                _copy_entities(entities, station_name=None, time_range=None),
                use_vector=False,
                must_match_fault=bool(main_fault_terms),
                must_match_device=has_specific_device,
            )
        )

    if has_specific_device or fault:
        layers.append(
            _build_layer(
                "peer_same_device_fault",
                "同类设备同现象",
                "supplemental",
                "indirect",
                5,
                _copy_entities(entities, station_name=None, line_num=None, time_range=None),
                use_vector=True,
                must_match_fault=bool(main_fault_terms),
                must_match_device=has_specific_device,
            )
        )

    if neighbor_fault_terms:
        layers.append(
            _build_layer(
                "peer_neighbor_fault",
                "相近现象参考",
                "supplemental",
                "weak",
                6,
                _copy_entities(
                    entities,
                    station_name=None,
                    line_num=None,
                    fault_phenomenon=" ".join(neighbor_fault_terms[:4]),
                    time_range=None,
                ),
                use_vector=True,
                must_match_fault=False,
                must_match_device=has_specific_device,
            )
        )

    if specialty:
        layers.append(
            _build_layer(
                "general_specialty",
                "同专业补充参考",
                "supplemental",
                "weak",
                7,
                _copy_entities(entities, station_name=None, line_num=None, device=None, fault_phenomenon=None, time_range=None),
                use_vector=True,
            )
        )

    return layers


def _planner_prompt(user_query: str, parsed: dict[str, Any], default_plan: dict[str, Any]) -> str:
    compact_plan = {
        "mode": default_plan["mode"],
        "main_scene": default_plan["main_scene"],
        "exact_fault_terms": default_plan["exact_fault_terms"],
        "neighbor_fault_terms": default_plan["neighbor_fault_terms"],
        "device_aliases": default_plan["device_aliases"],
        "layers": [
            {
                "layer_id": layer["layer_id"],
                "label": layer["label"],
                "priority": layer["priority"],
            }
            for layer in default_plan["layers"]
        ],
    }
    return f"""你是地铁运维检索规划器。你的任务不是直接回答故障，而是把用户问题转成更合理的检索计划。

要求：
1. 保留原始故障现象，不要把黑屏、白屏、死机、离线硬合并成一个词。
2. 可以补充“相近现象”，但只能用于弱参考。
3. 只返回 JSON，不要解释。
4. exact_fault_terms 只能放最直接的故障现象。
5. neighbor_fault_terms 只能放相近现象，数量不超过 4 个。
6. layers 只允许调整优先级或删除明显不需要的层，不要发明新层。

当前用户问题：
{user_query}

当前解析结果：
{json.dumps(parsed, ensure_ascii=False)}

当前默认计划：
{json.dumps(compact_plan, ensure_ascii=False)}

返回格式：
{{
  "exact_fault_terms": ["黑屏"],
  "neighbor_fault_terms": ["无显示", "显示异常"],
  "device_aliases": ["综合监控工作站", "工作站"],
  "drop_layers": ["general_specialty"],
  "priority_adjustments": {{
    "station_same_device": 1,
    "direct_exact": 2
  }},
  "notes": "可为空"
}}
"""


def _merge_plan(default_plan: dict[str, Any], llm_output: dict[str, Any]) -> dict[str, Any]:
    plan = deepcopy(default_plan)

    if isinstance(llm_output.get("exact_fault_terms"), list):
        exact_terms = _dedupe([str(item) for item in llm_output["exact_fault_terms"] if item])
        if exact_terms:
            plan["exact_fault_terms"] = exact_terms[:4]

    if isinstance(llm_output.get("neighbor_fault_terms"), list):
        neighbor_terms = _dedupe([str(item) for item in llm_output["neighbor_fault_terms"] if item])
        if neighbor_terms:
            plan["neighbor_fault_terms"] = neighbor_terms[:4]

    if isinstance(llm_output.get("device_aliases"), list):
        aliases = _dedupe([str(item) for item in llm_output["device_aliases"] if item])
        if aliases:
            plan["device_aliases"] = aliases[:8]

    drop_layers = set()
    if isinstance(llm_output.get("drop_layers"), list):
        drop_layers = {str(item) for item in llm_output["drop_layers"] if item}

    priority_adjustments = llm_output.get("priority_adjustments", {})
    layers: list[dict[str, Any]] = []
    for layer in plan["layers"]:
        if layer["layer_id"] in drop_layers:
            continue
        if isinstance(priority_adjustments, dict) and layer["layer_id"] in priority_adjustments:
            try:
                layer["priority"] = int(priority_adjustments[layer["layer_id"]])
            except Exception:  # noqa: BLE001
                pass
        layers.append(layer)
    layers.sort(key=lambda item: (int(item.get("priority", 99)), item["layer_id"]))
    for index, layer in enumerate(layers, start=1):
        layer["priority"] = index
    plan["layers"] = layers
    plan["planner_source"] = "llm_refined"
    plan["notes"] = _safe_text(llm_output.get("notes"))
    return plan


def build_retrieval_plan(user_query: str, parsed: dict[str, Any], ai_client: AIClient) -> dict[str, Any]:
    entities = deepcopy(parsed.get("entities", {}) or {})
    fault = _safe_text(entities.get("fault_phenomenon"))
    exact_fault_terms = split_fault_terms(fault)
    neighbor_fault_terms = get_neighbor_terms(fault)
    mechanism_terms = get_mechanism_terms(fault)
    plan = {
        "mode": parsed.get("query_type") or parsed.get("intent") or "diagnosis",
        "main_scene": entities,
        "exact_fault_terms": exact_fault_terms,
        "neighbor_fault_terms": neighbor_fault_terms,
        "mechanism_terms": mechanism_terms,
        "device_aliases": _device_aliases(entities),
        "layers": _build_default_layers(parsed, exact_fault_terms, neighbor_fault_terms),
        "planner_source": "heuristic",
        "notes": "",
    }

    if parsed.get("intent") != "diagnosis":
        return plan

    planner_entities = entities
    use_llm = bool(_safe_text(planner_entities.get("fault_phenomenon")) or _safe_text(planner_entities.get("device")))
    if not use_llm:
        return plan

    try:
        llm_output = ai_client.call_llm_json(prompt=_planner_prompt(user_query, parsed, plan), temperature=0.0, timeout=45)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval planner fallback to heuristic: %s", exc)
        return plan

    try:
        merged = _merge_plan(plan, llm_output)
        if not merged["exact_fault_terms"] and plan["exact_fault_terms"]:
            merged["exact_fault_terms"] = plan["exact_fault_terms"]
        if not merged["neighbor_fault_terms"]:
            merged["neighbor_fault_terms"] = plan["neighbor_fault_terms"]
        if not merged["device_aliases"]:
            merged["device_aliases"] = plan["device_aliases"]
        return merged
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval planner merge failed: %s", exc)
        return plan
