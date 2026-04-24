from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import pandas as pd

from .config import get_settings
from .db import DatabaseManager
from .text_utils import expand_specialty_synonyms, extract_fault_cause, normalize_specialty, normalize_text


logger = logging.getLogger("server_maximo.services")


def reciprocal_rank_fusion(results_lists: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for results in results_lists:
        for rank, doc_id in enumerate(results):
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.keys(), key=lambda item: scores[item], reverse=True)


def _entities_to_dict(entities: Any) -> dict[str, Any]:
    if hasattr(entities, "model_dump"):
        data = entities.model_dump()
    elif isinstance(entities, dict):
        data = dict(entities)
    else:
        raise TypeError("不支持的实体参数格式")

    if isinstance(data.get("time_range"), dict) and not any(data["time_range"].values()):
        data["time_range"] = None

    if data.get("station_name"):
        data["station_name"] = normalize_text(data["station_name"])
    if data.get("specialty"):
        data["specialty"] = normalize_specialty(data["specialty"])
    if data.get("device"):
        data["device"] = normalize_text(data["device"])
    if data.get("fault_phenomenon"):
        data["fault_phenomenon"] = normalize_text(data["fault_phenomenon"])
    return data


def _serialize_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    safe_df = df.copy()
    for column in safe_df.columns:
        if pd.api.types.is_datetime64_any_dtype(safe_df[column]):
            safe_df[column] = safe_df[column].dt.strftime("%Y-%m-%d %H:%M:%S")
    safe_df = safe_df.where(pd.notna(safe_df), None)
    return safe_df.to_dict(orient="records")


def _split_query_terms(value: str) -> list[str]:
    normalized = normalize_text(value or "")
    if not normalized:
        return []

    terms: list[str] = []
    for item in [normalized, *re.findall(r"[A-Za-z0-9\u4e00-\u9fa5]{2,12}", normalized)]:
        item = item.strip()
        if len(item) < 2:
            continue
        if item not in terms:
            terms.append(item)
    return terms[:4]


def _build_text_search_conditions(
    search_value: str,
    fields: list[str],
    params: dict[str, Any],
    prefix: str,
    param_counter: int,
) -> tuple[str | None, int]:
    terms = _split_query_terms(search_value)
    if not terms:
        return None, param_counter

    term_clauses: list[str] = []
    for term in terms:
        param_name = f"{prefix}_{param_counter}"
        params[param_name] = f"%{DatabaseManager.sanitize_input(term)}%"
        param_counter += 1
        field_clauses = [f"UPPER(COALESCE({field}, '')) LIKE UPPER(:{param_name})" for field in fields]
        term_clauses.append(f"({' OR '.join(field_clauses)})")
    return f"({' AND '.join(term_clauses)})", param_counter


