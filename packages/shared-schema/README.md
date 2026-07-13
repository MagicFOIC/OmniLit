# @omnilit/shared-schema

OmniLit 桌面端、网页端和本地服务共享的数据协议。`schemas/omnilit-v1.schema.json`
是唯一权威来源；`src/generated.ts` 和
`omnilit_qt/shared_protocol_models.py` 均由代码生成器产生，不应手工编辑。

当前协议版本为 `1.0`，图谱数据版本为 `1`。读取端必须拒绝未知主版本，
但应容忍同一主版本中的未知字段，以便小版本向后兼容。旧 QML 图谱结构继续由
`KnowledgeGraphDocument` 提供，跨平台边界则使用 `shared_protocol` 适配器。

图谱探索边界还定义 `GraphNeighborPage`、`LiteratureRow` 与 `LiteraturePage`。邻居页携带实际
节点/关系和分页游标，前端可按 ID 去重合并；文献页由 Python 既有投影规则生成，避免 Web
重复实现排序、年份和引用计数规则。

`Task`/`TaskProgress` 覆盖 queued、running、stopping、succeeded、failed、cancelled 状态，
并携带消息、创建/开始/结束时间和 `resultRef`。`completed` 仅作为旧调用方兼容状态保留，
新 Local Agent 任务以 `succeeded` 表示成功。

大图边界使用 `GraphProjection`/`GraphProjectionStatus`：语义 GraphData 与当前渲染投影分离，
响应明确报告预算、真实/聚合/裁剪节点数、投影耗时和是否超出 120 ms 基线。

保存视图边界使用版本 2 的 `GraphViewState`，并拆分 exploration、filters、selection、path、
viewport、summary、list、restore 和 mutation DTO。它与现有 QML 快照格式兼容，同时补充 Web
节点类型筛选、待复核筛选和真实画布尺寸；单文献最多保存 100 个视图。

生成并检查类型：

```text
python tools/codegen/generate_shared_schema_types.py
python tools/codegen/generate_shared_schema_types.py --check
```
