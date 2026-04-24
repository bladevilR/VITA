# ================================================================================
# VITA v15.1 - 内网部署版（安全加固版）
# 第1段（共6段）：配置、工具函数、全局初始化
# ================================================================================

import streamlit as st
import faiss
import numpy as np
import pandas as pd
import oracledb
import requests
import json
import os
from datetime import datetime, timedelta
import time
import re
from typing import Dict, List, Optional, Tuple, Any, Callable
from functools import lru_cache
from collections import defaultdict
import logging

# 页面配置 - 必须是第一个 Streamlit 调用
st.set_page_config(
    page_title="VITA - 智能设备维护助手",
    page_icon="⚙",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ============================================
# 加载 .env 配置文件（如果存在）
# ============================================
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # 不覆盖已有环境变量
except ImportError:
    pass

# ============================================
# 日志配置
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('VITA')

# ============================================
# 配置区域（兼容 VITA_ 前缀和无前缀两种环境变量命名）
# ============================================
def _env(key: str, default: str = "") -> str:
    """读取环境变量，优先 VITA_ 前缀，其次无前缀，最后 fallback 默认值"""
    return os.getenv(f"VITA_{key}") or os.getenv(key) or default

DB_USER = _env("DB_USER", "maxsearch")
DB_PASSWORD = _env("DB_PASSWORD", "sZ36!mTrBxH")
DB_DSN = _env("DB_DSN", "10.97.4.7:1521/eamprod")
ORACLE_CLIENT_PATH = _env("ORACLE_CLIENT", "D:/instantclient/instantclient_23_9")

# 内网模型API配置
LLM_API_URL = _env("LLM_URL", "http://10.96.158.22:8000/v1")
LLM_API_KEY = _env("LLM_KEY", "hebz9jMiWwkqiV2NTDE1AiBEKj_Sz0Ga")
LLM_MODEL = _env("LLM_MODEL", "gemma-4-31b-it")

# 备用LLM配置
LLM_FALLBACK_URL = _env("LLM_FALLBACK_URL", "http://10.96.158.22:8000/v1")
LLM_FALLBACK_KEY = _env("LLM_FALLBACK_KEY", "hebz9jMiWwkqiV2NTDE1AiBEKj_Sz0Ga")
LLM_FALLBACK_MODEL = _env("LLM_FALLBACK_MODEL", "gemma-4-31b-it")

EMBEDDING_API_URL = _env("EMBEDDING_URL", "http://10.98.12.69:8080/embed")
RERANK_API_URL = _env("RERANK_URL", "http://10.98.12.69:8081/rerank")

INDEX_FILE = _env("INDEX_FILE", "kb_zhipu.index")
ID_MAP_FILE = _env("ID_MAP_FILE", "kb_zhipu_id_map.npy")

GENERAL_GUIDE_LINK = "http://ecm.sz-mtr.com/preview.html?fileid=7479483"

# API重试配置
MAX_RETRIES = int(_env("MAX_RETRIES", "2"))
RETRY_DELAY = float(_env("RETRY_DELAY", "1.0"))

# 数据库连接池配置
DB_POOL_MIN = int(_env("DB_POOL_MIN", "2"))
DB_POOL_MAX = int(_env("DB_POOL_MAX", "10"))
DB_POOL_INCREMENT = int(_env("DB_POOL_INCREMENT", "1"))
DB_CONNECT_TIMEOUT = int(_env("DB_CONNECT_TIMEOUT", "8"))  # TCP连接超时（秒）

# ============================================
# 统一同义词配置（完整版）
# ============================================
SPECIALTY_SYNONYMS = {
    'ISCS': ['ISCS', 'ISCS设备', '综合监控', '综合监控设备', '综监', 'ISCS系统', '综合监控系统'],
    '屏蔽门': ['屏蔽门', '屏蔽门设备', '站台门', 'PSD', '站台屏蔽门', '安全门'],
    'AFC': ['AFC', 'AFC设备', '自动售检票', '售检票', '自动售票', '闸机', '出入闸机', '检票机'],
    'BAS': ['BAS', 'BAS设备', '环境监控', '环控系统', '环境与设备监控'],
    'FAS': ['FAS', 'FAS设备', '火灾报警', '消防系统', '火灾自动报警'],
    '门禁': ['门禁', '门禁设备', '门禁系统', '门禁通道门', '通道门', '出入口控制', '门禁控制'],
    '电扶梯': ['电扶梯', '电扶梯设备', '扶梯', '自动扶梯', '扶手电梯'],
    '给排水': ['给排水', '给排水设备', '给水排水'],
    '通风空调': ['通风空调', '通风空调设备', '环控', '空调通风', '暖通空调'],
    '低压供电': ['低压供电', '低压供电设备', '低压配电'],
    '高压供电': ['高压供电', '高压供电设备', '高压配电'],
    '房建': ['房建', '房建结构', '建筑结构', '土建'],
    '通信': ['通信', '通信设备', '通讯设备'],
    '信号': ['信号', '信号设备', '信号系统'],
    '安检': ['安检', '安检仪设备', '安检设备', '安全检查'],
}

# 按key长度降序排列，避免短子串先于长词匹配（如 "扶梯" 不应匹配 "电扶梯" 内部）
CORE_SYNONYM_MAP = [
    ("综合监控系统", "ISCS"),
    ("门禁通道门", "门禁设备"),
    ("综合监控", "ISCS"),
    ("电扶梯设备", "电扶梯设备"),   # 已标准化的直接跳过（幂等）
    ("门禁系统", "门禁设备"),
    ("电扶梯", "电扶梯设备"),
    ("站台门", "屏蔽门"),
    ("通道门", "门禁设备"),
    ("检票机", "AFC设备"),
    ("综监", "ISCS"),
    ("扶梯", "电扶梯设备"),
    ("闸机", "AFC设备"),
]

ELECTROMECHANICAL_SPECIALTIES = [
    "AFC设备", "屏蔽门设备", "电扶梯设备", "FAS设备", "BAS设备",
    "给排水设备", "通风空调设备", "低压供电设备", "高压供电设备"
]


# ============================================
# 基础工具函数
# ============================================
def normalize_text(text: str) -> str:
    """文本标准化：应用核心同义词映射（首次命中即停止，防止子串冲突）"""
    if not isinstance(text, str):
        return text
    for synonym, standard in CORE_SYNONYM_MAP:
        if synonym in text:
            text = text.replace(synonym, standard)
            break  # 仅匹配第一个命中规则，避免子串二次替换
    return text


def show_progress(message: str):
    """显示进度信息（低调）"""
    logger.info(message)


def show_debug(message: str, elapsed_time: Optional[float] = None):
    """调试信息只写日志，不显示在界面上"""
    if elapsed_time:
        logger.info(f"{message} ({elapsed_time:.2f}s)")
    else:
        logger.info(message)


def show_success(message: str):
    """显示成功信息"""
    st.success(message)


def show_warning(message: str):
    """显示警告信息"""
    st.warning(message)


def show_info(message: str):
    """显示提示信息"""
    st.info(message)


def extract_fault_cause(longdesc: str) -> Optional[str]:
    """从详细描述中提取故障原因"""
    if not isinstance(longdesc, str):
        return None
    patterns = [
        r'原因[:：]\s*([^。；;]+)',
        r'故障原因[:：]\s*([^。；;]+)',
        r'问题原因[:：]\s*([^。；;]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, longdesc)
        if match:
            return match.group(1).strip()
    return None


def expand_specialty_synonyms(specialty: str) -> List[str]:
    """
    扩展专业同义词
    优先使用预定义映射，确保准确性
    """
    specialty_upper = specialty.upper()

    # 在预定义字典中查找
    for key, variants in SPECIALTY_SYNONYMS.items():
        if specialty in variants or specialty_upper in [v.upper() for v in variants]:
            return variants

    # 未找到则返回原词
    return [specialty]


# ============================================
# LLM调用封装（带重试机制）
# ============================================
def call_llm_with_validation(
        prompt: str,
        require_json: bool = True,
        temperature: float = 0.1,
        validation_func: Optional[Callable[[Dict], bool]] = None,
        timeout: int = 90,
        max_retries: int = MAX_RETRIES
) -> Dict[str, Any]:
    """
    统一的LLM调用接口 - 支持主模型与备用模型自动切换

    特性：
    - 主备自动切换
    - 自动重试机制（指数退避）
    - JSON解析错误处理
    - 详细日志记录
    """
    # 主备模型配置
    endpoints = [
        (LLM_API_URL, LLM_API_KEY, LLM_MODEL, "主模型"),
        (LLM_FALLBACK_URL, LLM_FALLBACK_KEY, LLM_FALLBACK_MODEL, "备用模型"),
    ]

    for api_url, api_key, model, label in endpoints:
        last_error = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = RETRY_DELAY * (2 ** (attempt - 1))
                    logger.info(f"{label} LLM调用重试 {attempt + 1}/{max_retries}，等待 {delay:.1f}s")
                    time.sleep(delay)

                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}'
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_completion_tokens": 16000,
                    "temperature": temperature,
                    "top_p": 0.9 if temperature > 0 else 0,
                }

                response = requests.post(
                    f"{api_url}/chat/completions",
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=timeout
                )
                response.raise_for_status()

                full_text = response.json()['choices'][0]['message']['content']
                json_str = full_text.split("</think>")[-1].strip() if "</think>" in full_text else full_text.strip()

                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]

                if require_json:
                    result = json.loads(json_str.strip())
                else:
                    result = {"content": json_str}

                if validation_func and not validation_func(result):
                    raise ValueError("LLM输出未通过验证")

                logger.info(f"{label}({model}) LLM调用成功 (尝试 {attempt + 1})")
                return result

            except requests.Timeout as e:
                last_error = f"请求超时 (attempt {attempt + 1})"
                logger.warning(f"{label}: {last_error}")
            except json.JSONDecodeError as e:
                last_error = f"JSON解析失败: {str(e)[:100]}"
                logger.warning(f"{label}: {last_error}, 原始内容: {json_str[:200] if 'json_str' in locals() else 'N/A'}")
            except requests.RequestException as e:
                last_error = f"网络错误: {str(e)[:100]}"
                logger.warning(f"{label}: {last_error}")
                break  # 网络错误直接切备用，不再重试
            except Exception as e:
                last_error = f"未知错误: {str(e)[:100]}"
                logger.error(f"{label}: {last_error}", exc_info=True)

        logger.warning(f"{label}({model}) 失败: {last_error}，尝试切换...")

    logger.error(f"所有LLM模型均调用失败: {last_error}")
    return {"error": last_error, "success": False}


def call_llm_stream(prompt: str, temperature: float = 0.3, max_tokens: int = 2000):
    """流式调用 LLM，yield 文本片段，可直接传给 st.write_stream()"""
    endpoints = [
        (LLM_API_URL, LLM_API_KEY, LLM_MODEL),
        (LLM_FALLBACK_URL, LLM_FALLBACK_KEY, LLM_FALLBACK_MODEL),
    ]

    for api_url, api_key, model in endpoints:
        try:
            logger.info(f"开始调用LLM: {model}, URL: {api_url}")
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": max_tokens,
                "temperature": temperature,
                "top_p": 0.9 if temperature > 0 else 0,
                "stream": True,
            }

            response = requests.post(
                f"{api_url}/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=120,
                stream=True,
            )
            response.raise_for_status()
            response.encoding = 'utf-8'  # 确保中文正确解码，避免 Latin-1 乱码
            logger.info(f"LLM响应状态码: {response.status_code}")

            in_thinking = False
            buffer = ""
            line_count = 0
            chunk_count = 0

            for line in response.iter_lines(decode_unicode=True):
                line_count += 1
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    logger.info(f"LLM流结束，共处理 {line_count} 行，生成 {chunk_count} 个chunk")
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                content = choices[0].get("delta", {}).get("content", "")
                if not content:
                    continue

                chunk_count += 1
                buffer += content

                if "<think>" in buffer and not in_thinking:
                    in_thinking = True
                    before = buffer.split("<think>")[0]
                    if before:
                        yield before
                    buffer = buffer.split("<think>", 1)[1]
                    continue

                if in_thinking:
                    if "</think>" in buffer:
                        in_thinking = False
                        after = buffer.split("</think>", 1)[1]
                        buffer = ""
                        if after:
                            yield after
                    continue

                yield content
                buffer = ""

            if buffer and not in_thinking:
                yield buffer

            logger.info(f"LLM流式调用成功 ({model})")
            return  # 成功则不再尝试备用

        except Exception as e:
            logger.warning(f"LLM流式调用失败 ({model}): {e}", exc_info=True)
            continue

    yield "\n\n[回复生成出错，请重试]"


def get_embedding(text: str, timeout: int = 30) -> Optional[Any]:
    """调用内网Embedding API获取向量"""
    headers = {'Content-Type': 'application/json'}
    payload = {"inputs": text}

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(RETRY_DELAY * attempt)
                logger.info(f"Embedding重试 {attempt + 1}/{MAX_RETRIES}")

            response = requests.post(
                EMBEDDING_API_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()
            # Embedding API 返回批量格式 [[...1024...]]，需要取 [0]
            if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list):
                return result[0]
            return result

        except Exception as e:
            logger.warning(f"Embedding调用失败 (attempt {attempt + 1}): {e}")

    logger.error(f"Embedding调用失败，已重试 {MAX_RETRIES} 次")
    st.error("Embedding调用失败，请稍后重试")
    return None


