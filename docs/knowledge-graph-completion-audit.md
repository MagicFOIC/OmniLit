# OmniLit 文献知识图谱完成度审计

本审计逐条对应 `knowledge-graph-vision.md`。判定规则：只有实现入口、数据契约、关键逻辑测试和可运行链路同时存在才记为“已证明”；只有 QML 字符串或设计意图不算完成证据。

## 1. 五类核心视图

| 显式要求 | 状态 | 实现证据 | 验证证据 |
| --- | --- | --- | --- |
| 搜索并定位节点 | 已证明 | `KnowledgeGraphController.search`、`KnowledgeGraphView.focusNode` | `test_knowledge_graph_controller.py`、`test_knowledge_graph_visuals.py` |
| 从种子论文开始，一度/二度展开 | 已证明 | `knowledge_graph_exploration.py` 的种子、分页邻居和深度状态 | `test_knowledge_graph_exploration.py`、`test_knowledge_graph_journey.py` |
| 引用/被引切换 | 已证明 | `neighbor_page` 的 `references` / `cited_by` 方向模式，详情面板入口 | `test_knowledge_graph_exploration.py`、`test_knowledge_graph_qml_contract.py` |
| 悬停预览、选中、邻居与路径高亮 | 已证明 | `KnowledgeGraphView.qml`、控制器 hover/selection/path 状态 | `test_knowledge_graph_visuals.py`、`test_knowledge_graph_controller.py` |
| 关系类型筛选 | 已证明 | 规范化的 `pathRelationTypes` / `setPathRelationFilter` | `test_knowledge_graph_paths.py`、`test_knowledge_graph_controller.py` |
| 年份、主题、作者、机构、期刊筛选 | 已证明 | `knowledge_graph_facets.py`、`GraphFilterBar.qml`，组合条件采用交集 | `test_knowledge_graph_facets.py`、控制器与 QML 契约测试 |
| 社区聚类 | 已证明 | `knowledge_graph_topics.py` 的确定性加权连通聚类 | `test_knowledge_graph_topics.py` |
| 最短路径 | 已证明 | `knowledge_graph_paths.py`，支持有向、无向、关系过滤和逐步解释 | `test_knowledge_graph_paths.py`、关键旅程测试 |
| 保存/恢复当前视图 | 已证明 | `knowledge_graph_views.py` v2；保存探索、分面、路径、选择和视口 | `test_knowledge_graph_views.py`、控制器往返测试 |
| 分享和导出 | 已证明 | JSON/Markdown/CSV/Mermaid/PNG；版本化 `.omnilit-graph.json` 可恢复分享包和 SHA-256 完整性校验 | `test_knowledge_graph_export.py`、`test_knowledge_graph_image_export.py`、`test_knowledge_graph_share.py`、关键旅程测试 |
| 撤销、重做、恢复默认 | 已证明 | `knowledge_graph_history.py` 与控制器历史快照 | `test_knowledge_graph_history.py`、控制器测试 |
| 详情面板、原文证据定位 | 已证明 | `KnowledgeGraphPanel.qml`，证据页码、边界框、元素 ID 信号 | 控制器、视觉和文献库 QML 测试 |
| 图谱与可搜索/排序/筛选文献列表双向联动 | 已证明 | `knowledge_graph_literature.py`、`GraphLiteratureList.qml` | `test_knowledge_graph_literature.py`、控制器/QML 契约测试 |
| 默认焦点加上下文，不一次显示全库 | 已证明 | 种子初始化、分页展开、节点上限和 LOD 投影 | exploration/LOD/controller 测试和固定规模基准 |

### 领域概览

| 显式要求 | 状态 | 实现与验证证据 |
| --- | --- | --- |
| 一级主题、二级子主题、文献数 | 已证明 | `build_topic_map` 的 topics/subtopics/size；`TopicMapPage.qml`；主题测试 |
| 代表论文、代表作者 | 已证明 | 主题中心度代表论文；真实作者元数据的论文数与平均中心度代表作者；主题测试 |
| 增长速度 | 已证明 | 年度窗口增长与趋势解释；主题测试 |
| 主题相似性 | 已证明 | 主题质心余弦相似度、每主题最多三条强连接、共享词/完整特征解释；气泡图连线；主题/QML 测试 |
| 当前主题位置 | 已证明 | selectedTopicId、键盘选择、气泡边框与详情同步；TopicBubbleMap 与 QML 测试 |
| 不退化为普通关系图 | 已证明 | 专用气泡布局、规模编码、子主题层级、相似度背景连线和侧栏解释，而非通用节点画布 |

### 时间演化

