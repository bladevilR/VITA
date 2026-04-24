from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import streamlit as st

from workstation_vita.engine import WorkstationEngine


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

st.set_page_config(page_title="维保助手", page_icon="维", layout="centered")

COLUMN_LABELS = {
    "TICKETID": "工单号",
    "REPORTDATE": "报修时间",
    "LINENUM": "线路",
    "STATIONNAME": "车站",
    "DESCRIPTION": "故障描述",
    "STATUS": "状态",
    "SPECIALTY": "专业",
    "OWNERGROUP": "责任班组",
    "SOLUTION": "处理措施",
    "FAULT_CAUSE": "故障原因",
    "FAILURECODE": "设备编码",
    "PROBLEMCODE": "现象编码",
    "ASSETNUM": "设备编号",
    "PLAN_LABEL": "证据层级",
    "PLAN_EVIDENCE": "证据类型",
    "PLAN_PRIORITY": "计划顺位",
    "RELEVANCE_SCORE": "相关度",
    "RETRIEVAL_RANK": "检索顺位",
}


@st.cache_resource(show_spinner=False)
def build_engine() -> WorkstationEngine:
    return WorkstationEngine()


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    renamed = df.copy()
    renamed = renamed.where(pd.notna(renamed), "")
    renamed = renamed.replace({"None": "", "nan": "", "NaN": ""})
    renamed = renamed.rename(columns={key: value for key, value in COLUMN_LABELS.items() if key in renamed.columns})
    if "线路" in renamed.columns:
        renamed["线路"] = renamed["线路"].apply(lambda value: f"{value}号线" if str(value).isdigit() else value)
    return renamed


def _render_table(title: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with st.expander(title, expanded=False):
        st.dataframe(_rename_columns(pd.DataFrame(rows)), use_container_width=True, hide_index=True)


def _render_analytics(analytics: dict[str, Any]) -> None:
    if not analytics:
        return

    trend = analytics.get("time_trend", {})
    risk = analytics.get("risk_assessment", {})
    st.markdown("### 诊断依据")
    st.caption(
        f"全量匹配 {analytics.get('total_cases', 0)} 条，本线路 {analytics.get('line_cases', 0)} 条，"
        f"本站 {analytics.get('station_cases', 0)} 条"
    )
    st.caption(
        f"近7天 {trend.get('recent_7d', 0)} 次，近30天 {trend.get('recent_30d', 0)} 次，"
        f"趋势 {trend.get('trend', '持平')}，风险等级 {risk.get('level', '低')}"
    )

    if analytics.get("high_freq_stations"):
        high_freq_df = pd.DataFrame(analytics["high_freq_stations"]).rename(
            columns={"station": "高频站点", "count": "次数"}
        )
        st.dataframe(high_freq_df, use_container_width=True, hide_index=True)

    if analytics.get("solution_stats"):
        solution_df = pd.DataFrame(analytics["solution_stats"]).rename(
            columns={"method": "处理方式", "count": "次数", "percentage": "占比"}
        )
        with st.expander("处理方式分布", expanded=False):
            st.dataframe(solution_df, use_container_width=True, hide_index=True)

    if analytics.get("cause_stats"):
        cause_df = pd.DataFrame(analytics["cause_stats"]).rename(
            columns={"cause": "原因", "count": "次数", "percentage": "占比"}
        )
        with st.expander("原因分布", expanded=False):
            st.dataframe(cause_df, use_container_width=True, hide_index=True)


try:
    engine = build_engine()
except Exception as exc:  # noqa: BLE001
    st.title("维保助手")
    st.error(f"启动失败：{exc}")
    st.stop()

st.title("维保助手")
st.caption("服务端负责查库，本机负责检索、推理和界面交互。")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.markdown("### 运行状态")
    try:
        health = engine.server_health()
        st.metric("服务端接口", "在线" if health.get("status") == "ok" else "未知")
        st.caption(f"数据库可用：{'是' if health.get('db_available') else '否'}")
        if health.get("db_message"):
            st.caption(str(health.get("db_message")))
    except Exception as exc:  # noqa: BLE001
        st.metric("服务端接口", "离线")
        st.caption(str(exc))

    st.metric("向量库条数", f"{engine.vector_store.count:,}")
    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        details = message.get("details") or {}
        _render_table("统计明细", details.get("rows") or [])
        _render_table("直接相关案例", details.get("direct_cases") or [])
        _render_table("本站历史案例", details.get("station_cases") or [])
        _render_table("同线同类案例", details.get("line_cases") or [])
        _render_table("补充参考案例", details.get("supplemental_cases") or [])
        _render_table("最终引用案例", details.get("top_cases") or [])
        _render_analytics(details.get("analytics") or {})


prompt = st.chat_input("请输入故障现象、设备、车站、线路或时间条件")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("正在分析..."):
            try:
                response = engine.process_query(prompt)
                answer_markdown = response["answer_markdown"]
                details = response.get("details", {})
                st.markdown(answer_markdown)
                _render_table("统计明细", details.get("rows") or [])
                _render_table("直接相关案例", details.get("direct_cases") or [])
                _render_table("本站历史案例", details.get("station_cases") or [])
                _render_table("同线同类案例", details.get("line_cases") or [])
                _render_table("补充参考案例", details.get("supplemental_cases") or [])
                _render_table("最终引用案例", details.get("top_cases") or [])
                _render_analytics(details.get("analytics") or {})
                st.session_state.messages.append({"role": "assistant", "content": answer_markdown, "details": details})
            except Exception as exc:  # noqa: BLE001
                error_text = f"处理失败：{exc}"
                st.error(error_text)
                st.session_state.messages.append({"role": "assistant", "content": error_text})