def rerank_results(query: str, texts: List[str], top_k: int = 20, timeout: int = 30) -> Optional[List[Dict]]:
    """
    调用内网Rerank模型重排序结果

    Args:
        query: 查询文本
        texts: 待排序文本列表
        top_k: 返回前k个结果
        timeout: 超时时间

    Returns:
        排序后的结果列表，每项包含index和score
    """
    if not texts:
        return None

    headers = {'Content-Type': 'application/json'}
    payload = {
        "query": query,
        "texts": texts,
        "top_k": min(top_k, len(texts))
    }

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(RETRY_DELAY * attempt)

            response = requests.post(
                RERANK_API_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Rerank成功，重排序 {len(texts)} 个结果")
            return result

        except Exception as e:
            logger.warning(f"Rerank调用失败 (attempt {attempt + 1}): {str(e)[:50]}")

    show_debug("Rerank调用失败，使用原始排序")
    return None


def reciprocal_rank_fusion(results_lists: List[List[str]], k: int = 60) -> List[str]:
    """
    RRF 融合多路召回结果
    参考: Cormack et al. 2009, "Reciprocal Rank Fusion outperforms
    Condorcet and individual Rank Learning Methods"
    k=60 是原论文推荐的默认值
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    for results in results_lists:
        for rank, doc_id in enumerate(results):
            rrf_scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)


def keyword_search_oracle(entities: Dict, top_k: int = 50) -> List[str]:
    """
    Oracle 关键词检索 —— BM25 稀疏检索的实用替代方案

    通过 INSTR 精确词匹配捕获向量检索可能遗漏的案例
    （设备编号、故障代码等精确词在向量空间中表现较差）
    """
    # 快速失败：数据库不可用时直接返回空，不阻塞主流程
    if not DatabaseManager.is_available():
        logger.debug("关键词检索跳过：数据库连接池不可用")
        return []

    device = (entities.get('device') or '').strip()
    specialty = (entities.get('specialty') or '').strip()
    fault_phenomenon = (entities.get('fault_phenomenon') or '').strip()

    # 收集有效搜索词（最多4个，避免 SQL 过长）
    search_terms = []
    if device and len(device) >= 2:
        search_terms.append(device)
    if specialty and len(specialty) >= 2 and specialty not in search_terms:
        search_terms.append(specialty)
    if fault_phenomenon and len(fault_phenomenon) >= 2 and fault_phenomenon not in search_terms:
        search_terms.append(fault_phenomenon)
    search_terms = search_terms[:4]

    if not search_terms:
        return []

    try:
        # 构建 INSTR 匹配条件（Oracle 无需 % 通配符，更易利用索引）
        params: Dict[str, Any] = {}
        where_parts = []
        score_parts = []

        for i, term in enumerate(search_terms):
            params[f'kw{i}'] = term
            where_parts.append(f"INSTR(SR.DESCRIPTION, :kw{i}) > 0")
            score_parts.append(f"CASE WHEN INSTR(SR.DESCRIPTION, :kw{i}) > 0 THEN 1 ELSE 0 END")

        # 专业过滤（大幅减少扫描范围）
        specialty_where = ""
        if specialty:
            synonyms = expand_specialty_synonyms(specialty)
            spec_parts = []
            for j, syn in enumerate(synonyms[:6]):
                params[f'spec{j}'] = syn
                spec_parts.append(f"SR.SPECIALTY = :spec{j}")
            if spec_parts:
                specialty_where = f" AND ({' OR '.join(spec_parts)})"

        score_sql = " + ".join(score_parts)
        where_sql = " OR ".join(where_parts)

        sql = f"""
        SELECT TICKETID FROM (
            SELECT SR.TICKETID,
                   ({score_sql}) AS KW_SCORE
            FROM MAXIMO.SR SR
            WHERE ({where_sql})
            {specialty_where}
              AND SR.STATUS NOT IN ('CANCELLED')
              AND LENGTH(COALESCE(SR.SOLUTION, SR.PROCREMEDY, '')) > 5
            ORDER BY KW_SCORE DESC, SR.REPORTDATE DESC
        ) WHERE ROWNUM <= {top_k}
        """

        result_df = DatabaseManager.execute_query_safe(sql, params)
        if result_df.empty:
            return []
        ticket_ids = [str(tid) for tid in result_df['TICKETID'].tolist()]
        logger.info(f"关键词检索: 返回 {len(ticket_ids)} 个候选")
        return ticket_ids

    except Exception as e:
        logger.warning(f"关键词检索失败（将仅使用向量检索）: {e}")
        return []


def apply_rerank_to_df(df: pd.DataFrame, query: str, top_k: int = 20) -> Tuple[pd.DataFrame, bool]:
    """
    对 DataFrame 中的案例应用神经 Rerank 重排序

    构建结构化文本后调用内网 Rerank 服务，返回精排后的 top_k 行
    返回: (reranked_df, 是否成功应用了rerank)
    """
    if df.empty or len(df) <= 1:
        return df.head(top_k), False

    # 构建每条案例的文本表示（供 reranker 使用）
    texts = []
    for _, row in df.iterrows():
        solution_preview = str(row.get('SOLUTION', ''))[:150]
        text = (
            f"专业:{row.get('SPECIALTY', '')} "
            f"车站:{row.get('STATIONNAME', '')} "
            f"描述:{row.get('DESCRIPTION', '')} "
            f"处理:{solution_preview}"
        )
        texts.append(text)

    rerank_result = rerank_results(query, texts, top_k=min(top_k, len(texts)))

    if not rerank_result:
        logger.debug("Rerank 不可用，使用规则排序结果")
        return df.head(top_k), False

    try:
        # 兼容不同 API 返回格式
        if isinstance(rerank_result, list) and len(rerank_result) > 0:
            first = rerank_result[0]
            # 格式1: [{"index": N, "score": X}, ...]
            if isinstance(first, dict) and 'index' in first:
                ordered_indices = [item['index'] for item in rerank_result
                                   if isinstance(item.get('index'), int)]
            # 格式2: [[index, score], ...]
            elif isinstance(first, (list, tuple)) and len(first) >= 1:
                ordered_indices = [int(item[0]) for item in rerank_result]
            else:
                return df.head(top_k), False
        elif isinstance(rerank_result, dict) and 'results' in rerank_result:
            # 格式3: {"results": [{"index": N, ...}, ...]}
            ordered_indices = [item['index'] for item in rerank_result['results']
                               if isinstance(item.get('index'), int)]
        else:
            return df.head(top_k), False

        # 过滤超界索引
        max_idx = len(df) - 1
        ordered_indices = [i for i in ordered_indices if 0 <= i <= max_idx]

        if not ordered_indices:
            return df.head(top_k), False

        df_reset = df.reset_index(drop=True)
        reranked_df = df_reset.iloc[ordered_indices[:top_k]].reset_index(drop=True)
        logger.info(f"Rerank 完成: {len(df)} → {len(reranked_df)} 个案例")
        return reranked_df, True

    except Exception as e:
        logger.warning(f"Rerank 结果处理失败，使用规则排序: {e}")
        return df.head(top_k), False


# ============================================
# 数据库管理器（带连接池和参数化查询）
# ============================================
class DatabaseManager:
    """数据库连接池管理器"""
    _pool = None
    _pool_failed = False  # 标记连接池是否创建失败，避免反复超时重试

    @classmethod
    def _test_connectivity(cls, timeout: int = 3) -> bool:
        """TCP 预检：快速判断数据库是否网络可达（避免 SCAN 监听器的长超时）"""
        import socket
        try:
            # 从 DSN 中提取 host:port（兼容 host:port/service 和 SCAN 格式）
            dsn_part = DB_DSN.split('/')[0]
            if ':' in dsn_part:
                host, port_str = dsn_part.rsplit(':', 1)
                port = int(port_str)
            else:
                host, port = dsn_part, 1521

            # 手动解析 DNS 取首个 IP，避免 create_connection 逐 IP 重试
            addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            if not addrs:
                return False
            ip = addrs[0][4][0]

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            s.close()
            return True
        except Exception as e:
            logger.warning(f"数据库 TCP 预检失败 ({DB_DSN} → {ip if 'ip' in dir() else '?'}): {e}")
            return False

    @classmethod
    def get_pool(cls):
        """获取或创建连接池"""
        if cls._pool_failed:
            return None
        if cls._pool is None:
            if not DB_PASSWORD:
                raise ValueError("数据库密码未设置，请配置环境变量 VITA_DB_PASSWORD")

            # TCP 预检：3秒内判断网络可达性，避免 SCAN 监听器 60s 超时
            if not cls._test_connectivity(timeout=DB_CONNECT_TIMEOUT):
                cls._pool_failed = True
                logger.error(f"数据库不可达 ({DB_DSN})，关键词检索将降级为仅向量模式")
                return None

            try:
                cls._pool = oracledb.create_pool(
                    user=DB_USER,
                    password=DB_PASSWORD,
                    dsn=DB_DSN,
                    min=DB_POOL_MIN,
                    max=DB_POOL_MAX,
                    increment=DB_POOL_INCREMENT,
                    getmode=oracledb.POOL_GETMODE_WAIT,
                    tcp_connect_timeout=DB_CONNECT_TIMEOUT
                )
                logger.info(f"数据库连接池创建成功 (min={DB_POOL_MIN}, max={DB_POOL_MAX}, dsn={DB_DSN})")
            except Exception as e:
                logger.error(f"连接池创建失败 (dsn={DB_DSN}): {e}")
                cls._pool_failed = True
                raise
        return cls._pool

    @classmethod
    def get_connection(cls):
        """从连接池获取连接"""
        pool = cls.get_pool()
        if pool is None:
            raise ConnectionError("数据库连接池不可用")
        return pool.acquire()

    @classmethod
    def is_available(cls) -> bool:
        """检查数据库是否可用（避免在不可达时反复超时）"""
        return not cls._pool_failed

    @staticmethod
    def sanitize_input(value: str) -> str:
        """
        清理用户输入，防止SQL注入
        只允许字母、数字、中文和基本标点
        """
        if not isinstance(value, str):
            return str(value)
        # 移除SQL注入常见字符
        dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "xp_", "exec", "execute", "drop", "delete", "insert", "update"]
        result = value
        for char in dangerous_chars:
            result = result.replace(char, "")
        # 限制长度
        return result[:200]

    @staticmethod
    def execute_query(sql: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """
        执行参数化查询并返回DataFrame

        Args:
            sql: SQL语句，使用 :param_name 作为占位符
            params: 参数字典

        Returns:
            查询结果DataFrame
        """
        try:
            with DatabaseManager.get_connection() as conn:
                if params:
                    logger.debug(f"执行参数化查询，参数: {list(params.keys())}")
                return pd.read_sql(sql, conn, params=params)
        except Exception as e:
            logger.error(f"数据库查询失败: {str(e)}")
            st.error(f"数据库查询失败: {str(e)[:200]}")
            with st.expander("查看SQL语句（调试用）", expanded=False):
                st.code(sql, language="sql")
                if params:
                    st.json(params)
            return pd.DataFrame()

    @staticmethod
    def execute_query_safe(sql: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """
        安全执行查询，带重试机制

        Args:
            sql: SQL语句
            params: 参数字典

        Returns:
            查询结果DataFrame
        """
        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    time.sleep(RETRY_DELAY * attempt)
                    logger.info(f"数据库查询重试 {attempt + 1}/{MAX_RETRIES}")

                with DatabaseManager.get_connection() as conn:
                    return pd.read_sql(sql, conn, params=params)

            except oracledb.DatabaseError as e:
                error_obj, = e.args
                logger.warning(f"数据库错误 (attempt {attempt + 1}): {error_obj.message}")
                if attempt == MAX_RETRIES - 1:
                    raise
            except Exception as e:
                logger.error(f"查询失败: {e}")
                if attempt == MAX_RETRIES - 1:
                    raise

        return pd.DataFrame()


# ============================================
# 全局资源初始化
# ============================================
@st.cache_resource(show_spinner=False)
def initialize_resources():
    """初始化并缓存全局资源（注意：不能在此函数内调用 st.* UI 元素）"""
    init_start = time.time()

    print("[DEBUG] initialize_resources started")

    try:
        # 尝试初始化Oracle客户端（可选，如果路径不存在则使用Thin模式）
        print("[DEBUG] Initializing Oracle client...")
        try:
            if os.path.exists(ORACLE_CLIENT_PATH):
                oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
                logger.info(f"使用Oracle Thick模式: {ORACLE_CLIENT_PATH}")
                print(f"[DEBUG] Oracle Thick mode: {ORACLE_CLIENT_PATH}")
            else:
                logger.info("Oracle客户端路径不存在，使用Thin模式连接")
                print("[DEBUG] Oracle client path not found, using Thin mode")
        except Exception as e:
            logger.warning(f"Oracle初始化警告: {e}，将使用Thin模式")
            print(f"[DEBUG] Oracle init warning: {e}")

        # Check if knowledge base files exist
        print(f"[DEBUG] Checking INDEX_FILE: {INDEX_FILE}")
        if not os.path.exists(INDEX_FILE):
            print(f"[ERROR] INDEX_FILE not found: {INDEX_FILE}")
            print(f"[DEBUG] Current files: {os.listdir('.')}")
            logger.error(f"向量索引文件未找到: {INDEX_FILE}")
            return None, None

        print("[DEBUG] Loading FAISS index...")
        index = faiss.read_index(INDEX_FILE)
        print(f"[DEBUG] FAISS index loaded successfully, {index.ntotal} vectors")

        print(f"[DEBUG] Checking ID_MAP_FILE: {ID_MAP_FILE}")
        if not os.path.exists(ID_MAP_FILE):
            print(f"[ERROR] ID_MAP_FILE not found: {ID_MAP_FILE}")
            logger.error(f"ID映射文件未找到: {ID_MAP_FILE}")
            return None, None

        print("[DEBUG] Loading ID map...")
        id_map = np.load(ID_MAP_FILE, allow_pickle=True)
        print(f"[DEBUG] ID map loaded successfully, shape: {id_map.shape}")

        init_time = time.time() - init_start

        logger.info(f"系统初始化完成 ({init_time:.2f}s)")

        return index, id_map

    except Exception as e:
        print(f"[ERROR] Resource initialization failed: {e}")
        import traceback
        traceback.print_exc()
        logger.error(f"全局资源初始化失败: {e}")
        return None, None


# 执行全局初始化（仅首次显示 spinner，后续从缓存直接获取）
if "vita_initialized" not in st.session_state:
    print("[DEBUG] Starting system initialization...")
    print(f"[DEBUG] Current directory: {os.getcwd()}")
    print(f"[DEBUG] INDEX_FILE: {INDEX_FILE}")
    print(f"[DEBUG] ID_MAP_FILE: {ID_MAP_FILE}")
    try:
        with st.spinner("正在初始化系统..."):
            faiss_index, id_map = initialize_resources()
        print("[DEBUG] System initialization completed successfully")
        st.session_state.vita_initialized = True
        if faiss_index is not None:
            st.toast("系统初始化完成", icon="✅")
        else:
            st.error("系统资源加载失败，请检查知识库文件是否存在")
    except Exception as e:
        print(f"[ERROR] System initialization failed: {e}")
        import traceback
        traceback.print_exc()
        faiss_index, id_map = None, None
else:
    faiss_index, id_map = initialize_resources()  # 直接从 @st.cache_resource 缓存获取，无开销


# ================================================================================
# VITA v15.0 - 内网部署版
# 第2段（共6段）：智能解析器
# ================================================================================

def fast_parse_local(user_query: str) -> Optional[Dict]:
    """
    本地快速意图识别 —— 用关键词规则在 <1ms 内完成解析
    仅处理高置信度的简单查询；复杂查询返回 None 交给 LLM

    覆盖场景：
    1. 闲聊/打招呼 → 直接返回 chitchat
    2. 明确意图的统计/责任/诊断查询 → 提取实体后直接返回
    """
    query = user_query.strip()
    if not query:
        return None

    # ── 闲聊识别 ──────────────────────────────────────────────
    chitchat_patterns = [
        "你好", "您好", "在吗", "在不在", "帮帮我", "hello", "hi",
        "谢谢", "感谢", "辛苦了", "好的", "明白了", "收到",
    ]
    # 短查询闲聊检测：排除包含诊断关键词的情况（如"怎么修"）
    diagnosis_short_kw = ["怎么办", "怎么处理", "怎么修", "怎么解决"]
    if query in chitchat_patterns or (len(query) <= 3 and not any(
        kw in query for kw in ["线", "站", "门", "灯", "梯", "机", "屏"]
    ) and not any(kw in query for kw in diagnosis_short_kw)):
        return {"intent": "chitchat", "entities": {}, "confidence": 1.0}

    # ── 意图关键词 ────────────────────────────────────────────
    diagnosis_kw = ["怎么办", "怎么处理", "如何解决", "如何处理", "怎么修", "怎么解决", "什么原因", "是什么原因", "为什么"]
    # 历史查询关键词（优先级高于统计）
    history_kw = ["之前", "以前", "有没有坏过", "坏过", "出过", "发生过", "最近有什么故障", "有什么故障"]
    statistics_kw = ["多少", "统计", "有几个", "有几起", "有多少", "排名", "最多"]
    # "查一下"、"查询"、"故障情况"等词既可能是统计也可能是诊断，需要结合上下文
    ambiguous_kw = ["查一下", "查询", "故障情况", "哪些", "有哪些", "故障记录"]
    responsibility_kw = ["谁负责", "归谁管", "哪个班组", "找谁", "谁管", "归谁"]

    intent = None
    if any(kw in query for kw in responsibility_kw):
        intent = "responsibility"
    elif any(kw in query for kw in history_kw):
        # 历史查询优先识别为诊断（查看历史案例）
        intent = "diagnosis"
    elif any(kw in query for kw in statistics_kw):
        intent = "statistics"
    elif any(kw in query for kw in diagnosis_kw):
        intent = "diagnosis"
    elif any(kw in query for kw in ambiguous_kw):
        # 模糊关键词：如果包含设备名，默认为诊断；否则为统计
        device_indicators = ["AFC", "BAS", "FAS", "ISCS", "屏蔽门", "闸机", "电扶梯", "扶梯",
                            "门禁", "给排水", "通风空调", "低压供电", "高压供电", "安检", "工作站"]
        query_upper = query.upper()
        if any(kw.upper() in query_upper for kw in device_indicators):
            intent = "diagnosis"
        else:
            intent = "statistics"

    # 隐式诊断意图：包含设备/专业但无明确意图词 → 默认为诊断
    if intent is None:
        device_indicators = ["AFC", "BAS", "FAS", "ISCS", "屏蔽门", "闸机", "电扶梯", "扶梯",
                            "门禁", "给排水", "通风空调", "低压供电", "高压供电", "安检", "工作站",
                            "门", "灯", "梯", "机", "屏", "报警"]
        query_upper = query.upper()
        if any(kw.upper() in query_upper for kw in device_indicators):
            intent = "diagnosis"

    if intent is None:
        return None  # 意图不明确，交给 LLM

    # ── 实体提取（规则 + 正则）────────────────────────────────
    entities = {
        "line_num": None,
        "station_name": None,
        "specialty": None,
        "device": None,
        "fault_phenomenon": None,
        "time_range": None,
    }

    # 线路
    line_matches = re.findall(r'(\d{1,2})\s*号线', query)
    if line_matches:
        entities["line_num"] = ",".join(line_matches)

    # 车站（常见模式："XX站"）
    station_match = re.search(r'([\u4e00-\u9fa5]{2,6}(?:站|车站))', query)
    if station_match:
        station = station_match.group(1).rstrip("站").rstrip("车")
        entities["station_name"] = station

    # 设备/专业（用 KEYWORD_RULES 的 key 做匹配）
    normalized_query = normalize_text(query)
    for keyword, info in [
        ("ISCS", {"specialty": "ISCS设备", "device": "ISCS"}),
        ("屏蔽门", {"specialty": "屏蔽门设备", "device": "屏蔽门"}),
        ("AFC", {"specialty": "AFC设备", "device": "AFC"}),
        ("BAS", {"specialty": "BAS设备", "device": "BAS"}),
        ("FAS", {"specialty": "FAS设备", "device": "FAS"}),
        ("门禁", {"specialty": "门禁设备", "device": "门禁"}),
        ("电扶梯", {"specialty": "电扶梯设备", "device": "电扶梯"}),
        ("扶梯", {"specialty": "电扶梯设备", "device": "电扶梯"}),
        ("给排水", {"specialty": "给排水设备", "device": "给排水"}),
        ("通风空调", {"specialty": "通风空调设备", "device": "通风空调"}),
        ("低压供电", {"specialty": "低压供电设备", "device": "低压供电"}),
        ("高压供电", {"specialty": "高压供电设备", "device": "高压供电"}),
        ("安检", {"specialty": "安检仪设备", "device": "安检"}),
        ("闸机", {"specialty": "AFC设备", "device": "AFC闸机"}),
        ("工作站", {"specialty": "ISCS设备", "device": "ISCS工作站"}),
    ]:
        if keyword in normalized_query:
            if not entities["specialty"]:
                entities["specialty"] = info["specialty"]
            if not entities["device"]:
                entities["device"] = info["device"]
            break

    # 故障现象（提取设备名称后面的描述性词语）
    phenomenon_patterns = [
        r'(黑屏|白屏|死机|卡死|无法启动|打不开|关不上|无法关闭|无法打开|不亮|闪烁|报警|异响|漏水|积水|坏了)',
    ]
    for pattern in phenomenon_patterns:
        m = re.search(pattern, query)
        if m:
            entities["fault_phenomenon"] = m.group(1)
            break

    # 时间范围
    current_date = datetime.now().strftime('%Y-%m-%d')
    if "今天" in query or "今日" in query:
        entities["time_range"] = {"start_date": current_date, "end_date": current_date}
    elif "本周" in query:
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        entities["time_range"] = {"start_date": monday.strftime('%Y-%m-%d'), "end_date": current_date}
    elif "本月" in query:
        entities["time_range"] = {"start_date": datetime.now().strftime('%Y-%m-01'), "end_date": current_date}
    else:
        # 匹配 "最近X天" 或 "最近一个月"
        days_match = re.search(r'最近\s*(\d+)\s*天', query)
        month_match = re.search(r'最近\s*一个月', query)
        if days_match:
            n = int(days_match.group(1))
            start = (datetime.now() - timedelta(days=n)).strftime('%Y-%m-%d')
            entities["time_range"] = {"start_date": start, "end_date": current_date}
        elif month_match:
            start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            entities["time_range"] = {"start_date": start, "end_date": current_date}

    # 统计查询的子类型
    query_type = None
    compare_dimension = None
    if intent == "statistics":
        if any(kw in query for kw in ["哪条线", "哪个线", "哪条"]):
            query_type = "comparison"
            compare_dimension = "line"
        elif any(kw in query for kw in ["哪个站", "哪个车站"]):
            query_type = "comparison"
            compare_dimension = "station"
        elif any(kw in query for kw in ["哪个专业"]):
            query_type = "comparison"
            compare_dimension = "specialty"
        elif any(kw in query for kw in ["排名", "最多", "top", "前十"]):
            query_type = "ranking"
        else:
            query_type = "count"

    result = {
        "intent": intent,
        "entities": entities,
        "query_type": query_type,
        "compare_dimension": compare_dimension,
        "confidence": 0.9,
        "_source": "local_fast_parse",
    }

    logger.info(f"本地快速解析: intent={intent}, device={entities.get('device')}, specialty={entities.get('specialty')}")
    return result


def parse_user_query(user_query: str) -> Dict:
    """
    智能解析器：用户查询 → 结构化实体

    设计理念：
    - 本地快速解析优先（<1ms），覆盖简单查询
    - LLM解析兜底：处理复杂/模糊的自然语言
    """
    # 快速路径：本地规则解析
    fast_result = fast_parse_local(user_query)
    if fast_result is not None:
        return fast_result
    current_date = datetime.now().strftime('%Y-%m-%d')

    prompt = f"""你是地铁运维专家助手，负责解析查询。当前日期：{current_date}

【核心规则】
1. intent（意图）：
   • diagnosis - 询问"怎么办"、"怎么处理"
   • statistics - 询问"多少"、"有几个"、"统计"
   • responsibility - 询问"谁负责"、"归谁管"

2. line_num（线路）：
   • 提取纯数字，多条线路用逗号分隔
   • 示例："3号线" → "3"，"1、2、4、7号线" → "1,2,4,7"

3. specialty（专业）：
   • 从device中提取专业大类
   • 如：ISCS、屏蔽门、AFC、BAS、FAS、门禁等
   • 如无法判断 → null

4. device（设备）：
   • 保留完整设备名称，不要省略
   • "ISCS工作站" ✓   "工作站" ✗
   • "屏蔽门控制器" ✓  "控制器" ✗

5. time_range（时间）：
   • 今天 → {{"start_date":"{current_date}","end_date":"{current_date}"}}
   • 本周 → start_date=本周一, end_date=今天
   • 最近N天 → start_date=今天-N天, end_date=今天
   • 无时间 → null

6. query_type（统计类型，仅statistics时填写）：
   • ranking - 问"故障类型排名"、"哪种故障最多"（按故障类型分组）
   • comparison - 问"哪条线最多"、"哪个站最多"、"哪个专业最多"（按维度对比）
   • count - 问"有多少"、"有几个"（计数和列表）

7. compare_dimension（对比维度，仅comparison时填写）：
   • line - 按线路对比，如"哪条线故障最多"
   • station - 按车站对比，如"哪个站故障最多"
   • specialty - 按专业对比，如"哪个专业故障最多"

【输出格式】严格JSON
{{
  "intent": "diagnosis/statistics/responsibility",
  "entities": {{
    "line_num": "数字或逗号分隔多个数字或null",
    "station_name": "车站名或null",
    "specialty": "专业或null",
    "device": "完整设备名",
    "fault_phenomenon": "故障现象或null",
    "time_range": {{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}} 或null
  }},
  "query_type": "ranking/count/comparison/null",
  "compare_dimension": "line/station/specialty/null",
  "confidence": 0-1
}}

【用户查询】"{user_query}"
"""

    result = call_llm_with_validation(
        prompt=prompt,
        require_json=True,
        temperature=0.0,
        timeout=90
    )

    if "error" in result:
        return {
            "intent": "error",
            "error_message": result["error"],
            "original_query": user_query
        }

    # ========================================
    # 本地验证与标准化（确保数据质量）
    # ========================================
    entities = result.get("entities", {})

    # 1. 同义词标准化（核心业务规则）
    for key in ["device", "specialty"]:
        if entities.get(key):
            entities[key] = normalize_text(entities[key])

    # 2. line_num提取纯数字（支持多线路，逗号分隔）
    if entities.get("line_num"):
        nums = re.findall(r'\d+', str(entities["line_num"]))
        if nums:
            entities["line_num"] = ",".join(nums)

    # 3. intent兜底验证
    valid_intents = ["diagnosis", "statistics", "responsibility"]
    if result.get("intent") not in valid_intents:
        if any(kw in user_query for kw in ["多少", "统计", "排名", "有几个"]):
            result["intent"] = "statistics"
        elif any(kw in user_query for kw in ["谁", "负责", "归谁管", "找谁"]):
            result["intent"] = "responsibility"
        else:
            result["intent"] = "diagnosis"

    # 4. query_type智能修正
    if result.get("intent") == "statistics":
        query_type = result.get("query_type")
        if query_type not in ["ranking", "count", "comparison"]:
            if result.get("compare_dimension") in ["line", "station", "specialty"]:
                result["query_type"] = "comparison"
            elif any(kw in user_query for kw in ["最多", "排名", "top", "前十"]):
                # 判断是"哪条线/哪个站最多"(comparison) 还是"哪种故障最多"(ranking)
                if any(kw in user_query for kw in ["哪条线", "哪个线", "哪条", "哪个站", "哪个专业", "哪个车站"]):
                    result["query_type"] = "comparison"
                    if any(kw in user_query for kw in ["线", "号线"]):
                        result["compare_dimension"] = "line"
                    elif any(kw in user_query for kw in ["站", "车站"]):
                        result["compare_dimension"] = "station"
                    elif any(kw in user_query for kw in ["专业"]):
                        result["compare_dimension"] = "specialty"
                else:
                    result["query_type"] = "ranking"
            else:
                result["query_type"] = "count"

    # 5. 时间范围格式验证
    time_range = entities.get("time_range")
    if time_range and isinstance(time_range, dict):
        try:
            if "start_date" in time_range:
                datetime.strptime(time_range["start_date"], "%Y-%m-%d")
            if "end_date" in time_range:
                datetime.strptime(time_range["end_date"], "%Y-%m-%d")
        except ValueError:
            entities["time_range"] = None

    return result


def build_sql_conditions_from_entities(entities: Dict) -> Tuple[str, Dict[str, Any]]:
    """
    根据实体构建SQL WHERE条件（参数化查询，防止SQL注入）

    输入：entities字典
    输出：(SQL WHERE子句, 参数字典)
    """
    conditions = []
    params = {}
    param_counter = 0

    # 线路过滤（参数化，支持多线路）
    if entities.get('line_num'):
        line_nums = [DatabaseManager.sanitize_input(n.strip()) for n in str(entities['line_num']).split(',') if n.strip()]
        if len(line_nums) == 1:
            param_name = f"line_num_{param_counter}"
            conditions.append(f"SR.LINENUM = :{param_name}")
            params[param_name] = line_nums[0]
            param_counter += 1
        elif line_nums:
            line_placeholders = []
            for ln in line_nums:
                param_name = f"line_num_{param_counter}"
                line_placeholders.append(f":{param_name}")
                params[param_name] = ln
                param_counter += 1
            conditions.append(f"SR.LINENUM IN ({', '.join(line_placeholders)})")

    # 车站过滤（参数化）
    if entities.get('station_name'):
        station = DatabaseManager.sanitize_input(entities['station_name'])
        param_name = f"station_{param_counter}"
        conditions.append(f"UPPER(SR.STATIONNAME) LIKE UPPER(:{param_name})")
        params[param_name] = f"%{station}%"
        param_counter += 1

    # 专业过滤（带同义词扩展，参数化）
    if entities.get('specialty'):
        specialty = normalize_text(entities['specialty'])
        synonyms = expand_specialty_synonyms(specialty)
        # 限制同义词数量，防止SQL过长
        synonyms = synonyms[:10]

        specialty_conditions = []
        for syn in synonyms:
            syn_clean = DatabaseManager.sanitize_input(syn)
            param_name = f"specialty_{param_counter}"
            specialty_conditions.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:{param_name})")
            params[param_name] = f"%{syn_clean}%"
            param_counter += 1

        if specialty_conditions:
            conditions.append(f"({' OR '.join(specialty_conditions)})")

    # 时间范围过滤（参数化）
    time_range = entities.get('time_range')
    if time_range and isinstance(time_range, dict):
        start_date = time_range.get('start_date')
        end_date = time_range.get('end_date')
        if start_date and end_date:
            # 验证日期格式
            try:
                datetime.strptime(start_date, "%Y-%m-%d")
                datetime.strptime(end_date, "%Y-%m-%d")
                params['start_date'] = start_date
                params['end_date'] = end_date
                conditions.append(
                    "TRUNC(SR.REPORTDATE) BETWEEN "
                    "TO_DATE(:start_date, 'YYYY-MM-DD') AND "
                    "TO_DATE(:end_date, 'YYYY-MM-DD')"
                )
            except ValueError:
                logger.warning(f"无效的日期格式: {start_date} - {end_date}")

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return where_clause, params


def build_better_search_query(entities: Dict) -> str:
    """
    构建向量检索查询

    优先级策略：
    1. 设备+专业（最重要）
    2. 故障现象（重要）
    3. 位置信息（参考）
    """
    parts = []

    # 优先级1：专业+设备
    specialty = entities.get('specialty', '')
    device = entities.get('device', '')

    if specialty and device:
        if specialty not in device:
            parts.append(f"{specialty} {device}")
        else:
            parts.append(f"{device}")
    elif device:
        parts.append(f"{device}")
    elif specialty:
        parts.append(f"{specialty}")

    # 优先级2：故障现象
    phenomenon = entities.get('fault_phenomenon', '')
    if phenomenon:
        parts.append(f"{phenomenon}")

    # 优先级3：位置信息（权重降低）
    location_parts = []
    if entities.get('line_num'):
        location_parts.append(f"{entities['line_num']}号线")
    if entities.get('station_name'):
        location_parts.append(f"{entities['station_name']}")

    if location_parts:
        parts.append(" ".join(location_parts))

    return " ".join(parts) if parts else "故障诊断"


# ================================================================================
# VITA v14.0 - 参赛最终版
# 第3段（共6段）：责任归属查询
# ================================================================================

def get_synonym_expansion(term: str) -> List[str]:
    """
    LLM辅助的动态同义词扩展
    用于处理预定义字典未覆盖的长尾词汇
    超时保护：最多等 15s，失败则返回原词
    """
    prompt = f"""你是地铁设备术语专家。为以下术语生成同义词。

【术语】"{term}"

【要求】
• 只返回地铁运维领域真实存在的术语
• 包含：缩写、全称、俗称
• 最多5个最相关的术语

【输出格式】严格JSON
{{"synonyms": ["术语1", "术语2", "术语3"]}}

【示例】
输入："ISCS" → {{"synonyms": ["综合监控", "综监系统", "ISCS系统"]}}
输入："电扶梯" → {{"synonyms": ["扶梯设备", "自动扶梯"]}}
"""

    result = call_llm_with_validation(
        prompt=prompt,
        require_json=True,
        temperature=0.1,
        timeout=8,   # 责任归属查询对速度敏感，快速降级到本地同义词
        max_retries=1  # 只试一次，失败就用本地同义词
    )

    if "error" not in result and "synonyms" in result:
        return [term] + result["synonyms"]
    else:
        return [term]


def query_responsibility(entities: Dict) -> Optional[str]:
    """
    责任归属查询引擎

    四级降级策略：
    Level 1: 精确匹配（线路+专业）
    Level 2: 同义词扩展（预定义+LLM动态生成）
    Level 3: 模糊匹配（描述字段）
    Level 4: 全局降级（不限线路）
    """
    show_progress("责任归属查询中...")

    # 优先用已标准化的 specialty（精确匹配数据库字段），device 作为备选
    search_term = entities.get('specialty') or entities.get('device')
    # 短名称（去掉"设备"后缀）用于描述字段的模糊匹配
    search_term_short = entities.get('device') or search_term.replace('设备', '') if search_term else None
    line_num = entities.get('line_num')

    if not search_term:
        show_warning("未能识别出设备或专业信息")
        show_info("建议：请明确设备名称，例如：'2号线的屏蔽门归谁管？'")
        return "未能识别出设备或专业信息，请明确设备名称。"

    search_term = normalize_text(search_term)
    search_term_clean = DatabaseManager.sanitize_input(search_term)
    search_term_short_clean = DatabaseManager.sanitize_input(search_term_short) if search_term_short else search_term_clean

    try:
        result_df = pd.DataFrame()
        query_level = None
        expanded_terms = None

        with DatabaseManager.get_connection() as conn:

            # ========================================
            # Level 1: 精确匹配（参数化查询）
            # ========================================
            if line_num:
                show_debug(f"Level 1: 精确匹配查询 ({line_num}号线)")
                line_num_clean = DatabaseManager.sanitize_input(str(line_num))

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
                params = {
                    'line_num': line_num_clean,
                    'search_term': f'%{search_term_clean}%',
                    'search_term_short': f'%{search_term_short_clean}%'
                }
                result_df = pd.read_sql(sql, conn, params=params)

                if not result_df.empty:
                    query_level = "precise"

            # ========================================
            # Level 2: 同义词扩展（参数化查询）
            # ========================================
            if result_df.empty:
                show_debug("Level 2: 同义词智能扩展")

                expanded_terms = expand_specialty_synonyms(search_term)
                if len(expanded_terms) == 1:
                    expanded_terms = get_synonym_expansion(search_term)
                # 限制同义词数量
                expanded_terms = expanded_terms[:10]

                show_debug(f"扩展词汇: {', '.join(expanded_terms[:3])}...")

                # 构建参数化查询
                params = {}
                conditions = []
                for i, term in enumerate(expanded_terms):
                    term_clean = DatabaseManager.sanitize_input(term)
                    param_name = f'term_{i}'
                    conditions.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:{param_name})")
                    params[param_name] = f'%{term_clean}%'

                where_clause = f"({' OR '.join(conditions)})"
                if line_num:
                    line_num_clean = DatabaseManager.sanitize_input(str(line_num))
                    where_clause += " AND SR.LINENUM = :line_num"
                    params['line_num'] = line_num_clean

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

            # ========================================
            # Level 3: 模糊匹配（参数化查询）
            # ========================================
            if result_df.empty:
                show_debug("Level 3: 描述字段模糊匹配")

                # 同时搜索完整名称和短名称，提高匹配率
                params = {
                    'search_term': f'%{search_term_clean}%',
                    'search_term_short': f'%{search_term_short_clean}%'
                }
                where_clause = "(UPPER(SR.DESCRIPTION) LIKE UPPER(:search_term) OR UPPER(SR.DESCRIPTION) LIKE UPPER(:search_term_short))"
                if line_num:
                    line_num_clean = DatabaseManager.sanitize_input(str(line_num))
                    where_clause += " AND SR.LINENUM = :line_num"
                    params['line_num'] = line_num_clean

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

            # ========================================
            # Level 4: 全局降级（参数化查询）
            # ========================================
            if result_df.empty and line_num:
                show_debug("Level 4: 扩大到全系统范围")

                params = {}
                if expanded_terms:
                    conditions = []
                    for i, term in enumerate(expanded_terms):
                        term_clean = DatabaseManager.sanitize_input(term)
                        param_name = f'term_{i}'
                        conditions.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:{param_name})")
                        params[param_name] = f'%{term_clean}%'
                    where_conditions = ' OR '.join(conditions)
                else:
                    where_conditions = "UPPER(SR.SPECIALTY) LIKE UPPER(:search_term)"
                    params['search_term'] = f'%{search_term_clean}%'

                sql = f"""
                SELECT OWNERGROUP, COUNT(*) AS CNT
                FROM MAXIMO.SR SR
                WHERE ({where_conditions})
                  AND OWNERGROUP IS NOT NULL
                GROUP BY OWNERGROUP
                ORDER BY CNT DESC
                FETCH FIRST 5 ROWS ONLY
                """
                result_df = pd.read_sql(sql, conn, params=params)

                if not result_df.empty:
                    query_level = "global_fallback"

        # ========================================
        # 结果呈现
        # ========================================
        if result_df.empty:
            # OWNERGROUP 全为 NULL 时的降级策略：只展示事实数据，不猜测
            logger.info(f"[责任归属] 所有级别均未找到 OWNERGROUP，尝试降级策略")
            try:
                with DatabaseManager.get_connection() as fallback_conn:
                    fb_params = {}
                    fb_conditions = []
                    if expanded_terms:
                        for i, term in enumerate(expanded_terms[:5]):
                            fb_conditions.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:t_{i})")
                            fb_params[f't_{i}'] = f'%{DatabaseManager.sanitize_input(term)}%'
                    else:
                        fb_conditions.append("UPPER(SR.SPECIALTY) LIKE UPPER(:st)")
                        fb_params['st'] = f'%{search_term_clean}%'

                    fb_where = ' OR '.join(fb_conditions)
                    if line_num:
                        ln_clean = DatabaseManager.sanitize_input(str(line_num))
                        fb_line_clause = " AND SR.LINENUM = :ln"
                        fb_params['ln'] = ln_clean
                    else:
                        fb_line_clause = ""

                    count_sql = f"""
                    SELECT COUNT(*) AS TOTAL_CNT FROM MAXIMO.SR SR
                    WHERE ({fb_where}){fb_line_clause}
                    """
                    count_df = pd.read_sql(count_sql, fallback_conn, params=fb_params)
                    total_records = int(count_df.iloc[0]['TOTAL_CNT']) if not count_df.empty else 0

                    if total_records > 0:
                        line_desc = f"{line_num}号线" if line_num else "全线网"

                        station_sql = f"""
                        SELECT SR.STATIONNAME, COUNT(*) AS CNT FROM MAXIMO.SR SR
                        WHERE ({fb_where}){fb_line_clause} AND SR.STATIONNAME IS NOT NULL
                        GROUP BY SR.STATIONNAME ORDER BY CNT DESC
                        FETCH FIRST 5 ROWS ONLY
                        """
                        station_df = pd.read_sql(station_sql, fallback_conn, params=fb_params)

                        msg = f"**{line_desc}**的 **{search_term}** 共有 **{total_records:,}** 条工单记录，但系统中该专业的班组归属信息（OWNERGROUP）暂未录入，无法直接查询到负责班组。\n\n建议联系线路设备管理部门确认具体的班组分工。"
                        st.markdown(msg)

                        if not station_df.empty:
                            with st.expander(f"{line_desc}{search_term}工单分布", expanded=False):
                                st.markdown("**工单高发站点**")
                                st.dataframe(
                                    station_df.rename(columns={'STATIONNAME': '站点', 'CNT': '工单数'}),
                                    hide_index=True
                                )
                        return msg
                    else:
                        msg = f"没有找到 **{search_term}** 的历史处理记录。试试用更通用的设备名称，或者去掉线路限制。"
                        st.markdown(msg)
                        return msg

            except Exception as fallback_e:
                logger.warning(f"降级策略失败: {fallback_e}")
                msg = f"没有找到 **{search_term}** 的历史处理记录。试试用更通用的设备名称，或者去掉线路限制。"
                st.markdown(msg)
                return msg
        else:
            top_group = result_df.iloc[0]['OWNERGROUP']
            top_count = int(result_df.iloc[0]['CNT'])
            total_count = int(result_df['CNT'].sum())
            top_pct = top_count / total_count * 100

            # 自然语言回答
            if query_level == "global_fallback":
                answer = f"在 {line_num}号线没有找到记录，但从全线网来看，**{search_term}** 主要由 **{top_group}** 负责（历史处理 {top_count} 次，占{top_pct:.0f}%）。"
            elif query_level == "fuzzy_description":
                answer = f"根据描述字段匹配，**{search_term}** 建议联系 **{top_group}**（历史处理 {top_count} 次，占{top_pct:.0f}%），仅供参考。"
            else:
                answer = f"**{search_term}** 主要由 **{top_group}** 负责（历史处理 {top_count} 次，占{top_pct:.0f}%）。"

            # 多班组补充
            if len(result_df) > 1:
                second = result_df.iloc[1]
                answer += f"\n\n其次是 **{second['OWNERGROUP']}**（{int(second['CNT'])}次）。"

            # 洞察
            if top_pct > 70:
                answer += f"\n\n归属非常明确，{top_group} 是主要责任方。"
            elif top_pct < 40 and len(result_df) > 1:
                answer += "\n\n涉及多个班组协同处理，建议根据具体情况判断或咨询调度。"

            st.markdown(answer)

            # 详细数据折叠
            with st.expander("班组处理统计详情", expanded=False):
                display_df = result_df.rename(columns={
                    'OWNERGROUP': '班组名称',
                    'CNT': '处理次数'
                })

                display_df['处理次数'] = display_df['处理次数'].astype(int)
                display_df['占比'] = display_df['处理次数'].apply(
                    lambda x: f"{x / total_count * 100:.1f}%"
                )

                st.dataframe(
                    display_df,
                    width='stretch',
                    hide_index=True
                )

            return answer

    except Exception as e:
        st.error("责任归属查询失败")
        st.exception(e)
        return None


# ================================================================================
# VITA v14.0 - 参赛最终版
# 第4段（共6段）：统计查询引擎
# ================================================================================

def query_statistics(entities: Dict, query_type: str) -> Optional[str]:
    """
    统计查询引擎

    支持两种查询模式：
    1. ranking - 故障类型排名（找出高频故障）
    2. count - 计数与列表（详细数据展示）
    """
    show_progress("统计查询中...")

    try:
        # 构建SQL条件（参数化查询）
        where_clause, params = build_sql_conditions_from_entities(entities)
        show_debug(f"查询条件: {where_clause}")
        logger.info(f"统计查询参数: {list(params.keys())}")

        with DatabaseManager.get_connection() as conn:

            # ========================================
            # 模式1: 故障类型排名
            # ========================================
            if query_type == "ranking":
                show_debug("执行故障类型排名查询...")

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
                    msg = "没有找到符合条件的故障记录，试试放宽时间范围或去掉线路限制。"
                    st.markdown(msg)
                    return msg

                # ========================================
                # 排名结果展示
                # ========================================
                total_count = int(result_df['FAULT_COUNT'].sum())
                top1 = result_df.iloc[0]
                top1_name = top1['FAULT_TYPE']
                top1_count = int(top1['FAULT_COUNT'])
                top1_pct = top1_count / total_count * 100

                # 先用自然语言回答
                summary = f"共 **{total_count}** 条故障记录，最高频的是 **{top1_name}**（{top1_count}次，占{top1_pct:.0f}%）"
                if len(result_df) >= 3:
                    top2 = result_df.iloc[1]
                    top3 = result_df.iloc[2]
                    summary += f"，其次是 **{top2['FAULT_TYPE']}**（{int(top2['FAULT_COUNT'])}次）和 **{top3['FAULT_TYPE']}**（{int(top3['FAULT_COUNT'])}次）。"
                else:
                    summary += "。"

                # 数据洞察
                if len(result_df) >= 3:
                    top3_count = int(result_df.head(3)['FAULT_COUNT'].sum())
                    top3_ratio = top3_count / total_count
                    if top3_ratio > 0.6:
                        summary += f"\n\n前3类故障占了总数的 {top3_ratio * 100:.0f}%，集中度较高，建议优先关注。"

                st.markdown(summary)

                # 详细排名折叠
                with st.expander("查看完整排名", expanded=False):
                    display_df = result_df.rename(columns={
                        'FAULT_TYPE': '故障类型',
                        'FAULT_COUNT': '发生次数'
                    })
                    display_df['发生次数'] = display_df['发生次数'].astype(int)
                    display_df['占比'] = display_df['发生次数'].apply(
                        lambda x: f"{x / total_count * 100:.1f}%"
                    )
                    st.dataframe(display_df, width='stretch', hide_index=True)

                return summary

            # ========================================
            # 模式2: 维度对比（哪条线/哪个站/哪个专业最多）
            # ========================================
            elif query_type == "comparison":
                dimension = entities.get('compare_dimension', 'line')
                dim_map = {
                    'line': ('SR.LINENUM', '线路'),
                    'station': ('SR.STATIONNAME', '车站'),
                    'specialty': ('SR.SPECIALTY', '专业'),
                }
                db_col, dim_label = dim_map.get(dimension, dim_map['line'])

                show_debug(f"执行{dim_label}对比查询...")

                sql = f"""
                SELECT
                    {db_col} AS DIM_VALUE,
                    COUNT(*) AS FAULT_COUNT
                FROM MAXIMO.SR SR
                WHERE {where_clause}
                  AND {db_col} IS NOT NULL
                GROUP BY {db_col}
                ORDER BY FAULT_COUNT DESC
                FETCH FIRST 20 ROWS ONLY
                """

                result_df = pd.read_sql(sql, conn, params=params)

                if result_df.empty:
                    msg = "没有找到符合条件的故障记录，试试放宽时间范围。"
                    st.markdown(msg)
                    return msg

                total_count = int(result_df['FAULT_COUNT'].sum())
                top_row = result_df.iloc[0]
                top_val = top_row['DIM_VALUE']
                if dimension == 'line':
                    top_val = f"{top_val}号线"
                top_count = int(top_row['FAULT_COUNT'])
                top_pct = top_count / total_count * 100

                # 自然语言回答
                summary = f"共 **{total_count}** 条故障，**{top_val}** 最多（{top_count}次，占{top_pct:.0f}%）"
                if len(result_df) >= 2:
                    r2 = result_df.iloc[1]
                    v2 = f"{r2['DIM_VALUE']}号线" if dimension == 'line' else r2['DIM_VALUE']
                    summary += f"，其次是 **{v2}**（{int(r2['FAULT_COUNT'])}次）。"
                else:
                    summary += "。"

                st.markdown(summary)

                # 完整排名折叠
                with st.expander(f"查看各{dim_label}详细对比", expanded=False):
                    display_df = result_df.rename(columns={
                        'DIM_VALUE': dim_label,
                        'FAULT_COUNT': '故障次数'
                    })
                    display_df['故障次数'] = display_df['故障次数'].astype(int)
                    display_df['占比'] = display_df['故障次数'].apply(
                        lambda x: f"{x / total_count * 100:.1f}%"
                    )
                    if dimension == 'line':
                        display_df[dim_label] = display_df[dim_label].apply(lambda x: f"{x}号线")
                    st.dataframe(display_df, width='stretch', hide_index=True)

                return summary

            # ========================================
            # 模式3: 计数与详细列表
            # ========================================
            else:  # count
                show_debug("执行计数与列表查询...")

                # 如果用户没指定时间范围，默认限制为最近30天，避免返回全量历史数据
                if not entities.get('time_range'):
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    start_30d = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                    entities['time_range'] = {"start_date": start_30d, "end_date": today_str}
                    where_clause, params = build_sql_conditions_from_entities(entities)

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
                    msg = "没有找到符合条件的故障记录。可以试试放宽时间范围或去掉线路限制。"
                    st.markdown(msg)
                    return msg

                # ========================================
                # 自然语言摘要
                # ========================================
                # 构建位置描述
                line_num = entities.get('line_num')
                location_desc = f"{line_num}号线" if line_num else "全线网"

                time_range = entities.get('time_range')
                if time_range:
                    start_date = time_range.get('start_date')
                    end_date = time_range.get('end_date')
                    today = datetime.now().strftime('%Y-%m-%d')
                    if start_date == end_date:
                        # 同一天不重复显示
                        time_desc = "今天" if start_date == today else start_date
                    else:
                        time_desc = f"{start_date} 至 {end_date}"
                else:
                    time_desc = "查询时段内"

                # 主句
                summary = f"**{location_desc}{time_desc}共有 {count} 个故障**"

                # 专业分布摘要
                if 'SPECIALTY' in result_df.columns:
                    specialty_dist = result_df['SPECIALTY'].value_counts().head(3)
                    if not specialty_dist.empty:
                        top_spec = specialty_dist.index[0]
                        top_spec_count = int(specialty_dist.iloc[0])
                        top_spec_pct = top_spec_count / count * 100
                        summary += f"，其中 **{top_spec}** 最多（{top_spec_count}个，占{top_spec_pct:.0f}%）"

                # 高发车站摘要
                if 'STATIONNAME' in result_df.columns:
                    station_dist = result_df['STATIONNAME'].dropna().value_counts().head(1)
                    if not station_dist.empty and len(result_df['STATIONNAME'].dropna().unique()) > 1:
                        top_station = station_dist.index[0]
                        top_station_count = int(station_dist.iloc[0])
                        summary += f"，高发站点为 **{top_station}**（{top_station_count}个）"

                summary += "。"

                # 状态摘要
                if 'STATUS' in result_df.columns:
                    status_dist = result_df['STATUS'].value_counts()
                    resolved_keywords = ['CLOSE', 'RESOLVED', 'COMP', '关闭', '完成']
                    resolved_count = sum(
                        int(status_dist.get(s, 0))
                        for s in status_dist.index
                        if any(k in str(s).upper() for k in resolved_keywords)
                    )
                    if resolved_count > 0:
                        summary += f"\n\n已处理 {resolved_count} 个，未处理 {count - resolved_count} 个。"

                st.markdown(summary)

                # ========================================
                # 详细数据折叠展示
                # ========================================
                with st.expander("按专业/车站/班组分布", expanded=False):
                    col1, col2 = st.columns(2)

                    with col1:
                        if 'SPECIALTY' in result_df.columns:
                            st.markdown("**专业分布**")
                            for spec, cnt in result_df['SPECIALTY'].value_counts().head(5).items():
                                st.text(f"  {spec}: {cnt}条 ({cnt / count * 100:.0f}%)")

                        st.markdown("")
                        if 'STATIONNAME' in result_df.columns:
                            station_dist = result_df['STATIONNAME'].dropna().value_counts().head(5)
                            if not station_dist.empty:
                                st.markdown("**高发车站**")
                                for station, cnt in station_dist.items():
                                    st.text(f"  {station}: {cnt}次")

                    with col2:
                        if 'OWNERGROUP' in result_df.columns:
                            group_dist = result_df['OWNERGROUP'].dropna().value_counts().head(5)
                            if not group_dist.empty:
                                st.markdown("**处理班组**")
                                for group, cnt in group_dist.items():
                                    st.text(f"  {group}: {cnt}条")

                        st.markdown("")
                        if 'STATUS' in result_df.columns:
                            st.markdown("**工单状态**")
                            for status, cnt in result_df['STATUS'].value_counts().items():
                                st.text(f"  {status}: {cnt}条")

                # 时间趋势（仅多天数据时显示）
                if time_range and 'REPORTDATE' in result_df.columns:
                    result_df = result_df.copy()
                    result_df['REPORTDATE'] = pd.to_datetime(result_df['REPORTDATE'])
                    daily_counts = result_df.groupby(
                        result_df['REPORTDATE'].dt.date
                    ).size()

                    if len(daily_counts) > 1:
                        with st.expander("时间趋势", expanded=False):
                            avg_per_day = daily_counts.mean()
                            max_day = daily_counts.idxmax()
                            max_count = daily_counts.max()

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("日均", f"{avg_per_day:.1f} 条")
                            with col2:
                                st.metric("峰值日期", str(max_day))
                            with col3:
                                st.metric("峰值", f"{max_count} 条")

                            if len(daily_counts) > 7:
                                recent_avg = daily_counts.tail(3).mean()
                                earlier_avg = daily_counts.head(3).mean()
                                if recent_avg > earlier_avg * 1.2:
                                    st.warning("近期故障频率上升，建议加强关注。")
                                elif recent_avg < earlier_avg * 0.8:
                                    st.success("近期故障频率下降，趋势良好。")

                # 故障记录列表
                with st.expander(f"故障记录明细（{min(count, 100)}条）", expanded=False):
                    display_df = result_df.head(100).copy()
                    column_mapping = {
                        'TICKETID': '工单号', 'REPORTDATE': '报告时间',
                        'LINENUM': '线路', 'STATIONNAME': '车站',
                        'DESCRIPTION': '故障描述', 'STATUS': '状态',
                        'SPECIALTY': '专业', 'OWNERGROUP': '处理班组'
                    }
                    display_df = display_df.rename(columns=column_mapping)
                    if '报告时间' in display_df.columns:
                        display_df['报告时间'] = pd.to_datetime(
                            display_df['报告时间']
                        ).dt.strftime('%Y-%m-%d %H:%M')
                    st.dataframe(display_df, width='stretch', hide_index=True)
                    if count > 100:
                        st.caption(f"共 {count:,} 条，当前显示前 100 条。")

                return summary

    except Exception as e:
        st.error("统计查询执行失败")
        st.exception(e)
        return None


# ================================================================================
# VITA v14.0 - 参赛最终版
# 第5段（共6段）：故障诊断引擎（核心功能）
# ================================================================================

# ============================================
# 混合检索：元数据预过滤 + 向量检索
# ============================================
def metadata_filtered_vector_search(
        entities: Dict,
        user_query: str,
        faiss_index,
        id_map
) -> pd.DataFrame:
    """
    混合检索：向量语义检索 + 关键词检索 + RRF 融合

    改进点（v16.0）：
    1. FAISS 检索 k 从 50 提升到 100，扩大候选集
    2. 新增 Oracle 关键词检索，捕获精确词匹配案例
    3. RRF 融合两路结果，兼顾语义相似度和关键词匹配
    4. 参数化 SQL 查询（修复原版 SQL 注入风险）
    """
    show_progress("正在知识库中检索...")

    # 构建查询文本（原版格式）
    context_parts = []
    if entities.get('line_num'):
        line_nums = str(entities['line_num']).split(',')
        line_str = '、'.join(n.strip() + '号线' for n in line_nums)
        context_parts.append(f"线路:{line_str}")
    if entities.get('station_name'):
        context_parts.append(f"车站:{entities.get('station_name')}")
    context_parts.append(f"设备:{entities.get('device')}")
    context_parts.append(f"现象:{entities.get('fault_phenomenon')}")

    query_text = " | ".join(filter(None, context_parts))
    show_debug(f"向量检索查询: {query_text}")

    # ── 路径1：向量检索 ──────────────────────────────────────
    headers = {'Content-Type': 'application/json'}
    payload = {"inputs": query_text}
    try:
        response = requests.post(EMBEDDING_API_URL, headers=headers,
                                 data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        query_embedding = response.json()
        # Embedding API 返回批量格式 [[...1024...]]，需要取 [0] 得到 1024 维向量
        if isinstance(query_embedding, list) and len(query_embedding) == 1 and isinstance(query_embedding[0], list):
            query_embedding = query_embedding[0]
    except Exception as e:
        st.error(f"Embedding调用失败: {e}")
        return pd.DataFrame()

    distances, indices = faiss_index.search(
        np.array([query_embedding], dtype='float32'), k=50  # 优化：降低到50提升速度
    )
    vector_ticket_ids = [str(tid) for tid in id_map[indices[0]]]
    show_debug(f"向量检索: {len(vector_ticket_ids)} 个候选")

    # ── 路径2：关键词检索 ────────────────────────────────────
    keyword_ticket_ids = keyword_search_oracle(entities, top_k=50)
    show_debug(f"关键词检索: {len(keyword_ticket_ids)} 个候选")

    # ── RRF 融合 ─────────────────────────────────────────────
    if keyword_ticket_ids:
        fused_ids = reciprocal_rank_fusion([vector_ticket_ids, keyword_ticket_ids])
        show_debug(f"RRF 融合后: {len(fused_ids)} 个唯一候选（向量+关键词）")
    else:
        fused_ids = vector_ticket_ids
        show_debug("关键词检索无结果，仅使用向量检索")

    # 限制最终候选数量
    fused_ticket_ids = fused_ids[:100]

    if not fused_ticket_ids:
        show_warning("知识库检索无匹配案例")
        return pd.DataFrame()

    # ── 参数化查询获取完整工单数据（修复 SQL 注入）───────────
    if not DatabaseManager.is_available():
        show_warning("数据库连接不可用，无法获取工单详情")
        show_info("向量检索已找到候选案例，但需要数据库连接才能获取完整信息。请检查网络或联系管理员。")
        return pd.DataFrame()

    try:
        # 使用命名占位符，避免字符串拼接
        placeholders = ", ".join([f":id_{i}" for i in range(len(fused_ticket_ids))])
        params = {f"id_{i}": tid for i, tid in enumerate(fused_ticket_ids)}
        sql = f"""
        SELECT SR.TICKETID, SR.ASSETNUM, SR.LINENUM, SR.STATIONNAME,
               SR.DESCRIPTION, SR.LONGDESCRIPTION, SR.SPECIALTY, SR.REPORTDATE,
               COALESCE(SR.SOLUTION, SR.PROCREMEDY, '未记录') AS SOLUTION,
               SR.FAILURECODE, SR.PROBLEMCODE
        FROM MAXIMO.SR SR
        WHERE SR.TICKETID IN ({placeholders})
        """
        cases_df = DatabaseManager.execute_query_safe(sql, params)
    except Exception as e:
        logger.error(f"案例详情查询失败: {e}")
        return pd.DataFrame()

    show_success(f"检索完成: 向量{len(vector_ticket_ids)}条 + 关键词{len(keyword_ticket_ids)}条 → 融合{len(cases_df)}条")
    return cases_df


# ============================================
# 相关度评分（增加位置权重）
# ============================================
def calculate_relevance_score(row, entities: Dict) -> int:
    """
    案例相关度评分
    核心改进：增加位置权重（同车站+50，同线路+20）
    """
    score = 0

    # 专业匹配（权重最高）
    if entities.get('specialty') and pd.notna(row['SPECIALTY']):
        user_specialty = entities['specialty'].upper()
        case_specialty = str(row['SPECIALTY']).upper()

        if user_specialty in case_specialty or case_specialty in user_specialty:
            score += 500
        else:
            specialty_variants = expand_specialty_synonyms(entities['specialty'])
            for variant in specialty_variants:
                if variant.upper() in case_specialty:
                    score += 500
                    break

    # 故障现象匹配
    if entities.get('fault_phenomenon') and pd.notna(row['PROBLEMCODE']):
        if entities['fault_phenomenon'] in str(row['PROBLEMCODE']):
            score += 100

    # 故障现象在描述中匹配
    if entities.get('fault_phenomenon') and pd.notna(row['DESCRIPTION']):
        if entities['fault_phenomenon'] in str(row['DESCRIPTION']):
            score += 80

    # 设备名称匹配
    if entities.get('device') and pd.notna(row['FAILURECODE']):
        if entities['device'] in str(row['FAILURECODE']):
            score += 80

    # 车站匹配（新增权重）
    if entities.get('station_name') and pd.notna(row['STATIONNAME']):
        if entities.get('station_name') in str(row['STATIONNAME']):
            score += 50

    # 线路匹配（支持多线路）
    if entities.get('line_num'):
        user_lines = [n.strip() for n in str(entities['line_num']).split(',')]
        if str(row['LINENUM']) in user_lines:
            score += 20

    return score


# ============================================
# 歧义检测（本地计算，替代 LLM 调用，省 ~20s）
# ============================================
def detect_ambiguity_local(
        cases_df: pd.DataFrame,
        device: str,
        user_query: str
) -> Dict:
    """本地歧义检测 — 用阈值规则替代 LLM 调用"""
    specialty_distribution = cases_df['SPECIALTY'].value_counts()
    total = len(cases_df)

    if total == 0:
        return {"should_stop": False}

    top_specialties = []
    for spec, count in specialty_distribution.head(5).items():
        pct = round(float(count) / total * 100, 1)
        top_specialties.append({"specialty": spec, "count": int(count), "pct": pct})

    # 规则1: 主导专业 >75% → 无歧义
    if top_specialties and top_specialties[0]["pct"] > 75:
        return {"should_stop": False}

    # 规则2: 2个以上专业各占 >20% → 存在歧义
    high_share = [s for s in top_specialties if s["pct"] > 20]
    if len(high_share) >= 2:
        st.markdown("---")
        st.warning("### 检测到专业归属歧义")
        st.markdown("历史案例分布在多个专业：")
        for s in high_share:
            st.markdown(f"- **{s['specialty']}**: {s['count']}次 ({s['pct']:.0f}%)")
        st.markdown(f"\n请在问题中明确设备类型，例如指定是哪个专业的{device}。")
        return {"should_stop": True}

    return {"should_stop": False}


# ============================================
# 案例数据分析（增加分层统计）
# ============================================
def analyze_case_data(cases_df: pd.DataFrame, entities: Dict) -> Dict:
    """
    案例数据统计分析（v2 — 全量DB聚合）

    设计原则：
    - 统计数据（计数、占比、趋势）从数据库全量聚合，不依赖检索的少量案例
    - 本站历史从数据库直接查最近记录
    - 检索到的 top 案例仅供 LLM 引用具体维修方案
    - DB 查询失败时自动降级到案例级分析
    """
    line_num = entities.get('line_num')
    station_name = entities.get('station_name')
    specialty = normalize_text(entities.get('specialty') or entities.get('device') or '')

    # 返回值初始化
    result = {
        'total_cases': 0, 'line_cases': 0, 'station_cases': 0,
        'solution_stats': [], 'cause_stats': [], 'station_history': [],
        'high_freq_stations': [], 'specialty_distribution': {},
        'time_trend': {'recent_30d': 0, 'prev_30d': 0, 'trend': '平稳'},
        'risk_assessment': {'level': 'low', 'freq_text': '', 'recommendation': ''},
    }

    # ── 构建 SPECIALTY 条件 ─────────────────────────────
    synonyms = expand_specialty_synonyms(specialty) if specialty else []
    if not synonyms:
        synonyms = [specialty] if specialty else []

    def _build_sp_clause(params_dict, prefix='sp'):
        conds = []
        for i, syn in enumerate(synonyms[:5]):
            key = f'{prefix}_{i}'
            conds.append(f"UPPER(SR.SPECIALTY) LIKE UPPER(:{key})")
            params_dict[key] = f'%{DatabaseManager.sanitize_input(syn)}%'
        return ' OR '.join(conds) if conds else '1=1'

    # ── 数据库全量聚合（一次连接完成） ──────────────────
    try:
        with DatabaseManager.get_connection() as conn:
            sp_params = {}
            sp_where = _build_sp_clause(sp_params)

            # ① 合并查询：总量 + 本线路 + 本站 + 趋势（1条SQL）
            ln_case = "0"
            stn_case = "0"
            extra_params = {**sp_params}
            if line_num:
                extra_params['ln'] = DatabaseManager.sanitize_input(str(line_num))
                ln_case = "CASE WHEN SR.LINENUM = :ln THEN 1 ELSE 0 END"
            if station_name:
                extra_params['stn'] = f'%{DatabaseManager.sanitize_input(station_name)}%'
                stn_case = "CASE WHEN UPPER(SR.STATIONNAME) LIKE UPPER(:stn) THEN 1 ELSE 0 END"

            main_sql = f"""
            SELECT
                COUNT(*) AS TOTAL_CNT,
                SUM({ln_case}) AS LINE_CNT,
                SUM({stn_case}) AS STN_CNT,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 7 THEN 1 ELSE 0 END) AS D7,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 30 THEN 1 ELSE 0 END) AS D30,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 60 AND SR.REPORTDATE <= SYSDATE - 30 THEN 1 ELSE 0 END) AS PREV30,
                SUM(CASE WHEN SR.REPORTDATE > SYSDATE - 90 THEN 1 ELSE 0 END) AS D90
            FROM MAXIMO.SR SR WHERE ({sp_where})
            """
            main_df = pd.read_sql(main_sql, conn, params=extra_params)
            if not main_df.empty:
                r = main_df.iloc[0]
                result['total_cases'] = int(r['TOTAL_CNT'] or 0)
                result['line_cases'] = int(r['LINE_CNT'] or 0)
                result['station_cases'] = int(r['STN_CNT'] or 0)
                d7 = int(r['D7'] or 0)
                d30 = int(r['D30'] or 0)
                prev30 = int(r['PREV30'] or 0)
                d90 = int(r['D90'] or 0)
                result['time_trend'] = {
                    'recent_7d': d7, 'recent_30d': d30,
                    'prev_30d': prev30, 'recent_90d': d90,
                    'trend': '上升' if d30 > prev30 else '下降' if d30 < prev30 else '平稳'
                }

            # ② 处理方式统计（1条 CASE WHEN 合并SQL）
            kw_list = ['重启', '更换', '调整', '清洁', '紧固', '检查', '复位', '修复', '断电', '重新配置']
            kw_cases = ", ".join(
                f"SUM(CASE WHEN SR.SOLUTION LIKE '%{kw}%' THEN 1 ELSE 0 END) AS KW{i}"
                for i, kw in enumerate(kw_list)
            )
            sol_sql = f"SELECT {kw_cases} FROM MAXIMO.SR SR WHERE ({sp_where})"
            sol_df = pd.read_sql(sol_sql, conn, params=sp_params)
            if not sol_df.empty:
                total = result['total_cases'] or 1
                for i, kw in enumerate(kw_list):
                    cnt = int(sol_df.iloc[0][f'KW{i}'] or 0)
                    if cnt > 0:
                        result['solution_stats'].append({
                            'method': kw, 'count': cnt,
                            'percentage': round(cnt / total * 100, 1)
                        })
                result['solution_stats'].sort(key=lambda x: x['count'], reverse=True)

            # ③ 故障原因分布
            try:
                cause_sql = f"""
                SELECT REGEXP_SUBSTR(SR.LONGDESCRIPTION, '原因[：:](.*)', 1, 1, 'n', 1) AS CAUSE,
                       COUNT(*) AS CNT
                FROM MAXIMO.SR SR
                WHERE ({sp_where}) AND SR.LONGDESCRIPTION IS NOT NULL
                GROUP BY REGEXP_SUBSTR(SR.LONGDESCRIPTION, '原因[：:](.*)', 1, 1, 'n', 1)
                HAVING REGEXP_SUBSTR(SR.LONGDESCRIPTION, '原因[：:](.*)', 1, 1, 'n', 1) IS NOT NULL
                ORDER BY CNT DESC FETCH FIRST 5 ROWS ONLY
                """
                cause_df = pd.read_sql(cause_sql, conn, params=sp_params)
                total = result['total_cases'] or 1
                for _, row in cause_df.iterrows():
                    c = str(row['CAUSE']).strip()[:50]
                    if c:
                        result['cause_stats'].append({
                            'cause': c, 'count': int(row['CNT']),
                            'percentage': round(int(row['CNT']) / total * 100, 1)
                        })
            except Exception:
                pass  # Oracle REGEXP 异常时跳过

            # ④ 高发站点 TOP 5
            top_stn_sql = f"""
            SELECT SR.STATIONNAME, COUNT(*) AS CNT
            FROM MAXIMO.SR SR
            WHERE ({sp_where}) AND SR.STATIONNAME IS NOT NULL
            GROUP BY SR.STATIONNAME ORDER BY CNT DESC
            FETCH FIRST 5 ROWS ONLY
            """
            top_stn_df = pd.read_sql(top_stn_sql, conn, params=sp_params)
            if not top_stn_df.empty:
                result['high_freq_stations'] = [
                    {'station': row['STATIONNAME'], 'count': int(row['CNT'])}
                    for _, row in top_stn_df.iterrows()
                ]

            # ⑤ 本站同设备历史（DB直接查最近3条）
            if station_name:
                hist_params = {**sp_params, 'stn_h': f'%{DatabaseManager.sanitize_input(station_name)}%'}
                hist_sql = f"""
                SELECT SR.TICKETID, SR.REPORTDATE, SR.DESCRIPTION, SR.SOLUTION
                FROM MAXIMO.SR SR
                WHERE ({sp_where}) AND UPPER(SR.STATIONNAME) LIKE UPPER(:stn_h)
                ORDER BY SR.REPORTDATE DESC
                FETCH FIRST 3 ROWS ONLY
                """
                hist_df = pd.read_sql(hist_sql, conn, params=hist_params)
                for _, row in hist_df.iterrows():
                    result['station_history'].append({
                        'ticket': str(row.get('TICKETID', 'N/A')),
                        'date': str(row.get('REPORTDATE', ''))[:10],
                        'desc': str(row.get('DESCRIPTION', ''))[:80],
                        'solution': str(row.get('SOLUTION', ''))[:120],
                    })

        logger.info(f"[统计] DB全量: total={result['total_cases']}, line={result['line_cases']}, station={result['station_cases']}")

    except Exception as e:
        logger.warning(f"数据库聚合统计失败，降级到案例级分析: {e}")
        # ── 降级：从检索到的案例中分析 ──
        result['total_cases'] = len(cases_df)
        if line_num:
            user_lines = [n.strip() for n in str(line_num).split(',')]
            result['line_cases'] = len(cases_df[cases_df['LINENUM'].astype(str).isin(user_lines)])
        if station_name:
            result['station_cases'] = len(cases_df[cases_df['STATIONNAME'].str.contains(station_name, na=False)])
        # 处理方式（降级）
        for kw in ['重启', '更换', '调整', '清洁', '紧固', '检查', '复位', '修复']:
            cnt = int(cases_df['SOLUTION'].str.contains(kw, na=False).sum())
            if cnt > 0:
                result['solution_stats'].append({
                    'method': kw, 'count': cnt,
                    'percentage': round(cnt / max(len(cases_df), 1) * 100, 1)
                })
        result['solution_stats'].sort(key=lambda x: x['count'], reverse=True)
        # 本站历史（降级）
        if station_name:
            cp = cases_df.copy()
            cp['REPORTDATE'] = pd.to_datetime(cp['REPORTDATE'])
            sdf = cp[cp['STATIONNAME'].str.contains(station_name, na=False)]
            for _, row in sdf.sort_values('REPORTDATE', ascending=False).head(3).iterrows():
                result['station_history'].append({
                    'ticket': row.get('TICKETID', 'N/A'), 'date': str(row.get('REPORTDATE', ''))[:10],
                    'desc': str(row.get('DESCRIPTION', ''))[:80], 'solution': str(row.get('SOLUTION', ''))[:120],
                })

    # 原因统计补充（如果DB没查到，从案例里取）
    if not result['cause_stats'] and 'FAULT_CAUSE' in cases_df.columns:
        for cause, count in cases_df['FAULT_CAUSE'].dropna().value_counts().head(5).items():
            if str(cause).strip() and str(cause) != 'nan':
                result['cause_stats'].append({
                    'cause': str(cause)[:50], 'count': int(count),
                    'percentage': round(int(count) / max(len(cases_df), 1) * 100, 1)
                })

    # 专业分布
    result['specialty_distribution'] = {
        k: int(v) for k, v in cases_df['SPECIALTY'].value_counts().head(3).to_dict().items()
    }

    # ── 风险评估（原 analyze_similar_faults 的逻辑） ──
    trend = result['time_trend']
    d7 = trend.get('recent_7d', 0)
    d30 = trend.get('recent_30d', 0)
    d90 = trend.get('recent_90d', 0)
    if d7 >= 5 or d30 >= 15:
        risk_level, freq_text = 'critical', f'近7天{d7}次、近30天{d30}次，高频活跃故障'
    elif d7 >= 3 or d30 >= 8:
        risk_level, freq_text = 'high', f'近7天{d7}次、近30天{d30}次，频率较高'
    elif d30 >= 3 or d90 >= 10:
        risk_level, freq_text = 'medium', f'近30天{d30}次、近90天{d90}次，频率一般'
    else:
        risk_level, freq_text = 'low', f'近30天{d30}次，故障较少'

    rec_map = {
        'critical': '建议立即排查并制定专项整治方案',
        'high': '建议加强巡检频次，关注同类设备状态',
        'medium': '建议按常规维保计划关注',
        'low': '故障较少，保持常规维护即可'
    }
    result['risk_assessment'] = {
        'level': risk_level, 'freq_text': freq_text,
        'recommendation': rec_map[risk_level]
    }

    return result


# 知识库查询
# ============================================
def query_knowledge_base(device: str, action: Optional[str], specialty: str) -> Dict:
    """三级知识库查询策略"""
    if specialty in ELECTROMECHANICAL_SPECIALTIES:
        return {
            'level': 'general_guide',
            'specialty': specialty,
            'link': GENERAL_GUIDE_LINK
        }
    return {
        'level': 'no_standard',
        'specialty': specialty
    }


# ============================================
# 生成诊断报告
# ============================================
def generate_diagnostic_report(
        data_analysis: Dict,
        knowledge_result: Dict,
        most_similar_case: Dict,
        user_query: str = ""
) -> str:
    """生成专业诊断报告"""
    report_data = {
        '处理方式统计': data_analysis['solution_stats'][:5],
        '最相似案例': {
            '工单号': most_similar_case.get('TICKETID'),
            '描述': most_similar_case.get('DESCRIPTION'),
            '措施': most_similar_case.get('SOLUTION')
        },
        '知识库': knowledge_result
    }

    prompt = f"""你是一个经验丰富的地铁设备维修工程师。用户问了一个设备相关的问题，下面是从历史工单中提取的关键数据。

