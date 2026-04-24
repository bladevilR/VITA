import os
import json
import requests
import pandas as pd
import oracledb
import re
import faiss
import numpy as np
import pickle

# --- 1. 全部配置信息 ---
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "htdora-scan.sz-mtr.com:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# 内网模型API配置
LLM_API_URL = os.getenv("VITA_LLM_URL") or os.getenv("LLM_URL") or "http://10.96.158.22:8000/v1"
LLM_API_KEY = os.getenv("VITA_LLM_KEY") or os.getenv("LLM_KEY") or "hebz9jMiWwkqiV2NTDE1AiBEKj_Sz0Ga"
LLM_MODEL = os.getenv("VITA_LLM_MODEL") or os.getenv("LLM_MODEL") or "gemma-4-31b-it"
EMBEDDING_API_URL = "http://10.98.12.69:8080/embed"

# --- 2. 初始化所有客户端 ---
try:
    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
    print("Oracle客户端初始化成功。")
except Exception as e:
    print(f"客户端初始化失败: {e}")
    exit()

# --- 3. 加载AI知识库 (程序启动时执行一次) ---
INDEX_FILE = "knowledge_base.index"
MAPPING_FILE = "kb_ticket_mapping.pkl"
try:
    faiss_index = faiss.read_index(INDEX_FILE)
    with open(MAPPING_FILE, 'rb') as f:
        index_to_ticketid_map = pickle.load(f)
    print(f"AI知识库加载成功，包含 {faiss_index.ntotal} 条经验。")
except Exception as e:
    faiss_index = None
    print(f"警告：AI知识库加载失败: {e}。故障推荐功能将不可用。")


