# VITA RAG 系统优化方案

> 基于 VITA v15.1 源码审计 + 2025-2026 RAG 领域最新研究设计
> 编写日期：2026-02-25

---

## 一、现状诊断（关键问题定位）

通过对 `vita.py`（v15.1）、`vita_v2/` 模块的完整代码审计，发现以下核心问题：

| 问题 | 严重度 | 代码位置 |
|------|--------|----------|
| **无稀疏检索**：设备编号(AFC-001)、故障代码等精确词全靠向量语义匹配 | 高 | `vita.py:1375-1433` |
| **FAISS 无元数据过滤**：46万向量全量搜索，未按线路/车站/专业分区 | 高 | `vita.py:1407` 固定 `k=50` |
| **rerank 是死代码**：v1 定义了 `rerank_results`(L285-328) 但从未调用 | 高 | `vita.py:285-328` |
| **v1/v2 割裂**：v2 有 HyDE/多路召回/rerank 但未集成到任何入口 | 中 | `vita_v2/retriever.py` |
| **无索引构建管线**：index 文件丢失则无法重建 | 中 | 无相关代码 |
| **无分块策略**：长工单的 LONGDESCRIPTION 整条做 embedding | 中 | 无 chunking 逻辑 |
| **无评估体系**：无 Recall@K / MRR / 忠实度指标 | 中 | 无相关代码 |
| **无答案溯源**：LLM 报告未引用具体工单号，无法验证幻觉 | 中 | `vita.py:1813-1883` |
| **SQL 拼接风险**：ticket_ids 直接拼入 SQL | 低 | `vita.py:1421` |

---

## 二、目标架构（结合最新实践）

```
┌─────────────────────────────────────────────────────────────┐
│                        用户查询                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  意图路由器   │  (现有 query_parser 增强)
                    │  + 歧义检测  │
                    └──┬───┬───┬──┘
            ┌──────────┘   │   └──────────┐
            ▼              ▼              ▼
       故障诊断        统计查询       责任查询
            │              │              │
    ┌───────▼────────┐     │        (保留现有四级降级)
    │  查询增强层      │     │
    │  ├─ 原始查询     │     │
    │  ├─ HyDE 假设文档│     │
    │  └─ 查询改写 x2  │     │
    └───────┬────────┘     │
            │              │
    ┌───────▼────────┐     │
    │  三路混合召回     │     │
    │  ├─ 稠密向量检索  │ ◄── Qdrant (替代 FAISS)
    │  ├─ 稀疏 BM25    │ ◄── Qdrant 内置 / Elasticsearch
    │  └─ 元数据过滤    │ ◄── Qdrant payload filter
    └───────���────────┘     │
            │              │
    ┌───────▼────────┐     │
    │  RRF 融合排序    │     │
    │  + 神经 Rerank  │ ◄── 现有 rerank 服务 (激活)
    └───────┬────────┘     │
            │              │
    ┌───────▼────────┐     │
    │  Corrective RAG │     │
    │  相关性自检      │     │
    │  ├─ 足够 → 生成  │     │
    │  └─ 不足 → 扩展  │     │
    └───────┬────────┘     │
            │              │
    ┌───────▼──────────────▼──┐
    │  LLM 报告生成 + 答案溯源  │
    │  每条建议标注工单号引用     │
    └───────┬─────────────────┘
            │
    ┌───────▼────────┐
    │  评估与监控      │
    │  ├─ RAGAS 离线   │
    │  └─ 日志追踪在线 │
    └────────────────┘
```

---

## 三、分阶段实施方案

### Phase 1：激活现有能力 + BM25 稀疏检索

> 影响最大、改动最小

#### 1.1 激活 Rerank

`vita.py:285-328` 已经有完整的 `rerank_results` 函数但从未调用。在诊断流程中激活它：

```python
# vita.py 诊断流程中，在 calculate_relevance_score 之后增加：

# 原始：直接用规则分数排序
# 优化：规则预筛 → 神经 Rerank 精排
candidates = sorted_by_rule_score[:50]  # 规则分数取 top 50
reranked = rerank_results(query_text, candidates)  # 调用已有的 rerank API
final_cases = reranked[:20]  # rerank 后取 top 20
```

**依据**：Anthropic Contextual Retrieval 研究显示，加入 Rerank 可在已有管线上额外降低 **30%** 的检索失败率。

#### 1.2 集成 BM25 稀疏检索

