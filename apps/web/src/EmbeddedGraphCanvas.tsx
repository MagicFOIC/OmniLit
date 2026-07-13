import { useCallback, useEffect, useRef, useState } from "react"
import { GraphCanvas } from "@omnilit/knowledge-graph"
import type { GraphData } from "@omnilit/shared-schema"
import type { GraphSelection } from "@omnilit/knowledge-graph"

interface QtSignal {
  connect(callback: () => void): void
  disconnect(callback: () => void): void
}

interface KnowledgeGraphBridge {
  canvasGraphData(callback: (data: GraphData) => void): void
  canvasSelection(callback: (selection: { nodeId?: string; edgeId?: string }) => void): void
  selectNode(nodeId: string, callback?: (selected: boolean) => void): void
  selectEdge(edgeId: string, callback?: (selected: boolean) => void): void
  setHoveredNode(nodeId: string): void
  setCanvasViewport(width: number, height: number, scale: number, panX: number, panY: number): void
  renderChanged: QtSignal
  changed: QtSignal
}

function connectController(): Promise<KnowledgeGraphBridge> {
  const transport = window.qt?.webChannelTransport
  if (!transport) return Promise.reject(new Error("Qt WebChannel transport is unavailable"))
  const create = () => new Promise<KnowledgeGraphBridge>((resolve, reject) => {
    const Constructor = window.QWebChannel
    if (!Constructor) return reject(new Error("Qt WebChannel runtime is unavailable"))
    new Constructor(transport, (channel) => {
      const controller = channel.objects.knowledgeGraphController as KnowledgeGraphBridge | undefined
      if (controller) resolve(controller)
      else reject(new Error("Knowledge graph bridge is unavailable"))
    })
  })
  if (window.QWebChannel) return create()
  return new Promise((resolve, reject) => {
    const script = document.createElement("script")
    script.src = "qrc:///qtwebchannel/qwebchannel.js"
    script.onload = () => { void create().then(resolve, reject) }
    script.onerror = () => reject(new Error("Qt WebChannel runtime could not be loaded"))
    document.head.appendChild(script)
  })
}

export function EmbeddedGraphCanvas() {
  const [data, setData] = useState<GraphData>()
  const [selection, setSelection] = useState<GraphSelection>({})
  const [error, setError] = useState("")
  const bridgeRef = useRef<KnowledgeGraphBridge | undefined>(undefined)
  const viewportTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    let active = true
    let bridge: KnowledgeGraphBridge | undefined
    const refreshData = () => bridge?.canvasGraphData((value) => { if (active) setData(value) })
    const refreshSelection = () => bridge?.canvasSelection((value) => {
      if (active) setSelection({ nodeId: value.nodeId || undefined, edgeId: value.edgeId || undefined })
    })
    void connectController().then((value) => {
      if (!active) return
      bridge = value
      bridgeRef.current = value
      value.renderChanged.connect(refreshData)
      value.changed.connect(refreshSelection)
      refreshData()
      refreshSelection()
    }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "React graph canvas failed") })
    return () => {
      active = false
      if (viewportTimer.current) window.clearTimeout(viewportTimer.current)
      bridge?.renderChanged.disconnect(refreshData)
      bridge?.changed.disconnect(refreshSelection)
      bridgeRef.current = undefined
    }
  }, [])

  const updateViewport = useCallback((viewport: { width: number; height: number; scale: number; panX: number; panY: number }) => {
    if (viewportTimer.current) window.clearTimeout(viewportTimer.current)
    viewportTimer.current = window.setTimeout(() => bridgeRef.current?.setCanvasViewport(viewport.width, viewport.height, viewport.scale, viewport.panX, viewport.panY), 120)
  }, [])

  if (error) return <div className="embedded-canvas-error" role="alert">{error}</div>
  if (!data) return <div className="embedded-canvas-loading" role="status">正在加载 React 图谱画布…</div>
  return <main className="embedded-graph-canvas"><GraphCanvas data={data} filters={{ query: "", nodeTypes: [], needsReviewOnly: false }} selection={selection} onNodeSelect={(nodeId) => bridgeRef.current?.selectNode(nodeId)} onEdgeSelect={(edgeId) => bridgeRef.current?.selectEdge(edgeId)} onNodeHover={(nodeId) => bridgeRef.current?.setHoveredNode(nodeId ?? "")} onViewportChange={updateViewport} /></main>
}
