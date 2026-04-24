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
# 配置
# ============================================
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "10.97.4.7:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# 内网模型API配置
LLM_API_URL = os.getenv("VITA_LLM_URL") or os.getenv("LLM_URL") or "http://10.96.158.22:8000/v1"
LLM_API_KEY = os.getenv("VITA_LLM_KEY") or os.getenv("LLM_KEY") or "hebz9jMiWwkqiV2NTDE1AiBEKj_Sz0Ga"
LLM_MODEL = os.getenv("VITA_LLM_MODEL") or os.getenv("LLM_MODEL") or "gemma-4-31b-it"
EMBEDDING_API_URL = "http://10.98.12.69:8080/embed"
RERANK_API_URL = "http://10.98.12.69:8081/rerank"

INDEX_FILE = "kb_zhipu.index"
ID_MAP_FILE = "kb_zhipu_id_map.npy"

# ==============================================================================
# 同义词映射配置 - 核心统一标准
# ==============================================================================
SYNONYM_MAP = {
    # 线路统一标准：全部转换为阿拉伯数字
    "一号线": "1号线", "二号线": "2号线", "三号线": "3号线", "四号线": "4号线",
    "五号线": "5号线", "六号线": "6号线", "七号线": "7号线", "八号线": "8号线",
    "九号线": "9号线", "十号线": "10号线",
    "十一号线": "11号线", "十二号线": "12号线", "十三号线": "13号线",
    "十四号线": "14号线", "十五号线": "15号线", "十六号线": "16号线",
    "十七号线": "17号线", "十八号线": "18号线", "十九号线": "19号线",
    "二十号线": "20号线",

    # 系统统一标准：全部转换为ISCS
    "综合监控": "ISCS",
    "综合监控系统": "ISCS",
    "综合监控设备": "ISCS设备",
    "ISCS系统": "ISCS",
}

# 生成反向同义词（用于数据库结果标准化）
REVERSE_SYNONYM_PATTERNS = [
    (r'([一二三四五六七八九十]+)号线', lambda m: SYNONYM_MAP.get(m.group(0), m.group(0))),
    (r'综合监控', 'ISCS'),
]

# ==============================================================================
# 歧义识别配置
# ==============================================================================
AMBIGUITY_DICT = {
    "电脑": '检测到模糊词"电脑"，请明确是哪个系统的电脑？(例如: ISCS工作站, PIS播放主机, 安防电脑)',
    "屏幕": '检测到模糊词"屏幕"，请明确是哪个设备的屏幕？(例如: ISCS大屏, 站台PIS屏, 车载PIS屏)',
    "灯": '检测到模糊词"灯"，请明确是哪种灯？(例如: 站台导向灯, 区间照明灯, 广告灯箱)',
    "门": '检测到模糊词"门"，请明确是哪种门？(例如: 屏蔽门, 门禁, 紧急疏散门)',
}

AMBIGUITY_RESOLUTION = {
    "电脑": ["工作站", "主机", "服务器", "客户端", "PC", "ISCS", "PIS", "AFC", "BAS", "FAS", "安防"],
    "屏幕": ["大屏", "显示屏", "PIS屏", "监视器", "触摸屏", "ISCS"],
    "灯": ["导向灯", "照明灯", "应急灯", "指示灯", "灯箱", "广告"],
    "门": ["屏蔽门", "门禁", "疏散门", "卷帘门", "扇门"],
}

KEYWORD_RULES = {
    "ISCS": {'专业': 'ISCS设备', '设备': 'ISCS'},
    "ISCS工作站": {'专业': 'ISCS设备', '设备': 'ISCS工作站'},
    "房建结构": {'专业': '房建结构', '设备': '房建结构'},
    "低压供电": {'专业': '低压供电设备', '设备': '低压供电'},
    "通风空调": {'专业': '通风空调设备', '设备': '通风空调'},
    "高压供电": {'专业': '高压供电设备', '设备': '高压供电'},
    "气体灭火": {'专业': '气体灭火设备', '设备': '气体灭火'},
    "广告灯箱": {'专业': '广告灯箱设备', '设备': '广告灯箱'},
    "AFC": {'专业': 'AFC设备', '设备': 'AFC'},
    "电扶梯": {'专业': '电扶梯设备', '设备': '电扶梯'},
    "FAS": {'专业': 'FAS设备', '设备': 'FAS'},
    "给排水": {'专业': '给排水设备', '设备': '给排水'},
    "屏蔽门": {'专业': '屏蔽门设备', '设备': '屏蔽门'},
    "电客车": {'专业': '电客车', '设备': '电客车'},
    "安检仪": {'专业': '安检仪设备', '设备': '安检仪'},
    "BAS": {'专业': 'BAS设备', '设备': 'BAS'},
    "接触网": {'专业': '接触网设备', '设备': '接触网'},
    "蓄电池": {'专业': '蓄电池设备（综合维修）', '设备': '蓄电池'},
    "非运营": {'专业': '非运营设备', '设备': '非运营'},
    "通信": {'专业': '通信设备', '设备': '通信'},
    "门禁": {'专业': '门禁设备', '设备': '门禁'},
    "信号": {'专业': '信号设备', '设备': '信号'},
    "轨道": {'专业': '轨道设备', '设备': '轨道'},
}

ALL_SPECIALTIES = [
    "ISCS设备", "通信设备", "AFC设备", "屏蔽门设备", "电扶梯设备",
    "FAS设备", "BAS设备", "给排水设备", "气体灭火设备", "低压供电设备",
    "高压供电设备", "通风空调设备", "信号设备", "接触网设备", "轨道设备",
    "电客车", "门禁设备", "安检仪设备", "房建结构", "非运营设备"
]

# ============================================
# 页面配置 & 初始化
# ============================================
st.set_page_config(page_title="VITA 智履助手", page_icon="🔧", layout="centered")
st.title("VITA 智履设备维护助手")
st.caption("AI专家诊断 + 智能追问 + 数据统计 | 实时连接 Maximo 服务器")


# ============================================
# 工具函数
# ============================================
def show_progress(message):
    """显示进度信息"""
    st.markdown(f"*📍 {message}*")


