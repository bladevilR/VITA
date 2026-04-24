# ================================================================================
# VITA v13.0 - "最终修正"
# 模块1：核心配置与解析器
# ================================================================================

import streamlit as st
import faiss
import numpy as np
import pandas as pd
import oracledb
import requests
import json
import os
from datetime import datetime
import time
import re

# ============================================
# 1.1 - 内网模型配置
# ============================================
# 数据库连接配置
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "10.97.4.7:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# 内网模型API配置
LLM_API_URL = "http://10.98.12.68:8081/v1"
LLM_API_KEY = "2000|sk-kDmIfBMkm0w6Qy2G2NtkIWS9rtpGiqH0"
LLM_MODEL = "glm4_5"
EMBEDDING_API_URL = "http://10.98.12.69:8080/embed"

# Faiss 向量索引文件路径
INDEX_FILE = "kb_zhipu.index"
ID_MAP_FILE = "kb_zhipu_id_map.npy"

# 分级知识策略配置
GENERAL_GUIDE_LINK = "http://ecm.sz-mtr.com/preview.html?fileid=7479483"
ELECTROMECHANICAL_SPECIALTIES = [
    "AFC设备", "屏蔽门设备", "电扶梯设备", "FAS设备", "BAS设备",
    "给排水设备", "通风空调设备", "低压供电设备", "高压供电设备"
]


# ============================================
# 1.3 - 基础工具函数
# ============================================

def show_progress(message):
    """在界面上显示格式化的进度信息。"""
    st.markdown(f"*📍 {message}*")


def show_debug(message, elapsed_time=None):
    """在界面上显示用于调试的、小字体的日志信息。"""
    if elapsed_time:
        st.markdown(f"<small><i>🔍 {message} (耗时: {elapsed_time:.2f}秒)</i></small>", unsafe_allow_html=True)
    else:
        st.markdown(f"<small><i>🔍 {message}</i></small>", unsafe_allow_html=True)


# 企业内部专有知识，使用本地规则进行100%可靠的转换
SYNONYM_MAP = {
    "站台门": "屏蔽门",
    "综合监控": "ISCS",
    "综合监控系统": "ISCS",
    "门禁": "门禁设备"  # 新增
}


def normalize_text(text):
    """对文本进行标准化处理，替换同义词。"""
    if not isinstance(text, str): return text
    for synonym, standard in SYNONYM_MAP.items():
        text = text.replace(synonym, standard)
    return text


def extract_fault_cause(longdesc):
    """从详细描述(LONGDESCRIPTION)中提取结构化的故障原因。"""
    if not isinstance(longdesc, str): return None
    cause_patterns = [r'原因[:：]\s*([^。；;]+)', r'故障原因[:：]\s*([^。；;]+)', r'问题原因[:：]\s*([^。；;]+)']
    for pattern in cause_patterns:
        match = re.search(pattern, longdesc)
        if match:
            return match.group(1).strip()
    return None


def build_synonym_sql_conditions(field_name, search_term):
    """为SQL查询构建包含所有同义词的WHERE条件子句。"""
    normalized_term = normalize_text(search_term)
    all_variants = list(
        set([normalized_term] + [k for k, v in SYNONYM_MAP.items() if v == normalized_term or k == normalized_term]))
    conditions = [f"UPPER({field_name}) LIKE UPPER('%{variant}%')" for variant in all_variants]
    return f"({' OR '.join(conditions)})"


# ============================================
# 1.4 - 全能解析器函数
# ============================================