请你根据这些数据，直接回答用户的问题。

【核心原则】
- 答即所问：用户问原因就分析原因，问怎么修就给步骤，问是否常见就说频率
- 说人话：像一个老师傅在现场指导，不要写"诊断报告"、"注意事项"这种官话标题
- 精准有用：只说跟这个问题直接相关的内容，不堆砌无关信息
- 可以引用案例工单号作为依据，但不要罗列案例清单
- 回复控制在150-300字，简洁有力

【用户问题】{user_query}

【历史数据】
```json
{json.dumps(report_data, ensure_ascii=False, indent=2)}
```

直接回复用户："""

    response = call_llm_with_validation(
        prompt=prompt,
        require_json=False,
        temperature=0.3,
        timeout=90
    )

    if 'error' in response:
        return "报告生成失败"

    return response.get('content', '报告异常')


def generate_diagnostic_report_stream(
        data_analysis: Dict,
        knowledge_result: Dict,
        top_cases: pd.DataFrame,
        user_query: str = "",
        entities: Dict = None
):
    """
    流式生成诊断报告（v2 — 数据驱动）
    
    数据来源：
    - data_analysis: 来自数据库全量聚合统计
    - top_cases: 来自 rerank 精排的 top 20 案例（用于具体案例引用）
    """

    # 构建 top 5 案例的结构化文本
    case_summaries = []
    for i, (_, row) in enumerate(top_cases.head(5).iterrows()):
        case_summaries.append(
            f"案例{i+1} [{row.get('TICKETID', 'N/A')}]:\n"
            f"  线路/站点: {row.get('LINENUM', '?')}号线 {row.get('STATIONNAME', '?')}\n"
            f"  描述: {str(row.get('DESCRIPTION', ''))[:120]}\n"
            f"  原因: {str(row.get('FAULT_CAUSE', '未记录'))[:80]}\n"
            f"  措施: {str(row.get('SOLUTION', ''))[:200]}"
        )
    cases_text = "\n".join(case_summaries)

    # 处理方式统计
    stats_text = "、".join(
        f"{s['method']}({s['count']}次,{s['percentage']}%)"
        for s in data_analysis['solution_stats'][:5]
    ) if data_analysis['solution_stats'] else "暂无统计"

    # 故障原因统计
    cause_text = "、".join(
        f"{c['cause']}({c['count']}次,{c['percentage']}%)"
        for c in data_analysis.get('cause_stats', [])[:5]
    ) if data_analysis.get('cause_stats') else "暂无原因分类记录"

    # 本站历史
    station_history_text = ""
    station_history = data_analysis.get('station_history', [])
    if station_history:
        station_name = entities.get('station_name', '') if entities else ''
        history_items = []
        for h in station_history:
            history_items.append(f"  - [{h['ticket']}] {h['date']}: {h['desc']} → 处理: {h['solution']}")
        station_history_text = f"\n【本站（{station_name}）同设备近期故障记录】\n" + "\n".join(history_items)

    # 趋势
    trend = data_analysis.get('time_trend', {})
    trend_text = ""
    if trend:
        trend_text = f"近7天{trend.get('recent_7d', 0)}次、近30天{trend.get('recent_30d', 0)}次、前30天{trend.get('prev_30d', 0)}次，趋势{trend.get('trend', '平稳')}"

    # 高发站点
    high_freq = data_analysis.get('high_freq_stations', [])
    high_freq_text = ""
    if high_freq:
        high_freq_text = "\n- 高发站点: " + "、".join(f"{s['station']}({s['count']}次)" for s in high_freq[:5])

    # 风险评估
    risk = data_analysis.get('risk_assessment', {})
    risk_text = ""
    if risk.get('freq_text'):
        risk_labels = {'low': '低', 'medium': '中', 'high': '高', 'critical': '严重'}
        risk_text = f"\n- 风险等级: {risk_labels.get(risk.get('level', 'low'), '低')} — {risk.get('freq_text', '')}"

    prompt = f"""你是经验丰富的地铁设备维修工程师，正在基于历史维修数据为现场同事提供科学、严谨的故障排查建议。