def show_debug(message, elapsed_time=None):
    """显示调试信息（小字体斜体）"""
    if elapsed_time:
        st.markdown(f"<small><i>🔍 {message} (耗时: {elapsed_time:.2f}秒)</i></small>", unsafe_allow_html=True)
    else:
        st.markdown(f"<small><i>🔍 {message}</i></small>", unsafe_allow_html=True)


def normalize_text(text):
    """
    深度同义词标准化 - 适用于所有文本
    这个函数会在用户输入、数据库查询、知识库检索时统一调用
    """
    if not text or not isinstance(text, str):
        return text

    normalized = text

    # Step 1: 应用同义词映射表
    for synonym, standard in SYNONYM_MAP.items():
        normalized = normalized.replace(synonym, standard)

    # Step 2: 应用正则表达式模式
    for pattern, replacement in REVERSE_SYNONYM_PATTERNS:
        if callable(replacement):
            normalized = re.sub(pattern, replacement, normalized)
        else:
            normalized = re.sub(pattern, replacement, normalized)

    return normalized


def normalize_dataframe(df, columns):
    """
    标准化DataFrame中指定列的文本
    确保数据库返回的数据也应用同义词转换
    """
    df_copy = df.copy()
    for col in columns:
        if col in df_copy.columns:
            df_copy[col] = df_copy[col].apply(lambda x: normalize_text(str(x)) if pd.notna(x) else x)
    return df_copy


def build_synonym_sql_conditions(field_name, search_term):
    """
    构建包含同义词的SQL查询条件
    例如：查询"综合监控"时，自动包含"ISCS"的结果
    """
    normalized_term = normalize_text(search_term)

    # 找出所有可能的同义词
    all_variants = [normalized_term]
    for synonym, standard in SYNONYM_MAP.items():
        if standard == normalized_term or synonym == search_term:
            all_variants.append(synonym)
            all_variants.append(standard)

    # 去重
    all_variants = list(set(all_variants))

    # 构建OR条件
    conditions = [f"UPPER({field_name}) LIKE UPPER('%{variant}%')" for variant in all_variants]

    return f"({' OR '.join(conditions)})"


@st.cache_resource
def initialize_resources():
    start_time = time.time()
    try:
        oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
        if not os.path.exists(INDEX_FILE):
            st.error(f"找不到: {INDEX_FILE}")
            return None, None
        index = faiss.read_index(INDEX_FILE)
        id_map = np.load(ID_MAP_FILE, allow_pickle=True)
        return index, id_map
    except Exception as e:
        st.error(f"初始化失败: {e}")
        return None, None


faiss_index, id_map = initialize_resources()


