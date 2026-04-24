# VITA 故障诊断检索工作流设计与落地指南

版本：2026-03-26  
适用范围：`E:\vita\packages\workstation_vita` 工作站包  
对应实现：`src\workstation_vita\parser.py`、`src\workstation_vita\engine.py`、`src\workstation_vita\ui_app.py`

## 摘要

本文给出 VITA 故障诊断问答系统的正式设计方案。目标不是做一个泛化聊天机器人，而是做一个面向地铁运维故障场景的、以工单和维修记录为中心的诊断工作流。该工作流要求在用户提出自然语言问题时，优先返回与 `设备 + 现象 + 地点 + 时间` 最贴近的历史故障，并在直接证据不足时，继续提供 `本站历史`、`同类设备相近现象` 与 `通用处置指引`，同时严格区分证据强弱，避免将无关案例伪装成直接依据。

截至 2026 年 3 月 26 日，主流官方实践已经基本收敛到以下组合：`结构化知识沉淀 + 混合检索 + 元数据过滤 + 重排 + 评测闭环`。其中，复杂问题的子查询拆解与检索规划可以让模型参与，但生产可控性仍然要求保留事实边界、证据分级和可复现评估。

本方案最终落地为一种“半代理检索”架构：模型负责理解问题与规划检索层级，检索系统负责按分层证据执行查找和约束，最终由模型在证据边界内完成总结与建议生成。

关键词：故障诊断，工单检索，混合检索，证据分级，RAG，KCS，ITIL

## 1. 背景与问题定义

当前场景有四个现实约束：

1. Maximo 查库在服务端，工作站不能直接访问数据库。
2. LLM、Embedding、Rerank 在工作站，更便于调试和维护。
3. 用户问题高度场景化，常常同时包含设备、地点、现象、处置意图。
4. 如果只靠向量相似度，极易把“看起来类似”的工单误判为“直接相关”。

过去的典型失败模式包括：

1. 用户问“陆慕站综合监控工作站黑屏了怎么办”，系统却引用锁具、苏 e 行、AFC 无关案例。
2. 用户问“胥江路站 TVM5 频繁死机重启无效怎么处理”，系统只抓到 AFC 泛类案例，反而没优先抓本站 TVM5 工单。
3. 用户问历史类问题时，系统误当成实时诊断，导致现象抽取错乱。

这些问题说明：单层检索和单轮实体抽取不足以支撑生产级故障问答。

## 2. 设计目标

本方案定义五个一级目标：

1. 准确性：优先返回最贴近当前问题的直接历史案例。
2. 可解释性：每条建议必须能说明来自哪一层证据。
3. 可控性：模型不能越权把弱相关案例说成直接证据。
4. 可维护性：规则与模型职责分离，便于后续演进。
5. 可评估性：系统输出必须能被固定样例和指标持续回归验证。

## 3. 参考体系与经验基础

### 3.1 知识管理与运维方法论

`KCS` 的核心价值在于把“解决问题的过程”持续沉淀到知识库，而不是事后补文档。KCS 官方将“incident / case / trouble ticket”等视为同类支持事件，并强调系统记录的重要性。这与 Maximo 工单库高度契合。  
参考：

- Consortium for Service Innovation, KCS v6 Practices Guide  
  https://library.serviceinnovation.org/KCS/KCS_v6/KCS_v6_Practices_Guide
- Consortium for Service Innovation, Terminology and Scope  
  https://library.serviceinnovation.org/KCS/KCS_v6/KCS_v6_Adoption_Guide/000_Introduction/010_Terminology_and_Scope

`ITIL Incident / Problem Management` 则提供了“先恢复服务，再定位根因”的流程框架。对于地铁现场运维，这意味着系统输出不能只谈根因分析，还必须给出优先处置路径。

### 3.2 检索增强生成的官方实践

截至 2026-03-26，Azure 官方对于 RAG 的建议已经较明确：

1. 经典 RAG 适合追求速度、简单性和可控性。
2. 更复杂的问题适合让模型参与检索规划，但这会增加延时与成本。
3. 高质量检索需要 `hybrid search`、`semantic ranking`、`metadata filter` 与参数调优共同作用。

参考：

- Azure AI Search, RAG and Generative AI  
  https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview
- Azure AI Search, Agentic Retrieval Overview  
  https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview
- Azure AI Search, Create a hybrid query  
  https://learn.microsoft.com/en-us/azure/search/hybrid-search-how-to-query
- Azure AI Search, Vector query filters  
  https://learn.microsoft.com/en-us/azure/search/vector-search-filters

Pinecone 官方则持续强调 `metadata filtering` 对实际业务检索质量的重要性，这正对应本项目中的 `线路 / 车站 / 专业 / 设备 / 时间`。  
参考：