【用户问题】
{user_query}

【数据分析结果】
- 检索到相关历史案例共 {data_analysis['total_cases']} 条
- 本线路相关案例: {data_analysis['line_cases']} 条
- 本站相关案例: {data_analysis['station_cases']} 条
- 故障原因分布: {cause_text}
- 处理方式分布: {stats_text}
- 时间趋势: {trend_text}{high_freq_text}{risk_text}
{station_history_text}

【最相关的历史维修案例】
{cases_text}

【回答要求——数据驱动，科学严谨】
请按以下结构回答：

1. **故障概况**：简述共有多少类似故障记录，主要原因分布比例

2. **最可能原因排序**：根据历史数据中的原因占比，从高到低列出最可能的原因，每个原因标注占比和代表案例工单号

3. **推荐排查步骤**：根据原因概率从高到低，给出逐步排查方案。每步需说明：
   - 具体检查什么
   - 如何判断是否是该原因
   - 对应的处理方法
   - 历史案例依据（工单号）

4. **本站历史参考**（如有本站数据）：提及该站上次类似故障的时间和修复方式

5. **注意事项**：安全提醒、容易忽略的关联故障等

篇幅要求：400-1000字，根据问题复杂度自然展开，关键是每个结论都要有数据依据，不要凭空推测。