引入轻量级全文检索，与现有向量检索并行执行：

```python
# 方案A（推荐，纯 Python，无需额外服务）：
# 使用 rank_bm25 库，在内存中构建 BM25 索引

from rank_bm25 import BM25Okapi
import jieba

class BM25Index:
    def __init__(self, corpus_df):
        """从 Oracle 导出的工单 DataFrame 构建 BM25 索引"""
        self.ticket_ids = corpus_df['TICKETID'].tolist()
        tokenized = [list(jieba.cut(doc)) for doc in corpus_df['DESCRIPTION']]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 50) -> list[str]:
        tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokens)
        top_indices = scores.argsort()[-top_k:][::-1]
        return [self.ticket_ids[i] for i in top_indices]
```

```python
# 方案B（性能更好，需部署 Elasticsearch）：
# 适用于需要处理增量更新的场景
# 使用 ES 8.x 的中文分词 (ik_max_word) + BM25
```

#### 1.3 RRF 融合

将向量检索和 BM25 结果用 Reciprocal Rank Fusion 合并：

```python
def reciprocal_rank_fusion(results_lists: list[list[str]], k: int = 60) -> list[str]:
    """
    RRF 融合多路召回结果
    参考: Cormack et al. 2009, "Reciprocal Rank Fusion outperforms
    Condorcet and individual Rank Learning Methods"
    """
    rrf_scores = defaultdict(float)
    for results in results_lists:
        for rank, doc_id in enumerate(results):
            rrf_scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(rrf_scores, key=rrf_scores.get, reverse=True)

# 使用
vector_results = faiss_search(query_embedding, k=50)   # 现有
bm25_results = bm25_index.search(query_text, top_k=50)  # 新增
fused = reciprocal_rank_fusion([vector_results, bm25_results])
reranked = rerank_results(query, fused[:80])  # rerank top 80
final = reranked[:20]
```

**依据**：arXiv:2501.07391 的实验表明，BM25 + Dense + RRF 的 Blended RAG 在所有基准上都优于单路检索。在设备运维场景中尤其关键——设备编号 `AFC`、故障代码 `FAILURECODE` 这类精确词 BM25 的召回率远高于向量检索。

#### 1.4 新增依赖

```
# requirements.txt 新增
rank-bm25==0.2.2      # 轻量 BM25
jieba==0.42.1          # 中文分词
```

---

### Phase 2：向量库迁移 + 元数据过滤

> 解决架构瓶颈

#### 2.1 为什么选 Qdrant

| 对比维度 | FAISS | Qdrant | Milvus |
|----------|-------|--------|--------|
| 元数据过滤 | 不支持 | 原生 payload filter | 支持 |
| 增量写入 | 需重建索引 | 实时 | 实时 |
| 稀疏向量 | 不支持 | 原生支持 | 支持 |
| ColBERT late interaction | 不支持 | 原生支持 | 不支持 |
| 部署复杂度 | 无需部署 | Docker 单容器 | 分布式，较重 |
| 46万向量量级 | 足够 | 足够 | 过重 |
| 内网部署 | ✓ | ✓ (单二进制/Docker) | ✓ |
| 语言 | C++/Python | Rust | Go |

**结论**：Qdrant 在轻量部署（Docker 单容器即可）+ 功能完备性上最适合 VITA 的规模和内网环境。Milvus 更适合数十亿规模。

#### 2.2 数据模型设计

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    SparseVectorParams, SparseIndexParams,
    NamedVector, NamedSparseVector,
    Filter, FieldCondition, MatchValue, Range
)

# 创建 collection，同时支持稠密和稀疏向量
client = QdrantClient(host="10.98.12.69", port=6333)

client.create_collection(
    collection_name="vita_work_orders",
    vectors_config={
        "dense": VectorParams(size=1024, distance=Distance.COSINE)
    },
    sparse_vectors_config={
        "bm25": SparseVectorParams(
            index=SparseIndexParams(on_disk=False)
        )
    }
)

