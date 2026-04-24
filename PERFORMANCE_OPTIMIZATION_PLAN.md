# VITA 性能优化方案 - 响应速度提升

> 目标：将用户等待时间从 30-90秒 降低到 10-20秒
> 重点：LLM 调用优化 + 用户体验改进

---

## 一、当前性能瓶颈分析

### 🔴 主要问题

**1. LLM 调用时间过长**
```python
# 当前配置
"max_completion_tokens": 16000  # 过大！
timeout=90  # 故障诊断
timeout=15  # 责任归属（已优化）
```

**问题**：
- 16000 tokens 的生成限制过高，导致 LLM 生成时间长
- 实际诊断报告通常只需要 500-1000 tokens
- 用户在等待时缺少明确的进度反馈

**2. 缺少流式输出**
```python
# 当前：一次性返回完整结果
result = call_llm_with_validation(prompt, timeout=90)
st.markdown(result)  # 用户等待 30-90 秒后才看到内容
```

**3. 进度提示不够直观**
```python
show_progress("正在知识库中检索...")  # 只是文字，没有进度条
show_debug("向量检索: 50 个候选")      # 小字体，不明显
```

---

## 二、优化方案（保持单文件结构）

### 🚀 方案 1：LLM 参数优化（立即见效）

#### 1.1 降低 token 限制
```python
# 修改前
"max_completion_tokens": 16000  # 太大了

# 修改后 - 根据场景区分
DIAGNOSIS_MAX_TOKENS = 1500      # 故障诊断：1500 足够
STATISTICS_MAX_TOKENS = 800      # 统计查询：800 足够
RESPONSIBILITY_MAX_TOKENS = 500  # 责任归属：500 足够
```

**预期效果**：响应时间减少 40-60%

#### 1.2 优化 Prompt 长度
```python
# 当前问题：Prompt 过长，包含大量案例详情
report_prompt = f"""
你是经验丰富的地铁运维专家...

【最相似案例】（共20条）
案例1: {case1_full_details}  # 每条案例 200+ tokens
案例2: {case2_full_details}
...
案例20: {case20_full_details}
"""

# 优化后：只传递关键信息
report_prompt = f"""
你是地铁运维专家，基于历史数据给出简洁建议。

【用户问题】{user_query}

【数据统计】
- 最常用方法：{most_common_method}（{count}次成功）
- 最近案例：{latest_case_summary}（50字以内）
- 设备履历：{device_history_summary}（30字以内）

【输出要求】
1. 直接给出处理建议（3-5句话）
2. 说明注意事项（2-3句话）
3. 总字数控制在300字以内
"""
```

**预期效果**：
- Prompt tokens: 2000+ → 500-800
- 生成速度提升 30%

---

### 🎨 方案 2：用户体验优化（关键！）

#### 2.1 实时进度条
```python
def diagnose_fault_with_progress(entities, user_query, faiss_index, id_map):
    """带实时进度反馈的故障诊断"""

    # 创建进度条和状态文本
    progress_bar = st.progress(0)
    status_text = st.empty()

    # 阶段1：检索（预计 3-5秒）
    status_text.text("🔍 正在知识库中检索相似案例...")
    progress_bar.progress(20)
    cases_df = metadata_filtered_vector_search(entities, user_query, faiss_index, id_map)

    # 阶段2：重排序（预计 2-3秒）
    status_text.text("🎯 正在使用 AI 优化结果排序...")
    progress_bar.progress(40)
    reranked_df, used_rerank = apply_rerank_if_available(user_query, cases_df, top_k=20)

    # 阶段3：统计分析（预计 1秒）
    status_text.text("📊 正在分析历史修复方式...")
    progress_bar.progress(60)
    solution_stats = analyze_solution_patterns(reranked_df)

    # 阶段4：生成报告（预计 5-10秒）
    status_text.text("🤖 AI 专家正在生成诊断报告...")
    progress_bar.progress(80)
    report = generate_diagnosis_report(user_query, reranked_df, solution_stats)

    # 完成
    progress_bar.progress(100)
    status_text.text("✅ 诊断完成！")
    time.sleep(0.5)  # 短暂停留，让用户看到完成状态

    # 清除进度提示
    progress_bar.empty()
    status_text.empty()

    return report
```