def build_sql_conditions_from_entities(entities: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}
    param_counter = 0

    line_num = entities.get("line_num")
    if line_num:
        line_nums = [DatabaseManager.sanitize_input(item.strip()) for item in str(line_num).split(",") if item.strip()]
        if len(line_nums) == 1:
            param_name = f"line_num_{param_counter}"
            conditions.append(f"SR.LINENUM = :{param_name}")
            params[param_name] = line_nums[0]
            param_counter += 1
        elif line_nums:
            placeholders: list[str] = []
            for line_value in line_nums:
                param_name = f"line_num_{param_counter}"
                placeholders.append(f":{param_name}")
                params[param_name] = line_value
                param_counter += 1
            conditions.append(f"SR.LINENUM IN ({', '.join(placeholders)})")

    station_name = entities.get("station_name")
    if station_name:
        station = DatabaseManager.sanitize_input(station_name)
        param_name = f"station_{param_counter}"
        conditions.append(f"UPPER(SR.STATIONNAME) LIKE UPPER(:{param_name})")
        params[param_name] = f"%{station}%"
        param_counter += 1

    specialty = entities.get("specialty")
    if specialty:
        synonyms = expand_specialty_synonyms(specialty)[:10]
        specialty_conditions: list[str] = []
        for synonym in synonyms:
            param_name = f"specialty_{param_counter}"
            specialty_conditions.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:{param_name})")
            params[param_name] = f"%{DatabaseManager.sanitize_input(synonym)}%"
            param_counter += 1
        if specialty_conditions:
            conditions.append(f"({' OR '.join(specialty_conditions)})")

    device = entities.get("device")
    if device and normalize_text(str(device)) != normalize_text(str(specialty or "")):
        clause, param_counter = _build_text_search_conditions(
            str(device),
            ["SR.ASSETNUM", "SR.FAILURECODE", "SR.DESCRIPTION", "SR.LONGDESCRIPTION", "SR.SOLUTION", "SR.PROCREMEDY"],
            params,
            "device",
            param_counter,
        )
        if clause:
            conditions.append(clause)

    fault_phenomenon = entities.get("fault_phenomenon")
    if fault_phenomenon:
        clause, param_counter = _build_text_search_conditions(
            str(fault_phenomenon),
            ["SR.PROBLEMCODE", "SR.FAILURECODE", "SR.DESCRIPTION", "SR.LONGDESCRIPTION", "SR.SOLUTION", "SR.PROCREMEDY"],
            params,
            "fault",
            param_counter,
        )
        if clause:
            conditions.append(clause)

    time_range = entities.get("time_range")
    if time_range and isinstance(time_range, dict):
        start_date = time_range.get("start_date")
        end_date = time_range.get("end_date")
        if start_date and end_date:
            try:
                datetime.strptime(start_date, "%Y-%m-%d")
                datetime.strptime(end_date, "%Y-%m-%d")
                params["start_date"] = start_date
                params["end_date"] = end_date
                conditions.append(
                    "TRUNC(SR.REPORTDATE) BETWEEN "
                    "TO_DATE(:start_date, 'YYYY-MM-DD') AND "
                    "TO_DATE(:end_date, 'YYYY-MM-DD')"
                )
            except ValueError:
                logger.warning("Invalid time range ignored: %s - %s", start_date, end_date)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return where_clause, params


def keyword_search_oracle(entities: dict[str, Any], top_k: int = 50) -> list[str]:
    if not DatabaseManager.is_available():
        return []

    device = (entities.get("device") or "").strip()
    specialty = (entities.get("specialty") or "").strip()
    phenomenon = (entities.get("fault_phenomenon") or "").strip()

    search_terms: list[str] = []
    for term in (device, specialty, phenomenon):
        if term and len(term) >= 2 and term not in search_terms:
            search_terms.append(term)
    search_terms = search_terms[:4]

    if not search_terms:
        return []

    params: dict[str, Any] = {}
    where_parts: list[str] = []
    score_parts: list[str] = []

    for index, term in enumerate(search_terms):
        params[f"kw{index}"] = term
        where_parts.append(f"INSTR(SR.DESCRIPTION, :kw{index}) > 0")
        score_parts.append(f"CASE WHEN INSTR(SR.DESCRIPTION, :kw{index}) > 0 THEN 1 ELSE 0 END")

    specialty_where = ""
    if specialty:
        spec_parts: list[str] = []
        for spec_index, synonym in enumerate(expand_specialty_synonyms(specialty)[:6]):
            params[f"spec{spec_index}"] = synonym
            spec_parts.append(f"SR.SPECIALTY = :spec{spec_index}")
        if spec_parts:
            specialty_where = f" AND ({' OR '.join(spec_parts)})"

    sql = f"""
    SELECT TICKETID FROM (
        SELECT SR.TICKETID,
               ({' + '.join(score_parts)}) AS KW_SCORE
        FROM MAXIMO.SR SR
        WHERE ({' OR '.join(where_parts)})
        {specialty_where}
          AND SR.STATUS NOT IN ('CANCELLED')
          AND LENGTH(COALESCE(SR.SOLUTION, SR.PROCREMEDY, '')) > 5
        ORDER BY KW_SCORE DESC, SR.REPORTDATE DESC
    ) WHERE ROWNUM <= {int(top_k)}
    """
    result_df = DatabaseManager.execute_query_safe(sql, params)
    if result_df.empty:
        return []
    return [str(ticket_id) for ticket_id in result_df["TICKETID"].tolist()]


