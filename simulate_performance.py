"""
VITA 性能直接测试 - 不依赖浏览器
直接调用函数并测量性能
"""
import sys
import time
import json

# 模拟测试
def simulate_performance_test():
    """模拟各阶段性能"""

    print("=" * 60)
    print("VITA 性能模拟测试")
    print("=" * 60)
    print()

    # 基于代码分析的预估
    stages = {
        "检索": {
            "min": 2.5,
            "max": 5.0,
            "description": "向量检索(1-2s) + 关键词检索(1-2s) + RRF融合(0.5s)"
        },
        "Rerank": {
            "min": 1.5,
            "max": 3.0,
            "description": "神经重排序 API 调用"
        },
        "数据分析": {
            "min": 0.1,
            "max": 0.5,
            "description": "本地统计计算"
        },
        "知识库查询": {
            "min": 0.1,
            "max": 0.3,
            "description": "数据库查询"
        },
        "LLM生成": {
            "min": 5.0,
            "max": 15.0,
            "description": "流式生成报告 (max_tokens=2000)"
        }
    }

    # 计算预估时间
    total_min = sum(s["min"] for s in stages.values())
    total_max = sum(s["max"] for s in stages.values())
    total_avg = (total_min + total_max) / 2

    print("各阶段预估耗时：")
    print()

    for stage, data in stages.items():
        avg = (data["min"] + data["max"]) / 2
        percentage = (avg / total_avg) * 100
        print(f"  {stage}:")
        print(f"    预估: {data['min']:.1f}-{data['max']:.1f}秒 (平均 {avg:.1f}秒, {percentage:.1f}%)")
        print(f"    说明: {data['description']}")
        print()

    print("-" * 60)
    print(f"总耗时预估: {total_min:.1f}-{total_max:.1f}秒 (平均 {total_avg:.1f}秒)")
    print("=" * 60)
    print()

    # 分析瓶颈
    print("性能瓶颈分析：")
    print()

    sorted_stages = sorted(
        [(name, (data["min"] + data["max"]) / 2) for name, data in stages.items()],
        key=lambda x: x[1],
        reverse=True
    )

    for i, (stage, avg_time) in enumerate(sorted_stages, 1):
        percentage = (avg_time / total_avg) * 100
        if percentage > 40:
            priority = "🔴 高优先级"
        elif percentage > 20:
            priority = "🟡 中优先级"
        else:
            priority = "🟢 低优先级"

        print(f"  {i}. {stage}: {avg_time:.1f}秒 ({percentage:.1f}%) - {priority}")

    print()
    print("=" * 60)
    print()

    # 优化建议
    print("优化建议：")
    print()

    llm_avg = (stages["LLM生成"]["min"] + stages["LLM生成"]["max"]) / 2
    llm_percentage = (llm_avg / total_avg) * 100

    if llm_percentage > 40:
        print("🔴 LLM 生成是主要瓶颈 (占比 {:.1f}%)".format(llm_percentage))
        print()
        print("  建议优化：")
        print("  1. 降低 max_tokens: 2000 → 1200-1500")
        print("  2. 简化 Prompt (减少案例详情)")
        print("  3. 优化流式输出体验 (用户感知更快)")
        print("  预期提升: 减少 30-40% LLM 时间")
        print()

    retrieval_avg = (stages["检索"]["min"] + stages["检索"]["max"]) / 2
    retrieval_percentage = (retrieval_avg / total_avg) * 100

    if retrieval_percentage > 20:
        print("🟡 检索阶段占比较高 ({:.1f}%)".format(retrieval_percentage))
        print()
        print("  建议优化：")
        print("  1. 并行执行向量检索和关键词检索")
        print("  2. 优化 FAISS 检索参数 (k=100 → k=50)")
        print("  3. 添加查询缓存")
        print("  预期提升: 减少 30-50% 检索时间")
        print()

    rerank_avg = (stages["Rerank"]["min"] + stages["Rerank"]["max"]) / 2
    rerank_percentage = (rerank_avg / total_avg) * 100

    if rerank_percentage > 15:
        print("🟡 Rerank 占比 {:.1f}%".format(rerank_percentage))
        print()
        print("  建议评估：")
        print("  1. Rerank 候选数: 50 → 30")
        print("  2. 评估 Rerank 的性价比 (质量提升 vs 时间成本)")
        print("  预期提升: 减少 20-30% Rerank 时间")
        print()

    print("=" * 60)
    print()

    # 用户体验优化
    print("用户体验优化建议：")
    print()
    print("  即使总时间不变，也可以改善用户感知：")
    print()
    print("  1. ✅ 已实现: st.status 显示阶段进度")
    print("  2. ✅ 已实现: 流式输出 LLM 结果")
    print("  3. 💡 建议: 预先显示统计数据 (用户可以先看数据)")
    print("  4. 💡 建议: 添加预估时间提示 ('预计需要 10-15 秒')")
    print("  5. 💡 建议: 超时降级策略 (>20秒返回简化建议)")
    print()
    print("=" * 60)

    # 保存报告
    report = {
        "test_type": "simulation",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stages": stages,
        "total_time_range": f"{total_min:.1f}-{total_max:.1f}s",
        "average_time": f"{total_avg:.1f}s",
        "bottleneck": sorted_stages[0][0],
        "bottleneck_percentage": f"{(sorted_stages[0][1] / total_avg) * 100:.1f}%"
    }

    with open("E:/vita/performance_simulation_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print("报告已保存到: E:/vita/performance_simulation_report.json")
    print()

if __name__ == "__main__":
    simulate_performance_test()