| 显式要求 | 状态 | 实现与验证证据 |
| --- | --- | --- |
| 按年份排列论文 | 已证明 | `events` 年卡和 `EvolutionTimeline.qml` |
| 关键引文路径 | 已证明 | 仅使用真实有向馆藏引文的 DAG 路径，保留原始引用方向和影响展示解释；演化测试 |
| 出现、增长、分裂、合并、衰退 | 已证明 | emergence/expansion；跨主题真实引文流的 split/merge signal；馆藏覆盖下 decline signal，均带限制性解释；演化测试 |
| 主题逐年代表论文 | 已证明 | 每个非空 `topicSeries.points` 和年度 topic event 的 `representativePaper`；演化/QML 测试 |
| 播放、时间范围 | 已证明 | TopicMapController 播放游标、范围状态和时间窗口图；控制器/演化测试 |
| 比较两个主题速度 | 已证明 | `topicSpeedComparisons` 和双下拉比较界面，输出篇/年公式解释；演化/QML 测试 |
| 里程碑与转折点 | 已证明 | keyScore、主题出现/扩张、跨主题桥、生命周期信号；时间线菱形标记和详情 |
| 年份/主题/论文与图谱联动 | 已证明 | windowTopics、选中论文、evolutionGraph、返回时间线状态；主题控制器、文献库 QML 与关键旅程测试 |

### 聚类与密度分析

| 显式要求 | 状态 | 实现与验证证据 |
| --- | --- | --- |
| 社区、标签、规模比较、内部关键论文 | 已证明 | 主题聚类与 network analysis 的 core/community 指标；主题和网络分析测试 |
| 密度热力图、关键词共现 | 已证明 | 有界关键词网络、density 值和密度画布；`NetworkAnalysisView.qml` 与测试 |
| 共被引、文献耦合 | 已证明 | 真实引用集合的 coCitation/coupling，来源与截断诊断；网络分析测试 |
| 桥接节点 | 已证明 | 采样介数与主题跨度 bridgeScore，带自然语言理由；网络分析测试 |
| 分析类型切换与解释 | 已证明 | 七种模式切换、覆盖率、算法解释和空状态；NetworkAnalysisView/QML 测试 |
| 不只依赖颜色 | 已证明 | 标签、大小、密度数值、排名卡、边界和说明同时编码；QML 视图与契约测试 |

### ORKG 风格语义比较

| 显式要求 | 状态 | 实现与验证证据 |
| --- | --- | --- |
| 13 类实体 | 已证明 | Paper/Author/Institution/Venue/Topic/ResearchQuestion/Method/Model/Dataset/Metric/Result/Conclusion/Limitation 的构建、迁移和展示 | ontology/pipeline/semantic comparison 测试 |
| 15 类正式关系 | 已证明 | `knowledge_graph_ontology.py` 集中契约；旧 PROPOSES/USES/EVALUATES_ON/MEASURED_BY/ACHIEVES/BELONGS_TO_TOPIC 兼容迁移 | `test_knowledge_graph_ontology.py`、relation precision/pipeline 测试 |
| 多论文九维比较 | 已证明 | 研究问题、方法、模型、数据集、指标、结果、贡献、局限等九维矩阵 | semantic comparison 和关键旅程测试 |
| 来源、置信度、缺失与冲突解释 | 已证明 | 单元格证据、置信度、自动来源、明确缺失和双边冲突证据 | semantic comparison/QML/Markdown 导出测试 |
| 人工校正 | 已证明 | 确认、修正、补充、排除覆盖层；原始自动抽取保留；持久化与撤销 | semantic comparison/controller 测试 |

## 2. 统一交互与视觉

| 原则 | 状态 | 证据 |
| --- | --- | --- |
| 远/中/近语义缩放 | 已证明 | `knowledge_graph_lod.py` 与 KnowledgeGraphView 分层标签、边和聚合；LOD/视觉测试 |
| 焦点、邻居、无关淡化、路径高亮、详情和列表同步 | 已证明 | KnowledgeGraphView/Panel/LiteratureList 共用控制器状态；控制器/视觉测试 |
| 动画只服务展开、布局、路径、演化和状态 | 已证明 | Motion 令牌、受控过渡和回放；无持续物理漂浮循环；QML 检查 |
| 统一设计令牌和实体命名 | 已证明 | Theme/Motion/LayoutMetrics、GraphLegend 与集中 ontology 关系标签；视觉/ontology 测试 |
| 工作台结构、深浅模式、受限颜色/尺寸/边、标签优先级 | 已证明 | KnowledgeGraphPage 与各分析视图复用主题令牌；节点尺寸限幅和标签 LOD；视觉测试 |
| 小地图、图例和状态说明 | 已证明 | KnowledgeGraphView minimap/GraphLegend；主题大小/颜色/相似线图例；时间线符号图例；网络密度/合作网络说明；各页 status/empty/error/loading 状态 |
| 键盘和基础无障碍 | 已证明 | 图谱、气泡图、时间线和列表方向键/Enter/Space；按钮工具提示；QML 契约测试 |

## 3. 数据与算法能力