#### 2.2 流式输出（推荐！）
```python
def generate_diagnosis_report_stream(user_query, cases_df, solution_stats):
    """流式生成诊断报告 - 用户立即看到内容"""

    # 创建占位符
    report_placeholder = st.empty()
    accumulated_text = ""

    # 简化的 prompt
    prompt = f"""基于历史数据给出简洁诊断建议。

用户问题：{user_query}
最常用方法：{solution_stats['most_common']}（{solution_stats['count']}次）

直接输出处理建议，控制在200字内。"""

    # 流式调用 LLM
    for chunk in call_llm_stream(prompt, max_tokens=800):
        accumulated_text += chunk
        report_placeholder.markdown(accumulated_text + "▌")  # 添加光标效果

    # 移除光标
    report_placeholder.markdown(accumulated_text)

    return accumulated_text
```

**用户体验对比**：
- **优化前**：等待 30 秒 → 突然显示完整报告
- **优化后**：等待 2 秒 → 逐字显示报告（类似 ChatGPT）

#### 2.3 预先显示关键数据
```python
def diagnose_fault_optimized(entities, user_query, faiss_index, id_map):
    """优化版故障诊断 - 先显示数据，再生成报告"""

    # 1. 快速检索和统计（5-8秒）
    with st.spinner("🔍 正在检索历史案例..."):
        cases_df = metadata_filtered_vector_search(...)
        reranked_df, _ = apply_rerank_if_available(...)
        solution_stats = analyze_solution_patterns(reranked_df)

    # 2. 立即显示统计结果（用户不用等 LLM）
    st.success("✅ 找到相似案例！")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("相似案例", f"{len(reranked_df)} 条")
    with col2:
        st.metric("最常用方法", solution_stats['most_common'])
    with col3:
        st.metric("成功次数", f"{solution_stats['count']} 次")

    # 3. 显示案例表格（用户可以先看数据）
    with st.expander("📋 查看历史案例详情", expanded=True):
        st.dataframe(reranked_df.head(10))

    # 4. 流式生成 AI 建议（用户已经看到数据，不会焦虑）
    st.markdown("### 🤖 AI 专家建议")
    with st.spinner("正在生成诊断建议..."):
        report = generate_diagnosis_report_stream(...)
```

**心理学优势**：
- 用户在 5-8 秒内就能看到数据
- 即使 AI 报告需要 10 秒，用户也在看表格，不会感觉慢
- 总体感知等待时间：30秒 → 5秒

---

### ⚡ 方案 3：并行处理

#### 3.1 异步数据加载
```python
import concurrent.futures

def diagnose_fault_parallel(entities, user_query, faiss_index, id_map):
    """并行执行多个独立任务"""

    with st.spinner("🔍 正在检索..."):
        # 并行执行向量检索和关键词检索
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_vector = executor.submit(vector_search, query_embedding, faiss_index)
            future_keyword = executor.submit(keyword_search_oracle, entities)

            vector_results = future_vector.result()
            keyword_results = future_keyword.result()

        # RRF 融合
        fused_ids = reciprocal_rank_fusion([vector_results, keyword_results])
```

**预期效果**：
- 向量检索（3秒）+ 关键词检索（3秒）= 6秒
- 并行后：max(3秒, 3秒) = 3秒
- 节省 50% 时间

#### 3.2 缓存热门查询
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def cached_diagnosis(query_hash, entities_str):
    """缓存最近的诊断结果"""
    # 实际诊断逻辑
    pass

def diagnose_fault_cached(entities, user_query, faiss_index, id_map):
    # 生成查询指纹
    query_hash = hashlib.md5(
        f"{user_query}_{entities.get('device')}_{entities.get('line_num')}".encode()
    ).hexdigest()

    # 尝试从缓存获取
    cached_result = st.session_state.get(f"diagnosis_{query_hash}")
    if cached_result:
        st.info("💡 使用缓存结果（秒级响应）")
        return cached_result

    # 执行诊断
    result = diagnose_fault_optimized(...)

    # 保存到缓存
    st.session_state[f"diagnosis_{query_hash}"] = result
    return result
```

---

### 🎯 方案 4：智能降级策略

#### 4.1 快速模式 vs 详细模式
```python
def diagnose_fault_adaptive(entities, user_query, faiss_index, id_map):
    """自适应诊断 - 根据情况选择模式"""

    # 检查是否是简单查询
    is_simple = (
        len(user_query) < 20 and  # 查询很短
        entities.get('device') in COMMON_DEVICES  # 常见设备
    )

    if is_simple:
        # 快速模式：只用规则 + 简单统计
        st.info("⚡ 检测到常见问题，使用快速诊断模式")
        return quick_diagnosis(entities, user_query)
    else:
        # 详细模式：完整 RAG 流程
        return full_diagnosis(entities, user_query, faiss_index, id_map)

