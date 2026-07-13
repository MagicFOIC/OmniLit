import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"
import { PROTOCOL_VERSION, type GraphData, type GraphEdge, type GraphNeighborPage, type GraphNode, type GraphProjection, type GraphTimeline, type GraphViewRestore, type GraphViewSaveRequest, type LiteraturePage, type LiteratureRow } from "@omnilit/shared-schema"
import { GraphCanvas } from "./GraphCanvas"
import { NodeMindMap } from "./NodeMindMap"
import { CitationNetwork } from "./CitationNetwork"
import { CollaborationPanel, type CollaborationDataSource } from "./CollaborationPanel"
import { SavedViewsPanel, type SavedViewsDataSource } from "./SavedViewsPanel"
import { TimelinePanel, type TimelineQuerySelection } from "./TimelinePanel"
import type { GraphLayoutStyle, GraphRenderMetrics, GraphViewport } from "./renderer"
import { createKnowledgeGraphState, filterGraphData, knowledgeGraphReducer, nodeTypeCounts, selectedEdge, selectedNode } from "./state"

export interface KnowledgeGraphDataSource {
  expandNeighbors(request: { recordId: string; nodeId: string; mode: string; offset: number; limit: number; signal: AbortSignal }): Promise<GraphNeighborPage>
  loadLiterature(request: { recordId: string; visibleNodeIds: string[]; selectedNodeId?: string; hoveredNodeId?: string; signal: AbortSignal }): Promise<LiteraturePage>
  projectGraph?(request: { recordId: string; viewport: Record<string, number>; pinnedNodeIds?: string[]; pinnedEdgeIds?: string[]; layoutStyle?: string; signal: AbortSignal }): Promise<GraphProjection>
  loadTimeline?(request: { timelineKey: string; protocolVersion: "1.0"; startYear?: number; endYear?: number; playbackYear?: number; viewport: Record<string, number>; pinnedNodeIds?: string[]; signal: AbortSignal }): Promise<GraphTimeline>
  savedViews?: SavedViewsDataSource
  collaboration?: CollaborationDataSource
}

export interface KnowledgeGraphOption { recordId: string; title: string; nodeCount: number; edgeCount: number }
export interface KnowledgeGraphPageProps {
  data: GraphData
  dataSource?: KnowledgeGraphDataSource
  timelineKey?: string
  graphOptions?: readonly KnowledgeGraphOption[]
  selectedGraphIds?: readonly string[]
  loadingGraphIds?: readonly string[]
  onGraphToggle?: (recordId: string) => void
}

const TYPE_LABELS: Record<string, string> = {
  paper: "论文", citation: "引用文献", author: "作者", institution: "机构", topic: "主题", method: "方法",
  dataset: "数据集", result: "结果", model: "模型", metric: "指标", cluster: "聚合节点"
}
const EXPANSION_MODES = [
  ["all", "全部关系"], ["references", "参考文献"], ["cited_by", "被引用"], ["authors", "作者"], ["topics", "主题"]
] as const
const NODE_LIST_BATCH = 100
const GRAPH_COLUMN_OPTIONS = [1, 2, 3] as const
type GraphColumnCount = typeof GRAPH_COLUMN_OPTIONS[number]
const DENSITY_OPTIONS = [{ value: "overview", label: "概览" }, { value: "normal", label: "标准" }, { value: "detail", label: "细节" }] as const
const DEFAULT_VIEWPORT: GraphViewport = { width: 960, height: 640, scale: 1, panX: 0, panY: 0 }
const LAYOUT_DISPLAY_STYLE: Record<GraphLayoutStyle, "overview" | "academic" | "radial" | "focus"> = { snowflake: "radial", hierarchy: "academic", concentric: "focus", grid: "overview" }

function layoutFromDisplayStyle(style: string): GraphLayoutStyle {
  return style === "academic" ? "hierarchy" : style === "focus" ? "concentric" : style === "overview" ? "grid" : "snowflake"
}

export function projectionViewport(viewport: GraphViewport, density: "overview" | "normal" | "detail"): Record<string, number> {
  const densityScale = { overview: 0.5, normal: 1, detail: 2 }[density]
  return { ...viewport, scale: Math.max(0.05, viewport.scale * densityScale), overscan: 120 }
}

function nodeConfidence(node: GraphNode): number { return node.metrics?.confidence ?? 1 }