- Pinecone, Filter by metadata  
  https://docs.pinecone.io/guides/search/filter-by-metadata

### 3.3 评测闭环

官方实践已经不支持“凭感觉调效果”。OpenAI 和 Microsoft 都明确把 `eval-driven development` 作为生产应用的基本要求。  
参考：

- OpenAI, Agent evals  
  https://platform.openai.com/docs/guides/agent-evals
- OpenAI, Evaluation best practices  
  https://platform.openai.com/docs/guides/evaluation-best-practices
- Microsoft Foundry, RAG evaluators  
  https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators

## 4. 总体架构

### 4.1 物理部署

系统拆分为两侧：

1. 服务端  
   负责 Oracle / Maximo 访问、SQL 执行、原始工单与统计数据返回。
2. 工作站端  
   负责 UI、钉钉桥接、查询理解、Embedding、向量召回、重排、答案生成。

这样可以避免服务端申请外网权限，也允许工作站灵活更换模型与策略。

### 4.2 逻辑分层

整个故障问答链路分为六层：

1. 问题理解层
2. 检索规划层
3. 分层检索层
4. 证据分级层
5. 答案生成层
6. 评测与回归层

## 5. 职责划分：模型做什么，规则做什么

### 5.1 模型负责

模型负责三件事：

1. 理解用户真实意图  
   例如把“陆慕站综合监控工作站黑屏了怎么办”理解为一个复合问题，而不是仅抽几个字段。
2. 规划分层检索  
   把原始问题拆成多个检索层级，如直接匹配、本站历史、相近现象、通用指引。
3. 在证据边界内做归纳  
   把多层证据整理成符合运维语言习惯的回答。

### 5.2 规则与检索系统负责

规则与检索系统负责四件事：

1. 元数据约束  
   例如车站、线路、专业、时间范围。
2. 证据等级判定  
   例如直接匹配、相近参考、本站历史、通用知识。
3. 统计与排序  
   包括时间趋势、站点分布、工单排序。
4. 输出边界  
   禁止模型把弱证据包装成强证据。

## 6. 推荐工作流模板

### 6.1 问题理解

系统首先识别以下要素：

1. 意图  
   诊断、历史、统计、责任归属。
2. 主场景  
   `车站 + 设备 + 现象 + 时间`
3. 相邻线索  
   同专业、同类设备、相近现象。

这里不建议把 `黑屏`、`白屏`、`死机` 粗暴合并成同义词，而建议使用“三层现象语义”：

1. 原词层  
   只认完全一致，用于直接匹配。
2. 近邻层  
   仅用于补充召回，例如 `黑屏` 近邻 `无显示`。
3. 机理层  
   只用于原因推理，不用于强匹配。

### 6.2 检索规划

推荐模型先生成一个“检索计划对象”，而不是只输出实体：

```json
{
  "intent": "diagnosis",
  "main_scene": {
    "station_name": "陆慕站",
    "specialty": "ISCS",
    "device": "综合监控工作站",
    "fault_phenomenon": "黑屏"
  },
  "retrieval_plan": [
    {"layer": "direct_exact", "priority": 1},
    {"layer": "station_same_device", "priority": 2},
    {"layer": "station_same_specialty", "priority": 3},
    {"layer": "peer_similar_phenomenon", "priority": 4},
    {"layer": "general_guidance", "priority": 5}
  ]
}
```

### 6.3 分层检索

建议采用以下五层模板：

1. 直接匹配  
   `车站 + 设备 + 现象` 完全或高度一致。
2. 本站同设备历史  
   设备一致，现象可不同。
3. 本站同专业历史  
   专业一致，设备可不同。
4. 同类设备相近现象  
   跨站点但设备族一致，现象近邻。
5. 通用处置指引  
   仅作为兜底，不可替代历史证据。

### 6.4 检索技术组合

推荐组合为：

1. 精确过滤  
   基于车站、专业、时间范围做预过滤。
2. 关键词检索  
   保证 `TVM5`、`黑屏`、`综合监控工作站` 不会被语义扩散吞掉。
3. 向量召回  
   负责发现表达不同但语义接近的案例。
4. 重排  
   对候选结果做最终排序。

生产上更稳的策略不是“让模型全权控制检索”，而是：

1. 对精确场景优先走低噪声检索。
2. 对模糊场景再启用更强的语义扩展。
3. 对召回结果做本地证据分级。

### 6.5 证据分级

输出必须明确分四类：

1. 直接证据  
   当前设备或当前现象的直接历史记录。
2. 间接参考  
   本站同设备、同专业或同类设备相近现象。
3. 通用建议  
   来自通用维修流程或标准化指引。
4. 依据不足  
   系统没找到足够证据的部分。