# ============================================
# LLM调用
# ============================================
def call_llm(prompt, timeout=90, max_retries=2):
    """调用内网LLM生成专家报告（OpenAI兼容格式）"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LLM_API_KEY}'
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_completion_tokens": 16000,
        "temperature": 0.0,
        "top_p": 0,
        "enable_thinking": True
    }

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                show_debug(f"第 {attempt + 1} 次尝试...")

            response = requests.post(f"{LLM_API_URL}/chat/completions", headers=headers, data=json.dumps(payload), timeout=timeout)
            response.raise_for_status()
            result = response.json()

            # OpenAI兼容格式解析
            full_text = result['choices'][0]['message']['content']
            if "</think>" in full_text:
                return full_text.split("</think>")[-1].strip()
            return full_text.strip()
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                show_debug(f"⏱️ 请求超时，正在重试... ({attempt + 1}/{max_retries})")
                continue
            else:
                st.error(f"❌ LLM调用超时（已重试{max_retries}次），请稍后重试")
                return None
        except Exception as e:
            if attempt < max_retries - 1:
                show_debug(f"❌ 调用失败: {str(e)[:100]}，正在重试...")
                continue
            else:
                st.error(f"❌ LLM调用失败: {e}")
                return None

    return None


def get_embedding(text, timeout=30):
    """调用内网Embedding模型获取向量"""
    headers = {
        'Content-Type': 'application/json'
    }
    payload = {
        "inputs": text
    }

    try:
        response = requests.post(EMBEDDING_API_URL, headers=headers, data=json.dumps(payload), timeout=timeout)
        response.raise_for_status()
        # 返回embedding向量
        return response.json()
    except Exception as e:
        st.error(f"❌ Embedding调用失败: {e}")
        return None


def rerank_results(query, texts, timeout=30):
    """调用内网Rerank模型重排序结果"""
    headers = {
        'Content-Type': 'application/json'
    }
    payload = {
        "query": query,
        "texts": texts
    }

    try:
        response = requests.post(RERANK_API_URL, headers=headers, data=json.dumps(payload), timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        show_debug(f"Rerank调用失败: {str(e)[:50]}，使用原始排序")
        return None


# ============================================
# 查询意图识别
# ============================================
def identify_query_intent(user_query):
    """识别查询意图：故障诊断、统计查询、责任归属"""
    stat_keywords = ["多少", "有几个", "几次", "统计", "哪个站", "哪条线", "最多", "排名"]
    responsibility_keywords = ["报给谁", "谁负责", "哪个部门", "归谁管", "谁处理"]

    query_lower = user_query.lower()

    if any(kw in query_lower for kw in responsibility_keywords):
        return "responsibility"
    elif any(kw in query_lower for kw in stat_keywords):
        return "statistics"
    else:
        return "diagnosis"


# ============================================
# 核心引擎
# ============================================
def preprocess_query_local(user_query):
    """本地关键词匹配（已标准化的查询）"""
    sorted_rules = sorted(KEYWORD_RULES.items(), key=lambda x: len(x[0]), reverse=True)

    for keyword, info in sorted_rules:
        if keyword in user_query or keyword.lower() in user_query.lower():
            extracted_info = info.copy()
            extracted_info["故障现象"] = user_query
            show_debug(f"命中关键词: '{keyword}'")
            return extracted_info

    show_debug("未匹配到关键词，需要追问")
    return None


def diagnose_fault(user_query, faiss_index, id_map):
    """场景1和2：故障诊断 - 深度同义词处理版"""

    show_progress("🔄 正在标准化查询...")
    start_total = time.time()

    # Step 0: 标准化用户输入
    normalized_query = normalize_text(user_query)
    show_debug(f"标准化后: {normalized_query}", 0.001)

    # Step 1: 本地关键词匹配
    show_progress("🔍 正在分析设备类型...")
    start_step = time.time()
    extracted_info = preprocess_query_local(normalized_query)
    show_debug("本地关键词匹配完成", time.time() - start_step)

    if not extracted_info:
        msg = "未能识别设备类型，请您提供以下信息：\n\n"
        msg += "1. 线别和站名（例如：11号线神童泾站 或 十一号线神童泾站）\n"
        msg += "2. 具体位置（例如：站厅层、站台、车控室）\n"
        msg += f"3. 设备类型（例如：{', '.join(ALL_SPECIALTIES[:5])}）\n\n"
        msg += "或直接完整描述：\"11号线XX站的ISCS黑屏了\""
        st.markdown(msg)  # 立即显示
        st.session_state.messages.append({"role": "assistant", "content": msg})
        return

    try:
        # Step 2: 构建查询并向量检索（使用标准化后的文本）
        show_progress("📚 正在检索知识库...")
        start_step = time.time()

        query_parts = [
            f"专业:{normalize_text(extracted_info.get('专业', '未知'))}",
            f"设备:{normalize_text(extracted_info.get('设备', '未知'))}",
            f"故障:{normalize_text(extracted_info.get('故障现象', normalized_query))}"
        ]
        rich_query = " | ".join(query_parts)
        show_debug(f"向量检索语句: {rich_query}")

        # 使用内网Embedding API
        query_embedding = get_embedding(rich_query)
        if query_embedding is None:
            st.error("❌ 无法获取查询向量")
            return

        distances, indices = faiss_index.search(
            np.array([query_embedding], dtype='float32'),
            k=50  # 扩充到50条，为rerank做准备
        )
        ticket_ids = tuple(str(tid) for tid in id_map[indices[0]])
        show_debug(f"向量检索完成，找到 {len(ticket_ids)} 个候选案例", time.time() - start_step)

        # Step 3: 数据库查询（带同义词扩展）
        show_progress("💾 正在查询 Maximo 历史案例...")
        start_step = time.time()

        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            if not ticket_ids:
                st.warning("向量搜索未返回结果")
                return

            sql_placeholder = ", ".join([f"'{tid}'" for tid in ticket_ids])

            # 使用同义词扩展的SQL查询
            specialty_condition = build_synonym_sql_conditions('SR.SPECIALTY', extracted_info.get('专业', ''))

            sql = f"""
            SELECT 
                SR.TICKETID,
                SR.DESCRIPTION,
                SR.REPORTDATE,
                COALESCE(LOC.DESCRIPTION, SR.LOCATION, '未明确记录') AS LOCATION_DESC,
                SR.SPECIALTY,
                SR.ASSETNUM,
                SR.LOCATION,
                COALESCE(SR.SOLUTION, SR.PROCREMEDY, '未记录') AS SOLUTION
            FROM MAXIMO.SR SR
            LEFT JOIN MAXIMO.LOCATIONS LOC ON SR.LOCATION = LOC.LOCATION
            WHERE SR.TICKETID IN ({sql_placeholder})
            """

            cases_df = pd.read_sql(sql, conn)

            # 对返回的数据应用标准化
            cases_df = normalize_dataframe(cases_df, ['DESCRIPTION', 'SPECIALTY', 'LOCATION_DESC', 'SOLUTION'])

            cases_df['TICKETID'] = pd.Categorical(
                cases_df['TICKETID'],
                categories=ticket_ids,
                ordered=True
            )
            cases_df = cases_df.sort_values('TICKETID')

        show_debug(f"数据库查询完成，检索到 {len(cases_df)} 条记录 (已应用同义词标准化)", time.time() - start_step)

        # 筛选有效案例（排除"其他"）
        curated_df = cases_df[
            ~cases_df['SOLUTION'].str.contains('其他|未记录|无', case=False, na=False) &
            (cases_df['SOLUTION'].str.len() > 3)
            ].copy()

        show_debug(f"筛选后有效案例: {len(curated_df)} 条 (已排除'其他'类)")

        # Step 3.5: 使用Rerank模型重排序（优化检索质量）
        if len(curated_df) > 0:
            show_progress("🎯 正在使用AI重排序优化结果...")
            start_step = time.time()

            # 构建rerank文本列表
            rerank_texts = []
            for idx, row in curated_df.head(30).iterrows():  # 取前30条进行rerank
                text = f"{row['DESCRIPTION']} {row['SOLUTION']}"
                rerank_texts.append(text)

            # 调用rerank API
            rerank_result = rerank_results(rich_query, rerank_texts)
            if rerank_result:
                try:
                    # 根据rerank结果重新排序
                    # rerank_result应该返回排序后的索引或分数
                    if isinstance(rerank_result, list) and len(rerank_result) > 0:
                        # 假设返回格式为 [{"index": 0, "score": 0.95}, ...]
                        sorted_indices = [item.get('index', i) for i, item in enumerate(rerank_result)]
                        curated_df_temp = curated_df.head(30).iloc[sorted_indices].copy()
                        # 合并未rerank的部分
                        if len(curated_df) > 30:
                            curated_df = pd.concat([curated_df_temp, curated_df.iloc[30:]], ignore_index=True)
                        else:
                            curated_df = curated_df_temp.reset_index(drop=True)
                        show_debug(f"Rerank重排序完成，结果已优化", time.time() - start_step)
                except Exception as e:
                    show_debug(f"Rerank结果解析失败: {str(e)[:50]}，使用原始排序")
            else:
                show_debug("Rerank跳过，使用向量相似度排序")

        if curated_df.empty:
            msg = "未找到包含明确解决方案的相似案例。\n\n建议：\n1. 更换关键词重新描述\n2. 联系专业维护人员"
            st.markdown(msg)  # 立即显示
            st.session_state.messages.append({"role": "assistant", "content": msg})
            return

        # Step 4: 统计分析 - 基于20条案例
        show_progress("📊 正在统计历史修复方式（大数原则）...")
        start_step = time.time()

        top_case = curated_df.iloc[0].to_dict()

        # 统计修复方式（严格排除"其他"）
        solution_stats = {}
        keywords = ['重启', '更换', '调整', '清洁', '紧固', '检查', '复位', '参数设置', '软件升级', '重新配置', '校准',
                    '修复']

        for idx, row in curated_df.head(20).iterrows():
            solution_text = str(row['SOLUTION'])

            # 跳过包含"其他"的记录
            if '其他' in solution_text:
                continue

            found = False
            for key in keywords:
                if key in solution_text:
                    if key not in solution_stats:
                        solution_stats[key] = {'count': 0, 'cases': []}
                    solution_stats[key]['count'] += 1
                    report_date = str(row['REPORTDATE'])[:10] if row['REPORTDATE'] and str(
                        row['REPORTDATE']) != 'NaT' else '日期未知'
                    location = str(row['LOCATION_DESC'])[:20]
                    solution = str(solution_text)[:30]
                    case_desc = f"{report_date} | {location} | {solution}"
                    solution_stats[key]['cases'].append(case_desc)
                    found = True
                    break

        # 找出最多的修复方式
        sorted_stats = sorted(solution_stats.items(), key=lambda x: x[1]['count'], reverse=True)

        if not sorted_stats:
            msg = "⚠️ 历史案例中没有找到有效的修复方式统计\n\n可能原因：\n• 该故障类型较新，历史记录较少\n• 历史记录中缺少详细的处理方案\n\n建议联系专业维护人员处理。"
            st.markdown(msg)  # 立即显示
            st.session_state.messages.append({"role": "assistant", "content": msg})
            return

        most_common_method = sorted_stats[0][0]
        most_common_count = sorted_stats[0][1]['count']

        show_debug(f"统计完成，最常用修复方式: **{most_common_method}** ({most_common_count}次)",
                   time.time() - start_step)

        # Step 5: 推荐同设备案例
        show_progress("🔗 正在查找同设备相关案例...")
        start_step = time.time()

        same_device_cases = []
        related_device_cases = []

        if pd.notna(top_case.get('ASSETNUM')) and top_case.get('ASSETNUM') and str(top_case.get('ASSETNUM')) != '':
            # 查找同设备同地点的故障
            same_location_device = curated_df[
                (curated_df['ASSETNUM'] == top_case['ASSETNUM']) &
                (curated_df['LOCATION'] == top_case['LOCATION']) &
                (curated_df['TICKETID'] != top_case['TICKETID'])
                ]
            if len(same_location_device) > 0:
                same_device_cases = same_location_device.head(3).to_dict('records')
                show_debug(f"找到 {len(same_device_cases)} 个同设备同地点案例")

            # 如果没有同地点的，找同设备其他地点故障
            if not same_device_cases:
                same_device = curated_df[
                    (curated_df['ASSETNUM'] == top_case['ASSETNUM']) &
                    (curated_df['TICKETID'] != top_case['TICKETID'])
                    ]
                if len(same_device) > 0:
                    related_device_cases = same_device.head(3).to_dict('records')
                    show_debug(f"找到 {len(related_device_cases)} 个同设备其他地点案例")

        show_debug(f"同设备案例查找完成", time.time() - start_step)

        # Step 6: 生成AI诊断报告
        show_progress("🤖 正在生成 AI 专家诊断报告...")
        start_step = time.time()

        # 构建统计文本（简化版）
        stats_text = ""
        for method, info in sorted_stats[:3]:  # 只取前3个
            stats_text += f"• **{method}**: {info['count']}次\n"

        # 构建同设备案例文本（简化版）
        device_recommendation = ""
        if same_device_cases:
            device_recommendation = "\n**同设备同地点案例：**\n"
            case = same_device_cases[0]  # 只取第1个
            device_recommendation += f"• {case['DESCRIPTION'][:40]} → {case['SOLUTION'][:40]}\n"
        elif related_device_cases:
            device_recommendation = "\n**同设备其他案例：**\n"
            case = related_device_cases[0]  # 只取第1个
            device_recommendation += f"• {case['DESCRIPTION'][:40]} → {case['SOLUTION'][:40]}\n"

        top_case_date = str(top_case['REPORTDATE'])[:10] if top_case['REPORTDATE'] and str(
            top_case['REPORTDATE']) != 'NaT' else '日期未知'

        # 精简prompt，减少token数量，让回答更流畅自然
        report_prompt = f"""你是经验丰富的地铁运维专家，用自然流畅的语言给一线工程师提供实用建议。

