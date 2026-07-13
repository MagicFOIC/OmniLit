import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { NavLink, Navigate, Route, Routes, useSearchParams } from "react-router-dom"
import type { CloudGraphSummary, GraphData, GraphEdge, GraphNeighborPage, GraphNode, LiteraturePage } from "@omnilit/shared-schema"
import { ApiClientError } from "@omnilit/api-client"
import type { KnowledgeGraphDataSource } from "@omnilit/knowledge-graph"
import { activeTimelineKey, apiClient, businessApiClient, cloudApiClient, cloudApiConfigured, demoGraph, graphApiClient, graphDataSource, localAgentConfigured, platformBridge, qtEmbedded } from "./runtime"
import { createGraphBenchmark } from "./benchmark"
import { applyBusinessSettings } from "./uiSettings"
import { clearLocalAgentConnection, normalizeLocalAgentConnection, probeLocalAgent, saveLocalAgentConnection } from "./localAgentConfig"
import { EmbeddedGraphCanvas } from "./EmbeddedGraphCanvas"

const SharedKnowledgeGraphPage = lazy(() => import("@omnilit/knowledge-graph").then((module) => ({ default: module.KnowledgeGraphPage })))
const SharedLibraryPage = lazy(() => import("./LibraryPage").then((module) => ({ default: module.LibraryPage })))
const SharedCollectionsPage = lazy(() => import("./CollectionsPage").then((module) => ({ default: module.CollectionsPage })))
const AccountPage = lazy(() => import("./AccountPage").then((module) => ({ default: module.AccountPage })))
const InvitePage = lazy(() => import("./InvitePage").then((module) => ({ default: module.InvitePage })))
const ResearchWorkspacePage = lazy(() => import("./ResearchWorkspacePage").then((module) => ({ default: module.ResearchWorkspacePage })))
const StatisticsPage = lazy(() => import("./StatisticsPage").then((module) => ({ default: module.StatisticsPage })))
const AIWorkspacePage = lazy(() => import("./AIWorkspacePage").then((module) => ({ default: module.AIWorkspacePage })))
const BusinessSettingsPage = lazy(() => import("./BusinessSettingsPage").then((module) => ({ default: module.BusinessSettingsPage })))
const PublicLibraryPage = lazy(() => import("./PublicLibraryPage").then((module) => ({ default: module.PublicLibraryPage })))
const VerifyEmailPage = lazy(() => import("./VerifyEmailPage").then((module) => ({ default: module.VerifyEmailPage })))

function ProductShell({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    let active = true
    void businessApiClient.getBusinessSettings().then((settings) => {
      if (active) applyBusinessSettings(settings)
    }).catch(() => undefined)
    return () => { active = false }
  }, [])
  return (
    <div className="product-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand"><span className="brand-mark">O</span><span>OmniLit</span></div>
        <nav>
          <NavLink to="/graph">知识图谱</NavLink>
          <NavLink to="/library">文献库</NavLink>
          <NavLink to="/public-library">公共文献库</NavLink>
          <NavLink to="/collections">研究集合</NavLink>
          <NavLink to="/workspace">研究工作空间</NavLink>
          <NavLink to="/statistics">统计分析</NavLink>
          <NavLink to="/ai">AI 工作区</NavLink>
          <NavLink to="/account">账户与同步</NavLink>
          <NavLink to="/settings">业务设置</NavLink>
          <NavLink to="/about">运行环境</NavLink>
        </nav>
      </aside>
      <main className="workspace">{children}</main>
    </div>
  )
}

export function combineGraphs(recordIds: readonly string[], graphs: Readonly<Record<string, GraphData>>): GraphData {
  const selected = recordIds.flatMap((recordId) => graphs[recordId] ? [{ recordId, graph: graphs[recordId] }] : [])
  const first = selected[0]?.graph
  if (!first) return { protocolVersion: "1.0", schemaVersion: 1, recordId: "multi-selection", nodes: [], edges: [], metadata: { selectedRecordIds: [] } }
  const nodes = new Map(selected.flatMap(({ graph }) => graph.nodes).map((node) => [node.id, node]))
  const edges = new Map(selected.flatMap(({ graph }) => graph.edges).map((edge) => [edge.id, edge]))
  const graphPartitions = selected.map(({ recordId, graph }) => ({
    recordId,
    rootNodeId: graph.nodes.find((node) => node.id === `paper:${recordId}`)?.id
      ?? graph.nodes.find((node) => node.type === "paper" && String(node.attributes.recordId ?? "") === recordId)?.id
      ?? graph.nodes.find((node) => node.type === "paper")?.id
      ?? graph.nodes[0]?.id
      ?? "",
    nodeIds: graph.nodes.map((node) => node.id),
    edgeIds: graph.edges.map((edge) => edge.id)
  }))
  return {
    ...first,
    recordId: recordIds.length === 1 ? recordIds[0] ?? first.recordId : "multi-selection",
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    metadata: { ...first.metadata, selectedRecordIds: [...recordIds], graphPartitions, composite: recordIds.length > 1 }
  }
}

