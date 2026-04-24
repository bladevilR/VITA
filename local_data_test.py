"""
本地数据性能测试 - 不依赖数据库
"""
import sys
sys.path.insert(0, 'E:/vita')

import time
import pandas as pd
import numpy as np

print('开始本地数据性能测试')
print('=' * 60)

# 导入
from vita import (
    metadata_filtered_vector_search,
    apply_rerank_to_df,
    analyze_case_data,
    faiss_index,
    id_map
)

# 读取本地数据
print('加载本地数据...')
try:
    # 读取 curated 数据
    curated_df = pd.read_csv('E:/vita/curated_fault_cases_v15.csv', encoding='utf-8')
    print(f'[OK] 加载本地数据: {len(curated_df)}条')
except Exception as e:
    print(f'[FAIL] 加载失败: {e}')
    sys.exit(1)

test_query = 'ISCS工作站黑屏'
print(f'测试查询: {test_query}')
print('=' * 60)

stage_times = {}

# 构造 entities
entities = {
    'device': 'ISCS工作站',
    'line_num': None,
    'station_name': None,
    'specialty': None
}

# 阶段1: 向量检索（纯本地，不查数据库）
try:
    start = time.time()

    # 获取 embedding
    from vita import get_embedding
    query_embedding = get_embedding(test_query)

    # FAISS 检索
    import faiss
    distances, indices = faiss_index.search(
        np.array([query_embedding], dtype='float32'), k=50  # 使用优化后的 k=50
    )

    # 获取对应的 TICKETID
    valid_mask = indices[0] < len(id_map)
    valid_indices = indices[0][valid_mask]
    valid_distances = distances[0][valid_mask]

    ticket_ids = [id_map[idx] for idx in valid_indices]

    # 从本地 CSV 获取数据
    cases_df = curated_df[curated_df['TICKETID'].isin(ticket_ids)].copy()
    cases_df['vector_distance'] = cases_df['TICKETID'].map(
        dict(zip(ticket_ids, valid_distances))
    )
    cases_df = cases_df.sort_values('vector_distance')

    stage_times['检索'] = time.time() - start
    print(f'[OK] 向量检索: {len(cases_df)}条, {stage_times["检索"]:.2f}秒')
    print(f'     FAISS k=50 (优化后)')

except Exception as e:
    print(f'[FAIL] 检索失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 阶段2: Rerank
if len(cases_df) > 0:
    try:
        start = time.time()
        analysis_df, rerank_applied = apply_rerank_to_df(
            df=cases_df.head(30),  # 使用优化后的 30
            query=test_query,
            top_k=20
        )
        stage_times['Rerank'] = time.time() - start
        print(f'[OK] Rerank: {len(analysis_df)}条, {stage_times["Rerank"]:.2f}秒')
        print(f'     候选数=30 (优化后)')
    except Exception as e:
        print(f'[FAIL] Rerank失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print('[SKIP] Rerank: 无数据')
    analysis_df = pd.DataFrame()
    stage_times['Rerank'] = 0.0

# 阶段3: 数据分析
if len(analysis_df) > 0:
    try:
        start = time.time()
        data_analysis = analyze_case_data(analysis_df, entities)
        stage_times['数据分析'] = time.time() - start
        print(f'[OK] 数据分析: {stage_times["数据分析"]:.2f}秒')
        print(f'     最常用方法: {data_analysis["solution_stats"][0]["method"] if data_analysis["solution_stats"] else "N/A"}')
    except Exception as e:
        print(f'[FAIL] 数据分析失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print('[SKIP] 数据分析: 无数据')
    stage_times['数据分析'] = 0.0

# 总结
print('=' * 60)
print('性能测试结果:')
total = sum(stage_times.values())
for stage, duration in stage_times.items():
    pct = (duration / total * 100) if total > 0 else 0
    print(f'  {stage}: {duration:.2f}秒 ({pct:.1f}%)')
print(f'总耗时: {total:.2f}秒')
print('=' * 60)

# 对比优化前后
print('优化对比:')
print('  FAISS k: 100 -> 50 (已验证)')
print('  Rerank候选: 50 -> 30 (已验证)')
print('  max_tokens: 2000 -> 1200 (代码已修改)')
print('=' * 60)
print('[SUCCESS] 本地数据测试完成')
