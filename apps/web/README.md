# OmniLit Web

Phase 2 的独立浏览器入口。应用使用共享 JSON Schema/TypeScript DTO、统一 API Client、
Browser Platform Bridge 和从现有 QML 主题抽取的设计令牌；不读取 `window.qt`，也不要求
启动桌面应用或真实后端。

```text
npm install --cache .npm-cache
npm run web:dev
npm run phase2:web:check
```

当前 `/graph` 使用共享包中的固定 GraphData 和 `@omnilit/knowledge-graph` 的首个 G6
纵向切片，支持画布选择、图例、筛选、节点列表和详情。节点展开、文献联动、时间轴、
交互式聚类、趋势分析与产品导出仍按阶段 D 后续切片迁移。

当前 `/graph` 还提供共享知识演化时间轴：演示模式读取固定 GraphTimeline；连接 Local Agent 时可用 `VITE_TIMELINE_KEY` 指定桌面 `topic_maps` 集合键或 evolution cache key。范围和播放会同步更新年度事件、关键路径、G6 图与关联文献。