# 每条工单的 payload (元数据)
payload = {
    "ticket_id": "SR-123456",
    "line_num": "3",
    "station": "横山",
    "specialty": "ISCS",
    "description": "ISCS工作站黑屏无法操作",
    "solution": "重启工作站后恢复正常...",
    "failure_code": "ISCS-DISPLAY-001",
    "problem_code": "BLACK_SCREEN",
    "report_date": "2025-06-15T10:30:00",
    "has_solution": True
}
```

#### 2.3 检索时元数据过滤

```python
def search_with_metadata(query_embedding, entities, top_k=50):
    """带元数据过滤的混合检索"""

    # 构建过滤条件
    must_conditions = []
    should_conditions = []

    if entities.get("line"):
        must_conditions.append(
            FieldCondition(key="line_num", match=MatchValue(value=entities["line"]))
        )

    if entities.get("specialty"):
        # 用同义词扩展为 should (OR) 条件
        synonyms = get_specialty_synonyms(entities["specialty"])
        should_conditions = [
            FieldCondition(key="specialty", match=MatchValue(value=s))
            for s in synonyms
        ]

    if entities.get("time_range"):
        must_conditions.append(
            FieldCondition(key="report_date", range=Range(
                gte=entities["time_range"]["start"],
                lte=entities["time_range"]["end"]
            ))
        )

    # 过滤掉无解决方案的工单
    must_conditions.append(
        FieldCondition(key="has_solution", match=MatchValue(value=True))
    )

    query_filter = Filter(must=must_conditions, should=should_conditions)

    # Qdrant 混合检索：dense + sparse 同时执行
    results = client.query_points(
        collection_name="vita_work_orders",
        prefetch=[
            # 稠密向量路
            Prefetch(query=query_embedding, using="dense", limit=100),
            # 稀疏 BM25 路
            Prefetch(query=sparse_query, using="bm25", limit=100),
        ],
        query=FusionQuery(fusion=Fusion.RRF),  # RRF 融合
        query_filter=query_filter,
        limit=top_k,
    )
    return results
```

**核心收益**：

- 用户查询"3号线横山站ISCS黑屏"时，不再在46万全量工单中搜索，而是先按 `line_num=3 AND specialty∈ISCS同义词集` 过滤到几千条，再向量检索——精度和速度同步提升
- 增量更新：新工单实时写入，无需重建索引
- 稀疏向量原生支持，Phase 1 的 BM25 可以从 Python 内存迁移到 Qdrant 内置

#### 2.4 索引构建管线（填补现有空白）

```python
class IndexBuilder:
    """增量索引构建器 - 解决现有系统无索引管线的问题"""

    def __init__(self, db_manager, qdrant_client, embed_service):
        self.db = db_manager
        self.qdrant = qdrant_client
        self.embed = embed_service
        self.batch_size = 100

    def full_build(self):
        """全量构建（首次迁移用）"""
        sql = """SELECT TICKETID, DESCRIPTION, LONGDESCRIPTION,
                        SOLUTION, LINENUM, STATIONNAME, SPECIALTY,
                        FAILURECODE, PROBLEMCODE, REPORTDATE
                 FROM MAXIMO.SR
                 WHERE STATUS NOT IN ('CANCELLED')"""
        df = self.db.query(sql)

        for batch_start in range(0, len(df), self.batch_size):
            batch = df.iloc[batch_start:batch_start + self.batch_size]
            self._index_batch(batch)

    def incremental_update(self, since_date):
        """增量更新（定时任务，如每日凌晨）"""
        sql = """SELECT ... FROM MAXIMO.SR
                 WHERE REPORTDATE >= :since_date"""
        df = self.db.query(sql, params={"since_date": since_date})
        self._index_batch(df)

    def _index_batch(self, df):
        texts = self._prepare_texts(df)
        embeddings = self.embed.batch_encode(texts)
        sparse_vectors = self._compute_sparse(texts)  # jieba 分词 → 稀疏向量

        points = [
            PointStruct(
                id=row['TICKETID'],
                vector={"dense": emb, "bm25": sparse},
                payload=self._build_payload(row)
            )
            for (_, row), emb, sparse in zip(df.iterrows(), embeddings, sparse_vectors)
        ]
        self.qdrant.upsert("vita_work_orders", points)
```

---

### Phase 3：检索增强（Contextual Retrieval + Corrective RAG）

#### 3.1 Contextual Embedding（Anthropic 方法论）

**问题**：当前每条工单直接 embed `DESCRIPTION` 文本，丢失了上下文信息。

**方案**：在 embedding 之前用 LLM 为每条工单生成上下文前缀（离线处理，一次性成本）：

```python
CONTEXT_PROMPT = """请为以下地铁设备故障工单生成一段简短的上下文说明（50字以内），
包含：所属线路、车站、设备类型、故障类别。

工单信息：
线路: {line_num}
车站: {station}
专业: {specialty}
故障代码: {failure_code}
描述: {description}

上下文说明："""