直接回答："""

    yield from call_llm_stream(prompt, temperature=0.3, max_tokens=1500)


# ================================================================================
# VITA v14.0 - 参赛最终版
# 第6段（共6段）：故障诊断主流程 + Streamlit主程序
# ================================================================================

def diagnose_fault(entities: Dict, user_query: str, faiss_index, id_map):
    """
    故障诊断引擎 - 完整流程

    核心改进：
    1. 全线网检索，保证样本量
    2. 按位置权重排序
    3. 过滤不相关案例（相关度<60分）
    4. 展示分层统计数据
    5. 同类故障分析替代设备履历
    """
    device = entities.get('device') or entities.get('specialty')
    if not device:
        st.markdown('没有识别出具体的设备信息。可以说得更详细些，比如"ISCS工作站黑屏怎么办"。')
        return

    try:
        start_time = time.time()
        stage_times = {}  # 记录各阶段耗时

        with st.status("正在分析...", expanded=True) as diag_status:

            # 阶段1：混合检索
            stage_start = time.time()
            diag_status.write("📚 检索相关历史案例...")

            cases_df = metadata_filtered_vector_search(
                entities=entities,
                user_query=user_query,
                faiss_index=faiss_index,
                id_map=id_map
            )
            stage_times['检索'] = time.time() - stage_start
            logger.info(f"[性能] 检索耗时: {stage_times['检索']:.2f}秒")

            if cases_df.empty:
                diag_status.update(label="未找到匹配案例", state="error")
                st.info("建议：尝试使用更通用的设备名称或专业类别")
                return

            # 提取故障原因
            cases_df['FAULT_CAUSE'] = cases_df['LONGDESCRIPTION'].apply(extract_fault_cause)

            # 相关度打分（增加位置权重）
            cases_df['RELEVANCE_SCORE'] = cases_df.apply(
                lambda row: calculate_relevance_score(row, entities),
                axis=1
            )
            cases_df = cases_df.sort_values('RELEVANCE_SCORE', ascending=False)

            # 过滤有解决方案的案例
            curated_df = cases_df[cases_df['SOLUTION'].str.len() > 5]

            if curated_df.empty:
                diag_status.update(label="相似案例缺少解决方案", state="complete")
                st.info("建议：参考历史案例的故障描述，联系对应班组处理")
                with st.expander("查看无解决方案的相似案例", expanded=False):
                    st.dataframe(
                        cases_df.head(10)[['TICKETID', 'REPORTDATE', 'DESCRIPTION', 'RELEVANCE_SCORE']],
                        width='stretch',
                        hide_index=True
                    )
                return

            diag_status.write(f"✅ 找到 {len(curated_df)} 条有效案例")

            # 阶段2：神经 Rerank 精排
            stage_start = time.time()
            diag_status.write("⚖️ 神经重排序...")
            analysis_df, rerank_applied = apply_rerank_to_df(
                df=curated_df.head(30),  # 优化：从50降到30提升速度
                query=user_query,
                top_k=20
            )
            stage_times['Rerank'] = time.time() - stage_start
            logger.info(f"[性能] Rerank耗时: {stage_times['Rerank']:.2f}秒")

            # 阶段3：歧义检测（本地计算，<1ms）
            ambiguity_result = detect_ambiguity_local(
                analysis_df, device, user_query
            )
            if ambiguity_result.get('should_stop'):
                diag_status.update(label="需要澄清设备类型", state="complete")
                return

            # 阶段4：数据分析
            stage_start = time.time()
            diag_status.write("📊 统计分析...")
            data_analysis = analyze_case_data(analysis_df, entities)
            stage_times['数据分析'] = time.time() - stage_start
            logger.info(f"[性能] 数据分析耗时: {stage_times['数据分析']:.2f}秒")

            # 阶段5 已合并到 analyze_case_data（风险评估）

            # 阶段6：知识库查询
            stage_start = time.time()
            diag_status.write("📖 查询知识库...")
            top_action = data_analysis['solution_stats'][0]['method'] if data_analysis['solution_stats'] else None
            knowledge_result = query_knowledge_base(
                device, top_action, analysis_df.iloc[0]['SPECIALTY']
            )
            stage_times['知识库查询'] = time.time() - stage_start
            logger.info(f"[性能] 知识库查询耗时: {stage_times['知识库查询']:.2f}秒")

            # 风险评估已在 data_analysis 中
            risk = data_analysis.get('risk_assessment', {})

            total_time = time.time() - start_time
            diag_status.update(
                label=f"分析完成（{total_time:.1f}s）· 检索 {len(cases_df)} 条 → 精排 {len(analysis_df)} 条",
                state="complete",
                expanded=False
            )

        # ========================================
        # 报告展示（在 status 块外渲染，显示在主聊天区）
        # ========================================

        # 显示生成提示
        stage_start = time.time()
        with st.spinner("💭 正在生成诊断建议..."):
            # 主报告（流式输出，同时收集文本用于历史记录）
            collected_chunks = []
            def _capturing_stream():
                logger.info("开始生成诊断报告流...")
                chunk_count = 0
                for chunk in generate_diagnostic_report_stream(
                    data_analysis=data_analysis,
                    knowledge_result=knowledge_result,
                    top_cases=analysis_df,
                    user_query=user_query,
                    entities=entities
                ):
                    chunk_count += 1
                    collected_chunks.append(chunk)
                    yield chunk
                logger.info(f"诊断报告流生成完成，共 {chunk_count} 个chunk，总长度 {len(''.join(collected_chunks))} 字符")

            st.write_stream(_capturing_stream())
            response_text = "".join(collected_chunks)
            stage_times['LLM生成'] = time.time() - stage_start
            logger.info(f"[性能] LLM生成耗时: {stage_times['LLM生成']:.2f}秒")
            logger.info(f"诊断报告已显示，长度 {len(response_text)} 字符")

        # 性能总结
        total_time = time.time() - start_time
        logger.info(f"[性能总结] 总耗时: {total_time:.2f}秒")
        for stage, duration in stage_times.items():
            percentage = (duration / total_time * 100) if total_time > 0 else 0
            logger.info(f"  - {stage}: {duration:.2f}秒 ({percentage:.1f}%)")

        # 提取回答中引用的工单号，展示案例详情
        mentioned_ids = re.findall(r'SD\d+', response_text)
        if mentioned_ids:
            referenced = analysis_df[analysis_df['TICKETID'].isin(mentioned_ids)]
            if not referenced.empty:
                with st.expander(f"引用案例详情（{len(referenced)}条）", expanded=False):
                    for _, row in referenced.iterrows():
                        st.markdown(f"**{row['TICKETID']}** · {row.get('LINENUM', '')}号线{row.get('STATIONNAME', '')} · {pd.to_datetime(row['REPORTDATE']).strftime('%Y-%m-%d')}")
                        st.markdown(f"> **故障描述**: {row.get('DESCRIPTION', '无')}")
                        sol = row.get('SOLUTION', '')
                        if sol and len(str(sol)) > 5:
                            st.markdown(f"> **处理措施**: {sol}")
                        st.markdown("---")

        # 风险评估摘要
        risk = data_analysis.get('risk_assessment', {})
        risk_labels = {'low': '低', 'medium': '中', 'high': '高', 'critical': '严重'}
        if risk.get('level') and risk['level'] != 'low':
            with st.expander(f"⚠️ 风险评估：{risk_labels.get(risk['level'], '中')}风险", expanded=False):
                st.markdown(f"**频率**: {risk.get('freq_text', '')}")
                st.markdown(f"**建议**: {risk.get('recommendation', '')}")
                trend = data_analysis.get('time_trend', {})
                st.markdown(f"**趋势**: 近30天{trend.get('recent_30d', 0)}次 vs 前30天{trend.get('prev_30d', 0)}次 → {trend.get('trend', '平稳')}")
                high_freq = data_analysis.get('high_freq_stations', [])
                if high_freq:
                    st.markdown("**高发站点**: " + "、".join(f"{s['station']}({s['count']}次)" for s in high_freq[:5]))

        # 附录：相似案例列表
        with st.expander(f"相似案例（{min(20, len(analysis_df))}条）", expanded=False):
            display_df = analysis_df[[
                'TICKETID', 'REPORTDATE', 'LINENUM', 'STATIONNAME',
                'DESCRIPTION', 'SOLUTION', 'RELEVANCE_SCORE'
            ]].copy()

            display_df = display_df.rename(columns={
                'TICKETID': '工单号',
                'REPORTDATE': '报告时间',
                'LINENUM': '线路',
                'STATIONNAME': '车站',
                'DESCRIPTION': '故障描述',
                'SOLUTION': '处理措施',
                'RELEVANCE_SCORE': '相关度得分'
            })

            display_df['报告时间'] = pd.to_datetime(
                display_df['报告时间']
            ).dt.strftime('%Y-%m-%d')

            st.dataframe(
                display_df,
                width='stretch',
                hide_index=True
            )

        # 技术说明（调试用）
        with st.expander("执行详情", expanded=False):
            st.markdown(f"""
            ### 分析流程指标

            **1. 混合检索**
            - 向量语义检索（FAISS IVF, k=100）
            - 关键词精确匹配（Oracle INSTR）
            - RRF 倒数排名融合
            - 候选案例: {len(cases_df)} 条
            - 有效案例: {len(curated_df)} 条

            **2. 神经重排序**
            - Cross-Encoder: {'已启用' if rerank_applied else '规则降级'}
            - 精排后: {len(analysis_df)} 条

            **3. 多维度分析**
            - 全局样本: {data_analysis['total_cases']} 条
            - 本线路: {data_analysis['line_cases']} 条
            - 本站: {data_analysis['station_cases']} 条
            - 处理方式种类: {len(data_analysis['solution_stats'])}

            **4. 智能评估**
            - 歧义检测: {'通过' if not ambiguity_result.get('should_stop') else '已触发'}
            - 知识库: {knowledge_result.get('level', '无')}
            """)

        return response_text

    except Exception as e:
        st.error("诊断过程出现异常")
        st.exception(e)
        return None


# ================================================================================
# Streamlit 主程序
# ================================================================================

# 样式
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    *, [class*="css"] {
        font-family: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    }

    /* 背景 - 带一点质感 */
    .stApp {
        background: #f5f7fa;
        background-image: radial-gradient(circle at 20% 50%, rgba(220,230,245,0.4) 0%, transparent 50%),
                          radial-gradient(circle at 80% 20%, rgba(210,220,240,0.3) 0%, transparent 50%);
    }
    #MainMenu, footer { visibility: hidden; }
    header { background: transparent !important; }

    .block-container { max-width: 840px; padding-top: 2rem; padding-bottom: 6rem; }

    /* 聊天气泡 */
    .stChatMessage {
        background: rgba(255,255,255,0.85) !important;
        backdrop-filter: blur(8px) !important;
        border: 1px solid rgba(226,232,240,0.6) !important;
        border-radius: 18px !important;
        padding: 1.3rem 1.5rem !important;
        margin: 0.7rem 0 !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.04) !important;
        transition: all 0.2s ease !important;
    }
    .stChatMessage:hover {
        box-shadow: 0 4px 20px rgba(0,0,0,0.07) !important;
    }
    [data-testid="stChatMessage"][aria-label="user"] {
        background: rgba(237,242,255,0.9) !important;
        border-color: rgba(190,210,245,0.5) !important;
    }

    /* Header */
    .vita-header { text-align: center; padding: 1.5rem 0 1rem 0; }
    .vita-header h2 {
        font-size: 1.8rem; font-weight: 700; margin: 0; letter-spacing: -0.03em;
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .vita-header p { font-size: 0.82rem; color: #8b8fa3; margin: 0.4rem 0 0 0; }

    /* 推荐提问按钮 */
    .stButton > button {
        background: white; color: #475569; border: 1px solid #e2e8f0;
        border-radius: 22px; padding: 0.55rem 1.2rem; font-size: 0.85rem;
        font-weight: 400; transition: all 0.2s ease; text-align: left;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .stButton > button:hover {
        background: #eef2ff; border-color: #818cf8; color: #4338ca;
        transform: translateY(-1px); box-shadow: 0 3px 10px rgba(99,102,241,0.12);
    }

    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background: rgba(248,250,252,0.9) !important;
        backdrop-filter: blur(12px) !important;
        border-right: 1px solid rgba(226,232,240,0.6) !important;
    }

    /* Metric */
    [data-testid="stMetric"] {
        background: white; border: 1px solid #e8eaed; border-radius: 14px;
        padding: 1.1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.03);
    }
    [data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 700; color: #0f172a; }

    /* 提示框 */
    .element-container .stSuccess { background: rgba(16,185,129,0.08); border: none; border-left: 4px solid #10b981; color: #065f46; border-radius: 8px; }
    .element-container .stWarning { background: rgba(245,158,11,0.08); border: none; border-left: 4px solid #f59e0b; color: #92400e; border-radius: 8px; }
    .element-container .stInfo { background: rgba(59,130,246,0.08); border: none; border-left: 4px solid #3b82f6; color: #1e3a8a; border-radius: 8px; }
    .element-container .stError { background: rgba(239,68,68,0.08); border: none; border-left: 4px solid #ef4444; color: #991b1b; border-radius: 8px; }

    /* DataFrame */
    [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.04); border: 1px solid #e8eaed; }

    /* Expander 美化 */
    .streamlit-expanderHeader { font-size: 0.88rem; font-weight: 500; color: #475569; }
    details[data-testid="stExpander"] {
        background: white; border: 1px solid #e8eaed; border-radius: 12px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.03); margin-top: 0.5rem;
    }

    /* Status 组件 */
    [data-testid="stStatusWidget"] { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="vita-header">
    <h2>VITA</h2>
    <p>智能设备维护助手 · Powered by %s</p>
</div>
""" % LLM_MODEL, unsafe_allow_html=True)