export function mergeCachedGraph(graph: GraphData, nodes: readonly GraphNode[], edges: readonly GraphEdge[]): GraphData {
  const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]))
  const edgeMap = new Map(graph.edges.map((edge) => [edge.id, edge]))
  nodes.forEach((node) => nodeMap.set(node.id, node))
  edges.forEach((edge) => edgeMap.set(edge.id, edge))
  return { ...graph, nodes: [...nodeMap.values()], edges: [...edgeMap.values()] }
}

function GraphRoute() {
  const [parameters] = useSearchParams()
  const benchmarkValue = Number(parameters.get("benchmark") ?? 0)
  const requestedRecordId = parameters.get("recordId")?.trim() || ""
  const requestedRecordTitle = parameters.get("recordTitle")?.trim().slice(0, 500) || ""
  const benchmarkGraph = import.meta.env.DEV && benchmarkValue > 0 ? createGraphBenchmark(benchmarkValue) : undefined
  const [error, setError] = useState("")
  const [empty, setEmpty] = useState(false)
  const [agentRestartRequired, setAgentRestartRequired] = useState(false)
  const [availableGraphs, setAvailableGraphs] = useState<CloudGraphSummary[]>([])
  const [graphs, setGraphs] = useState<Record<string, GraphData>>(benchmarkGraph ? { [benchmarkGraph.recordId]: benchmarkGraph } : {})
  const [selectedGraphIds, setSelectedGraphIds] = useState<string[]>(benchmarkGraph ? [benchmarkGraph.recordId] : [])
  const [loadingGraphIds, setLoadingGraphIds] = useState<string[]>([])
  const [catalogLoading, setCatalogLoading] = useState(!benchmarkGraph)
  useEffect(() => {
    if (benchmarkGraph) return undefined
    const controller = new AbortController()
    setError("")
    setEmpty(false)
    setAgentRestartRequired(false)
    setCatalogLoading(true)
    setGraphs({})
    setSelectedGraphIds([])
    setLoadingGraphIds([])
    void (async () => {
      try {
        if (localAgentConfigured || cloudApiConfigured) {
          try {
            const available = await graphApiClient.listGraphs(controller.signal)
            if (!controller.signal.aborted) setAvailableGraphs(available.graphs)
            if (!available.graphs.length && !requestedRecordId) {
              if (!controller.signal.aborted) setEmpty(true)
              return
            }
          } catch (reason) {
            if (!requestedRecordId && reason instanceof ApiClientError && reason.payload.code === "not_found") {
              if (!controller.signal.aborted) setAgentRestartRequired(true)
              return
            }
            if (!requestedRecordId) throw reason
          }
        } else {
          setAvailableGraphs([{ recordId: demoGraph.recordId, title: "演示知识图谱", cloudRevision: 0, updatedAt: "", nodeCount: demoGraph.nodes.length, edgeCount: demoGraph.edges.length }])
          setGraphs({ [demoGraph.recordId]: demoGraph })
        }
        if (requestedRecordId) {
          const loaded = !localAgentConfigured && !cloudApiConfigured && requestedRecordId === demoGraph.recordId
            ? demoGraph
            : await graphApiClient.getGraph(requestedRecordId, controller.signal)
          if (!controller.signal.aborted) {
            setGraphs((current) => ({ ...current, [requestedRecordId]: loaded }))
            setSelectedGraphIds([requestedRecordId])
          }
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          const code = reason instanceof ApiClientError ? reason.payload.code : ""
          if (code === "graph_not_found") setEmpty(true)
          else if (code === "not_found") setAgentRestartRequired(true)
          else setError(reason instanceof Error ? reason.message : "知识图谱加载失败")
        }
      } finally {
        if (!controller.signal.aborted) setCatalogLoading(false)
      }
    })()
    return () => controller.abort()
  }, [benchmarkGraph, requestedRecordId])

  const graphOptions = useMemo(() => availableGraphs.map((item) => ({
    recordId: item.recordId,
    title: typeof item.title === "string" && item.title.trim() ? item.title : item.recordId,
    nodeCount: item.nodeCount,
    edgeCount: item.edgeCount
  })), [availableGraphs])
  const graph = useMemo(() => benchmarkGraph ?? combineGraphs(selectedGraphIds, graphs), [benchmarkGraph, graphs, selectedGraphIds])
  const toggleGraph = useCallback((recordId: string) => {
    if (selectedGraphIds.includes(recordId)) {
      setSelectedGraphIds((current) => current.filter((value) => value !== recordId))
      return
    }
    setSelectedGraphIds((current) => current.includes(recordId) ? current : [...current, recordId])
    if (graphs[recordId]) return
    setLoadingGraphIds((current) => current.includes(recordId) ? current : [...current, recordId])
    void graphApiClient.getGraph(recordId).then((loaded) => {
      setGraphs((current) => ({ ...current, [recordId]: loaded }))
    }).catch((reason: unknown) => {
      setSelectedGraphIds((current) => current.filter((value) => value !== recordId))
      setError(reason instanceof Error ? reason.message : "知识图谱加载失败")
    }).finally(() => {
      setLoadingGraphIds((current) => current.filter((value) => value !== recordId))
    })
  }, [graphs, selectedGraphIds])
  const coordinatedDataSource = useMemo<KnowledgeGraphDataSource | undefined>(() => {
    if (benchmarkGraph || selectedGraphIds.length === 0) return undefined
    const source = graphDataSource as KnowledgeGraphDataSource
    const expandNeighbors: KnowledgeGraphDataSource["expandNeighbors"] = async (request) => {
      const matchingOwners = selectedGraphIds.filter((recordId) => graphs[recordId]?.nodes.some((node) => node.id === request.nodeId))
      const owners = matchingOwners.length ? matchingOwners : selectedGraphIds.slice(0, 1)
      const pages = await Promise.all(owners.map((recordId) => source.expandNeighbors({ ...request, recordId })))
      const firstPage = pages[0]
      if (!firstPage) throw new Error("无法确定节点所属的知识图谱")
      setGraphs((current) => {
        const next = { ...current }
        pages.forEach((page, index) => {
          const owner = owners[index]
          const cached = owner ? current[owner] : undefined
          if (owner && cached) next[owner] = mergeCachedGraph(cached, page.nodes, page.edges)
        })
        return next
      })
      const nodes = new Map(pages.flatMap((page) => page.nodes).map((node) => [node.id, node]))
      const edges = new Map(pages.flatMap((page) => page.edges).map((edge) => [edge.id, edge]))
      return {
        protocolVersion: "1.0",
        schemaVersion: 1,
        recordId: selectedGraphIds.length === 1 ? selectedGraphIds[0] ?? firstPage.recordId : "multi-selection",
        nodeId: request.nodeId,
        relationMode: firstPage.relationMode,
        status: nodes.size || edges.size ? "ready" : "empty",
        nodes: [...nodes.values()],
        edges: [...edges.values()],
        offset: request.offset,
        nextOffset: Math.max(...pages.map((page) => page.nextOffset)),
        revealed: pages.reduce((total, page) => total + page.revealed, 0),
        total: pages.reduce((total, page) => total + page.total, 0),
        hasMore: pages.some((page) => page.hasMore)
      } satisfies GraphNeighborPage
    }
    const loadLiterature: KnowledgeGraphDataSource["loadLiterature"] = async (request) => {
      const pages = await Promise.all(selectedGraphIds.map((recordId) => source.loadLiterature({ ...request, recordId })))
      const rows = new Map(pages.flatMap((page) => page.rows).map((row) => [row.nodeId, row]))
      return {
        protocolVersion: "1.0",
        recordId: selectedGraphIds.length === 1 ? selectedGraphIds[0] ?? "multi-selection" : "multi-selection",
        rows: [...rows.values()],
        offset: 0,
        nextOffset: rows.size,
        total: rows.size,
        hasMore: pages.some((page) => page.hasMore)
      } satisfies LiteraturePage
    }
    const coordinated: KnowledgeGraphDataSource = { expandNeighbors, loadLiterature }
    const onlyRecordId = selectedGraphIds.length === 1 ? selectedGraphIds[0] : undefined
    if (onlyRecordId) {
      coordinated.savedViews = source.savedViews
      coordinated.collaboration = source.collaboration
      coordinated.loadTimeline = source.loadTimeline
      if (source.projectGraph) coordinated.projectGraph = async (request) => {
        const result = await source.projectGraph?.({ ...request, recordId: onlyRecordId })
        if (!result) throw new Error("图谱投影不可用")
        setGraphs((current) => ({ ...current, [onlyRecordId]: result.graph }))
        return result
      }
    }
    return coordinated
  }, [benchmarkGraph, graphs, selectedGraphIds])

  if (error) return <StatePanel tone="error" title="无法加载知识图谱" detail={error} />
  if (agentRestartRequired) return <StatePanel title="请重启 Local Agent" detail="当前运行的 Local Agent 版本过旧，尚不支持读取本地图谱列表。请停止旧进程并使用当前项目代码重新启动，然后刷新此页面。" />
  if (empty) return requestedRecordTitle
    ? <StatePanel title={`《${requestedRecordTitle}》的知识图谱尚未生成`} detail={`请在桌面端找到《${requestedRecordTitle}》并运行知识图谱，生成完成后刷新此页面。`} />
    : <StatePanel title="请先在本地运行知识图谱" detail="请在桌面端打开文献并运行知识图谱，生成完成后刷新此页面。" />
  if (catalogLoading) return <StatePanel title="正在加载知识图谱" detail="正在读取本地图谱目录…" busy />
  return <><div className="agent-mode" role="status">{benchmarkGraph ? `${benchmarkGraph.nodes.length.toLocaleString()} 节点浏览器性能基线` : localAgentConfigured ? "本地 Agent 已连接" : cloudApiConfigured ? "Cloud API 图谱已连接" : "演示数据模式 · 配置服务后读取真实数据"}</div><Suspense fallback={<StatePanel title="正在加载图谱渲染器" detail="正在初始化共享知识图谱模块…" busy />}><SharedKnowledgeGraphPage data={graph} dataSource={coordinatedDataSource} timelineKey={selectedGraphIds.length === 1 ? activeTimelineKey || undefined : undefined} graphOptions={graphOptions} selectedGraphIds={selectedGraphIds} loadingGraphIds={loadingGraphIds} onGraphToggle={toggleGraph} /></Suspense></>
}

