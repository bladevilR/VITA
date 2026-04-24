from __future__ import annotations

import json
import sys
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


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _rows_text(rows: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for row in rows:
        parts.extend(
            [
                _normalize_text(row.get("TICKETID")),
                _normalize_text(row.get("STATIONNAME")),
                _normalize_text(row.get("SPECIALTY")),
                _normalize_text(row.get("DESCRIPTION")),
                _normalize_text(row.get("SOLUTION")),
            ]
        )
    return " ".join(parts)


def _check_case(engine: WorkstationEngine, case: dict[str, object]) -> list[str]:
    errors: list[str] = []
    query = str(case["query"])
    response = engine.process_query(query)
    parsed = response.get("parsed", {})
    details = response.get("details", {})
    entities = parsed.get("entities", {}) or {}

    if response.get("intent") != case.get("expected_intent"):
        errors.append(f"intent={response.get('intent')}，期望 {case.get('expected_intent')}")

    if case.get("expected_query_type") and parsed.get("query_type") != case.get("expected_query_type"):
        errors.append(f"query_type={parsed.get('query_type')}，期望 {case.get('expected_query_type')}")

    if case.get("expected_device") and _normalize_text(entities.get("device")) != case.get("expected_device"):
        errors.append(f"device={entities.get('device')}，期望 {case.get('expected_device')}")

    if case.get("expected_specialty") and _normalize_text(entities.get("specialty")) != case.get("expected_specialty"):
        errors.append(f"specialty={entities.get('specialty')}，期望 {case.get('expected_specialty')}")

    if case.get("expected_fault") and case.get("expected_fault") not in _normalize_text(entities.get("fault_phenomenon")):
        errors.append(f"fault={entities.get('fault_phenomenon')}，期望包含 {case.get('expected_fault')}")

    direct_cases = details.get("direct_cases", []) or []
    station_cases = details.get("station_cases", []) or []
    top_cases = details.get("top_cases", []) or []
    combined_text = _rows_text(top_cases or station_cases or direct_cases)

    if len(direct_cases) < int(case.get("min_direct_cases", 0)):
        errors.append(f"direct_cases={len(direct_cases)}，低于期望 {case.get('min_direct_cases')}")

    if len(station_cases) < int(case.get("min_station_cases", 0)):
        errors.append(f"station_cases={len(station_cases)}，低于期望 {case.get('min_station_cases')}")

    if "max_direct_cases" in case and len(direct_cases) > int(case["max_direct_cases"]):
        errors.append(f"direct_cases={len(direct_cases)}，高于允许值 {case['max_direct_cases']}")

    for term in case.get("required_terms", []):
        if term not in combined_text:
            errors.append(f"结果中未命中关键字 {term}")

    for term in case.get("forbidden_terms", []):
        if term in combined_text:
            errors.append(f"结果中出现不应优先命中的词 {term}")

    return errors


def main() -> int:
    engine = WorkstationEngine()
    all_ok = True

    print("VITA 故障诊断工作流自测")
    print("=" * 80)

    for case in TEST_CASES:
        errors = _check_case(engine, case)
        if errors:
            all_ok = False
            print(f"[失败] {case['name']}")
            for item in errors:
                print(f"  - {item}")
        else:
            print(f"[通过] {case['name']}")

    print("=" * 80)
    print("结果：通过" if all_ok else "结果：失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