【用户问题】"{user_query}"

【最相似案例】
{top_case_date} | {top_case['LOCATION_DESC']}
故障：{top_case['DESCRIPTION'][:60]}
处理：{top_case['SOLUTION'][:120]}

【历史统计（20案例）】
{stats_text}
最常用：{most_common_method}（{most_common_count}次成功）

{device_recommendation}

请用自然、专业但易懂的语言，按以下结构输出：

### 🔧 VITA 专家诊断

**最近一次怎么修的？**

{top_case_date}在{top_case['LOCATION_DESC']}遇到过类似问题。当时的故障表现是{top_case['DESCRIPTION'][:50]}，最后通过{top_case['SOLUTION'][:80]}解决了。

**历史上大家都怎么处理？**

根据最近20个相似案例的统计：
{stats_text}

从历史数据看，**{most_common_method}**是最常用的方法，成功率最高（{most_common_count}次成功案例）。

{device_recommendation if device_recommendation else ""}

**我的建议**

1. **首先试试这个**：根据历史经验，建议先{most_common_method}。[用通俗易懂的语言描述具体步骤，2-3句话]

2. **如果不行**：[给出第二选择的简短建议，1-2句话]

3. **需要准备**：[简单说明可能需要的工具或备件]

---
*{datetime.now().strftime('%Y-%m-%d %H:%M')} | VITA v6.3*
"""

        report = call_llm(report_prompt, timeout=90, max_retries=2)
        show_debug(f"AI报告生成完成", time.time() - start_step)

        if report:
            # 使用容器确保内容显示
            with st.container():
                st.markdown(report)
            st.session_state.messages.append({"role": "assistant", "content": report})

            # 显示历史案例表格
            display_columns = {
                'TICKETID': '单号',
                'REPORTDATE': '时间',
                'LOCATION_DESC': '地点',
                'DESCRIPTION': '现象',
                'SOLUTION': '处理方法'
            }
            available_cols = [col for col in display_columns.keys() if col in curated_df.columns]
            display_df = curated_df.head(10)[available_cols].copy()

            # 格式化日期
            if 'REPORTDATE' in display_df.columns:
                display_df['REPORTDATE'] = display_df['REPORTDATE'].apply(
                    lambda x: str(x)[:10] if pd.notna(x) and str(x) != 'NaT' else '未知'
                )

            # 截断长文本
            if 'DESCRIPTION' in display_df.columns:
                display_df['DESCRIPTION'] = display_df['DESCRIPTION'].apply(
                    lambda x: str(x)[:50] + '...' if len(str(x)) > 50 else str(x)
                )
            if 'SOLUTION' in display_df.columns:
                display_df['SOLUTION'] = display_df['SOLUTION'].apply(
                    lambda x: str(x)[:50] + '...' if len(str(x)) > 50 else str(x)
                )

            display_df = display_df.rename(columns={k: display_columns[k] for k in available_cols})

            # 使用容器显示表格
            with st.container():
                st.dataframe(display_df, use_container_width=True)
            st.session_state.messages.append({"role": "assistant", "dataframe": display_df})

            show_debug(f"✅ 诊断完成，总耗时: {time.time() - start_total:.2f}秒")
        else:
            # 即使AI失败，也给出基础建议
            fallback_msg = f"""### 🔧 基础诊断建议

