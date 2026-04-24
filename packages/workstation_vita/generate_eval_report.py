from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
VENDOR_DIR = ROOT / "vendor"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from workstation_vita.engine import WorkstationEngine  # noqa: E402


TEST_CASES = json.loads((ROOT / "diagnosis_eval_cases.json").read_text(encoding="utf-8"))
REPORT_PATH = ROOT / "DIAGNOSIS_EVAL_REPORT.md"


def _normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _rows_text(rows: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for row in rows:
        chunks.extend(
            [
                _normalize(row.get("TICKETID")),
                _normalize(row.get("STATIONNAME")),
                _normalize(row.get("SPECIALTY")),
                _normalize(row.get("DESCRIPTION")),
                _normalize(row.get("SOLUTION")),
            ]
        )
    return " ".join(chunks)


def _check_case(engine: WorkstationEngine, case: dict[str, object]) -> dict[str, object]:
    query = str(case["query"])
    response = engine.process_query(query)
    parsed = response.get("parsed", {})
    details = response.get("details", {})
    entities = parsed.get("entities", {}) or {}
    direct_cases = details.get("direct_cases", []) or []
    station_cases = details.get("station_cases", []) or []
    top_cases = details.get("top_cases", []) or []
    combined_text = _rows_text(top_cases or station_cases or direct_cases)

    errors: list[str] = []
    if response.get("intent") != case.get("expected_intent"):
        errors.append(f"意图识别为 {response.get('intent')}，期望 {case.get('expected_intent')}")

    expected_query_type = case.get("expected_query_type")
    if expected_query_type and parsed.get("query_type") != expected_query_type:
        errors.append(f"查询类型为 {parsed.get('query_type')}，期望 {expected_query_type}")

    expected_device = case.get("expected_device")
    if expected_device and _normalize(entities.get("device")) != expected_device:
        errors.append(f"设备识别为 {entities.get('device')}，期望 {expected_device}")

    expected_specialty = case.get("expected_specialty")
    if expected_specialty and _normalize(entities.get("specialty")) != expected_specialty:
        errors.append(f"专业识别为 {entities.get('specialty')}，期望 {expected_specialty}")

    expected_fault = case.get("expected_fault")
    if expected_fault and expected_fault not in _normalize(entities.get("fault_phenomenon")):
        errors.append(f"现象识别为 {entities.get('fault_phenomenon')}，期望包含 {expected_fault}")

    min_direct_cases = int(case.get("min_direct_cases", 0))
    if len(direct_cases) < min_direct_cases:
        errors.append(f"直接相关案例仅 {len(direct_cases)} 条，低于期望 {min_direct_cases} 条")

    min_station_cases = int(case.get("min_station_cases", 0))
    if len(station_cases) < min_station_cases:
        errors.append(f"本站历史案例仅 {len(station_cases)} 条，低于期望 {min_station_cases} 条")

    if "max_direct_cases" in case and len(direct_cases) > int(case["max_direct_cases"]):
        errors.append(f"直接相关案例 {len(direct_cases)} 条，高于允许值 {case['max_direct_cases']} 条")

    for term in case.get("required_terms", []):
        if term not in combined_text:
            errors.append(f"结果中未命中关键字：{term}")

    for term in case.get("forbidden_terms", []):
        if term in combined_text:
            errors.append(f"结果中出现不应优先命中的词：{term}")

    answer = _normalize(response.get("answer_markdown")).strip()
    answer_preview = answer[:300] + ("..." if len(answer) > 300 else "")
    return {
        "name": case["name"],
        "query": query,
        "passed": not errors,
        "errors": errors,
        "execution_mode": details.get("execution_mode"),
        "direct_cases": len(direct_cases),
        "station_cases": len(station_cases),
        "top_cases": len(top_cases),
        "answer_preview": answer_preview,
    }


def main() -> int:
    engine = WorkstationEngine()
    results = [_check_case(engine, case) for case in TEST_CASES]
    passed_count = sum(1 for item in results if item["passed"])
    total_count = len(results)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# 故障诊断验收报告",
        "",
        f"- 生成时间：{generated_at}",
        f"- 总用例数：{total_count}",
        f"- 通过数：{passed_count}",
        f"- 失败数：{total_count - passed_count}",
        "",
    ]

    for item in results:
        status = "通过" if item["passed"] else "失败"
        lines.extend(
            [
                f"## {item['name']} [{status}]",
                "",
                f"- 提问：{item['query']}",
                f"- 执行模式：{item['execution_mode'] or '未知'}",
                f"- 直接相关案例：{item['direct_cases']}",
                f"- 本站历史案例：{item['station_cases']}",
                f"- 最终引用案例：{item['top_cases']}",
                "",
                "答案摘要：",
                "",
                item["answer_preview"] or "无",
                "",
            ]
        )
        if item["errors"]:
            lines.append("问题：")
            lines.append("")
            for error in item["errors"]:
                lines.append(f"- {error}")
            lines.append("")

    REPORT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"验收报告已生成：{REPORT_PATH}")
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
