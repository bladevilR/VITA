"""
真实端到端性能测试 - 最终版
"""
import sys
sys.path.insert(0, 'E:/vita')

import time

print('开始真实性能测试')
print('=' * 60)

# 导入
from vita import (
    metadata_filtered_vector_search,
    apply_rerank_to_df,
    analyze_case_data,
    faiss_index,
    id_map
)

test_query = 'ISCS工作站黑屏'
print(f'测试查询: {test_query}')
print('=' * 60)

stage_times = {}

# 构造 entities（模拟实体提取结果）
entities = {
    'device': 'ISCS工作站',
    'line_num': None,
    'station_name': None,
    'specialty': None
}
print(f'实体: {entities}')

# 阶段1: 检索
try:
    start = time.time()
    cases_df = metadata_filtered_vector_search(
        entities=entities,
        user_query=test_query,
        faiss_index=faiss_index,
        id_map=id_map
    )
    stage_times['检索'] = time.time() - start
    print(f'[OK] 检索: {len(cases_df)}条, {stage_times["检索"]:.2f}秒')
except Exception as e:
    print(f'[FAIL] 检索失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 阶段2: Rerank
try:
    start = time.time()
    analysis_df, _ = apply_rerank_to_df(
        df=cases_df.head(30),
        query=test_query,
        top_k=20
    )
    stage_times['Rerank'] = time.time() - start
    print(f'[OK] Rerank: {len(analysis_df)}条, {stage_times["Rerank"]:.2f}秒')
except Exception as e:
    print(f'[FAIL] Rerank失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 阶段3: 数据分析
if len(analysis_df) > 0:
    try:
        start = time.time()
        data_analysis = analyze_case_data(analysis_df, entities)
        stage_times['数据分析'] = time.time() - start
        print(f'[OK] 数据分析: {stage_times["数据分析"]:.2f}秒')
    except Exception as e:
        print(f'[FAIL] 数据分析失败: {e}')
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
print('[SUCCESS] 端到端测试完成')