**根据历史数据分析：**

**最相似案例：**
• 时间: {top_case_date}
• 地点: {top_case['LOCATION_DESC']}
• 处理: {top_case['SOLUTION'][:100]}

**历史统计显示：**
最常用的解决方法是 **{most_common_method}**（{most_common_count}次成功）

**建议：**
1. 优先尝试：{most_common_method}
2. 如果问题持续，参考下方历史案例表格
3. 联系专业维护人员

*AI详细报告生成失败，以上是基于数据的基础建议*
"""
            # 立即显示降级建议
            st.markdown(fallback_msg)
            st.session_state.messages.append({"role": "assistant", "content": fallback_msg})

            # 仍然显示历史案例表格
            display_columns = {
                'TICKETID': '单号',
                'REPORTDATE': '时间',
                'LOCATION_DESC': '地点',
                'DESCRIPTION': '现象',
                'SOLUTION': '处理方法'
            }
            available_cols = [col for col in display_columns.keys() if col in curated_df.columns]
            display_df = curated_df.head(10)[available_cols].copy()

            if 'REPORTDATE' in display_df.columns:
                display_df['REPORTDATE'] = display_df['REPORTDATE'].apply(
                    lambda x: str(x)[:10] if pd.notna(x) and str(x) != 'NaT' else '未知'
                )
            if 'DESCRIPTION' in display_df.columns:
                display_df['DESCRIPTION'] = display_df['DESCRIPTION'].apply(
                    lambda x: str(x)[:50] + '...' if len(str(x)) > 50 else str(x)
                )
            if 'SOLUTION' in display_df.columns:
                display_df['SOLUTION'] = display_df['SOLUTION'].apply(
                    lambda x: str(x)[:50] + '...' if len(str(x)) > 50 else str(x)
                )

            display_df = display_df.rename(columns={k: display_columns[k] for k in available_cols})

            # 立即显示表格
            st.dataframe(display_df, use_container_width=True)
            st.session_state.messages.append({"role": "assistant", "dataframe": display_df})

    except Exception as e:
        error_msg = f"❌ 处理失败: {str(e)}"
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        st.exception(e)


def query_statistics(user_query):
    """场景3：统计查询（带同义词处理）"""
    show_progress("📊 正在统计数据...")
    start_total = time.time()

    # 标准化查询
    normalized_query = normalize_text(user_query)
    show_debug(f"标准化查询: {normalized_query}", 0.001)

    try:
        # Step 1: 解析查询
        start_step = time.time()
        parse_prompt = f"""
你是数据分析助手，请从用户的查询中提取统计参数。

用户查询："{normalized_query}"

请提取以下信息并返回JSON格式：
1. specialty（专业名称，如：ISCS设备、AFC设备等，如果没提到返回null）
2. time_range（时间范围，如：今天、本周、上周、本月、上月，如果没提到返回null）
3. location（地点，如：某某站、某号线，如果没提到返回null）
4. status（状态，如：未关闭、已关闭、未修好，如果没提到返回"all"）
5. query_type（查询类型："count"表示数量统计，"ranking"表示排名）