def generate_contextual_text(row):
    context = call_llm(CONTEXT_PROMPT.format(**row), temperature=0.0, max_tokens=100)
    return f"{context}\n{row['description']}"

# 索引时使用 contextual_text 生成 embedding
contextual_text = generate_contextual_text(row)
embedding = embed(contextual_text)
```

**依据**：Anthropic 实验数据——Contextual Embedding 将检索失败率降低 **35%**，加上 BM25 和 Rerank 后降低 **67%**。Phase 1-3 叠加后理论上可以覆盖这个完整收益。

**成本控制**：

- 46万工单一次性处理，用较小的模型（GLM-4.5 Flash 或同级别）
- 使用 prompt caching 降低 token 消耗
- 后续增量工单才需要实时生成

#### 3.2 Corrective RAG（自校正检索）

在 LLM 生成诊断报告之前，增加一个相关性自检步骤：

```python
RELEVANCE_CHECK_PROMPT = """你是一个检索质量评估器。
用户查询: {query}

以下是检索到的历史工单，请判断每条与用户查询的相关性。
对每条工单回答: relevant / partially_relevant / irrelevant

{retrieved_cases}

输出 JSON: [{{"ticket_id": "...", "relevance": "..."}}]"""

def corrective_rag(query, entities, retrieved_cases):
    """Corrective RAG: 检索后自检，不足则扩展"""

    # Step 1: 相关性评估
    relevance = check_relevance(query, retrieved_cases)

    relevant_count = sum(1 for r in relevance if r['relevance'] == 'relevant')

    # Step 2: 判断是否需要补充检索
    if relevant_count < 3:
        # 放宽过滤条件重新检索
        relaxed_entities = relax_filters(entities)  # 去掉车站限制，保留线路
        extra_cases = search_with_metadata(query, relaxed_entities)
        retrieved_cases = merge_and_dedup(retrieved_cases, extra_cases)

    if relevant_count == 0:
        # 触发 Web/知识库兜底（如果有）或直接告知用户
        return "未找到足够相关的历史案例，建议联系相关专业工程师。"

    # Step 3: 只用 relevant 的案例生成报告
    filtered_cases = [c for c, r in zip(retrieved_cases, relevance)
                      if r['relevance'] != 'irrelevant']
    return generate_report(query, filtered_cases)
```

**依据**：CRAG（Corrective RAG, arXiv:2401.15884）论文证明，通过检索后自检可显著减少幻觉。在运维场景中，用不相关的工单生成诊断建议可能导致误操作，自检尤为重要。

#### 3.3 答案溯源（Citation Grounding）

修改报告生成 prompt，要求 LLM 对每条建议引用具体工单：

```python
REPORT_PROMPT_V2 = """基于以下历史案例生成故障诊断报告。

【重要要求】：
1. 每条具体的处理建议必须标注来源工单编号，格式：[SR-XXXXX]
2. 不得编造未在案例中出现的处理方法
3. 如果案例不足以支撑完整诊断，明确说明"以下建议仅基于有限案例"

历史案例：
{cases_with_ids}

用户问题：{query}
"""
```

**效果**：用户可以根据工单号回溯验证，发现幻觉时能立即识别。

---

### Phase 4：层次化索引 + 工单分块

#### 4.1 Parent-Child 双层索引

```
            ┌──────────────────────────┐
            │  摘要层 (Summary Index)   │  ← 粗检索用
            │  每条工单一个摘要向量      │
            └──────────┬───────────────┘
                       │ 1:N
            ┌──────────▼───────────────┐
            │  细节层 (Detail Index)    │  ← 精检索 + 返回给 LLM
            │  工单描述 chunk           │
            │  解决方案 chunk           │
            │  长描述分段 chunks        │
            └──────────────────────────┘
