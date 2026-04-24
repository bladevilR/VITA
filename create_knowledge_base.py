import os
import faiss
import numpy as np
import pandas as pd
import oracledb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import time
import json

# ============================================
# 🎛️ 配置区域
# ============================================
DB_USER = "maxsearch"
DB_PASSWORD = "sZ36!mTrBxH"
DB_DSN = "10.97.4.7:1521/eamprod"
ORACLE_CLIENT_PATH = "D:/instantclient/instantclient_23_9"

# ===> ⭐ 指定您下载的本地模型路径 <===
# 根据您的截图(image_4c5eb7.png)，模型放在models文件夹里
# 请确保这个文件夹名和您下载的模型名一致
LOCAL_MODEL_PATH = "models"  # 直接指向包含所有模型文件的文件夹

# ===> ⭐ 新的输出文件名，不会和智谱版的冲突 <===
INDEX_FILE = "kb_local.index"
ID_MAP_FILE = "kb_local_id_map.npy"
STATS_FILE = "kb_local_stats.json"

START_DATE = "2020-01-01"
BATCH_SIZE = 32  # 本地CPU计算，批次不宜过大

# ============================================
# 初始化
# ============================================
print("=" * 70)
print("🏗️  VITA 知识库构建工具 - 【本地模型版】")
print("=" * 70)

try:
    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
    print("✅ Oracle客户端初始化成功")
    print(f"⏳ 正在从 '{LOCAL_MODEL_PATH}' 加载本地Embedding模型...")
    # device='cpu' 使用CPU。如果有NVIDIA显卡，改成 'cuda'
    model = SentenceTransformer(LOCAL_MODEL_PATH, device='cpu')
    print("✅ 本地模型加载成功")
except Exception as e:
    print(f"❌ 初始化失败: {e}")
    exit(1)


# (后面的代码和上一版本地模型脚本完全一样，这里省略，您直接复制完整的代码块即可)
# ... (fetch_full_data, clean_data, prepare_rich_texts... ) ...

def fetch_full_data():
    print("\n" + "=" * 70)
    print("📊 步骤1: 全量数据获取")
    print("=" * 70)
    with oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN) as conn:
        query = f"""
            SELECT TICKETID, DESCRIPTION, ASSETNUM, LOCATION, REPORTDATE, CLASS, SPECIALTY
            FROM MAXIMO.SR 
            WHERE DESCRIPTION IS NOT NULL AND DESCRIPTION != ' ' AND REPORTDATE >= TO_DATE('{START_DATE}', 'YYYY-MM-DD')
            ORDER BY REPORTDATE DESC
        """
        df = pd.read_sql(query, conn)
        print(f"\n✅ 数据获取完成: {len(df):,} 条")
        return df


def clean_data(df):
    print("\n" + "=" * 70)
    print("🧹 步骤2: 数据清洗")
    print("=" * 70)
    df.drop_duplicates(subset=['TICKETID'], keep='last', inplace=True)
    df = df[df['DESCRIPTION'].notna() & (df['DESCRIPTION'].str.strip() != '') & (df['DESCRIPTION'].str.len() >= 5)]
    print(f"✅ 清洗完成，最终保留: {len(df):,} 条")
    return df


def create_rich_text(row):
    parts = []
    if pd.notna(row['SPECIALTY']): parts.append(f"专业:{row['SPECIALTY']}")
    if pd.notna(row['LOCATION']): parts.append(f"位置:{row['LOCATION']}")
    if pd.notna(row['ASSETNUM']): parts.append(f"设备:{row['ASSETNUM']}")
    parts.append(f"故障:{row['DESCRIPTION']}")
    if pd.notna(row['CLASS']): parts.append(f"类型:{row['CLASS']}")
    return " | ".join(parts)


def prepare_rich_texts(df):
    print("\n" + "=" * 70)
    print("📝 步骤3: 创建富文本")
    print("=" * 70)
    df['RICH_TEXT'] = df.apply(create_rich_text, axis=1)
    print(f"✅ 富文本创建完成")
    return df


def get_embeddings_batch_local(texts):
    try:
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings
    except Exception as e:
        print(f"  ❌ 本地向量化失败: {e}")
        return None


def build_vector_index(df):
    print("\n" + "=" * 70)
    print("🚀 步骤4: 本地生成向量并构建索引")
    print("=" * 70)
    dimension = model.get_sentence_embedding_dimension()
    index = faiss.IndexFlatL2(dimension)
    id_list = []
    total_rows = len(df)

    with tqdm(total=total_rows, desc="本地生成向量", unit="条") as pbar:
        for i in range(0, total_rows, BATCH_SIZE):
            batch_df = df.iloc[i:i + BATCH_SIZE]
            texts = batch_df['RICH_TEXT'].tolist()
            embeddings = get_embeddings_batch_local(texts)
            if embeddings is not None:
                vectors = np.array(embeddings, dtype='float32')
                index.add(vectors)
                id_list.extend([str(tid) for tid in batch_df['TICKETID'].tolist()])
                pbar.update(len(embeddings))
            else:
                pbar.update(len(texts))
                print(f"⚠️  批次 {i // BATCH_SIZE + 1} 失败，已跳过")
    print(f"✅ 向量生成完成，成功: {index.ntotal:,} 条")
    return index, id_list


def save_knowledge_base(index, id_list):
    print("\n" + "=" * 70)
    print("💾 步骤5: 保存知识库文件")
    print("=" * 70)
    faiss.write_index(index, INDEX_FILE)
    np.save(ID_MAP_FILE, np.array(id_list))
    stats = {"total_vectors": index.ntotal, "vector_dimension": index.d}
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)
    print(f"✅ FAISS索引已保存: {INDEX_FILE}")
    print(f"✅ ID映射已保存: {ID_MAP_FILE}")
    print(f"✅ 统计信息已保存: {STATS_FILE}")


def main():
    try:
        overall_start = time.time()
        df = fetch_full_data()
        df = clean_data(df)
        df = prepare_rich_texts(df)
        index, id_list = build_vector_index(df)
        save_knowledge_base(index, id_list)
        elapsed_time = (time.time() - overall_start) / 60
        print("\n" + "=" * 70)
        print(f"🎉 全量知识库构建完成！总耗时: {elapsed_time:.1f} 分钟")
        print("=" * 70)
    except Exception as e:
        print(f"\n\n❌ 构建失败: {e}")


if __name__ == '__main__':
    main()