只返回JSON，不要其他内容。
"""

        parse_result = call_llm(parse_prompt, timeout=30)
        show_debug("查询参数解析完成", time.time() - start_step)

        if not parse_result:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "查询解析失败，请重新描述您的问题"
            })
            return

        if "```json" in parse_result:
            parse_result = parse_result.split("```json")[1].split("```")[0]

        params = json.loads(parse_result)
        show_debug(f"解析参数: {params}")

        # Step 2: 构建SQL查询（带同义词扩展）
        start_step = time.time()
        sql_conditions = []
        sql_params = {}

        if params.get('specialty'):
            specialty = normalize_text(params['specialty'])
            # 使用同义词扩展查询
            specialty_condition = build_synonym_sql_conditions('SR.SPECIALTY', specialty)
            sql_conditions.append(specialty_condition)

        if params.get('time_range'):
            time_range = params['time_range']
            if time_range == '今天':
                sql_conditions.append("TRUNC(SR.REPORTDATE) = TRUNC(SYSDATE)")
            elif time_range == '本周':
                sql_conditions.append("TRUNC(SR.REPORTDATE) >= TRUNC(SYSDATE, 'IW')")
            elif time_range == '上周':
                sql_conditions.append(
                    "TRUNC(SR.REPORTDATE) >= TRUNC(SYSDATE - 7, 'IW') AND TRUNC(SR.REPORTDATE) < TRUNC(SYSDATE, 'IW')")
            elif time_range == '本月':
                sql_conditions.append("TRUNC(SR.REPORTDATE, 'MM') = TRUNC(SYSDATE, 'MM')")
            elif time_range == '上月':
                sql_conditions.append("TRUNC(SR.REPORTDATE, 'MM') = ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1)")

        if params.get('location'):
            location = normalize_text(params['location'])
            location_condition = build_synonym_sql_conditions('LOC.DESCRIPTION', location)
            sql_conditions.append(location_condition)

        status = params.get('status', 'all')
        if status == '未关闭' or status == '未修好':
            sql_conditions.append("SR.STATUS NOT IN ('CLOSED', 'RESOLVED')")
        elif status == '已关闭':
            sql_conditions.append("SR.STATUS IN ('CLOSED', 'RESOLVED')")

        where_clause = " AND ".join(sql_conditions) if sql_conditions else "1=1"

        sql = f"""
        SELECT 
            SR.TICKETID,
            SR.DESCRIPTION,
            TO_CHAR(SR.REPORTDATE, 'YYYY-MM-DD HH24:MI') AS REPORTDATE,
            SR.LOCATION AS LOCATION_CODE,
            LOC.DESCRIPTION AS LOCATION_NAME,
            SR.SPECIALTY,
            SR.STATUS,
            COALESCE(SR.SOLUTION, SR.PROCREMEDY, '未处理') AS SOLUTION
        FROM MAXIMO.SR SR
        LEFT JOIN MAXIMO.LOCATIONS LOC ON TRIM(SR.LOCATION) = TRIM(LOC.LOCATION)
        WHERE {where_clause}
        ORDER BY SR.REPORTDATE DESC
        """

        show_debug("SQL查询构建完成（已应用同义词扩展）")

        # Step 3: 执行查询
        show_progress("💾 正在连接Maximo服务器...")
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            result_df = pd.read_sql(sql, conn)

        # 标准化返回数据
        result_df = normalize_dataframe(result_df, ['DESCRIPTION', 'SPECIALTY', 'LOCATION_NAME', 'SOLUTION'])

        show_debug(f"数据库查询完成，共 {len(result_df)} 条记录（已标准化）", time.time() - start_step)

        result_df['LOCATION_DESC'] = result_df['LOCATION_NAME'].fillna(result_df['LOCATION_CODE']).fillna('未知地点')

        count = len(result_df)
        no_location_count = result_df['LOCATION_CODE'].isna().sum()

        # Step 4: 生成统计报告
        show_progress("📊 正在生成统计报告...")

        if count == 0:
            msg = f"📊 统计结果\n\n根据您的查询条件，未找到任何记录。\n\n*数据源: Maximo实时服务器*"
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.markdown(msg)
            show_debug(f"✅ 统计完成，总耗时: {time.time() - start_total:.2f}秒")
            return

        summary = f"📊 统计结果\n\n"

        if params.get('specialty'):
            summary += f"**{params['specialty']}专业** "

        if params.get('time_range'):
            summary += f"**{params['time_range']}** "

        if params.get('location'):
            summary += f"**{params['location']}** "

        if status == '未关闭' or status == '未修好':
            summary += f"共有 **{count}** 个未关闭的故障。"
        else:
            summary += f"共有 **{count}** 个故障记录。"

        if no_location_count > 0:
            summary += f"\n\n⚠️ 注意：其中 {no_location_count} 条记录没有地点信息。"

        if count > 0:
            summary += "\n\n**📈 简要分析：**\n"

            if 'STATUS' in result_df.columns:
                status_counts = result_df['STATUS'].value_counts()
                summary += f"• 状态分布：{', '.join([f'{k}({v}条)' for k, v in status_counts.head(3).items()])}\n"

            if 'LOCATION_DESC' in result_df.columns:
                location_with_data = result_df[result_df['LOCATION_DESC'] != '未知地点']
                if len(location_with_data) > 0:
                    location_counts = location_with_data['LOCATION_DESC'].value_counts()
                    top_location = location_counts.index[0]
                    summary += f"• 最多地点：{top_location}（{location_counts.iloc[0]}条）\n"

            if 'SPECIALTY' in result_df.columns:
                specialty_counts = result_df['SPECIALTY'].value_counts()
                if len(specialty_counts) > 0:
                    top_specialty = specialty_counts.index[0]
                    summary += f"• 最多专业：{top_specialty}（{specialty_counts.iloc[0]}条）\n"

        summary += f"\n*数据源: Maximo实时服务器 | 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 已应用同义词标准化*"

        # 立即显示文本结果
        st.markdown(summary)
        st.session_state.messages.append({"role": "assistant", "content": summary})

        # 准备表格数据
        display_result_df = result_df.copy()
        display_result_df['has_location'] = display_result_df['LOCATION_DESC'] != '未知地点'
        display_result_df = display_result_df.sort_values(['has_location', 'REPORTDATE'], ascending=[False, False])

        display_columns = {
            'TICKETID': '单号',
            'REPORTDATE': '报告时间',
            'LOCATION_DESC': '地点',
            'SPECIALTY': '专业',
            'DESCRIPTION': '故障描述',
            'STATUS': '状态',
            'SOLUTION': '处理'
        }

        available_cols = [col for col in display_columns.keys() if col in display_result_df.columns]
        display_df = display_result_df[available_cols].copy()

        # 截断长文本
        if 'DESCRIPTION' in display_df.columns:
            display_df['DESCRIPTION'] = display_df['DESCRIPTION'].apply(
                lambda x: str(x)[:40] + '...' if len(str(x)) > 40 else str(x)
            )
        if 'SOLUTION' in display_df.columns:
            display_df['SOLUTION'] = display_df['SOLUTION'].apply(
                lambda x: str(x)[:40] + '...' if len(str(x)) > 40 else str(x)
            )

        display_df = display_df.rename(columns={k: display_columns[k] for k in available_cols})

        # 立即显示表格
        st.dataframe(display_df, use_container_width=True)
        st.session_state.messages.append({"role": "assistant", "dataframe": display_df})

        show_debug(f"✅ 统计完成，总耗时: {time.time() - start_total:.2f}秒")

    except json.JSONDecodeError as e:
        error_msg = f"❌ 查询解析失败: {str(e)}\n\n请尝试更明确的表述，例如：\n• ISCS专业今天有多少个故障？\n• 本周AFC专业未关闭的故障有几个？"
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
    except Exception as e:
        error_msg = f"❌ 统计查询失败: {str(e)}"
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        st.exception(e)


def query_responsibility(user_query):
    """场景4：责任归属查询（带同义词处理）"""
    show_progress("👥 正在查询责任归属...")
    start_total = time.time()

    # 标准化查询
    normalized_query = normalize_text(user_query)
    show_debug(f"标准化查询: {normalized_query}", 0.001)

    try:
        # Step 1: 提取关键词
        start_step = time.time()
        parse_prompt = f"""