```

```python
def chunk_work_order(row):
    """将单条工单拆分为结构化 chunks"""
    chunks = []
    ticket_id = row['TICKETID']

    # Chunk 1: 故障描述（始终存在）
    chunks.append({
        "chunk_id": f"{ticket_id}_desc",
        "parent_id": ticket_id,
        "chunk_type": "description",
        "text": row['DESCRIPTION'],
    })

    # Chunk 2: 解决方案（如果存在）
    if row.get('SOLUTION') and len(str(row['SOLUTION'])) > 5:
        chunks.append({
            "chunk_id": f"{ticket_id}_solution",
            "parent_id": ticket_id,
            "chunk_type": "solution",
            "text": row['SOLUTION'],
        })

    # Chunk 3+: 长描述分段（如果超过 512 字符，按语义分段）
    long_desc = str(row.get('LONGDESCRIPTION', ''))
    if len(long_desc) > 512:
        segments = semantic_split(long_desc, max_len=400, overlap=50)
        for i, seg in enumerate(segments):
            chunks.append({
                "chunk_id": f"{ticket_id}_long_{i}",
                "parent_id": ticket_id,
                "chunk_type": "long_description",
                "text": seg,
            })

    # Summary: LLM 生成摘要
    summary = generate_summary(row)  # "3号线横山站ISCS工作站黑屏，重启后恢复"
    chunks.append({
        "chunk_id": f"{ticket_id}_summary",
        "parent_id": ticket_id,
        "chunk_type": "summary",
        "text": summary,
    })

    return chunks
```

检索策略：**小块嵌入，大块返回**——用 detail chunk 做精确匹配，但返回给 LLM 的是整条工单（parent）的完整信息。

#### 4.2 RAPTOR 层次化摘要（可选进阶）

参照 RAPTOR 论文（2024）和 Frontiers 2025 增强版，构建树状摘要结构：

```
Level 0: 原始工单 chunks
Level 1: 按 (专业 + 故障类型) 聚类 → 每簇一个摘要
Level 2: 按 (线路) 聚类 → 每线一个综合摘要

示例:
L2: "3号线ISCS系统近年主要故障为工作站黑屏(45%)和网络中断(30%)..."
 └─ L1: "ISCS工作站黑屏故障通常由显卡驱动或电源模块引起..."
     └─ L0: [SR-001: 横山站黑屏...] [SR-002: 翠竹站黑屏...] ...
```

**价值**：当用户问"3号线ISCS设备最近有什么问题"这类宏观问题时，直接命中 L1/L2 摘要，无需从底层工单拼凑答案。

---

### Phase 5：评估体系建设

#### 5.1 离线评估（RAGAS + DeepEval）

```python
# 构建评估数据集：从历史高分工单中抽样
eval_dataset = [
    {
        "question": "3号线横山站ISCS工作站黑屏怎么处理",
        "ground_truth_ids": ["SR-12345", "SR-12346"],  # 人工标注的相关工单
        "expected_answer_keywords": ["重启", "显卡驱动", "电源模块"]
    },
    # ... 100-200 条标注样本
]

# RAGAS 评估
from ragas.metrics import (
    context_precision,    # 检索到的文档中有多少是相关的
    context_recall,       # 相关文档被检索到了多少
    faithfulness,         # 答案是否忠于检索到的文档（反幻觉）
    answer_relevancy      # 答案与问题的相关性
)

# DeepEval CI/CD 集成
from deepeval.metrics import FaithfulnessMetric, ContextualRelevancyMetric
from deepeval.test_case import LLMTestCase

def test_retrieval_quality():
    """可集成到 CI/CD 管线"""
    test_case = LLMTestCase(
        input="横山站屏蔽门无法关闭",
        actual_output=vita_response,
        retrieval_context=retrieved_docs
    )
    metric = FaithfulnessMetric(threshold=0.7)
    metric.measure(test_case)
    assert metric.score >= 0.7
```

#### 5.2 在线监控

```python
# 每次查询记录检索追踪日志
trace = {
    "query_id": uuid4(),
    "timestamp": datetime.now(),
    "user_query": raw_query,
    "parsed_entities": entities,
    "retrieval": {
        "dense_candidates": len(dense_results),
        "bm25_candidates": len(bm25_results),
        "after_rrf": len(fused_results),
        "after_rerank": len(reranked),
        "top1_score": reranked[0].score if reranked else None,
    },
    "corrective_rag": {
        "relevant_count": relevant_count,
        "needed_expansion": relevant_count < 3,
    },
    "llm": {
        "model": "glm-4.5",
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "latency_ms": latency,
    }
}
logger.info(json.dumps(trace, ensure_ascii=False))
```

---

## 四、实施路线图

```
Phase 1 ──────────────────────────────────────
  ├── 1.1 激活已有 rerank（改几行代码）
  ├── 1.2 集成 rank_bm25 + jieba（新增约 100 行）
  ├── 1.3 实现 RRF 融合（新增约 30 行）
  └── 1.4 统一 v1/v2 最佳实践到主流程