function StatePanel({ title, detail, busy = false, tone = "neutral" }: { title: string; detail: string; busy?: boolean; tone?: "neutral" | "error" }) {
  return <section className={`state-panel state-${tone}`} aria-live="polite" aria-busy={busy}><span className={busy ? "spinner" : "state-icon"} aria-hidden="true" /><h1>{title}</h1><p>{detail}</p></section>
}

function AboutRoute() {
  return <section><header className="page-header"><div><p className="eyebrow">Platform Bridge</p><h1>普通浏览器运行</h1></div></header><div className="info-card"><h2>明确能力边界</h2><p>文件选择和下载使用浏览器能力；文件管理器定位与 Local Agent 在未配置时返回明确降级状态，不伪造桌面路径。</p></div></section>
}

function LocalAgentRoute() {
  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:8765")
  const [token, setToken] = useState("")
  const [status, setStatus] = useState(localAgentConfigured ? "当前页面已连接本地文献库。" : "当前使用演示数据，尚未连接本地文献库。")
  const [busy, setBusy] = useState(false)

  async function connect(): Promise<void> {
    setBusy(true)
    setStatus("正在验证 Local Agent…")
    try {
      const connection = normalizeLocalAgentConnection(baseUrl, token)
      await probeLocalAgent(connection)
      saveLocalAgentConnection(connection.baseUrl, connection.token)
      window.location.reload()
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "Local Agent 连接失败。")
      setBusy(false)
    }
  }

  function disconnect(): void {
    clearLocalAgentConnection()
    window.location.reload()
  }

  const currentOrigin = typeof window === "undefined" ? "当前网页地址" : window.location.origin
  const launchCommands = [
    '$env:OMNILIT_LOCAL_AGENT_TOKEN="omnilit-local-token-123456789"',
    `python omnilit_qt_app.py --local-agent --port 8765 --origin ${currentOrigin}`
  ]
  return <section className="local-agent-page"><header className="page-header"><div><p className="eyebrow">Local Agent</p><h1>本地文献库连接</h1><p>通过仅监听本机回环地址的 Local Agent 读取桌面文献缓存，不向网页上传本地文件。</p></div></header><div className="info-card local-agent-card"><h2>{localAgentConfigured ? "已连接" : "连接桌面数据"}</h2><p>启动 Local Agent 时需要允许此网页来源：<code>{currentOrigin}</code>。Token 只保存在当前标签页会话，关闭浏览器后失效。</p><div className="launch-command"><span>PowerShell 启动命令：</span><pre><code>{launchCommands.join("\n")}</code></pre></div><form onSubmit={(event) => { event.preventDefault(); void connect() }}><label>Local Agent 地址<input type="url" required value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="http://127.0.0.1:8765" /></label><label>一次性 Token<input type="password" required minLength={24} autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} /></label><div className="form-actions"><button type="submit" disabled={busy}>{busy ? "验证中…" : "验证并连接"}</button>{localAgentConfigured && <button type="button" onClick={disconnect}>断开本地连接</button>}</div></form><p className="mutation-status" role="status">{status}</p></div></section>
}