你是地铁运维专家，请从用户的查询中提取关键信息。

用户查询："{normalized_query}"

请提取设备或故障类型，只返回设备/故障的关键词，不要其他内容。
例如：
"电梯异响应该报给谁" → "电梯"
"屏蔽门故障归谁管" → "屏蔽门"
"ISCS系统问题找哪个部门" → "ISCS"
"""

        keyword = call_llm(parse_prompt, timeout=30)
        if keyword:
            keyword = normalize_text(keyword.strip())
        show_debug(f"关键词提取完成: {keyword}", time.time() - start_step)

        if not keyword:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "无法识别设备类型，请明确描述"
            })
            return

        # Step 2: 查询数据库（带同义词扩展）
        start_step = time.time()

        # 构建同义词扩展的查询条件
        description_condition = build_synonym_sql_conditions('SR.DESCRIPTION', keyword)
        specialty_condition = build_synonym_sql_conditions('SR.SPECIALTY', keyword)

        sql = f"""
        SELECT 
            SR.SPECIALTY,
            SR.OWNER,
            SR.OWNERGROUP,
            COUNT(*) AS CNT
        FROM MAXIMO.SR SR
        WHERE (
            {description_condition}
            OR {specialty_condition}
        )
        AND SR.OWNER IS NOT NULL
        GROUP BY SR.SPECIALTY, SR.OWNER, SR.OWNERGROUP
        ORDER BY COUNT(*) DESC
        FETCH FIRST 10 ROWS ONLY
        """

        show_debug("SQL查询构建完成（已应用同义词扩展）")

        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
            result_df = pd.read_sql(sql, conn)

        # 标准化返回数据
        result_df = normalize_dataframe(result_df, ['SPECIALTY'])

        show_debug(f"数据库查询完成，找到 {len(result_df)} 条记录（已标准化）", time.time() - start_step)

        if result_df.empty:
            msg = f"📋 责任归属查询结果\n\n未找到关于 **{keyword}** 的历史处理记录。\n\n建议：\n• 检查关键词是否正确\n• 联系调度中心确认\n\n*数据源: Maximo实时服务器 | 已应用同义词扩展*"
            st.markdown(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
            show_debug(f"✅ 查询完成，总耗时: {time.time() - start_total:.2f}秒")
            return

        total_cases = result_df['CNT'].sum()
        top_owner = result_df.iloc[0]

        report = f"📋 责任归属查询结果\n\n"
        report += f"根据历史记录，**{keyword}** 相关问题（共{total_cases}次）通常由以下人员/部门处理：\n\n"
        report += f"**👤 主要负责人：**\n"
        report += f"• 专业：{top_owner['SPECIALTY']}\n"

        if pd.notna(top_owner['OWNER']):
            report += f"• 负责人：{top_owner['OWNER']}\n"

        if pd.notna(top_owner['OWNERGROUP']):
            report += f"• 班组：{top_owner['OWNERGROUP']}\n"

        report += f"• 处理次数：{top_owner['CNT']}次（占{top_owner['CNT'] / total_cases * 100:.1f}%）\n"

        if len(result_df) > 1:
            report += f"\n**👥 其他相关人员：**\n"
            for idx, row in result_df.iloc[1:4].iterrows():
                owner_info = row['OWNER'] if pd.notna(row['OWNER']) else '未知'
                report += f"• {row['SPECIALTY']} - {owner_info}（{row['CNT']}次）\n"

        report += f"\n*数据源: Maximo实时服务器 | 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 已应用同义词标准化*"

        # 立即显示文本结果
        st.markdown(report)
        st.session_state.messages.append({"role": "assistant", "content": report})

        display_columns = {
            'SPECIALTY': '专业',
            'OWNER': '负责人',
            'OWNERGROUP': '班组',
            'CNT': '处理次数'
        }
        display_df = result_df[display_columns.keys()].rename(columns=display_columns)

        # 立即显示表格
        st.dataframe(display_df, use_container_width=True)
        st.session_state.messages.append({"role": "assistant", "dataframe": display_df})

        show_debug(f"✅ 查询完成，总耗时: {time.time() - start_total:.2f}秒")

    except Exception as e:
        error_msg = f"❌ 责任归属查询失败: {str(e)}"
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        st.exception(e)


# ============================================
# 聊天界面主逻辑
# ============================================
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": """您好，我是VITA智履维护助手 🔧

我可以帮您：

**1. 🔍 设备故障诊断**
告诉我故障现象，我会基于历史案例给出专家建议
试试问：“ISCS工作站死机了怎么办？”

**2. 📊 数据统计查询**
问我"2号线今天有多少故障"、"哪个专业故障最多"等统计问题

**3. 👥 责任归属查询**
问我"报给谁"、"谁负责"等归属问题

💡 *正在连接 Maximo 实时服务器，数据实时同步*
🔄 *已启用深度同义词标准化（线路、系统名称自动识别）*