Phase 2 ──────────────────────────────────────
  ├── 2.1 部署 Qdrant Docker 容器
  ├── 2.2 编写索引构建管线（全量 + 增量）
  ├── 2.3 改造检索层调用 Qdrant API
  └── 2.4 验证性能（应优于 FAISS 全量搜索）

Phase 3 ──────────────────────────────────────
  ├── 3.1 Contextual Embedding（离线处理 46 万工单）
  ├── 3.2 Corrective RAG 自检逻辑
  └── 3.3 答案溯源（修改报告 prompt）

Phase 4 ──────────────────────────────────────
  ├── 4.1 工单分块 + Parent-Child 索引
  └── 4.2 RAPTOR 层次摘要（可选）

Phase 5 ──────────────────────────────────────
  ├── 5.1 构建评估数据集（需业务专家参与标注）
  ├── 5.2 RAGAS / DeepEval 离线评估
  └── 5.3 查询追踪日志体系
```

---

## 五、新增依赖总结

```
# Phase 1
rank-bm25==0.2.2
jieba==0.42.1

# Phase 2
qdrant-client>=1.12.0

# Phase 5 (可选)
ragas>=0.2.0
deepeval>=1.0.0
```

---

## 六、与最新研究的对应关系

| 本方案措施 | 对应研究/实践 | 来源 |
|-----------|-------------|------|
| BM25 + Dense + RRF | Blended RAG | arXiv:2501.07391 |
| Contextual Embedding | Contextual Retrieval | Anthropic 2024.09 |
| Corrective RAG | CRAG | arXiv:2401.15884 |
| HyDE（v2 已有） | HyDE | Gao et al. 2022 |
| Rerank（激活死代码） | Cross-encoder Reranking | 业界标准实践 |
| Qdrant 混合检索 | 原生 Dense+Sparse+RRF | Qdrant 2025 |
| Parent-Child 分块 | Small-to-Big Retrieval | LlamaIndex / RAGFlow |
| RAPTOR 层次摘要 | Enhanced RAPTOR | Frontiers 2025 |
| 答案溯源 | Citation Grounding | 企业 RAG 最佳实践 |
| RAGAS 评估 | RAG Assessment | arXiv:2309.15217 |

---

## 七、关于 GraphRAG 的说明

考虑到 VITA 的数据是结构化工单（非长文档），且已有 Oracle 关系型数据库支撑实体关系，GraphRAG 的边际收益有限，**不建议在当前阶段引入**。

如果未来需要跨设备故障关联分析（如"A设备故障是否会引发B设备故障"），再考虑引入 LightRAG（EMNLP 2025，轻量级 GraphRAG 实现）。

---

## 附录：参考资料

- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - 2024.09
- [Blended RAG: Improving RAG Accuracy with Semantic Search and Hybrid Query-Based Retrievers](https://arxiv.org/abs/2501.07391) - 2025.01
- [Corrective RAG (CRAG)](https://arxiv.org/abs/2401.15884) - 2024.01
- [Agentic RAG Survey](https://arxiv.org/abs/2501.09136) - 2025.01
- [Comprehensive RAG Survey](https://arxiv.org/abs/2506.00054) - 2025.06
- [RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval](https://arxiv.org/abs/2401.18059) - 2024.01
- [Enhanced RAPTOR with Semantic Segmentation](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2025.1710121/full) - 2025
- [Late Chunking](https://arxiv.org/abs/2409.04701) - 2024.09, updated 2025.07
- [Evaluating Advanced Chunking: Late Chunking vs Contextual Retrieval](https://arxiv.org/abs/2504.19754) - ECIR 2025
- [RAGAS: Automated Evaluation of RAG](https://arxiv.org/abs/2309.15217) - 2023.09
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag) - v2.7.0
- [LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/) - 2025.06
- [LightRAG](https://github.com/HKUDS/LightRAG) - EMNLP 2025
- [Qdrant Documentation](https://qdrant.tech/documentation/) - 2025
- [BGE-M3: Multi-Functionality Multi-Linguality Multi-Granularity](https://github.com/FlagOpen/FlagEmbedding) - BAAI 2024
- [RAGFlow](https://github.com/infiniflow/ragflow) - v0.24.0
- [DSPy](https://github.com/stanfordnlp/dspy) - v2.5.29+
