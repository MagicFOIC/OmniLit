import { useCallback, useEffect, useRef, useState } from "react"
import type { GraphViewList, GraphViewRestore, GraphViewSaveRequest, GraphViewState, GraphViewSummary } from "@omnilit/shared-schema"
import type { GraphLayoutStyle } from "./renderer"

export interface SavedViewsDataSource {
  listViews(request: { recordId: string; signal: AbortSignal }): Promise<GraphViewList>
  saveView(request: { recordId: string; view: GraphViewSaveRequest; signal: AbortSignal }): Promise<GraphViewState>
  restoreView(request: { recordId: string; viewId: string; signal: AbortSignal }): Promise<GraphViewRestore>
  deleteView(request: { recordId: string; viewId: string; signal: AbortSignal }): Promise<unknown>
}

interface SavedViewsPanelProps {
  recordId: string
  dataSource?: SavedViewsDataSource
  createView?: (name: string) => GraphViewSaveRequest
  onRestore?: (result: GraphViewRestore) => void
  layoutStyle: GraphLayoutStyle
  onLayoutStyleChange: (style: GraphLayoutStyle) => void
}

const LAYOUT_OPTIONS = [
  { value: "snowflake", label: "雪花式", detail: "根文献居中，邻居放射展开" },
  { value: "hierarchy", label: "分层树", detail: "从根文献向下分层排列" },
  { value: "concentric", label: "同心圆", detail: "按多层圆环区分节点" },
  { value: "grid", label: "网格", detail: "规则网格减少视觉歧义" }
] as const satisfies readonly { value: GraphLayoutStyle; label: string; detail: string }[]

type PanelState = {
  status: "loading" | "ready" | "error"
  operation: "idle" | "saving" | "restoring" | "deleting"
  views: GraphViewSummary[]
  message: string
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "研究视图操作失败"
}

export function SavedViewsPanel({ recordId, dataSource, createView, onRestore, layoutStyle, onLayoutStyleChange }: SavedViewsPanelProps) {
  const [name, setName] = useState("")
  const [state, setState] = useState<PanelState>({ status: "loading", operation: "idle", views: [], message: "" })
  const requestRef = useRef<AbortController | undefined>(undefined)

  const load = useCallback((signal: AbortSignal) => {
    if (!dataSource) {
      setState({ status: "ready", operation: "idle", views: [], message: "" })
      return
    }
    setState((current) => ({ ...current, status: "loading", message: "" }))
    void dataSource.listViews({ recordId, signal }).then((result) => {
      setState({ status: "ready", operation: "idle", views: result.views, message: "" })
    }).catch((reason: unknown) => {
      if (!signal.aborted) setState((current) => ({ ...current, status: "error", operation: "idle", message: errorMessage(reason) }))
    })
  }, [dataSource, recordId])

  useEffect(() => {
    const controller = new AbortController()
    requestRef.current = controller
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  useEffect(() => () => requestRef.current?.abort(), [])

  const run = useCallback(async (operation: PanelState["operation"], action: (signal: AbortSignal) => Promise<void>) => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    setState((current) => ({ ...current, operation, message: "" }))
    try {
      await action(controller.signal)
      if (!controller.signal.aborted) load(controller.signal)
    } catch (reason) {
      if (!controller.signal.aborted) setState((current) => ({ ...current, operation: "idle", message: errorMessage(reason) }))
    }
  }, [load])

  const save = () => {
    if (!dataSource || !createView) return
    const cleanName = name.trim()
    if (!cleanName) {
      setState((current) => ({ ...current, message: "请输入视图名称。" }))
      return
    }
    void run("saving", async (signal) => {
      await dataSource.saveView({ recordId, view: createView(cleanName), signal })
      setName("")
    })
  }

  return <section className="kg-saved-views" aria-labelledby="saved-views-title">
    <div className="kg-saved-views-heading"><div><p className="kg-kicker">跨端研究状态</p><h2 id="saved-views-title">图谱视图与布局</h2></div><small>{dataSource ? `${state.views.length} 个已保存视图` : "当前组合视图"}</small></div>
    <fieldset className="kg-layout-options"><legend>知识图谱布局</legend>{LAYOUT_OPTIONS.map((option) => <label key={option.value} title={option.detail}><input type="radio" name="graph-layout" value={option.value} checked={layoutStyle === option.value} onChange={() => onLayoutStyleChange(option.value)} /><span><strong>{option.label}</strong><small>{option.detail}</small></span></label>)}</fieldset>
    {dataSource && createView && <div className="kg-save-view-form"><label><span>视图名称</span><input value={name} maxLength={80} disabled={state.operation !== "idle"} onChange={(event) => setName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") save() }} placeholder="例如：核心方法与作者" /></label><button type="button" disabled={state.operation !== "idle"} onClick={save}>{state.operation === "saving" ? "保存中…" : "保存当前视图"}</button></div>}
    {dataSource && state.status === "loading" && <p role="status">正在读取保存的视图…</p>}
    {dataSource && state.status === "error" && <p role="alert">{state.message}<button type="button" onClick={() => { const controller = new AbortController(); requestRef.current = controller; load(controller.signal) }}>重试</button></p>}
    {dataSource && state.status === "ready" && state.views.length === 0 && <p role="status">尚未保存研究视图。</p>}
    {state.message && state.status !== "error" && <p role="alert">{state.message}</p>}
    {dataSource && state.views.length > 0 && <ul>{state.views.map((view) => <li key={view.id}><span><strong>{view.name}</strong><small>{new Date(view.updatedAt).toLocaleString()}</small></span><span><button type="button" disabled={state.operation !== "idle"} onClick={() => void run("restoring", async (signal) => { const result = await dataSource.restoreView({ recordId, viewId: view.id, signal }); onRestore?.(result) })}>恢复</button><button type="button" disabled={state.operation !== "idle"} aria-label={`删除视图 ${view.name}`} onClick={() => void run("deleting", async (signal) => { await dataSource.deleteView({ recordId, viewId: view.id, signal }) })}>删除</button></span></li>)}</ul>}
  </section>
}
