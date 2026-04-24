from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
VENDOR_DIR = ROOT / "vendor"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from workstation_vita.engine import WorkstationEngine  # noqa: E402


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _rows_text(rows: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for row in rows:
        parts.extend(
            [
                _text(row.get("TICKETID")),
                _text(row.get("REPORTDATE")),
                _text(row.get("LINENUM")),
                _text(row.get("STATIONNAME")),
                _text(row.get("SPECIALTY")),
                _text(row.get("DESCRIPTION")),
                _text(row.get("SOLUTION")),
                _text(row.get("FAULT_CAUSE")),
                _text(row.get("FAILURECODE")),
                _text(row.get("PROBLEMCODE")),
                _text(row.get("ASSETNUM")),
            ]
        )
    return " ".join(parts)


def _preview(text: str, limit: int = 320) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _combined_text(response: dict[str, Any]) -> str:
    details = response.get("details", {}) or {}
    rows: list[dict[str, object]] = []
    for key in ("top_cases", "direct_cases", "station_cases", "line_cases", "supplemental_cases", "rows"):
        rows.extend(details.get(key, []) or [])
    answer = _text(response.get("answer_markdown"))
    return f"{answer}\n{_rows_text(rows)}"


def _check_case(case: dict[str, Any], response: dict[str, Any], seconds: float) -> dict[str, Any]:
    parsed = response.get("parsed", {}) or {}
    entities = parsed.get("entities", {}) or {}
    details = response.get("details", {}) or {}
    direct_cases = details.get("direct_cases", []) or []
    station_cases = details.get("station_cases", []) or []
    line_cases = details.get("line_cases", []) or []
    top_cases = details.get("top_cases", []) or []
    combined = _combined_text(response)
    errors: list[str] = []

    if response.get("intent") != case.get("expected_intent"):
        errors.append(f"意图识别为 {response.get('intent')}，期望 {case.get('expected_intent')}")

    expected_query_type = case.get("expected_query_type")
    if expected_query_type and parsed.get("query_type") != expected_query_type:
        errors.append(f"查询类型为 {parsed.get('query_type')}，期望 {expected_query_type}")

    expected_compare_dimension = case.get("expected_compare_dimension")
    if expected_compare_dimension and parsed.get("compare_dimension") != expected_compare_dimension:
        errors.append(f"比较维度为 {parsed.get('compare_dimension')}，期望 {expected_compare_dimension}")
    if expected_compare_dimension and not case.get("expected_station") and _text(entities.get("station_name")):
        errors.append(f"比较类问题不应识别出具体车站，但当前识别为 {entities.get('station_name')}")

    expected_line = case.get("expected_line")
    if expected_line and _text(entities.get("line_num")) != expected_line:
        errors.append(f"线路识别为 {entities.get('line_num')}，期望 {expected_line}")

    expected_station = case.get("expected_station")
    if expected_station and _text(entities.get("station_name")) != expected_station:
        errors.append(f"车站识别为 {entities.get('station_name')}，期望 {expected_station}")

    expected_specialty = case.get("expected_specialty")
    if expected_specialty and _text(entities.get("specialty")) != expected_specialty:
        errors.append(f"专业识别为 {entities.get('specialty')}，期望 {expected_specialty}")

    expected_device_contains = case.get("expected_device_contains")
    if expected_device_contains and expected_device_contains not in _text(entities.get("device")):
        errors.append(f"设备识别为 {entities.get('device')}，期望包含 {expected_device_contains}")

    expected_fault_contains = case.get("expected_fault_contains")
    if expected_fault_contains and expected_fault_contains not in _text(entities.get("fault_phenomenon")):
        errors.append(f"现象识别为 {entities.get('fault_phenomenon')}，期望包含 {expected_fault_contains}")

    min_direct_cases = int(case.get("min_direct_cases", 0))
    if len(direct_cases) < min_direct_cases:
        errors.append(f"直接相关案例 {len(direct_cases)} 条，低于期望 {min_direct_cases} 条")

    min_station_cases = int(case.get("min_station_cases", 0))
    if len(station_cases) < min_station_cases:
        errors.append(f"本站历史案例 {len(station_cases)} 条，低于期望 {min_station_cases} 条")

    if "max_direct_cases" in case and len(direct_cases) > int(case["max_direct_cases"]):
        errors.append(f"直接相关案例 {len(direct_cases)} 条，高于允许值 {case['max_direct_cases']} 条")

    for term in case.get("required_terms", []):
        if term not in combined:
            errors.append(f"答案和案例中未命中关键字：{term}")

    for term in case.get("forbidden_terms", []):
        if term in combined:
            errors.append(f"答案和案例中出现不应优先命中的词：{term}")

    answer_text = _text(response.get("answer_markdown"))
    for term in case.get("answer_required_terms", []):
        if term not in answer_text:
            errors.append(f"答案中未命中关键字：{term}")

    for term in case.get("answer_forbidden_terms", []):
        if term in answer_text:
            errors.append(f"答案中出现不应出现的内容：{term}")

    if "????" in answer_text or "乱码" in answer_text:
        errors.append("答案中出现乱码痕迹")

    return {
        "id": case["id"],
        "persona": case["persona"],
        "category": case["category"],
        "query": case["query"],
        "passed": not errors,
        "errors": errors,
        "seconds": round(seconds, 2),
        "intent": response.get("intent"),
        "query_type": parsed.get("query_type"),
        "compare_dimension": parsed.get("compare_dimension"),
        "entities": entities,
        "execution_mode": details.get("execution_mode"),
        "direct_cases": len(direct_cases),
        "station_cases": len(station_cases),
        "line_cases": len(line_cases),
        "top_cases": len(top_cases),
        "answer_preview": _preview(answer_text),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行真实用户问法回归")
    parser.add_argument("--cases", required=True, help="用例 JSON 路径")
    parser.add_argument("--report", required=True, help="输出 Markdown 报告路径")
    parser.add_argument("--results", required=True, help="输出 JSON 明细路径")
    parser.add_argument("--title", default="真实用户问法回归报告", help="报告标题")
    args = parser.parse_args()

    case_path = Path(args.cases).resolve()
    report_path = Path(args.report).resolve()
    results_path = Path(args.results).resolve()
    cases = json.loads(case_path.read_text(encoding="utf-8"))

    engine = WorkstationEngine()
    results: list[dict[str, Any]] = []
    started_at = datetime.now()

    print(f"开始跑 {len(cases)} 条真实用户问法回归，时间：{started_at:%Y-%m-%d %H:%M:%S}")
    for index, case in enumerate(cases, start=1):
        print(f"[{index:02d}/{len(cases)}] {case['id']} {case['query']}")
        t0 = time.time()
        response = engine.process_query(case["query"])
        results.append(_check_case(case, response, time.time() - t0))

    ended_at = datetime.now()
    passed_count = sum(1 for item in results if item["passed"])
    failed = [item for item in results if not item["passed"]]
    category_counter = Counter(item["category"] for item in results)
    failed_category_counter = Counter(item["category"] for item in failed)
    persona_counter = Counter(item["persona"] for item in results)
    avg_seconds = round(sum(item["seconds"] for item in results) / max(len(results), 1), 2)
    max_seconds = max(item["seconds"] for item in results)

    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# {args.title}",
        "",
        f"- 开始时间：{started_at:%Y-%m-%d %H:%M:%S}",
        f"- 结束时间：{ended_at:%Y-%m-%d %H:%M:%S}",
        f"- 总问题数：{len(results)}",
        f"- 通过数：{passed_count}",
        f"- 失败数：{len(failed)}",
        f"- 平均耗时：{avg_seconds} 秒",
        f"- 最长耗时：{max_seconds} 秒",
        "",
        "## 类别分布",
        "",
    ]

    for category, count in sorted(category_counter.items()):
        lines.append(f"- {category}：{count} 条，失败 {failed_category_counter.get(category, 0)} 条")

    lines.extend(["", "## 角色分布", ""])
    for persona, count in sorted(persona_counter.items()):
        lines.append(f"- {persona}：{count} 条")

    lines.extend(["", "## 失败问题", ""])
    if not failed:
        lines.append("- 无")
    else:
        for item in failed:
            lines.extend(
                [
                    f"### {item['id']} {item['query']}",
                    "",
                    f"- 角色：{item['persona']}",
                    f"- 类别：{item['category']}",
                    f"- 耗时：{item['seconds']} 秒",
                    f"- 意图：{item['intent']}",
                    f"- 查询类型：{item['query_type']}",
                    f"- 比较维度：{item['compare_dimension']}",
                    f"- 解析结果：{json.dumps(item['entities'], ensure_ascii=False)}",
                    f"- 执行模式：{item['execution_mode']}",
                    f"- 直接相关案例：{item['direct_cases']}",
                    f"- 本站历史案例：{item['station_cases']}",
                    f"- 同线同类案例：{item['line_cases']}",
                    f"- 最终引用案例：{item['top_cases']}",
                    "",
                    "问题：",
                    "",
                ]
            )
            for error in item["errors"]:
                lines.append(f"- {error}")
            lines.extend(["", "答案摘要：", "", item["answer_preview"], ""])

    lines.extend(["## 全量结果摘要", ""])
    for item in results:
        status = "通过" if item["passed"] else "失败"
        lines.extend(
            [
                f"### {item['id']} [{status}] {item['query']}",
                "",
                f"- 角色：{item['persona']}",
                f"- 类别：{item['category']}",
                f"- 耗时：{item['seconds']} 秒",
                f"- 意图：{item['intent']}",
                f"- 查询类型：{item['query_type']}",
                f"- 比较维度：{item['compare_dimension']}",
                f"- 解析结果：{json.dumps(item['entities'], ensure_ascii=False)}",
                f"- 执行模式：{item['execution_mode']}",
                f"- 直接相关案例：{item['direct_cases']}",
                f"- 本站历史案例：{item['station_cases']}",
                f"- 同线同类案例：{item['line_cases']}",
                f"- 最终引用案例：{item['top_cases']}",
                "",
                "答案摘要：",
                "",
                item["answer_preview"] or "无",
                "",
            ]
        )
        if item["errors"]:
            lines.append("校验问题：")
            lines.append("")
            for error in item["errors"]:
                lines.append(f"- {error}")
            lines.append("")

    report_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"回归报告已生成：{report_path}")
    print(f"结果明细已生成：{results_path}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