function DetailPanel({ node, edge, dataSource, expansion, mode, onModeChange, onExpand, onCancel, onDrillCluster }: {
  node?: GraphNode; edge?: GraphEdge; dataSource?: KnowledgeGraphDataSource
  expansion: ReturnType<typeof createKnowledgeGraphState>["expansion"]
  mode: string; onModeChange: (mode: string) => void; onExpand: () => void; onCancel: () => void; onDrillCluster?: (node: GraphNode) => void
}) {
  if (!node && !edge) return <aside className="kg-detail kg-detail-empty"><h2>节点详情</h2><p>选择画布、节点列表或文献列表中的条目，以查看来源、置信度和属性。</p></aside>
  if (edge) return <aside className="kg-detail"><p className="kg-kicker">关系</p><h2>{edge.type}</h2><dl><dt>来源</dt><dd>{edge.source}</dd><dt>目标</dt><dd>{edge.target}</dd><dt>权重</dt><dd>{edge.weight ?? 1}</dd></dl></aside>
  const evidence = node?.evidence ?? []
  const isLoading = expansion.status === "loading" && expansion.nodeId === node?.id
  const canLoadMore = expansion.status === "ready" && expansion.nodeId === node?.id && expansion.mode === mode && expansion.hasMore
  return <aside className="kg-detail">
    <p className="kg-kicker">{TYPE_LABELS[node?.type ?? ""] ?? node?.type}</p><h2>{node?.label}</h2>
    <dl><dt>置信度</dt><dd>{Math.round(nodeConfidence(node as GraphNode) * 100)}%</dd><dt>证据</dt><dd>{evidence.length} 条</dd>{Object.entries(node?.attributes ?? {}).slice(0, 6).map(([key, value]) => <div className="kg-detail-row" key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
    {node?.type === "cluster" && onDrillCluster ? <section className="kg-expansion" aria-label="聚合节点钻取"><p>该节点代表 {String(node.attributes.memberCount ?? "多个")} 个语义节点。</p><button type="button" onClick={() => onDrillCluster(node)}>展开聚合节点</button></section> : dataSource && <section className="kg-expansion" aria-label="节点展开">
      <label>关系范围<select value={mode} disabled={isLoading} onChange={(event) => onModeChange(event.target.value)}>{EXPANSION_MODES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      {isLoading ? <button type="button" onClick={onCancel}>取消展开</button> : <button type="button" onClick={onExpand}>{canLoadMore ? "加载更多邻居" : "展开邻居"}</button>}
      {expansion.nodeId === node?.id && expansion.status === "empty" && <p role="status">该关系范围没有更多邻居。</p>}
      {expansion.nodeId === node?.id && expansion.status === "error" && <p role="alert">{expansion.message}</p>}
    </section>}
    {evidence.length > 0 && <div className="kg-evidence"><h3>原文证据</h3>{evidence.map((item, index) => <blockquote key={`${item.elementId ?? "evidence"}-${index}`}>{item.excerpt || "未提供摘录"}<cite>第 {item.page} 页</cite></blockquote>)}</div>}
  </aside>
}

function GraphSelector({ options, selectedIds, loadingIds, onToggle }: { options: readonly KnowledgeGraphOption[]; selectedIds: readonly string[]; loadingIds: readonly string[]; onToggle?: (recordId: string) => void }) {
  const [query, setQuery] = useState("")
  const [columns, setColumns] = useState<GraphColumnCount>(1)
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const filteredOptions = useMemo(() => normalizedQuery ? options.filter((option) => `${option.title} ${option.recordId}`.toLocaleLowerCase().includes(normalizedQuery)) : options, [normalizedQuery, options])
  if (!options.length || !onToggle) return null
  return <section className="kg-graph-browser" aria-labelledby="graph-browser-title"><div className="kg-graph-browser-heading"><div><p className="kg-kicker">本地图谱</p><h2 id="graph-browser-title">选择加入画布的文献</h2></div><small>已选择 {selectedIds.length} 篇 · 显示 {filteredOptions.length} / {options.length}</small></div><div className="kg-graph-browser-controls"><label className="kg-graph-search"><span>筛选文献</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入文献标题…" /></label><div className="kg-graph-columns" aria-label="每行显示文献数"><span>每行显示</span><div>{GRAPH_COLUMN_OPTIONS.map((count) => <button type="button" key={count} aria-pressed={columns === count} onClick={() => setColumns(count)}>{count} 篇</button>)}</div></div></div>{filteredOptions.length ? <ul className={`kg-graph-grid columns-${columns}`}>{filteredOptions.map((option) => { const selected = selectedIds.includes(option.recordId); const loading = loadingIds.includes(option.recordId); return <li key={option.recordId}><button type="button" aria-pressed={selected} disabled={loading} onClick={() => onToggle(option.recordId)}><span className="kg-legend-dot kg-type-paper" /><span><strong>{option.title}</strong><small>{loading ? "正在加入画布…" : selected ? "已加入画布 · 再次点击移除" : "点击加入画布"} · {option.nodeCount} 节点 · {option.edgeCount} 关系</small></span></button></li> })}</ul> : <p className="kg-graph-empty" role="status">没有匹配的知识图谱。</p>}</section>
}

export function KnowledgeGraphPage({ data, dataSource, timelineKey: requestedTimelineKey, graphOptions = [], selectedGraphIds = [], loadingGraphIds = [], onGraphToggle }: KnowledgeGraphPageProps) {
  const [state, dispatch] = useReducer(knowledgeGraphReducer, data, createKnowledgeGraphState)
  const [mode, setMode] = useState("all")
  const [layoutStyle, setLayoutStyle] = useState<GraphLayoutStyle>("snowflake")
  const [nodeListLimit, setNodeListLimit] = useState(NODE_LIST_BATCH)
  const [renderMetrics, setRenderMetrics] = useState<GraphRenderMetrics | undefined>(undefined)
  const [browserMetrics, setBrowserMetrics] = useState<{ fps?: number; usedHeapMb?: number }>({})
  const [restoredViewport, setRestoredViewport] = useState<GraphViewport | undefined>(undefined)
  const [literature, setLiterature] = useState<{ rows: LiteratureRow[]; loading: boolean; error: string }>({ rows: [], loading: false, error: "" })
  const expansionAbort = useRef<AbortController | undefined>(undefined)
  const projectionAbort = useRef<AbortController | undefined>(undefined)
  const timelineAbort = useRef<AbortController | undefined>(undefined)
  const viewportRef = useRef<GraphViewport>(DEFAULT_VIEWPORT)
  const timelineKey = requestedTimelineKey || String(data.metadata.timelineKey ?? "")
  useEffect(() => dispatch({ type: "set-data", data }), [data])
  useEffect(() => () => { expansionAbort.current?.abort(); projectionAbort.current?.abort(); timelineAbort.current?.abort() }, [])
  const visible = useMemo(() => filterGraphData(state.data, state.filters), [state.data, state.filters])
  const listedNodes = visible.nodes.slice(0, nodeListLimit)
  const types = useMemo(() => nodeTypeCounts(state.data), [state.data])
  const activeNode = selectedNode(state)
  const activeEdge = selectedEdge(state)
  const collaborationTarget = activeNode ? { type: "node" as const, id: activeNode.id, label: activeNode.label } : activeEdge ? { type: "edge" as const, id: activeEdge.id, label: activeEdge.type } : { type: "graph" as const, id: state.data.recordId, label: "整个图谱" }
  const timelineGraphActive = state.data.metadata.evolution_graph === true
  useEffect(() => setNodeListLimit(NODE_LIST_BATCH), [state.filters.query, state.filters.nodeTypes, state.filters.needsReviewOnly])
  useEffect(() => {
    if (state.data.metadata.benchmark !== true || !renderMetrics || typeof requestAnimationFrame !== "function") return undefined
    let active = true
    let frame = 0
    const started = performance.now()
    let requestId = 0
    const tick = (now: number) => {
      frame += 1
      if (now - started < 1_000) {
        requestId = requestAnimationFrame(tick)
        return
      }
      if (!active) return
      const memory = (performance as Performance & { memory?: { usedJSHeapSize?: number } }).memory
      setBrowserMetrics({ fps: frame * 1_000 / Math.max(1, now - started), usedHeapMb: memory?.usedJSHeapSize ? memory.usedJSHeapSize / 1_048_576 : undefined })
    }
    requestId = requestAnimationFrame(tick)
    return () => { active = false; cancelAnimationFrame(requestId) }
  }, [renderMetrics, state.data.metadata.benchmark])

  useEffect(() => {
    if (!dataSource) {
      setLiterature({ rows: [], loading: false, error: "" })
      return undefined
    }
    if (timelineGraphActive) {
      const rows = state.data.nodes.filter((node) => node.type === "paper").map((node): LiteratureRow => ({
        nodeId: node.id, recordId: String(node.attributes.recordId ?? node.id.replace(/^paper:/, "")), kind: "paper",
        title: String(node.attributes.title ?? node.label), year: String(node.attributes.year ?? ""), authors: String(node.attributes.authors ?? ""), venue: String(node.attributes.venue ?? ""),
        citations: Number(node.attributes.citedByCount ?? 0), importance: node.metrics?.importance ?? 0.5, confidence: node.metrics?.confidence ?? 1,
        evidenceCount: node.evidence?.length ?? 0, selected: false, hovered: false,
        searchText: `${node.label} ${String(node.attributes.year ?? "")}`, relevance: node.metrics?.importance ?? 0.5
      }))
      setLiterature({ rows, loading: false, error: "" })
      return undefined
    }
    const controller = new AbortController()
    setLiterature((current) => ({ ...current, loading: true, error: "" }))
    void dataSource.loadLiterature({ recordId: state.data.recordId, visibleNodeIds: state.data.nodes.map((node) => node.id), signal: controller.signal })
      .then((page) => setLiterature({ rows: page.rows, loading: false, error: "" }))
      .catch((reason: unknown) => { if (!controller.signal.aborted) setLiterature({ rows: [], loading: false, error: reason instanceof Error ? reason.message : "文献投影失败" }) })
    return () => controller.abort()
  }, [dataSource, state.data.recordId, state.data.nodes, timelineGraphActive])

  const expand = useCallback(() => {
    if (!dataSource || !activeNode) return
    const samePage = state.expansion.nodeId === activeNode.id && state.expansion.mode === mode
    const offset = samePage && state.expansion.hasMore ? state.expansion.nextOffset : 0
    const controller = new AbortController()
    expansionAbort.current?.abort()
    expansionAbort.current = controller
    dispatch({ type: "expansion-loading", nodeId: activeNode.id, mode, offset })
    void dataSource.expandNeighbors({ recordId: state.data.recordId, nodeId: activeNode.id, mode, offset, limit: 12, signal: controller.signal }).then((page) => {
      dispatch({ type: "merge-data", nodes: page.nodes, edges: page.edges })
      dispatch({ type: "expansion-result", nodeId: activeNode.id, mode, nextOffset: page.nextOffset, hasMore: page.hasMore, empty: page.revealed === 0 })
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) dispatch({ type: "expansion-cancelled" })
      else dispatch({ type: "expansion-error", message: reason instanceof Error ? reason.message : "节点展开失败" })
    })
  }, [activeNode, dataSource, mode, state.data.recordId, state.expansion])

  const project = useCallback((density: "overview" | "normal" | "detail", pinnedNodeIds: string[] = []) => {
    if (!dataSource?.projectGraph) return
    const controller = new AbortController()
    projectionAbort.current?.abort()
    projectionAbort.current = controller
    dispatch({ type: "projection-loading", density })
    void dataSource.projectGraph({ recordId: state.data.recordId, viewport: projectionViewport(viewportRef.current, density), pinnedNodeIds, layoutStyle: density === "overview" ? "overview" : "academic", signal: controller.signal }).then((result) => {
      dispatch({ type: "projection-result", density, data: result.graph, summary: result.status })
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) dispatch({ type: "projection-cancelled" })
      else dispatch({ type: "projection-error", message: reason instanceof Error ? reason.message : "图谱投影失败" })
    })
  }, [dataSource, state.data.recordId])

  const queryTimeline = useCallback((selection?: TimelineQuerySelection) => {
    if (!dataSource?.loadTimeline || !timelineKey) return
    const controller = new AbortController()
    timelineAbort.current?.abort()
    timelineAbort.current = controller
    dispatch({ type: "timeline-loading" })
    void dataSource.loadTimeline({
      timelineKey,
      protocolVersion: PROTOCOL_VERSION,
      ...selection,
      viewport: projectionViewport(viewportRef.current, "normal"),
      signal: controller.signal
    }).then((result) => dispatch({ type: "timeline-result", data: result })).catch((reason: unknown) => {
      if (controller.signal.aborted) dispatch({ type: "timeline-cancelled" })
      else dispatch({ type: "timeline-error", message: reason instanceof Error ? reason.message : "时间演化查询失败" })
    })
  }, [dataSource, timelineKey])

  useEffect(() => {
    if (!dataSource?.loadTimeline || !timelineKey) return undefined
    queryTimeline()
    return () => timelineAbort.current?.abort()
  }, [dataSource?.loadTimeline, queryTimeline, timelineKey])

  const createSavedView = useCallback((name: string): GraphViewSaveRequest => {
    const viewport = viewportRef.current
    return {
      protocolVersion: PROTOCOL_VERSION,
      name,
      graphFingerprint: String(state.data.metadata.source_fingerprint ?? state.data.metadata.sourceFingerprint ?? ""),
      exploration: { nodeIds: state.data.nodes.slice(0, 2000).map((node) => node.id), edgeIds: state.data.edges.slice(0, 5000).map((edge) => edge.id), pages: {} },
      filters: { mode, searchText: state.filters.query, density: state.projection.density, literatureSortKey: "relevance", literatureSortDescending: true, facets: {}, nodeTypes: state.filters.nodeTypes, needsReviewOnly: state.filters.needsReviewOnly },
      selection: { nodeId: state.selection.nodeId ?? "", edgeId: state.selection.edgeId ?? "" },
      path: { startId: "", endId: "", directed: false, relationFilter: "ALL" },
      viewport: { displayStyle: LAYOUT_DISPLAY_STYLE[layoutStyle], focusDepth: 0, reviewMode: false, graphScale: viewport.scale, panX: viewport.panX, panY: viewport.panY, width: viewport.width, height: viewport.height, showArrows: true, showLabels: true, dimUnrelated: true, textFadeThreshold: 1.15, nodeSizeScale: 1, linkThickness: 1, animateLayout: false }
    }
  }, [layoutStyle, mode, state.data, state.filters, state.projection.density, state.selection])

  const restoreSavedView = useCallback((result: GraphViewRestore) => {
    dispatch({ type: "restore-view", result })
    setMode(result.view.filters.mode || "all")
    setLayoutStyle(layoutFromDisplayStyle(result.view.viewport.displayStyle))
    const current = viewportRef.current
    const restored = { width: result.view.viewport.width ?? current.width, height: result.view.viewport.height ?? current.height, scale: result.view.viewport.graphScale, panX: result.view.viewport.panX, panY: result.view.viewport.panY }
    viewportRef.current = restored
    setRestoredViewport(restored)
  }, [])

  return <section className="kg-page" aria-labelledby="graph-title">
    <header className="kg-header"><div><p className="kg-kicker">OmniLit · 科研工作台 {data.protocolVersion}</p><h1 id="graph-title">知识图谱</h1></div><span className="status-pill">G6 · 渐进式查询</span></header>
    <GraphSelector options={graphOptions} selectedIds={selectedGraphIds} loadingIds={loadingGraphIds} onToggle={onGraphToggle} />
    <div className="kg-toolbar" aria-label="图谱筛选工具栏">
      <label className="kg-search"><span>搜索节点</span><input type="search" value={state.filters.query} onChange={(event) => dispatch({ type: "set-query", query: event.target.value })} placeholder="标题、作者、方法…" /></label>
      <div className="kg-type-filters" aria-label="节点类型筛选">{types.map(({ type, count }) => <button type="button" key={type} aria-pressed={state.filters.nodeTypes.includes(type)} onClick={() => dispatch({ type: "toggle-node-type", nodeType: type })}><span className={`kg-legend-dot kg-type-${type}`} />{TYPE_LABELS[type] ?? type}<small>{count}</small></button>)}</div>
      {dataSource?.projectGraph && !timelineGraphActive && <div className="kg-density" aria-label="图谱细节层级">{DENSITY_OPTIONS.map(({ value, label }) => <button type="button" key={value} aria-pressed={state.projection.density === value} disabled={state.projection.status === "loading"} onClick={() => project(value)}>{label}</button>)}{state.projection.status === "loading" && <button type="button" onClick={() => projectionAbort.current?.abort()}>取消投影</button>}</div>}
      {(state.filters.query || state.filters.nodeTypes.length > 0 || state.filters.needsReviewOnly) && <button type="button" className="kg-clear" onClick={() => dispatch({ type: "clear-filters" })}>清除筛选</button>}
    </div>
    {!timelineGraphActive && <SavedViewsPanel recordId={state.data.recordId} dataSource={dataSource?.savedViews} createView={createSavedView} onRestore={restoreSavedView} layoutStyle={layoutStyle} onLayoutStyleChange={setLayoutStyle} />}
    {dataSource?.collaboration && !timelineGraphActive && <CollaborationPanel recordId={state.data.recordId} dataSource={dataSource.collaboration} target={collaborationTarget} />}
    {dataSource?.loadTimeline && timelineKey && <TimelinePanel timeline={state.timeline} onQuery={queryTimeline} onRetry={() => queryTimeline(state.timeline.data?.selection)} onCancel={() => timelineAbort.current?.abort()} onSelectPaper={(nodeId) => dispatch({ type: "select-node", nodeId })} />}
    <div className="kg-summary" aria-label="当前图谱摘要"><span><strong>{visible.nodes.length}</strong> 节点</span><span><strong>{visible.edges.length}</strong> 关系</span><span><strong>{visible.nodes.reduce((sum, node) => sum + (node.evidence?.length ?? 0), 0)}</strong> 证据</span></div>
    {state.projection.summary && <p className="kg-projection-status" role="status">{state.projection.summary.message} · {state.projection.summary.latencyMs.toFixed(1)} ms</p>}
    {state.projection.status === "error" && <p className="kg-projection-status" role="alert">{state.projection.message}</p>}
    {state.data.metadata.benchmark === true && renderMetrics && <output className="kg-render-metrics" aria-live="polite">G6 渲染 {renderMetrics.nodeCount.toLocaleString()} 节点 / {renderMetrics.edgeCount.toLocaleString()} 关系：{renderMetrics.durationMs.toFixed(1)} ms · 可交互 {renderMetrics.completedAtMs.toFixed(1)} ms{browserMetrics.fps ? ` · ${browserMetrics.fps.toFixed(1)} FPS` : ""}{browserMetrics.usedHeapMb ? ` · JS heap ${browserMetrics.usedHeapMb.toFixed(1)} MiB` : ""}</output>}
    {visible.nodes.length === 0 ? <div className="kg-empty" role="status"><h2>{graphOptions.length > 0 && selectedGraphIds.length === 0 ? "尚未向画布添加文献" : "当前筛选下没有节点"}</h2><p>{graphOptions.length > 0 && selectedGraphIds.length === 0 ? "请从上方本地图谱区域选择一篇或多篇文献。" : "调整关键词或节点类型后重试。"}</p>{(state.filters.query || state.filters.nodeTypes.length > 0) && <button type="button" onClick={() => dispatch({ type: "clear-filters" })}>恢复全部节点</button>}</div> : <div className="kg-workbench"><div className="kg-visual-column"><GraphCanvas data={state.data} filters={state.filters} selection={state.selection} viewport={restoredViewport} layoutStyle={layoutStyle} onNodeSelect={(nodeId) => dispatch({ type: "select-node", nodeId })} onEdgeSelect={(edgeId) => dispatch({ type: "select-edge", edgeId })} onNodeHover={(nodeId) => dispatch({ type: "hover-node", nodeId })} onRenderComplete={setRenderMetrics} onViewportChange={(viewport) => { viewportRef.current = viewport }} /><NodeMindMap data={state.data} nodes={listedNodes} totalCount={visible.nodes.length} selectedNodeId={state.selection.nodeId} onSelect={(nodeId) => dispatch({ type: "select-node", nodeId })} onLoadMore={listedNodes.length < visible.nodes.length ? () => setNodeListLimit((current) => current + NODE_LIST_BATCH) : undefined} /><CitationNetwork data={state.data} rows={literature.rows} loading={literature.loading} error={literature.error} selectedNodeId={state.selection.nodeId} onSelect={(nodeId) => dispatch({ type: "select-node", nodeId })} /></div><DetailPanel node={activeNode} edge={activeEdge} dataSource={timelineGraphActive ? undefined : dataSource} expansion={state.expansion} mode={mode} onModeChange={setMode} onExpand={expand} onCancel={() => expansionAbort.current?.abort()} onDrillCluster={!timelineGraphActive && dataSource?.projectGraph ? (node) => project("detail", Array.isArray(node.attributes.memberSample) ? node.attributes.memberSample.map(String) : []) : undefined} /></div>}
  </section>
}