# --- 功能一：Text-to-SQL ---
def generate_sql_from_text(user_question):
    prompt = f"""
    你是一个专业的Oracle数据库查询助手。你的任务是根据用户的提问，生成一段可以在Oracle数据库中执行的SQL查询语句。
    数据库中有一张名为 MAXIMO.TICKET 的表，这是实时的故障工单表。

    [重要规则]
    你必须且只能使用下面列出的列名，严禁使用或创造不存在的列名：
    - TICKETID, DESCRIPTION, REPORTDATE, SPECIALTY, STATUS

    你的输出必须遵循以下格式：
    1. 首先可以有<think>...</think>思考过程。
    2. 在</think>之后，必须紧跟着最终的SQL查询语句。
    3. SQL语句必须以 "SELECT" 开头，不要在末尾添加分号 ";"。
    ---
    现在，请根据以下用户提问生成SQL:
    用户提问: {user_question}
    SQL:
    """
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
    print("正在请求LLM生成SQL...")
    try:
        response = requests.post(f"{LLM_API_URL}/chat/completions", headers=headers, data=json.dumps(payload), timeout=60)
        response.raise_for_status()
        result_json = response.json()
        generated_text = result_json['choices'][0]['message']['content']
        if "</think>" in generated_text:
            sql_candidate = generated_text.split("</think>")[-1]
        else:
            sql_candidate = generated_text
        sql_match = re.search(r"SELECT.*", sql_candidate, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(0).strip().rstrip(';')
        else:
            return sql_candidate.strip()
    except Exception as e:
        print(f"调用LLM API失败或解析结果出错: {e}"); return None


def execute_sql_query(sql_query):
    if not sql_query: return "未能生成SQL查询。"
    clean_sql = sql_query.strip().rstrip(';')
    print(f"正在执行SQL: {clean_sql}")
    try:
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as connection:
            return pd.read_sql(clean_sql, connection)
    except Exception as e:
        return f"SQL执行失败: {str(e)}"


# --- 功能二：故障推荐 ---
def get_embedding(text):
    """调用内网Embedding API获取向量"""
    headers = {'Content-Type': 'application/json'}
    payload = {"inputs": text}
    try:
        response = requests.post(EMBEDDING_API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Embedding调用失败: {e}")
        return None


def search_knowledge_base(query_text, k=5):
    """在知识库中搜索最相似的案例"""
    if not faiss_index: return None, "知识库未加载。"
    print("正在将问题向量化...")
    try:
        query_embedding = get_embedding(query_text)
        if query_embedding is None:
            return None, "无法获取查询向量"

        print(f"正在知识库中搜索 {k} 个最相似案例...")
        distances, indices = faiss_index.search(np.array([query_embedding], dtype='float32'), k)

        # 将索引转换为TICKETID
        similar_ticket_ids = [index_to_ticketid_map[i] for i in indices[0]]

        print(f"找到相似案例 TICKETID: {similar_ticket_ids}")
        # 从数据库中获取这些案例的详细信息
        with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as connection:
            id_list = ','.join([f"'{tid}'" for tid in similar_ticket_ids])
            # 从历史表中查询，因为知识库是基于历史表创建的
            query = f"SELECT TICKETID, DESCRIPTION, PROCREMEDY FROM MAXIMO.C_SREXT WHERE TICKETID IN ({id_list})"
            df = pd.read_sql(query, connection)
            return df, None
    except Exception as e:
        return None, f"知识库检索或数据库查询失败: {e}"


def get_recommendation_from_llm(user_query, cases_df):
    """调用LLM对检索到的案例进行总结"""
    if cases_df.empty: return "在历史数据库中未找到相似案例的详细信息。"

    context = "\n\n".join([
        f"历史案例 {row['TICKETID']}:\n- 故障现象: {row['DESCRIPTION']}\n- 处理方法: {row['PROCREMEDY']}"
        for index, row in cases_df.iterrows()
    ])

    prompt = f"""
    你是一位经验丰富的设备维修专家。请根据用户当前遇到的问题，并参考以下最相似的历史维修案例，为用户提供一份清晰、专业的处置建议。

    [用户当前问题]
    {user_query}

    [相关历史案例]
    {context}

    [你的处置建议]
    请按以下格式输出：
    1. **方案一**: [详细说明第一个建议方案]。
       - **依据**: [引用相关的历史案例单号，例如 "参考案例 SD1234"]。
    2. **方案二**: [详细说明第二个建议方案]。
       - **依据**: [引用相关的历史案例单号]。
    (如果方案类似，请合并同类项，并总结出最常见的处理方式)
    """
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
    print("正在请求LLM生成处置建议...")
    try:
        response = requests.post(f"{LLM_API_URL}/chat/completions", headers=headers, data=json.dumps(payload), timeout=60)
        response.raise_for_status()
        result_json = response.json()
        full_text = result_json['choices'][0]['message']['content']
        if "</think>" in full_text:
            return full_text.split("</think>")[-1].strip()
        return full_text.strip()
    except Exception as e:
        return f"请求LLM总结失败: {e}"


# --- 主交互循环 ---
if __name__ == '__main__':
    print("\n--- 欢迎使用 VITA 智能助手 (v2.0 Final) ---")
    while True:
        print("\n请选择功能:")
        print("1. 智能查询 (通过自然语言查询实时数据)")
        print("2. 故障推荐 (根据故障描述获取处理建议)")
        choice = input("请输入选项 (1 或 2，输入 '退出' 来结束程序): ")

        if choice == '1':
            question = input("\n[智能查询] 请输入您的问题: ")
            sql = generate_sql_from_text(question)
            if sql:
                result = execute_sql_query(sql)
                print("\n--- 查询结果 ---")
                print(result)
        elif choice == '2':
            if not faiss_index:
                print("错误：知识库未成功加载，无法使用此功能。")
                continue
            question = input("\n[故障推荐] 请输入您的故障描述: ")
            similar_cases, error = search_knowledge_base(question)
            if error:
                print(f"\n错误: {error}")
            else:
                recommendation = get_recommendation_from_llm(question, similar_cases)
                print("\n--- VITA智能推荐 ---")
                print(recommendation)
        elif choice.lower() in ['退出', 'exit', 'quit']:
            break
        else:
            print("无效的选项，请输入 1 或 2。")