def call_all_in_one_parser(user_query):
    """
    VITA v13.0 的核心大脑。
    调用内网GLM4.5模型进行意图解析。
    其唯一职责是将用户的自然语言转换为严格、标准的JSON。
    """
    current_date = datetime.now().strftime('%Y-%m-%d')

    prompt = f"""
    你是一个专门解析地铁运维查询的AI助手，拥有强大的时间范围理解和计算能力。
    你的任务是将用户输入，结合【当前日期】，转换为严格的JSON格式。

    【当前日期】: {current_date}

    **第一步：意图识别**
    根据下面的【意图定义】，判断用户的核心意图。
    - **statistics**: 当用户询问数量、排名、列表或数据时使用。触发词包括："多少", "几个", "统计", "排名", "列出来", "最多的"。
    - **responsibility**: 当用户询问负责人、部门或班组时使用。触发词包括："谁负责", "归谁管", "找谁", "哪个部门", "联系谁", "报给谁"。
    - **diagnosis**: 当用户描述一个故障现象并询问如何解决，或直接陈述一个故障时使用。触发词包括："怎么办", "怎么处理", "坏了", "黑屏", "无法工作", "故障了"。

    **第二步：实体提取**
    识别所有实体。对于时间实体，你必须将其转换为一个包含`start_date`和`end_date`的对象。

    **绝对规则:**
    1.  只返回JSON对象，不要有任何其他文字或解释。
    2.  `intent`字段的值【必须】严格遵循【意图定义】，只能是 "diagnosis", "statistics", 或 "responsibility" 之一。
    3.  `line_num`字段的值【必须】是纯数字字符串, 例如 "2", 而不是 "2号线"。
    4.  `time_range`字段的值【必须】是一个包含`start_date`和`end_date`键的JSON对象，值必须是"YYYY-MM-DD"格式。如果无时间信息，则`time_range`为null。
    5.  如果信息不足，对应字段值必须为null。

    **输出JSON格式:**
    {{
      "intent": "...", "entities": {{"line_num": "...", "station_name": "...", "specialty": "...", "device": "...", "fault_phenomenon": "...", "time_range": {{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}}}}, "query_type": "..."
    }}

    ---
    现在，请严格按照以上规则，解析以下用户输入：
    "{user_query}"
    """
    show_debug("正在调用内网 GLM4.5 模型...")
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LLM_API_KEY}'
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 16000,
        "temperature": 0.0,
        "top_p": 0,
        "enable_thinking": True
    }
    try:
        response = requests.post(f"{LLM_API_URL}/chat/completions", headers=headers, data=json.dumps(payload), timeout=90)
        response.raise_for_status()
        full_text = response.json()['choices'][0]['message']['content']
        json_str = full_text.split("</think>")[-1].strip() if "</think>" in full_text else full_text.strip()
        if "```json" in json_str: json_str = json_str.split("```json")[1].split("```")[0]
        return json.loads(json_str)
    except Exception as e:
        return {"intent": "error", "error_message": str(e)}


# ============================================
# 1.5 - 全局资源初始化
# ============================================