def _sort_cases_by_rank(df: pd.DataFrame, ranked_ticket_ids: list[str]) -> pd.DataFrame:
    rank_map = {ticket_id: index for index, ticket_id in enumerate(ranked_ticket_ids)}
    sorted_df = df.copy()
    sorted_df["RETRIEVAL_RANK"] = sorted_df["TICKETID"].map(rank_map)
    sorted_df = sorted_df.sort_values("RETRIEVAL_RANK", ascending=True, na_position="last")
    return sorted_df.reset_index(drop=True)


def fetch_cases_by_ticket_ids(ticket_ids: list[str]) -> pd.DataFrame:
    if not ticket_ids:
        return pd.DataFrame()

    placeholders = ", ".join(f":id_{index}" for index in range(len(ticket_ids)))
    params = {f"id_{index}": ticket_id for index, ticket_id in enumerate(ticket_ids)}
    sql = f"""
    SELECT SR.TICKETID,
           SR.ASSETNUM,
           SR.LINENUM,
           SR.STATIONNAME,
           SR.DESCRIPTION,
           SR.LONGDESCRIPTION,
           SR.SPECIALTY,
           SR.REPORTDATE,
           COALESCE(SR.SOLUTION, SR.PROCREMEDY, '') AS SOLUTION,
           SR.FAILURECODE,
           SR.PROBLEMCODE
    FROM MAXIMO.SR SR
    WHERE SR.TICKETID IN ({placeholders})
    """
    result_df = DatabaseManager.execute_query_safe(sql, params)
    if result_df.empty:
        return result_df
    result_df["TICKETID"] = result_df["TICKETID"].astype(str)
    result_df["FAULT_CAUSE"] = result_df["LONGDESCRIPTION"].apply(extract_fault_cause)
    return _sort_cases_by_rank(result_df, ticket_ids)