## 7. 本项目的落地实现

### 7.1 已落地部分

当前工作站包已经落地以下能力：

1. 保留原始设备词  
   不再把 `TVM5` 直接压扁成 `AFC`，不再把 `综合监控工作站` 改坏。
2. 历史类查询识别  
   `历史故障有哪些` 会走历史模式，不再误判为诊断。
3. 严格证据分层  
   现在区分：
   - 直接相关案例
   - 本站历史案例
   - 同线同类案例
   - 补充参考案例
4. 精确场景降噪  
   对明确的设备与现象，不再默认依赖广义向量召回。
5. UI 中文化  
   前端表头和运行信息已去除不必要英文。

### 7.2 代码映射

当前实现的主要入口如下：

1. `src\workstation_vita\text_utils.py`  
   负责文本归一化、专业识别、别名扩展。
2. `src\workstation_vita\parser.py`  
   负责意图识别、设备编号抽取、现象识别、历史查询识别。
3. `src\workstation_vita\engine.py`  
   负责检索编排、案例注释、证据分层、答案提示词构建。
4. `src\workstation_vita\ui_app.py`  
   负责证据层展示和中文界面输出。

## 8. 推荐的下一阶段落地方向

### 8.1 从“字段解析”升级到“检索计划生成”

当前系统已经具备基本的分层检索能力，但下一阶段应让模型先生成检索计划，再由检索系统执行。原因有二：

1. 用户问题常常是复合问题，不是几个字段能表达完。
2. 模型更擅长判断“这句话需要同时查哪几层历史”。

### 8.2 现象近邻词典

不建议做粗暴同义词合并，而建议做“弱扩展词典”。例如：

1. `黑屏` 的近邻可以包含 `无显示`
2. `死机` 的近邻可以包含 `卡死`
3. `离线` 的近邻可以包含 `通讯中断`

这一层只能用于召回扩展，不可直接升级为直接证据。

### 8.3 结构化工单特征

建议服务端后续补充以下结构化字段，减少描述文本噪声：

1. 设备族
2. 设备编号
3. 现象标准词
4. 故障代码
5. 是否恢复
6. 首次恢复动作
7. 最终根因

## 9. 评测方法

### 9.1 样例集

建议建立固定的真实问题集，并长期维护。至少覆盖：

1. 精确诊断
2. 本站历史
3. 同类相近现象
4. 统计查询
5. 责任归属
6. 极端噪声问题

### 9.2 指标

推荐同时保留检索指标与答案指标。

检索指标：

1. 命中率
2. 首条相关率
3. 直接匹配命中率
4. 错引无关案例率

答案指标：

1. 相关性
2. 证据一致性
3. 处置可执行性
4. 不确定性表达是否真实

官方可参考的评测框架包括：

1. OpenAI 的 eval-driven development
2. Microsoft Foundry 的 `Document Retrieval`、`Max Relevance`、`Holes`

## 10. 当前推荐结论

对于本项目，最合适的成熟模板不是全自动代理，也不是纯规则，而是：

`KCS 结构化工单 + ITIL 故障分层 + 模型生成检索计划 + 精确匹配 / 本站历史 / 相近参考三层证据 + 混合检索与重排 + 持续评测`

考虑到 Azure 官方的 agentic retrieval 在 2026-03-26 仍属于预览能力，当前生产建议仍然是：

1. 保留本地可控编排
2. 引入模型参与检索计划
3. 不把证据分级完全交给模型
4. 用固定样例持续回归

这也是 VITA 当前工作站端最稳的演进路线。

## 参考资料

1. Azure AI Search, RAG and Generative AI  
   https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview
2. Azure AI Search, Agentic Retrieval Overview  
   https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview
3. Azure AI Search, Create a hybrid query  
   https://learn.microsoft.com/en-us/azure/search/hybrid-search-how-to-query
4. Azure AI Search, Vector query filters  
   https://learn.microsoft.com/en-us/azure/search/vector-search-filters
5. Pinecone, Filter by metadata  
   https://docs.pinecone.io/guides/search/filter-by-metadata
6. OpenAI, Agent evals  
   https://platform.openai.com/docs/guides/agent-evals
7. OpenAI, Evaluation best practices  
   https://platform.openai.com/docs/guides/evaluation-best-practices
8. Microsoft Foundry, RAG evaluators  
   https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators
9. Consortium for Service Innovation, KCS v6 Practices Guide  
   https://library.serviceinnovation.org/KCS/KCS_v6/KCS_v6_Practices_Guide
10. Consortium for Service Innovation, Terminology and Scope  
    https://library.serviceinnovation.org/KCS/KCS_v6/KCS_v6_Adoption_Guide/000_Introduction/010_Terminology_and_Scope
