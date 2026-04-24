"""
VITA v16.0 端到端验证（不依赖 Oracle，测试 Embedding → FAISS → Rerank 全流程）
"""
import json, time, os, sys
import requests
import numpy as np
import pandas as pd
import faiss
from collections import defaultdict
from typing import Dict, List, Tuple

os.chdir("E:/vita")

EMBEDDING_API_URL = "http://10.98.12.69:8080/embed"
RERANK_API_URL = "http://10.98.12.69:8081/rerank"

passed = 0
failed = 0

def ok(name, condition, detail=""):
    global passed, failed
    s = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    if condition: passed += 1
    else: failed += 1
    print(f"  [{s}] {name}" + (f"  ({detail})" if detail else ""))

# ====== 从 vita.py 复制的函数 ======
def reciprocal_rank_fusion(results_lists, k=60):
    rrf_scores = defaultdict(float)
    for results in results_lists:
        for rank, doc_id in enumerate(results):
            rrf_scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

def apply_rerank_to_df(df, query, top_k=20):
    if df.empty or len(df) <= 1:
        return df.head(top_k), False
    texts = []
    for _, row in df.iterrows():
        sol = str(row.get('SOLUTION', ''))[:150]
        text = (f"专业:{row.get('SPECIALTY', '')} "
                f"车站:{row.get('STATIONNAME', '')} "
                f"描述:{row.get('DESCRIPTION', '')} "
                f"处理:{sol}")
        texts.append(text)
    try:
        resp = requests.post(
            RERANK_API_URL,
            headers={'Content-Type': 'application/json'},
            data=json.dumps({"query": query, "texts": texts, "top_k": min(top_k, len(texts))}),
            timeout=15
        )
        if resp.status_code != 200:
            return df.head(top_k), False
        rerank_result = resp.json()
    except:
        return df.head(top_k), False

    if isinstance(rerank_result, list) and len(rerank_result) > 0:
        first = rerank_result[0]
        if isinstance(first, dict) and 'index' in first:
            ordered_indices = [item['index'] for item in rerank_result
                               if isinstance(item.get('index'), int)]
        else:
            return df.head(top_k), False
    else:
        return df.head(top_k), False

    max_idx = len(df) - 1
    ordered_indices = [i for i in ordered_indices if 0 <= i <= max_idx]
    if not ordered_indices:
        return df.head(top_k), False

    df_reset = df.reset_index(drop=True)
    return df_reset.iloc[ordered_indices].reset_index(drop=True), True

# ====== 测试 ======
print("=" * 65)
print("VITA v16.0 端到端验证 (Embedding → FAISS → Rerank)")
print("=" * 65)

# ---- 1. 加载 FAISS ----
print("\n[1] FAISS 索引")
t0 = time.time()
index = faiss.read_index("kb_zhipu.index")
id_map = np.load("kb_zhipu_id_map.npy", allow_pickle=True)
ok("加载成功", index.ntotal == 461065, f"{index.ntotal} vectors, {time.time()-t0:.1f}s")

# ---- 2. Embedding + FAISS 检索（修复后） ----
print("\n[2] 修复后的 Embedding + FAISS 检索")
test_queries = [
    ("ISCS工作站黑屏怎么处理", "ISCS"),
    ("屏蔽门无法关闭", "屏蔽门"),
    ("AFC闸机刷卡无反应", "AFC"),
]

all_results = {}

for query, expected_kw in test_queries:
    t0 = time.time()
    resp = requests.post(EMBEDDING_API_URL,
                         headers={'Content-Type': 'application/json'},
                         data=json.dumps({"inputs": query}), timeout=15)
    raw = resp.json()
    # 修复：处理嵌套格式
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
        embedding = raw[0]
    else:
        embedding = raw

    D, I = index.search(np.array([embedding], dtype='float32'), k=100)
    tids = [str(id_map[i]) for i in I[0]]
    dt = time.time() - t0
    ok(f"'{query}' → {len(tids)} 候选", len(tids) == 100, f"{dt:.2f}s")
    all_results[query] = tids