全部列出的能力均有正式数据输出和解释：引用/被引网络、共被引、文献耦合、关键词共现、作者合作、机构合作、PageRank 类重要性、社区发现、桥接节点、最短路径、主题相似度、文献语义相似度、关键词突现、主题增长率、主题演化路径、核心论文和推荐阅读路径。对应实现分别位于 `knowledge_graph_topics.py`、`knowledge_graph_evolution.py`、`knowledge_graph_network_analysis.py`、`knowledge_graph_research_network.py`、`knowledge_graph_paths.py` 和 `knowledge_graph_semantic_comparison.py`；相应测试覆盖确定性、证据边界和解释文本。

作者任职关系只在作者级 affiliation 明确存在时生成；普通论文级机构字段不会被猜成某位作者的任职。分裂、合并和衰退均标为“馆藏证据信号”，不外推为全领域事实。推荐只在当前馆藏和用户上下文内排序，并明确区分真实引文与语义过渡。

## 4. 工程、性能和质量门禁

| 要求 | 状态 | 证据 |
| --- | --- | --- |
| 数据/状态先于界面、无静态假页面 | 已证明 | 各视图均由正式 Python 数据契约和控制器驱动；关键旅程使用真实控制器接口 |
| 加载、空白、错误、反馈 | 已证明 | TopicMapController/KnowledgeGraphController 状态机及各页面状态组件；控制器/QML 测试 |
| 配置集中、兼容迁移 | 已证明 | ontology、schema、view v2、builder/cache version；旧关系和旧视图迁移测试 |
| 后台计算、不阻塞主线程 | 已证明 | ManagedWorker 生成；缓存即时加载和后台刷新；控制器测试 |
| 100/1k/5k/10k 固定规模 | 已证明 | LOD、主题、演化、网络分析、语义比较、研究网络固定规模测试与 `knowledge-graph-progress.md` 基准 |
| 超规模采用限幅/采样/分页/LOD | 已证明 | 邻居分页、MAX_* 上限、介数采样、主题最多 12、渲染投影与图像导出独立上下文 |
| 详情更新避免全图语义重建 | 已证明 | render projection cache 将 selection/path/viewport 纳入精确失效键；后台数据图不重建 |
| QML 实际加载 | 已证明 | `test_knowledge_graph_qml_runtime.py` 使用真实控制器实例化 KnowledgeGraphPage 与 TopicMapPage |
| 连续用户旅程 | 已证明 | `test_knowledge_graph_journey.py` 覆盖主题→局部图→路径/分面→保存/分享恢复→演化→结构分析→阅读路径→九维语义比较 |
| 完整回归、QML lint | 已证明 | 默认环境全仓 515 项通过（126 条条件跳过）；PySide 知识图谱 157 项通过（2 条条件跳过），主题/演化/分析/研究洞察/语义比较/关键旅程 16 项通过；真实 QML 页面实例化 1 项通过；72 个 QML 文件 lint 错误 0 |

## 5. 最终工作流对应

1. 文献库筛选结果或种子论文进入领域分析：已证明。
2. 主题气泡地图、子主题、代表论文/作者：已证明。
3. 主题进入局部论文图谱：已证明。
4. 引用、作者、机构、方法、模型和数据集关系展开：已证明。
5. 时间轴、播放和窗口图：已证明。
6. 核心、聚类、桥接、热点与突现：已证明。
7. 多论文九维语义比较与人工校正：已证明。
8. 研究集合上下文、保存视图和可恢复分享：已证明。
9. 下一步阅读建议和基础→桥梁→前沿路径：已证明。
10. 所有算法结果保留来源、分数构成、理由或已知限制：已证明。

## 6. 最终门禁结果与环境说明

- `python -m unittest discover -s tests`：515 项成功，126 项按可选依赖条件跳过。
- `D:\Tool\anaconda3\python.exe -m unittest discover -s tests -p "test_knowledge_graph*.py"`：157 项成功，2 项条件跳过。
- 主题控制器、主题/QML、演化、网络分析、研究洞察、语义比较和关键旅程组合：16 项成功。
- `test_knowledge_graph_qml_runtime`：KnowledgeGraphPage 与 TopicMapPage 使用真实控制器实例化成功。
- 全部 72 个 `ui/qml/*.qml`：`qmllint` 错误 0。
- `git diff --check` 与新增 Python 模块 `compileall`：通过（仅 Git 提示既有 LF/CRLF 转换策略）。
- 五分面“生成选项＋两条件交集”中位耗时：100 篇 0.72 ms、1,000 篇 6.94 ms、5,000 篇 40.03 ms、10,000 篇 89.36 ms。

额外尝试了 Anaconda 解释器的全仓 633 项测试。该命令有 27 个错误和 1 个失败，均落在知识图谱范围外：解释器缺少 `fitz`，图表 OCR 环境中的 NumPy 不可用，继而使 PDF 可解析性校验降级。相同全仓代码在默认项目解释器下 515 项全部通过；知识图谱 PySide 定向套件、真实 QML 实例化和全 QML lint 均通过。因此这些可选解释器依赖问题不构成本目标实现回归，但保留在此，不把未通过命令隐去。

基于以上逐项证据，`knowledge-graph-vision.md` 的显式产品、数据、交互、性能和最终连续工作流要求均已关闭。