def quick_diagnosis(entities, user_query):
    """快速诊断 - 3-5秒完成"""
    # 1. 直接查询数据库（不用向量检索）
    # 2. 简单统计
    # 3. 模板化回答（不调用 LLM）

    most_common = get_most_common_solution(entities['device'])

    return f"""
### ⚡ 快速诊断

**{entities['device']}** 最常见的处理方法是：**{most_common}**

根据历史数据，这个方法的成功率约 85%。

💡 如需详细分析，请提供更多信息（如具体故障现象、线路车站等）
"""
```

#### 4.2 超时保护
```python
def call_llm_with_timeout_protection(prompt, max_tokens=1500, timeout=15):
    """带超时保护的 LLM 调用"""

    try:
        # 第一次尝试：正常调用
        result = call_llm_with_validation(
            prompt,
            max_tokens=max_tokens,
            timeout=timeout
        )
        return result

    except requests.Timeout:
        # 超时后：返回基于数据的简化建议
        st.warning("⚠️ AI 响应较慢，为您提供基于数据的快速建议")
        return generate_fallback_response()

def generate_fallback_response():
    """降级响应 - 不依赖 LLM"""
    return f"""
### 📊 基于历史数据的建议

根据统计分析：
- 最常用方法：{solution_stats['most_common']}
- 成功次数：{solution_stats['count']} 次
- 最近案例：{latest_case['date']} - {latest_case['solution']}

**建议**：优先尝试上述最常用方法。

💡 详细的 AI 分析正在后台生成，请稍后刷新查看。
"""
```

---

## 三、具体实施代码

### 🔧 修改 1：优化 LLM 参数

```python
# 在 vita.py 配置区域添加
# ============================================
# LLM 性能优化配置
# ============================================
DIAGNOSIS_MAX_TOKENS = 1200      # 故障诊断（原 16000）
STATISTICS_MAX_TOKENS = 600      # 统计查询
RESPONSIBILITY_MAX_TOKENS = 400  # 责任归属
DIAGNOSIS_TIMEOUT = 20           # 诊断超时（原 90）
QUICK_TIMEOUT = 10               # 快速查询超时

# 修改 call_llm_with_validation 函数
def call_llm_with_validation(
    prompt: str,
    expected_format: str = "markdown",
    temperature: float = 0.3,
    max_tokens: int = 1200,  # 默认值从 16000 改为 1200
    timeout: int = 20,       # 默认值从 90 改为 20
    max_retries: int = MAX_RETRIES
) -> Optional[str]:
    # ... 其余代码不变
```

### 🔧 修改 2：添加进度条

```python
# 在 diagnose_fault 函数开头添加
def diagnose_fault(entities: Dict, user_query: str, faiss_index, id_map) -> Optional[str]:
    """故障诊断引擎 - 带进度反馈"""

    # 创建进度条
    progress_container = st.container()
    with progress_container:
        progress_bar = st.progress(0)
        status_text = st.empty()

    try:
        # 阶段 1：检索（20%）
        status_text.text("🔍 正在知识库中检索相似案例...")
        progress_bar.progress(20)

        cases_df = metadata_filtered_vector_search(entities, user_query, faiss_index, id_map)

        # 阶段 2：重排序（40%）
        status_text.text("🎯 正在优化结果排序...")
        progress_bar.progress(40)

        reranked_df, used_rerank = apply_rerank_if_available(user_query, cases_df, top_k=20)

        # 阶段 3：统计（60%）
        status_text.text("📊 正在分析历史修复方式...")
        progress_bar.progress(60)

        solution_stats = analyze_solution_patterns(reranked_df)

        # 阶段 4：生成报告（80%）
        status_text.text("🤖 AI 专家正在生成诊断报告...")
        progress_bar.progress(80)

        # 优化后的 prompt（更短）
        report = generate_diagnosis_report_optimized(user_query, reranked_df, solution_stats)

        # 完成（100%）
        progress_bar.progress(100)
        status_text.text("✅ 诊断完成！")
        time.sleep(0.3)

        # 清除进度提示
        progress_container.empty()

        return report

    except Exception as e:
        progress_container.empty()
        raise e