def analyze_case_data(cases_df: pd.DataFrame, entities: dict[str, Any]) -> dict[str, Any]:
    line_num = entities.get("line_num")
    station_name = entities.get("station_name")

    result: dict[str, Any] = {
        "total_cases": 0,
        "line_cases": 0,
        "station_cases": 0,
        "solution_stats": [],
        "cause_stats": [],
        "station_history": [],
        "high_freq_stations": [],
        "specialty_distribution": {},
        "time_trend": {"recent_7d": 0, "recent_30d": 0, "prev_30d": 0, "recent_90d": 0, "trend": "持平"},
        "risk_assessment": {"level": "低", "freq_text": "", "recommendation": ""},
    }

    exact_where, exact_params = build_sql_conditions_from_entities(entities)

    hotspot_entities = dict(entities)
    hotspot_entities["station_name"] = None
    hotspot_entities["time_range"] = None
    hotspot_where, hotspot_params = build_sql_conditions_from_entities(hotspot_entities)

    station_history_entities = dict(entities)
    station_history_entities["fault_phenomenon"] = None
    station_history_entities["time_range"] = None
    station_history_where, station_history_params = build_sql_conditions_from_entities(station_history_entities)

    try:
        with DatabaseManager.get_connection() as conn:
            extra_params = dict(exact_params)
            line_case = "0"
            station_case = "0"
            if line_num:
                first_line = DatabaseManager.sanitize_input(str(line_num).split(",")[0].strip())
                extra_params["metric_line_num"] = first_line
                line_case = "CASE WHEN SR.LINENUM = :metric_line_num THEN 1 ELSE 0 END"
            if station_name:
                extra_params["metric_station_name"] = f"%{DatabaseManager.sanitize_input(station_name)}%"
                station_case = "CASE WHEN UPPER(SR.STATIONNAME) LIKE UPPER(:metric_station_name) THEN 1 ELSE 0 END"

            main_sql = f"""
            SELECT
                COUNT(*) AS TOTAL_CNT,
                SUM({line_case}) AS LINE_CNT,
                SUM({station_case}) AS STN_CNT,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 7 THEN 1 ELSE 0 END) AS D7,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 30 THEN 1 ELSE 0 END) AS D30,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 60 AND SR.REPORTDATE <= SYSDATE - 30 THEN 1 ELSE 0 END) AS PREV30,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 90 THEN 1 ELSE 0 END) AS D90
            FROM MAXIMO.SR SR
            WHERE {exact_where}
            """
            main_df = pd.read_sql(main_sql, conn, params=extra_params)
            if not main_df.empty:
                row = main_df.iloc[0]
                result["total_cases"] = int(row["TOTAL_CNT"] or 0)
                result["line_cases"] = int(row["LINE_CNT"] or 0)
                result["station_cases"] = int(row["STN_CNT"] or 0)
                recent_7d = int(row["D7"] or 0)
                recent_30d = int(row["D30"] or 0)
                prev_30d = int(row["PREV30"] or 0)
                recent_90d = int(row["D90"] or 0)
                trend = "上升" if recent_30d > prev_30d else "下降" if recent_30d < prev_30d else "持平"
                result["time_trend"] = {
                    "recent_7d": recent_7d,
                    "recent_30d": recent_30d,
                    "prev_30d": prev_30d,
                    "recent_90d": recent_90d,
                    "trend": trend,
                }

            keywords = ["重启", "更换", "调整", "清洁", "紧固", "检查", "复位", "修复", "断电", "重新配置"]
            keyword_cases_sql = ", ".join(
                f"SUM(CASE WHEN SR.SOLUTION LIKE '%{keyword}%' THEN 1 ELSE 0 END) AS KW{index}"
                for index, keyword in enumerate(keywords)
            )
            solution_sql = f"SELECT {keyword_cases_sql} FROM MAXIMO.SR SR WHERE {exact_where}"
            solution_df = pd.read_sql(solution_sql, conn, params=exact_params)
            if not solution_df.empty:
                total = max(result["total_cases"], 1)
                for index, keyword in enumerate(keywords):
                    count = int(solution_df.iloc[0][f"KW{index}"] or 0)
                    if count > 0:
                        result["solution_stats"].append(
                            {"method": keyword, "count": count, "percentage": round(count / total * 100, 1)}
                        )
                result["solution_stats"].sort(key=lambda item: item["count"], reverse=True)

            cause_sql = f"""
            SELECT REGEXP_SUBSTR(SR.LONGDESCRIPTION, '原因[：:](.*)', 1, 1, 'n', 1) AS CAUSE,
                   COUNT(*) AS CNT
            FROM MAXIMO.SR SR
            WHERE {exact_where} AND SR.LONGDESCRIPTION IS NOT NULL
            GROUP BY REGEXP_SUBSTR(SR.LONGDESCRIPTION, '原因[：:](.*)', 1, 1, 'n', 1)
            HAVING REGEXP_SUBSTR(SR.LONGDESCRIPTION, '原因[：:](.*)', 1, 1, 'n', 1) IS NOT NULL
            ORDER BY CNT DESC FETCH FIRST 5 ROWS ONLY
            """
            try:
                cause_df = pd.read_sql(cause_sql, conn, params=exact_params)
                total = max(result["total_cases"], 1)
                for _, row in cause_df.iterrows():
                    cause = str(row["CAUSE"]).strip()[:80]
                    if cause:
                        result["cause_stats"].append(
                            {"cause": cause, "count": int(row["CNT"]), "percentage": round(int(row["CNT"]) / total * 100, 1)}
                        )
            except Exception:  # noqa: BLE001
                logger.debug("Cause aggregation skipped due to Oracle regexp limitations")

            if hotspot_where != "1=1":
                top_station_sql = f"""
                SELECT SR.STATIONNAME, COUNT(*) AS CNT
                FROM MAXIMO.SR SR
                WHERE {hotspot_where} AND SR.STATIONNAME IS NOT NULL
                GROUP BY SR.STATIONNAME
                ORDER BY CNT DESC
                FETCH FIRST 5 ROWS ONLY
                """
                top_station_df = pd.read_sql(top_station_sql, conn, params=hotspot_params)
                if not top_station_df.empty:
                    result["high_freq_stations"] = [
                        {"station": row["STATIONNAME"], "count": int(row["CNT"])}
                        for _, row in top_station_df.iterrows()
                    ]

            if station_name:
                history_sql = f"""
                SELECT SR.TICKETID, SR.REPORTDATE, SR.DESCRIPTION, COALESCE(SR.SOLUTION, SR.PROCREMEDY, '') AS SOLUTION
                FROM MAXIMO.SR SR
                WHERE {station_history_where}
                ORDER BY SR.REPORTDATE DESC
                FETCH FIRST 3 ROWS ONLY
                """
                history_df = pd.read_sql(history_sql, conn, params=station_history_params)
                for _, row in history_df.iterrows():
                    result["station_history"].append(
                        {
                            "ticket": str(row.get("TICKETID", "")),
                            "date": str(row.get("REPORTDATE", ""))[:10],
                            "desc": str(row.get("DESCRIPTION", ""))[:120],
                            "solution": str(row.get("SOLUTION", ""))[:180],
                        }
                    )

    except Exception as exc:  # noqa: BLE001
        logger.warning("Diagnosis aggregation fallback to case-level stats: %s", exc)
        result["total_cases"] = len(cases_df)
        if line_num and "LINENUM" in cases_df.columns:
            valid_lines = [item.strip() for item in str(line_num).split(",") if item.strip()]
            result["line_cases"] = len(cases_df[cases_df["LINENUM"].astype(str).isin(valid_lines)])
        if station_name and "STATIONNAME" in cases_df.columns:
            result["station_cases"] = len(cases_df[cases_df["STATIONNAME"].astype(str).str.contains(station_name, na=False)])
        for keyword in ["重启", "更换", "调整", "清洁", "紧固", "检查", "复位", "修复"]:
            if "SOLUTION" not in cases_df.columns:
                break
            count = int(cases_df["SOLUTION"].astype(str).str.contains(keyword, na=False).sum())
            if count > 0:
                result["solution_stats"].append(
                    {"method": keyword, "count": count, "percentage": round(count / max(len(cases_df), 1) * 100, 1)}
                )
        result["solution_stats"].sort(key=lambda item: item["count"], reverse=True)

    if not result["cause_stats"] and "FAULT_CAUSE" in cases_df.columns:
        cause_series = cases_df["FAULT_CAUSE"].dropna()
        for cause, count in cause_series.value_counts().head(5).items():
            result["cause_stats"].append(
                {"cause": str(cause)[:80], "count": int(count), "percentage": round(int(count) / max(len(cases_df), 1) * 100, 1)}
            )

    if "SPECIALTY" in cases_df.columns:
        result["specialty_distribution"] = {
            str(name): int(count)
            for name, count in cases_df["SPECIALTY"].astype(str).value_counts().head(5).items()
        }

    trend = result["time_trend"]
    recent_7d = trend.get("recent_7d", 0)
    recent_30d = trend.get("recent_30d", 0)
    recent_90d = trend.get("recent_90d", 0)
    if recent_7d >= 5 or recent_30d >= 15:
        level, freq_text = "极高", f"近7天 {recent_7d} 次，近30天 {recent_30d} 次"
    elif recent_7d >= 3 or recent_30d >= 8:
        level, freq_text = "高", f"近7天 {recent_7d} 次，近30天 {recent_30d} 次"
    elif recent_30d >= 3 or recent_90d >= 10:
        level, freq_text = "中", f"近30天 {recent_30d} 次，近90天 {recent_90d} 次"
    else:
        level, freq_text = "低", f"近30天 {recent_30d} 次"

    recommendations = {
        "极高": "建议立即排查并制定专项整治方案。",
        "高": "建议提高巡检频率并关注同类设备状态。",
        "中": "建议纳入近期维护关注清单。",
        "低": "当前频率较低，保持常规维护即可。",
    }
    result["risk_assessment"] = {"level": level, "freq_text": freq_text, "recommendation": recommendations[level]}
    return result