# 初始化聊天历史
if "messages" not in st.session_state:
    st.session_state.messages = []

# 推荐提问（无对话时显示）
SUGGESTED_PROMPTS = [
    "屏蔽门无法关闭怎么处理？",
    "ISCS工作站黑屏是什么原因？",
    "今天全线网有多少故障？",
    "本周哪条线故障最多？",
]

# 显示聊天历史
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 推荐提问（无对话时显示）
if not st.session_state.messages:
    st.markdown("")
    cols = st.columns(2)
    for i, sp in enumerate(SUGGESTED_PROMPTS):
        with cols[i % 2]:
            if st.button(sp, key=f"suggest_{i}", use_container_width=True):
                st.session_state.pending_prompt = sp
                st.rerun()

# 用户输入
_chat_input = st.chat_input("描述你的问题...")
_pending = st.session_state.get("pending_prompt")
if _pending:
    del st.session_state["pending_prompt"]
prompt = _chat_input or _pending

if prompt:
    # 添加用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # 助手响应
    with st.chat_message("assistant"):
        if faiss_index is None or id_map is None:
            st.error("系统资源未加载成功，请刷新页面重试")
        elif not DatabaseManager.is_available():
            st.error("数据库连接中断，请检查网络后刷新页面。")
        else:
            response_start = time.time()

            # 解析用户查询
            parsed_result = parse_user_query(prompt)
            intent = parsed_result.get("intent")
            entities = parsed_result.get("entities", {})
            is_fast = parsed_result.get("_source") == "local_fast_parse"

            # 闲聊直接回复，不走任何分析流程
            if intent == "chitchat":
                response_text = "你好！我是 VITA 智能设备维护助手，可以帮你：\n\n" \
                    "- **故障诊断** — 例如「屏蔽门无法关闭怎么处理？」\n" \
                    "- **数据统计** — 例如「今天全线网有多少故障？」\n" \
                    "- **责任归属** — 例如「屏蔽门归哪个班组管？」\n\n" \
                    "请描述你的问题，我来帮你查。"
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                st.stop()

            if is_fast:
                # 本地快速解析成功，跳过 LLM 理解阶段
                with st.status("问题已理解", expanded=False, state="complete") as status:
                    pass
            else:
                with st.status("理解问题中...", expanded=True) as status:
                    status.write("调用语言模型解析问题...")
                    if intent == "statistics":
                        status.write("识别为：统计查询")
                    elif intent == "responsibility":
                        status.write("识别为：责任归属查询")
                    elif intent == "diagnosis":
                        status.write("识别为：故障诊断")
                    status.update(label="问题已理解", state="complete", expanded=False)

            # 根据意图分发处理
            response_text = None

            if intent == "error":
                response_text = "没理解你的问题，可以换个方式再说一次吗？"
                st.markdown(response_text)

            elif intent == "statistics":
                if parsed_result.get("compare_dimension"):
                    entities["compare_dimension"] = parsed_result["compare_dimension"]
                response_text = query_statistics(entities, parsed_result.get("query_type", "count"))

            elif intent == "responsibility":
                response_text = query_responsibility(entities)

            elif intent == "diagnosis":
                response_text = diagnose_fault(entities, prompt, faiss_index, id_map)

            else:
                response_text = "没太明白你的意思。你可以问我故障怎么处理、查统计数据、或者问责任归属。"
                st.markdown(response_text)

            # 保存助手回复到聊天历史
            if response_text:
                st.session_state.messages.append({"role": "assistant", "content": response_text})

# ================================================================================
# 侧边栏（极简专业风格）
# ================================================================================

with st.sidebar:
    st.markdown("### 系统信息")

    if faiss_index is not None and id_map is not None:
        db_ok = DatabaseManager.is_available()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("知识库", f"{faiss_index.ntotal:,}")
        with col2:
            st.metric("数据库", "在线" if db_ok else "离线")

        st.metric("语言模型", LLM_MODEL)

        if not db_ok:
            st.warning("数据库离线，诊断/统计/归属查询暂不可用。")
    else:
        st.error("系统资源加载失败，请刷新页面")

    st.markdown("---")

    with st.expander("查询示例", expanded=True):
        st.markdown("""
**故障诊断**
- *"3号线横山站ISCS工作站黑屏"*
- *"屏蔽门打不开怎么处理"*

**数据统计**
- *"本周2号线故障最多的设备"*
- *"今天全线网有多少故障"*

**责任归属**
- *"屏蔽门归哪个班组管"*
        """)

    st.markdown("---")

    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("VITA v15.1")
    st.caption("Developed by 陈思航")

# ================================================================================
# 程序完成
# ================================================================================