```

### 🔧 修改 3：优化 Prompt

```python
def generate_diagnosis_report_optimized(user_query, cases_df, solution_stats):
    """生成优化后的诊断报告 - Prompt 更短，输出更快"""

    # 只取最关键的信息
    top_case = cases_df.iloc[0]
    most_common = solution_stats['most_common']
    success_count = solution_stats['count']

    # 精简 Prompt（从 2000+ tokens 降到 500 tokens）
    prompt = f"""你是地铁运维专家，给出简洁实用的建议。

【问题】{user_query}

【数据】
- 最常用方法：{most_common}（{success_count}次成功）
- 最近案例：{top_case['REPORTDATE'][:10]} {top_case['LOCATION']} - {top_case['SOLUTION'][:80]}

【要求】
1. 直接说处理步骤（3-5句）
2. 注意事项（2句）
3. 总共200字内

直接输出，不要标题。"""

    # 使用优化后的参数
    report = call_llm_with_validation(
        prompt,
        max_tokens=800,      # 从 16000 降到 800
        timeout=15,          # 从 90 降到 15
        temperature=0.3
    )

    return report
```

---

## 四、预期效果对比

### ⏱️ 响应时间对比

| 阶段 | 优化前 | 优化后 | 改进 |
|------|--------|--------|------|
| 向量检索 | 3-5秒 | 3-5秒 | - |
| 关键词检索 | 3秒 | 并行执行 | -3秒 |
| Rerank | 2-3秒 | 2-3秒 | - |
| LLM 生成 | 20-60秒 | 5-10秒 | -40秒 |
| **总计** | **30-70秒** | **10-20秒** | **-50秒** |

### 👤 用户体验对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 首次反馈 | 30秒后 | 5秒后（显示数据） |
| 进度可见性 | 小字提示 | 进度条 + 阶段说明 |
| 感知等待 | 漫长 | 可接受 |
| 降级策略 | 无 | 超时自动降级 |

---

## 五、实施优先级

### 🔴 立即实施（今天）
1. ✅ 降低 max_tokens：16000 → 1200
2. ✅ 缩短 timeout：90秒 → 20秒
3. ✅ 优化 Prompt 长度

**预期效果**：响应时间减少 50%

### 🟡 本周实施
1. ✅ 添加进度条
2. ✅ 预先显示数据
3. ✅ 超时降级策略

**预期效果**：用户体验显著提升

### 🟢 下周实施
1. 流式输出（需要测试）
2. 并行处理
3. 查询缓存

**预期效果**：进一步优化

---

## 六、风险评估

### ⚠️ 潜在风险

**1. 降低 max_tokens 可能导致回答不完整**
- **缓解措施**：测试 800/1200/1500 三个值，找到平衡点
- **监控指标**：检查是否有回答被截断

**2. 缩短 timeout 可能导致超时增加**
- **缓解措施**：实施降级策略，超时后返回基于数据的建议
- **监控指标**：记录超时率

**3. 简化 Prompt 可能影响回答质量**
- **缓解措施**：A/B 测试，对比用户满意度
- **监控指标**：用户反馈、重新查询率

---

## 七、监控指标

```python
# 添加性能监控
import time

class PerformanceTracker:
    def __init__(self):
        self.metrics = []

    def track(self, stage, duration):
        self.metrics.append({
            "stage": stage,
            "duration": duration,
            "timestamp": datetime.now()
        })

    def get_summary(self):
        total = sum(m['duration'] for m in self.metrics)
        return {
            "total_time": total,
            "stages": self.metrics
        }

# 使用
tracker = PerformanceTracker()

start = time.time()
# 执行检索
tracker.track("retrieval", time.time() - start)

start = time.time()
# 执行 LLM
tracker.track("llm_generation", time.time() - start)

# 记录到日志
logger.info(f"Performance: {tracker.get_summary()}")
```

---

## 八、总结

**核心优化策略**：
1. 🚀 **减少 LLM 生成时间**：降低 token 限制 + 简化 Prompt
2. 🎨 **改善用户感知**：进度条 + 预先显示数据 + 流式输出
3. ⚡ **并行处理**：向量检索和关键词检索同时进行
4. 🛡️ **降级保护**：超时后返回基于数据的建议

**预期总体效果**：
- 响应时间：30-70秒 → 10-20秒（减少 60-70%）
- 用户感知等待：30秒 → 5秒（减少 83%）
- 系统稳定性：提升（有降级策略）

需要我立即实施这些优化吗？