def run_statistics(entities_payload: Any, query_type: str) -> dict[str, Any]:
    entities = _entities_to_dict(entities_payload)
    where_clause, params = build_sql_conditions_from_entities(entities)

    with DatabaseManager.get_connection() as conn:
        if query_type == "ranking":
            sql = f"""
            SELECT
                CASE
                    WHEN SR.PROBLEMCODE IS NOT NULL THEN SR.PROBLEMCODE
                    ELSE SUBSTR(SR.DESCRIPTION, 1, 30)
                END AS FAULT_TYPE,
                COUNT(*) AS FAULT_COUNT
            FROM MAXIMO.SR SR
            WHERE {where_clause}
            GROUP BY
                CASE
                    WHEN SR.PROBLEMCODE IS NOT NULL THEN SR.PROBLEMCODE
                    ELSE SUBSTR(SR.DESCRIPTION, 1, 30)
                END
            ORDER BY FAULT_COUNT DESC
            FETCH FIRST 10 ROWS ONLY
            """
            result_df = pd.read_sql(sql, conn, params=params)
            if result_df.empty:
                return {"summary_markdown": "没有找到符合条件的故障记录。", "rows": [], "count": 0}
            total_count = int(result_df["FAULT_COUNT"].sum())
            top_row = result_df.iloc[0]
            summary = f"共 **{total_count}** 条故障记录，最高频的是 **{top_row['FAULT_TYPE']}**（{int(top_row['FAULT_COUNT'])} 次）。"
            return {
                "summary_markdown": summary,
                "rows": _serialize_df(result_df),
                "count": total_count,
                "query_type": query_type,
            }

        if query_type == "comparison":
            dimension = entities.get("compare_dimension") or "line"
            dim_map = {
                "line": ("SR.LINENUM", "线路"),
                "station": ("SR.STATIONNAME", "车站"),
                "specialty": ("SR.SPECIALTY", "专业"),
            }
            db_col, dim_label = dim_map.get(dimension, dim_map["line"])
            sql = f"""
            SELECT {db_col} AS DIM_VALUE, COUNT(*) AS FAULT_COUNT
            FROM MAXIMO.SR SR
            WHERE {where_clause} AND {db_col} IS NOT NULL
            GROUP BY {db_col}
            ORDER BY FAULT_COUNT DESC
            FETCH FIRST 20 ROWS ONLY
            """
            result_df = pd.read_sql(sql, conn, params=params)
            if result_df.empty:
                return {"summary_markdown": "没有找到符合条件的故障记录。", "rows": [], "count": 0}
            total_count = int(result_df["FAULT_COUNT"].sum())
            top_row = result_df.iloc[0]
            top_value = f"{top_row['DIM_VALUE']}号线" if dimension == "line" else str(top_row["DIM_VALUE"])
            summary = f"共 **{total_count}** 条故障，**{top_value}** 最多（{int(top_row['FAULT_COUNT'])} 次）。"
            return {
                "summary_markdown": summary,
                "rows": _serialize_df(result_df),
                "count": total_count,
                "query_type": query_type,
                "dimension_label": dim_label,
            }

        sql = f"""
        SELECT
            SR.TICKETID,
            SR.REPORTDATE,
            SR.LINENUM,
            SR.STATIONNAME,
            SR.DESCRIPTION,
            SR.STATUS,
            SR.SPECIALTY,
            SR.OWNERGROUP
        FROM MAXIMO.SR SR
        WHERE {where_clause}
        ORDER BY SR.REPORTDATE DESC
        """
        result_df = pd.read_sql(sql, conn, params=params)
        count = len(result_df)
        if count == 0:
            return {"summary_markdown": "没有找到符合条件的故障记录。", "rows": [], "count": 0}

        location_desc = f"{entities.get('line_num')}号线" if entities.get("line_num") else "全线网"
        time_desc = "查询时段内"
        time_range = entities.get("time_range") or {}
        if time_range.get("start_date") and time_range.get("end_date"):
            if time_range["start_date"] == time_range["end_date"]:
                time_desc = time_range["start_date"]
            else:
                time_desc = f"{time_range['start_date']} 至 {time_range['end_date']}"

        summary = f"**{location_desc} {time_desc}** 共有 **{count}** 个故障。"
        if "SPECIALTY" in result_df.columns:
            specialty_dist = result_df["SPECIALTY"].astype(str).value_counts().head(1)
            if not specialty_dist.empty:
                summary += f" 其中 **{specialty_dist.index[0]}** 最多（{int(specialty_dist.iloc[0])} 条）。"

        return {
            "summary_markdown": summary,
            "rows": _serialize_df(result_df.head(100)),
            "count": count,
            "query_type": query_type,
            "status_distribution": result_df["STATUS"].astype(str).value_counts().to_dict(),
            "specialty_distribution": {
                str(name): int(value) for name, value in result_df["SPECIALTY"].astype(str).value_counts().head(5).items()
            },
            "station_distribution": {
                str(name): int(value) for name, value in result_df["STATIONNAME"].dropna().astype(str).value_counts().head(5).items()
            },
        }