请描述您的问题。"""
    }]

if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "content" in message:
            st.markdown(message["content"])
        elif "dataframe" in message:
            st.dataframe(message["dataframe"], use_container_width=True)

if prompt := st.chat_input("请输入您的问题..."):
    # 深度标准化用户输入
    normalized_prompt = normalize_text(prompt)

    # 先添加用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 立即显示用户消息
    with st.chat_message("user"):
        st.markdown(prompt)
        if normalized_prompt != prompt:
            show_debug(f"标准化为: {normalized_prompt}")

    # 处理回复 - 必须在新的上下文中
    with st.chat_message("assistant"):
        if st.session_state.pending_clarification:
            has_keyword = False
            for keyword in KEYWORD_RULES:
                if keyword in normalized_prompt or keyword.lower() in normalized_prompt.lower():
                    has_keyword = True
                    break

            if has_keyword:
                original_query = st.session_state.pending_clarification["original_query"]
                combined_query = f"{original_query} {normalized_prompt}"
                st.session_state.pending_clarification = None

                show_debug(f"合并查询: {combined_query}")
                diagnose_fault(combined_query, faiss_index, id_map)
            else:
                ambiguous_keywords_found = []
                for keyword in AMBIGUITY_DICT:
                    if keyword in normalized_prompt:
                        resolution_options = AMBIGUITY_RESOLUTION.get(keyword, [])
                        has_resolution = any(
                            res in normalized_prompt or res.lower() in normalized_prompt.lower()
                            for res in resolution_options
                        )
                        if not has_resolution:
                            ambiguous_keywords_found.append(keyword)

                if ambiguous_keywords_found:
                    if len(ambiguous_keywords_found) == 1:
                        question = AMBIGUITY_DICT[ambiguous_keywords_found[0]] + "\n\n"
                        question += "**同时也请告知：**\n"
                        question += "• 线别和站名（支持：11号线 或 十一号线）\n"
                        question += "• 具体位置（例如：站厅层、站台、车控室）"
                    else:
                        question = f"检测到 {len(ambiguous_keywords_found)} 个模糊词：\n\n"
                        for kw in ambiguous_keywords_found:
                            question += f"• {AMBIGUITY_DICT[kw]}\n"
                        question += "\n**同时也请告知：**\n"
                        question += "• 线别和站名（支持：11号线 或 十一号线）\n"
                        question += "• 具体位置（例如：站厅层、站台、车控室）"

                    # 立即显示追问
                    st.markdown(question)
                    st.session_state.messages.append({"role": "assistant", "content": question})
                else:
                    msg = "请提供更完整的信息：\n\n"
                    msg += "• 线别和站名（支持：11号线 或 十一号线）\n"
                    msg += "• 具体位置（例如：站厅层、站台、车控室）\n"
                    msg += "• 设备类型（支持：ISCS 或 综合监控、AFC等）"
                    # 立即显示提示
                    st.markdown(msg)
                    st.session_state.messages.append({"role": "assistant", "content": msg})

        else:
            intent = identify_query_intent(normalized_prompt)
            show_debug(f"识别查询意图: {intent}")

            if intent == "statistics":
                query_statistics(normalized_prompt)
            elif intent == "responsibility":
                query_responsibility(normalized_prompt)
            else:
                ambiguous_keywords_found = []
                for keyword in AMBIGUITY_DICT:
                    if keyword in normalized_prompt:
                        resolution_options = AMBIGUITY_RESOLUTION.get(keyword, [])
                        has_resolution = any(
                            res in normalized_prompt or res.lower() in normalized_prompt.lower()
                            for res in resolution_options
                        )
                        if not has_resolution:
                            ambiguous_keywords_found.append(keyword)

                if ambiguous_keywords_found:
                    if len(ambiguous_keywords_found) == 1:
                        question = AMBIGUITY_DICT[ambiguous_keywords_found[0]] + "\n\n"
                        question += "**同时也请告知：**\n"
                        question += "• 线别和站名（支持：11号线 或 十一号线）\n"
                        question += "• 具体位置（例如：站厅层、站台、车控室）"
                    else:
                        question = f"检测到 {len(ambiguous_keywords_found)} 个模糊词：\n\n"
                        for kw in ambiguous_keywords_found:
                            question += f"• {AMBIGUITY_DICT[kw]}\n"
                        question += "\n**同时也请告知：**\n"
                        question += "• 线别和站名（支持：11号线 或 十一号线）\n"
                        question += "• 具体位置（例如：站厅层、站台、车控室）"

                    st.session_state.pending_clarification = {"original_query": normalized_prompt}
                    # 立即显示追问
                    st.markdown(question)
                    st.session_state.messages.append({"role": "assistant", "content": question})
                else:
                    diagnose_fault(normalized_prompt, faiss_index, id_map)

with st.sidebar:
    st.header("💼 系统信息")

    if faiss_index:
        st.metric("知识库规模", f"{faiss_index.ntotal:,} 条案例")

    st.metric("数据源", "Maximo 实时服务器")
    st.caption("🔗 10.97.4.7:1521/eamprod")
    st.caption("🔄 实时同步 | 深度同义词标准化")

    st.markdown("---")

    st.header("⚙️ 核心功能")

    st.markdown("""
    ### 🔍 故障诊断
    **基于20条历史案例深度分析**
    - ✅ 最相似案例参考（黄金案例）
    - ✅ 历史修复方式统计（大数原则）
    - ✅ 最常用修复方式推荐（排除"其他"）
    - ✅ 同设备同地点故障关联
    - ✅ 同设备其他故障参考
    - ✅ AI专家综合处置建议

    **特色：**
    - 🎯 优先推荐历史成功率最高的方法
    - 🔗 智能关联同设备历史故障
    - 📊 数据驱动的决策支持

    ### 📊 数据统计
    **实时查询Maximo数据库**
    - 按专业/时间/地点统计
    - 故障趋势分析
    - 状态分布查询
    - 支持同义词智能识别

    ### 👥 责任归属
    **快速定位负责人**
    - 历史处理记录追溯
    - 责任部门识别
    - 处理频次统计
    - 多人协同情况分析

    ### 🤖 智能追问
    **自动识别模糊描述**
    - 歧义词检测
    - 引导补充关键信息
    - 上下文理解

    ### 🔄 同义词标准化
    **深度语义理解**
    - 线路：一号线 ↔ 1号线
    - 系统：综合监控 ↔ ISCS
    - 全流程应用（输入+数据库+知识库）
    """)

    st.markdown("---")
    st.caption(f"**VITA v7.0** | 更新: {datetime.now().strftime('%Y-%m-%d')}")
    st.caption("Powered by 内网GLM4.5 + Rerank重排序 + 向量检索 + 实时数据")