# ---- 3. RRF 融合（模拟两路） ----
print("\n[3] RRF 融合")
# 模拟关键词检索返回部分重叠的结果
vector_ids = all_results["ISCS工作站黑屏怎么处理"]
# 模拟关键词检索（取向量结果的后半段 + 一些新ID）
fake_kw_ids = vector_ids[50:] + ["FAKE-001", "FAKE-002"]
fused = reciprocal_rank_fusion([vector_ids, fake_kw_ids])
ok("融合去重", len(fused) == len(set(vector_ids) | set(fake_kw_ids)),
   f"向量={len(vector_ids)}, 关键词={len(fake_kw_ids)}, 融合={len(fused)}")
ok("向量 top1 仍排首位", fused[0] == vector_ids[0],
   f"fused[0]={fused[0]}, vector[0]={vector_ids[0]}")

# ---- 4. 构造模拟 DataFrame 并测试 Rerank ----
print("\n[4] Rerank 精排（真实 API，模拟案例数据）")
mock_cases = pd.DataFrame([
    {"TICKETID": f"SR-{i}", "SPECIALTY": "ISCS设备", "STATIONNAME": f"站{i}",
     "DESCRIPTION": desc, "SOLUTION": sol, "RELEVANCE_SCORE": 500 - i * 10}
    for i, (desc, sol) in enumerate([
        ("ISCS工作站黑屏无法操作", "重启工作站后恢复正常"),
        ("ISCS服务器无响应", "重启ISCS服务进程"),
        ("ISCS工作站显示器花屏", "更换显卡"),
        ("AFC闸机刷卡无反应", "更换读卡器模块"),
        ("屏蔽门控制器故障", "更换DCU控制板"),
        ("ISCS网络通讯中断", "更换网络交换机端口"),
        ("BAS环控系统告警", "复位告警信号"),
        ("ISCS工作站开机后黑屏", "检查电源模块，更换VGA线缆"),
    ])
])

reranked_df, rerank_applied = apply_rerank_to_df(
    mock_cases, "ISCS工作站黑屏怎么处理", top_k=5
)

ok("Rerank API 调用成功", rerank_applied, f"返回 {len(reranked_df)} 条")
if rerank_applied:
    top1_desc = reranked_df.iloc[0]['DESCRIPTION']
    ok("Top1 是 ISCS 黑屏相关", "黑屏" in top1_desc, f"'{top1_desc}'")

    # AFC 闸机应该排在后面（与 ISCS 黑屏不相关）
    afc_pos = None
    for idx, row in reranked_df.iterrows():
        if "AFC" in row['DESCRIPTION']:
            afc_pos = idx
            break
    if afc_pos is not None:
        ok("AFC 案例排名靠后", afc_pos >= 3, f"AFC 位置={afc_pos}")
    else:
        ok("AFC 案例被过滤", True, "未进入 top5")

    print(f"\n  Rerank 排序结果:")
    for idx, row in reranked_df.iterrows():
        print(f"    #{idx+1} [{row['TICKETID']}] {row['DESCRIPTION']} → {row['SOLUTION'][:30]}")

# ---- 5. 数据流完整性验证 ----
print("\n[5] 数据流完整性")
ok("RELEVANCE_SCORE 列保留", "RELEVANCE_SCORE" in reranked_df.columns)
ok("TICKETID 列保留", "TICKETID" in reranked_df.columns)
ok("SOLUTION 列保留", "SOLUTION" in reranked_df.columns)
ok("reranked 行数 <= top_k", len(reranked_df) <= 5)
ok("index 从0开始连续", list(reranked_df.index) == list(range(len(reranked_df))))

# ---- 6. Rerank 降级测试 ----
print("\n[6] Rerank 降级测试")
# 空 DataFrame
empty_df, applied = apply_rerank_to_df(pd.DataFrame(), "test", 5)
ok("空 DataFrame 返回空", len(empty_df) == 0 and not applied)

# 单行 DataFrame
single_df, applied = apply_rerank_to_df(mock_cases.head(1), "test", 5)
ok("单行 DataFrame 不调 Rerank", not applied and len(single_df) == 1)

# ---- 汇总 ----
print("\n" + "=" * 65)
total = passed + failed
print(f"总计: {total} 项  |  \033[32m通过: {passed}\033[0m  |  \033[31m失败: {failed}\033[0m")
if failed == 0:
    print("\n所有测试通过。Embedding 格式修复 + FAISS + RRF + Rerank 全链路验证成功。")
print("=" * 65)