def run_responsibility(entities_payload: Any) -> dict[str, Any]:
    entities = _entities_to_dict(entities_payload)
    search_term = entities.get("specialty") or entities.get("device")
    if not search_term:
        return {"answer_markdown": "未识别出设备或专业信息。", "rows": [], "count": 0}

    search_term = normalize_text(search_term)
    search_term_clean = DatabaseManager.sanitize_input(search_term)
    search_term_short = DatabaseManager.sanitize_input(search_term.replace("设备", ""))
    line_num = entities.get("line_num")
    first_line = DatabaseManager.sanitize_input(str(line_num).split(",")[0].strip()) if line_num else None
    expanded_terms = expand_specialty_synonyms(search_term)[:10]

    result_df = pd.DataFrame()
    query_level = None

    with DatabaseManager.get_connection() as conn:
        if first_line:
            sql = """
            SELECT OWNERGROUP, COUNT(*) AS CNT
            FROM MAXIMO.SR SR
            WHERE SR.LINENUM = :line_num
              AND (UPPER(SR.SPECIALTY) LIKE UPPER(:search_term)
                   OR UPPER(SR.SPECIALTY) LIKE UPPER(:search_term_short))
              AND OWNERGROUP IS NOT NULL
            GROUP BY OWNERGROUP
            ORDER BY CNT DESC
            FETCH FIRST 5 ROWS ONLY
            """
            result_df = pd.read_sql(
                sql,
                conn,
                params={
                    "line_num": first_line,
                    "search_term": f"%{search_term_clean}%",
                    "search_term_short": f"%{search_term_short}%",
                },
            )
            if not result_df.empty:
                query_level = "precise"

        if result_df.empty:
            params: dict[str, Any] = {}
            conditions: list[str] = []
            for index, term in enumerate(expanded_terms):
                param_name = f"term_{index}"
                params[param_name] = f"%{DatabaseManager.sanitize_input(term)}%"
                conditions.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:{param_name})")
            where_clause = f"({' OR '.join(conditions)})"
            if first_line:
                where_clause += " AND SR.LINENUM = :line_num"
                params["line_num"] = first_line
            sql = f"""
            SELECT OWNERGROUP, COUNT(*) AS CNT
            FROM MAXIMO.SR SR
            WHERE {where_clause}
              AND OWNERGROUP IS NOT NULL
            GROUP BY OWNERGROUP
            ORDER BY CNT DESC
            FETCH FIRST 5 ROWS ONLY
            """
            result_df = pd.read_sql(sql, conn, params=params)
            if not result_df.empty:
                query_level = "synonym_expansion"

        if result_df.empty:
            params = {"search_term": f"%{search_term_clean}%", "search_term_short": f"%{search_term_short}%"}
            where_clause = "(UPPER(SR.DESCRIPTION) LIKE UPPER(:search_term) OR UPPER(SR.DESCRIPTION) LIKE UPPER(:search_term_short))"
            if first_line:
                where_clause += " AND SR.LINENUM = :line_num"
                params["line_num"] = first_line
            sql = f"""
            SELECT OWNERGROUP, COUNT(*) AS CNT
            FROM MAXIMO.SR SR
            WHERE {where_clause}
              AND OWNERGROUP IS NOT NULL
            GROUP BY OWNERGROUP
            ORDER BY CNT DESC
            FETCH FIRST 5 ROWS ONLY
            """
            result_df = pd.read_sql(sql, conn, params=params)
            if not result_df.empty:
                query_level = "fuzzy_description"

        if result_df.empty and first_line:
            params = {}
            conditions = []
            for index, term in enumerate(expanded_terms):
                param_name = f"term_{index}"
                params[param_name] = f"%{DatabaseManager.sanitize_input(term)}%"
                conditions.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:{param_name})")
            sql = f"""
            SELECT OWNERGROUP, COUNT(*) AS CNT
            FROM MAXIMO.SR SR
            WHERE ({' OR '.join(conditions)})
              AND OWNERGROUP IS NOT NULL
            GROUP BY OWNERGROUP
            ORDER BY CNT DESC
            FETCH FIRST 5 ROWS ONLY
            """
            result_df = pd.read_sql(sql, conn, params=params)
            if not result_df.empty:
                query_level = "global_fallback"

    if result_df.empty:
        return {"answer_markdown": f"没有找到 **{search_term}** 的历史处理记录。", "rows": [], "count": 0}

    top_group = str(result_df.iloc[0]["OWNERGROUP"])
    top_count = int(result_df.iloc[0]["CNT"])
    total_count = int(result_df["CNT"].sum())
    top_pct = round(top_count / max(total_count, 1) * 100, 1)

    if query_level == "global_fallback" and first_line:
        answer = f"在 **{first_line}号线** 没有足够记录，但从全线网历史看，**{search_term}** 主要由 **{top_group}** 负责（{top_count} 次，{top_pct}%）。"
    elif query_level == "fuzzy_description":
        answer = f"根据描述字段匹配，**{search_term}** 建议联系 **{top_group}**（{top_count} 次，{top_pct}%），仅供参考。"
    else:
        answer = f"**{search_term}** 主要由 **{top_group}** 负责（{top_count} 次，{top_pct}%）。"

    if len(result_df) > 1:
        second_row = result_df.iloc[1]
        answer += f"\n\n其次是 **{second_row['OWNERGROUP']}**（{int(second_row['CNT'])} 次）。"

    return {
        "answer_markdown": answer,
        "rows": _serialize_df(result_df),
        "count": total_count,
        "query_level": query_level,
    }