def get_embedding(text):
    """调用内网Embedding API获取向量"""
    headers = {'Content-Type': 'application/json'}
    payload = {"inputs": text}
    try:
        response = requests.post(EMBEDDING_API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Embedding调用失败: {e}")
        return None


def call_llm(prompt, timeout=90):
    """调用内网LLM生成报告"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LLM_API_KEY}'
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 16000,
        "temperature": 0.3,
        "top_p": 0.9,
        "enable_thinking": True
    }
    try:
        response = requests.post(f"{LLM_API_URL}/chat/completions", headers=headers, data=json.dumps(payload), timeout=timeout)
        response.raise_for_status()
        full_text = response.json()['choices'][0]['message']['content']
        if "</think>" in full_text:
            return full_text.split("</think>")[-1].strip()
        return full_text.strip()
    except Exception as e:
        return f"LLM调用失败: {e}"


@st.cache_resource
def initialize_resources():
    """
    初始化并缓存应用启动时需要的全局资源，如Oracle客户端和向量索引。
    """
    try:
        oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
        if not os.path.exists(INDEX_FILE):
            st.error(f"向量索引文件未找到: {INDEX_FILE}");
            return None, None
        index = faiss.read_index(INDEX_FILE)
        if not os.path.exists(ID_MAP_FILE):
            st.error(f"ID映射文件未找到: {ID_MAP_FILE}");
            return None, None
        id_map = np.load(ID_MAP_FILE, allow_pickle=True)
        return index, id_map
    except Exception as e:
        st.error(f"全局资源初始化失败: {e}");
        st.exception(e);
        return None, None


# 执行初始化
faiss_index, id_map = initialize_resources()


# ================================================================================
# VITA v13.0 - "最终修正"
# 模块2：故障诊断功能
# ================================================================================

def calculate_relevance_score(row, entities):
    """
    对从数据库中检索出的案例，根据其与用户查询的“故障本质”和“时空上下文”
    的相似度，进行多维度智能评分。
    """
    score = 0
    # 权重层 1: 故障本质匹配 (最高权重)
    if entities.get('fault_phenomenon') and pd.notna(row['PROBLEMCODE']) and entities['fault_phenomenon'] in str(
            row['PROBLEMCODE']):
        score += 100
    if entities.get('device') and pd.notna(row['FAILURECODE']) and entities['device'] in str(row['FAILURECODE']):
        score += 80

    # 权重层 2: 地理位置匹配 (次要权重)
    if entities.get('line_num') and str(row['LINENUM']) == entities.get('line_num'):
        score += 30
    if entities.get('station_name') and pd.notna(row['STATIONNAME']) and entities.get('station_name') in str(
            row['STATIONNAME']):
        score += 20

    # 权重层 3: 组织结构匹配 (辅助权重)
    if entities.get('specialty') and pd.notna(row['SPECIALTY']) and entities.get('specialty') in str(row['SPECIALTY']):
        score += 10

    return score


def diagnose_fault(entities, user_query, faiss_index, id_map):
    """
    VITA v13.0 的核心功能：一个多阶段、有决策、会自我修正的智能诊断引擎。
    """
    show_progress("🤖 专家诊断引擎启动...")

    # ----------------------------------------------------------------
    # 阶段 0: 前置条件检查
    # ----------------------------------------------------------------
    device = entities.get('device') or entities.get('specialty')
    if not device:
        st.warning("未能从您的问题中识别出具体的设备或专业，请提供更详细的信息。")
        return

    try:
        # ----------------------------------------------------------------
        # 阶段 1: 上下文感知的群体智慧检索
        # ----------------------------------------------------------------
        show_progress("📚 正在知识库中进行上下文感知检索...")
        # 【核心修正】将线路和车站信息注入向量检索查询
        context_parts = []
        if entities.get('line_num'): context_parts.append(f"线路:{entities.get('line_num')}")
        if entities.get('station_name'): context_parts.append(f"车站:{entities.get('station_name')}")
        context_parts.append(f"设备:{entities.get('device')}")
        context_parts.append(f"现象:{entities.get('fault_phenomenon')}")

        query_text = " | ".join(filter(None, context_parts))
        show_debug(f"向量检索查询: {query_text}")

        query_embedding = get_embedding(query_text)
        if query_embedding is None:
            st.error("无法获取查询向量")
            return
        distances, indices = faiss_index.search(np.array([query_embedding], dtype='float32'), k=50)
        ticket_ids = tuple(str(tid) for tid in id_map[indices[0]])

        if not ticket_ids:
            st.warning("知识库检索无匹配案例，无法进行下一步分析。")
            return

        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            sql_placeholder = ", ".join([f"'{tid}'" for tid in ticket_ids])
            sql = f"""
            SELECT SR.TICKETID, SR.ASSETNUM, SR.LINENUM, SR.STATIONNAME, SR.DESCRIPTION, SR.LONGDESCRIPTION, SR.SPECIALTY, SR.REPORTDATE, 
                   COALESCE(SR.SOLUTION, SR.PROCREMEDY, '未记录') AS SOLUTION, SR.FAILURECODE, SR.PROBLEMCODE
            FROM MAXIMO.SR SR WHERE SR.TICKETID IN ({sql_placeholder})
            """
            cases_df = pd.read_sql(sql, conn)

        cases_df['FAULT_CAUSE'] = cases_df['LONGDESCRIPTION'].apply(extract_fault_cause)
        cases_df['RELEVANCE_SCORE'] = cases_df.apply(lambda row: calculate_relevance_score(row, entities), axis=1)
        cases_df = cases_df.sort_values('RELEVANCE_SCORE', ascending=False)
        curated_df = cases_df[cases_df['SOLUTION'].str.len() > 5]

        if curated_df.empty:
            st.warning("虽然检索到相似案例，但它们都缺少明确的解决方案记录，无法给出有效建议。")
            return

        # ----------------------------------------------------------------
        # 阶段 2: 自我审查与智能追问 (歧义检测)
        # ----------------------------------------------------------------
        show_progress("🤔 正在进行自我审查与歧义检测...")
        analysis_df = curated_df.head(20)
        specialty_distribution = analysis_df['SPECIALTY'].value_counts(normalize=True)

        if len(specialty_distribution) > 1 and specialty_distribution.iloc[0] < 0.8:
            top_specialties = specialty_distribution.head(2).index.tolist()
            st.warning(f"""
            **检测到潜在的专业歧义！**

            历史案例表明，您提到的“**{device}**”故障同时涉及 **【{top_specialties[0]}】** 和 **【{top_specialties[1]}】** 两个专业，它们的处理方式和责任归属差异巨大。

            为了提供最精确的建议，请您在问题中明确指出具体的设备类型。

            **例如，您可以这样提问：**
            - "电客车的**牵引逆变器**故障怎么办？"
            - "车站的**应急电源(EPS)逆变器**故障怎么办？"
            """)
            return

        # ----------------------------------------------------------------
        # 阶段 3: 设备履历分析 (个体历史)
        # ----------------------------------------------------------------
        show_progress("📜 正在分析该设备的“履历”...")
        lifecycle_text = "未能在最相似案例中找到明确的资产编号，无法进行设备履历分析。"
        asset_num = curated_df.iloc[0]['ASSETNUM']
        if pd.notna(asset_num):
            with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
                lifecycle_sql = f"SELECT REPORTDATE FROM MAXIMO.SR WHERE ASSETNUM = '{asset_num}' ORDER BY REPORTDATE DESC"
                lifecycle_df = pd.read_sql(lifecycle_sql, conn)

            if not lifecycle_df.empty:
                total_faults = len(lifecycle_df)
                last_fault_date = pd.to_datetime(lifecycle_df.iloc[0]['REPORTDATE'])
                days_since_last = (datetime.now() - last_fault_date).days
                recent_faults = len(lifecycle_df[lifecycle_df['REPORTDATE'] > (datetime.now() - pd.Timedelta(days=30))])

                lifecycle_text = f"\n- **资产编号:** {asset_num}\n- **历史总故障:** {total_faults}次\n- **上次故障:** {days_since_last}天前 ({last_fault_date.strftime('%Y-%m-%d')})\n- **近期频率:** 最近30天内发生 **{recent_faults}** 次故障。"
                if recent_faults > 3:
                    lifecycle_text += "\n- **履历结论:** **此设备故障频率极高，可能已进入衰退期，单纯的临时性修复可能无法根治问题。**"

        # ----------------------------------------------------------------
        # 阶段 4: 分级知识策略 (SOP & 通用指南)
        # ----------------------------------------------------------------
        show_progress("📖 正在查询标准知识库...")
        knowledge_text = ""
        # 模拟SOP查询，未来可对接真实的知识库API
        sop_found = False

        if not sop_found:
            fault_specialty = curated_df.iloc[0]['SPECIALTY']
            if fault_specialty in ELECTROMECHANICAL_SPECIALTIES:
                knowledge_text = f"**⚠️ 未找到专项SOP，但已定位到总纲性文件：**\n[点击打开《机电设备故障处理指南》]({GENERAL_GUIDE_LINK})"

        # ----------------------------------------------------------------
        # 阶段 5: 最终报告生成
        # ----------------------------------------------------------------
        show_progress("🤖 正在生成最终专家诊断报告...")

        solution_stats = {}
        keywords = ['重启', '更换', '调整', '清洁', '紧固', '检查', '复位']
        for solution in analysis_df['SOLUTION']:
            for key in keywords:
                if key in str(solution): solution_stats[key] = solution_stats.get(key, 0) + 1
        sorted_stats = sorted(solution_stats.items(), key=lambda item: item[1], reverse=True)
        stats_text = ", ".join([f"{k}:{v}次" for k, v in sorted_stats[:3]]) if sorted_stats else "无明确的通用处理方式"

        top_case = curated_df.iloc[0].to_dict()

        report_prompt = f"""
        你是一位顶级的地铁设备维护专家。请根据我提供的多维度分析数据，为一线工程师生成一份专业、严谨、具有战略高度的诊断报告。

        【背景信息】
        - 用户问题: "{user_query}"

        【数据分析】
        1.  **群体智慧 (相似案例统计)**:
            - 最相似案例: {top_case['DESCRIPTION']} -> 处理措施: {top_case['SOLUTION']}
            - 高频处理方式 (Top 20): {stats_text}
        2.  **个体历史 (本设备履历分析)**:
            {lifecycle_text}
        3.  **标准知识库**:
            {knowledge_text if knowledge_text else "未在知识库中找到相关的标准流程或指南。"}

        【输出要求】
        请严格按照以下Markdown结构输出，语言专业、逻辑清晰:

        ### 🔧 VITA 专家诊断

        **1. 历史经验分析 (群体智慧)**
        [对高频处理方式进行定量分析。例如：“根据最相似的20个案例统计，其中‘重启’操作出现12次(60%)，‘更换’出现5次(25%)，这表明软件或临时性故障是主因...”]

        **2. 本设备履历分析 (个体历史)**
        [复述并分析履历数据，特别是对故障频率做出判断，并强调其对决策的影响。]

        **3. 综合诊断与建议**
        * **短期措施 (治标)**: [结合高频处理方式，给出可以快速恢复服务的临时性操作步骤。]
        * **长期策略 (治本)**: [【关键】结合履历分析，如果故障频率高，必须在此处明确提出“安排更换”或“进行大修”的战略性建议。]
        * **注意事项**: [提供安全提醒、操作要点或需要准备的工具。]

        {"--- \n### 📖 相关标准参考\n" + knowledge_text if knowledge_text else ""}
        """
        report = call_llm(report_prompt)
        st.markdown(report)

        # 【强制要求】提供数据支撑
        with st.expander("显示详细的相似历史案例列表 (Top 10)", expanded=True):
            display_df = curated_df.head(10)[
                ['TICKETID', 'REPORTDATE', 'LINENUM', 'STATIONNAME', 'DESCRIPTION', 'SOLUTION', 'RELEVANCE_SCORE']]
            display_df = display_df.rename(
                columns={'TICKETID': '工单号', 'REPORTDATE': '报告时间', 'LINENUM': '线路', 'STATIONNAME': '车站',
                         'DESCRIPTION': '故障描述', 'SOLUTION': '处理措施', 'RELEVANCE_SCORE': '相关度'})
            display_df['报告时间'] = pd.to_datetime(display_df['报告时间']).dt.strftime('%Y-%m-%d')
            st.dataframe(display_df, use_container_width=True)

    except Exception as e:
        st.error(f"❌ 诊断流程失败: {e}")
        st.exception(e)


# ================================================================================
# VITA v13.0 - "最终修正"
# 模块3：统计查询功能
# ================================================================================

def query_statistics(entities, query_type):
    """
    VITA v13.0 的核心功能：统计查询。
    接收解析器生成的结构化实体(entities)和查询类型(query_type)，
    执行“排名”或“计数与列表”两种模式的查询，并恢复了所有详细分析功能。
    """
    show_progress("📊 智能统计引擎启动...")

    try:
        # ----------------------------------------------------------------
        # 步骤 1: 构建 SQL 的 WHERE 条件
        # ----------------------------------------------------------------
        sql_conditions = []

        if entities.get('line_num'):
            sql_conditions.append(f"SR.LINENUM = '{entities['line_num']}'")
        if entities.get('specialty'):
            sql_conditions.append(build_synonym_sql_conditions('SR.SPECIALTY', entities['specialty']))
        if entities.get('station_name'):
            sql_conditions.append(f"SR.STATIONNAME LIKE '%{entities['station_name']}%'")

        # 【核心架构】处理由LLM计算好的、精确的日期范围
        time_range = entities.get('time_range')
        if time_range and 'start_date' in time_range and 'end_date' in time_range:
            start_date = time_range['start_date']
            end_date = time_range['end_date']
            # 使用 Oracle 的 BETWEEN 操作符，这是处理日期范围查询的最标准、最高效的方式
            sql_conditions.append(
                f"TRUNC(SR.REPORTDATE) BETWEEN TO_DATE('{start_date}', 'YYYY-MM-DD') AND TO_DATE('{end_date}', 'YYYY-MM-DD')")

        where_clause = " AND ".join(sql_conditions) if sql_conditions else "1=1"

        # ----------------------------------------------------------------
        # 步骤 2: 根据查询类型，执行不同的查询和分析逻辑
        # ----------------------------------------------------------------
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            if query_type == 'ranking':
                # --- 分支 2.1: 排名查询 ---
                show_debug("正在执行智能排名查询 (JOIN FAILURELIST)...")

                # 假设故障代码描述表为 MAXIMO.FAILURELIST
                # 查询并关联故障代码的中文描述
                sql = f"""
                SELECT 
                    FL.DESCRIPTION AS FAULT_TYPE, 
                    COUNT(SR.TICKETID) AS FAULT_COUNT
                FROM MAXIMO.SR SR
                JOIN MAXIMO.FAILURELIST FL ON SR.PROBLEMCODE = FL.FAILURECODE
                WHERE {where_clause} AND SR.PROBLEMCODE IS NOT NULL
                GROUP BY FL.DESCRIPTION 
                ORDER BY FAULT_COUNT DESC 
                FETCH FIRST 10 ROWS ONLY
                """
                result_df = pd.read_sql(sql, conn)

                summary = "📊 **查询结果：故障类型排名 Top 10**\n\n"
                if result_df.empty:
                    summary += "在指定条件下，未找到可供排名的标准化故障记录。"
                else:
                    for i, row in result_df.iterrows():
                        summary += f"{i + 1}. **{row['FAULT_TYPE']}**: {row['FAULT_COUNT']}次\n"

                st.markdown(summary)
                st.dataframe(result_df.rename(columns={'FAULT_TYPE': '故障类型', 'FAULT_COUNT': '次数'}),
                             use_container_width=True)

            else:  # 默认 'count' and list
                # --- 分支 2.2: 计数、分析与列表查询 ---
                show_debug("正在执行计数与列表查询...")

                # 查询所有需要的字段，用于后续的完整分析和列表展示
                sql = f"""
                SELECT SR.TICKETID, SR.REPORTDATE, SR.LINENUM, SR.STATIONNAME, SR.DESCRIPTION, SR.STATUS 
                FROM MAXIMO.SR SR 
                WHERE {where_clause} 
                ORDER BY SR.REPORTDATE DESC
                """
                result_df = pd.read_sql(sql, conn)

                count = len(result_df)
                st.markdown(f"📊 **统计结果**\n\n在您指定的条件下，共找到 **{count}** 条故障记录。")

                if not result_df.empty:
                    # 【功能回归】详细分析
                    st.markdown("--- \n**详细分析:**")
                    # 使用 st.text 以保持格式整洁
                    st.text(f"- 状态分布: {result_df['STATUS'].value_counts().to_dict()}")

                    if 'STATIONNAME' in result_df.columns and not result_df['STATIONNAME'].dropna().empty:
                        # 找到故障最多的车站
                        top_station = result_df['STATIONNAME'].value_counts().idxmax()
                        top_station_count = result_df['STATIONNAME'].value_counts().max()
                        st.text(f"- 故障最多车站: {top_station} ({top_station_count}次)")

                    # 【强制要求】数据支撑 - 故障列表
                    st.markdown("--- \n**故障列表如下 (最多显示100条)：**")
                    display_df = result_df.head(100).rename(columns={
                        'TICKETID': '工单号',
                        'REPORTDATE': '报告时间',
                        'LINENUM': '线路',
                        'STATIONNAME': '车站',
                        'DESCRIPTION': '故障描述',
                        'STATUS': '状态'
                    })
                    # 格式化日期显示
                    display_df['报告时间'] = pd.to_datetime(display_df['报告时间']).dt.strftime('%Y-%m-%d %H:%M')
                    st.dataframe(display_df, use_container_width=True)

    except Exception as e:
        st.error(f"❌ 統計查詢失敗: {e}")
        st.exception(e)


# ================================================================================
# VITA v13.0 - "最终修正"
# 模块4：责任归属功能
# ================================================================================

def query_responsibility(entities):
    """
    VITA v13.0 的核心功能：责任归属。
    通过“精确查询 + 智能降级”和“多重尝试”策略，查询数据库以确定最相关的处理班组。
    """
    show_progress("👥 责任归属引擎启动...")

    # 从实体中提取最关键的查询词（设备优先于专业）
    search_term = entities.get('device') or entities.get('specialty')
    if not search_term:
        st.warning("未能从您的问题中识别出关键的设备或专业，无法进行责任归属查询。")
        return

    try:
        line_num = entities.get('line_num')
        result_df = pd.DataFrame()
        is_fallback = False

        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            # ----------------------------------------------------------------
            # 步骤 1: 尝试进行精确查询 (带线路限制)
            # ----------------------------------------------------------------
            if line_num:
                show_debug(f"正在进行精确查询 (范围: {line_num}号线)...")
                # 优先使用“专业”字段进行精确匹配，因为这通常更可靠
                if entities.get('specialty'):
                    sql_conditions = [f"SR.SPECIALTY = '{normalize_text(entities.get('specialty'))}'"]
                else:  # 如果没有专业，则使用描述的模糊匹配
                    sql_conditions = [build_synonym_sql_conditions('SR.DESCRIPTION', search_term)]

                sql_conditions.append(f"SR.LINENUM = '{line_num}'")
                where_clause = " AND ".join(sql_conditions)
                sql = f"""SELECT OWNERGROUP, COUNT(*) AS CNT FROM MAXIMO.SR SR 
                          WHERE {where_clause} AND OWNERGROUP IS NOT NULL
                          GROUP BY OWNERGROUP ORDER BY CNT DESC FETCH FIRST 5 ROWS ONLY"""
                result_df = pd.read_sql(sql, conn)

            # ----------------------------------------------------------------
            # 步骤 2: 智能降级 (Fallback)，如果精确查询无果
            # ----------------------------------------------------------------
            if result_df.empty:
                if line_num:
                    show_debug(f"精确查询无结果，自动升级为全系统范围查询...")
                    is_fallback = True
                else:
                    show_debug("正在进行全系统范围查询...")

                # 采用“多重尝试”策略进行更广泛的搜索
                # 尝试1：按专业精确匹配
                if entities.get('specialty'):
                    where_clause_fallback = f"SR.SPECIALTY = '{normalize_text(entities.get('specialty'))}'"
                    sql_fallback = f"""SELECT OWNERGROUP, COUNT(*) AS CNT FROM MAXIMO.SR SR 
                                        WHERE {where_clause_fallback} AND OWNERGROUP IS NOT NULL
                                        GROUP BY OWNERGROUP ORDER BY CNT DESC FETCH FIRST 5 ROWS ONLY"""
                    result_df = pd.read_sql(sql_fallback, conn)

                # 尝试2：如果按专业还是找不到，则按描述模糊匹配
                if result_df.empty:
                    show_debug("按专业精确匹配失败，降级为按描述模糊匹配...")
                    where_clause_fallback = build_synonym_sql_conditions('SR.DESCRIPTION', search_term)
                    sql_fallback = f"""SELECT OWNERGROUP, COUNT(*) AS CNT FROM MAXIMO.SR SR 
                                       WHERE {where_clause_fallback} AND OWNERGROUP IS NOT NULL
                                       GROUP BY OWNERGROUP ORDER BY CNT DESC FETCH FIRST 5 ROWS ONLY"""
                    result_df = pd.read_sql(sql_fallback, conn)

        # ----------------------------------------------------------------
        # 步骤 3: 根据查询结果，生成智能化的报告
        # ----------------------------------------------------------------
        st.markdown(f"### 📋 **{search_term}** 的责任归属分析")

        if result_df.empty:
            st.warning(f"数据库中未找到与“{search_term}”相关的任何历史处理班组记录。")
        else:
            top_group = result_df.iloc[0]['OWNERGROUP']

            # 根据是否为降级查询，给出不同措辞的推荐
            if is_fallback:
                st.warning(f"注意：在 {line_num}号线 未找到精确记录。")
                st.info(f"**但在全系统范围内**，历史上最常处理“{search_term}”相关问题的班组是： **{top_group}**")
            else:
                line_context = f"在 {line_num}号线，" if line_num else ""
                st.success(f"根据历史数据，{line_context}最常处理此类问题的班组是： **{top_group}**")

            # 【强制要求】提供完整的排名列表作为数据支撑
            st.markdown("**相关班组处理次数排名:**")
            st.dataframe(
                result_df.rename(columns={'OWNERGROUP': '班组', 'CNT': '历史处理次数'}),
                use_container_width=True
            )

    except Exception as e:
        st.error(f"❌ 责任归属查询失败: {e}")
        st.exception(e)


# ================================================================================
# VITA v13.0.1 - "热修复"
# 模块5：主界面与交互逻辑
# ================================================================================

# ----------------------------------------------------------------
# 5.1 - 页面配置和初始化
# ----------------------------------------------------------------
# 设置页面标题、图标和布局
st.set_page_config(page_title="VITA 智履助手 v13.0", page_icon=" Phoenix ", layout="centered")

# 设置主标题和副标题
st.title("VITA 智履设备维护助手 v13.0")
st.caption("最终修正 | 功能完整 | 质量优先")

# 初始化聊天记录 (session_state)
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "您好，我是VITA v13.0，所有功能已按“最终修正”标准重构。请描述您的问题，我将为您提供诊断、统计或责任归属服务。"
    }]

# ----------------------------------------------------------------
# 5.2 - 聊天历史记录显示
# ----------------------------------------------------------------
# 循环遍历session_state中的所有消息，并将其显示在界面上
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # 根据消息内容的不同类型（文本或DataFrame）进行显示
        if "content" in message:
            st.markdown(message["content"])
        elif "dataframe" in message:
            st.dataframe(message["dataframe"], use_container_width=True)

# ----------------------------------------------------------------
# 5.3 - 用户输入处理与中央调度逻辑
# ----------------------------------------------------------------
if prompt := st.chat_input("例如：今天7号线有多少故障？或 ISCS工作站黑屏怎么办？"):
    # 1. 将用户的输入添加到聊天记录并立即显示
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. 开始处理流程，显示助手机器人占位符
    with st.chat_message("assistant"):
        # ✅ 【核心修正】---
        # 修正了对 NumPy 数组的布尔值判断逻辑
        if faiss_index is None or id_map is None:
            st.error("系统核心资源未加载成功，请检查配置文件和网络连接后刷新页面。")
        else:
            start_time = time.time()
            show_progress("🧠 正在启动全能解析器，请稍候...")

            # 3. 调用"大脑"：全能解析器
            parsed_result = call_all_in_one_parser(prompt)

            show_debug(f"解析完成，耗时: {time.time() - start_time:.2f}秒")
            # 【强制要求】默认展开显示解析器的JSON结果，让系统决策透明化
            with st.expander("显示解析器JSON结果", expanded=True):
                st.json(parsed_result)

            # 4. 从解析结果中提取核心指令
            intent = parsed_result.get("intent")
            entities = parsed_result.get("entities", {})

            # 5. 【最终架构】使用字典分派模式，调用对应的功能模块
            # 定义一个意图到函数的映射字典
            intent_actions = {
                "statistics": lambda: query_statistics(entities, parsed_result.get("query_type")),
                "responsibility": lambda: query_responsibility(entities),
                "diagnosis": lambda: diagnose_fault(entities, prompt, faiss_index, id_map),
                "error": lambda: st.error(f"解析器调用失败: {parsed_result.get('error_message', '未知错误')}")
            }

            # 尝试从字典中获取并执行与意图对应的函数
            action = intent_actions.get(intent)

            if action:
                action()  # 执行匹配到的函数
            else:
                # 如果意图不在我们的预期列表里，给出明确的错误提示
                st.error(f"无法理解返回的意图: '{intent}'。请检查Prompt或模型输出。")

# ----------------------------------------------------------------
# 5.4 - 侧边栏信息
# ----------------------------------------------------------------
with st.sidebar:
    st.header("VITA v13.0")
    st.caption("最终修正版")
    st.markdown("---")
    st.markdown("""
    **核心原则:**
    - ✅ **上下文感知**: 检索注入时空坐标，提升相关性。
    - ✅ **智能追问**: 在信息不足或存在歧义时，主动发起澄清。
    - ✅ **履历分析**: 追溯设备历史，给出战略性建议。
    - ✅ **分级知识**: 优先SOP > 通用指南 > AI建议。
    - ✅ **智能降级**: 在精确查询无果时，自动扩大范围。
    - ✅ **数据支撑**: 所有结论都附有详细的数据列表。
    """)
    st.markdown("---")
    # 显示当前使用的模型
    st.info("当前模型: **内网 GLM4.5**")