function StartRoute() {
  const [target, setTarget] = useState("")
  useEffect(() => {
    const controller = new AbortController()
    void businessApiClient.getBusinessSettings(controller.signal)
      .then((settings) => setTarget(`/${settings.startPage}`))
      .catch(() => { if (!controller.signal.aborted) setTarget("/graph") })
    return () => controller.abort()
  }, [])
  return target ? <Navigate to={target} replace /> : <StatePanel title="正在打开研究环境" detail="正在读取共享启动偏好…" busy />
}

export function App() {
  if (qtEmbedded && window.location.hash.startsWith("#/graph-canvas")) return <EmbeddedGraphCanvas />
  return <ProductShell><Routes>
    <Route path="/" element={<StartRoute />} />
    <Route path="/graph" element={<GraphRoute />} />
    <Route path="/library" element={<Suspense fallback={<StatePanel title="正在加载文献库" detail="正在初始化共享文献模块…" busy />}><SharedLibraryPage client={businessApiClient} cloudClient={cloudApiClient} /></Suspense>} />
    <Route path="/public-library" element={<Suspense fallback={<StatePanel title="正在加载公共文献库" detail="正在读取已审核的公共文献…" busy />}><PublicLibraryPage client={cloudApiClient} /></Suspense>} />
    <Route path="/collections" element={<Suspense fallback={<StatePanel title="正在加载研究集合" detail="正在初始化集合与工作区…" busy />}><SharedCollectionsPage client={businessApiClient} /></Suspense>} />
    <Route path="/workspace" element={<Suspense fallback={<StatePanel title="正在加载研究工作空间" detail="正在读取共享比较文献…" busy />}><ResearchWorkspacePage client={businessApiClient} bridge={platformBridge} /></Suspense>} />
    <Route path="/statistics" element={<Suspense fallback={<StatePanel title="正在加载统计分析" detail="正在聚合共享文献指标…" busy />}><StatisticsPage client={businessApiClient} bridge={platformBridge} /></Suspense>} />
    <Route path="/ai" element={<Suspense fallback={<StatePanel title="正在加载 AI 工作区" detail="正在准备证据边界与任务运行时…" busy />}><AIWorkspacePage client={businessApiClient} bridge={platformBridge} /></Suspense>} />
    <Route path="/account" element={<Suspense fallback={<StatePanel title="正在加载账户" detail="正在初始化 Cloud API 会话…" busy />}><AccountPage cloudClient={cloudApiClient} localClient={apiClient} cloudConfigured={cloudApiConfigured} localGraphSourceAvailable={localAgentConfigured} /></Suspense>} />
    <Route path="/settings" element={<Suspense fallback={<StatePanel title="正在加载业务设置" detail="正在读取共享业务偏好…" busy />}><BusinessSettingsPage client={businessApiClient} /></Suspense>} />
    <Route path="/invite/:token" element={<Suspense fallback={<StatePanel title="正在加载团队邀请" detail="正在验证邀请入口…" busy />}><InvitePage client={cloudApiClient} /></Suspense>} />
    <Route path="/verify-email/:token" element={<Suspense fallback={<StatePanel title="正在验证邮箱" detail="正在激活账户…" busy />}><VerifyEmailPage client={cloudApiClient} /></Suspense>} />
    <Route path="/about" element={<><LocalAgentRoute /><AboutRoute /></>} />
    <Route path="*" element={<Navigate to="/graph" replace />} />
  </Routes></ProductShell>
}