def run_diagnosis_support(user_query: str, entities_payload: Any, vector_candidate_ids: list[str], limit: int) -> dict[str, Any]:
    settings = get_settings()
    entities = _entities_to_dict(entities_payload)

    cleaned_vector_ids: list[str] = []
    for ticket_id in vector_candidate_ids:
        text = str(ticket_id).strip()
        if text and text not in cleaned_vector_ids:
            cleaned_vector_ids.append(text)

    keyword_ids = keyword_search_oracle(entities, top_k=50)
    if cleaned_vector_ids and keyword_ids:
        fused_ids = reciprocal_rank_fusion([cleaned_vector_ids, keyword_ids])
    elif cleaned_vector_ids:
        fused_ids = cleaned_vector_ids
    else:
        fused_ids = keyword_ids

    max_limit = max(1, min(limit, settings.max_cases_limit))
    fused_ids = fused_ids[:max_limit]
    cases_df = fetch_cases_by_ticket_ids(fused_ids)
    analytics = analyze_case_data(cases_df, entities)

    return {
        "user_query": user_query,
        "entities": entities,
        "vector_candidate_ids": cleaned_vector_ids,
        "keyword_candidate_ids": keyword_ids,
        "fused_ticket_ids": fused_ids,
        "cases": _serialize_df(cases_df),
        "analytics": analytics,
        "count": len(cases_df),
    }


def run_diagnosis_support_batch(user_query: str, layers: list[Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for layer in layers:
        layer_data = layer.model_dump() if hasattr(layer, "model_dump") else dict(layer)
        support = run_diagnosis_support(
            user_query=user_query,
            entities_payload=layer_data.get("entities", {}),
            vector_candidate_ids=layer_data.get("vector_candidate_ids", []) or [],
            limit=int(layer_data.get("limit", 100)),
        )
        results.append(
            {
                "layer_id": layer_data.get("layer_id"),
                "label": layer_data.get("label"),
                "bucket": layer_data.get("bucket"),
                "evidence_level": layer_data.get("evidence_level"),
                "priority": int(layer_data.get("priority", 1)),
                "result": support,
            }
        )

    return {
        "user_query": user_query,
        "layer_count": len(results),
        "layers": results,
    }
