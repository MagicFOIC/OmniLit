import { useEffect, useMemo, useRef } from "react"
import type { GraphData } from "@omnilit/shared-schema"
import { G6GraphRenderer } from "./G6GraphRenderer"
import { filterGraphData, type GraphFilters, type GraphSelection } from "./state"
import type { GraphLayoutStyle, GraphRenderer, GraphRendererFactory, GraphRenderMetrics, GraphViewport } from "./renderer"

export interface GraphCanvasProps {
  data: GraphData
  filters: GraphFilters
  selection: GraphSelection
  onNodeSelect: (nodeId: string) => void
  onEdgeSelect: (edgeId: string) => void
  onNodeHover?: (nodeId?: string) => void
  rendererFactory?: GraphRendererFactory
  onRenderComplete?: (metrics: GraphRenderMetrics) => void
  onViewportChange?: (viewport: GraphViewport) => void
  viewport?: GraphViewport
  layoutStyle?: GraphLayoutStyle
}

export function GraphCanvas({ data, filters, selection, onNodeSelect, onEdgeSelect, onNodeHover, rendererFactory, onRenderComplete, onViewportChange, viewport, layoutStyle = "snowflake" }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<GraphRenderer | undefined>(undefined)
  const callbacksRef = useRef({ onNodeSelect, onEdgeSelect, onNodeHover, onRenderComplete, onViewportChange })
  const valuesRef = useRef({ data, filters, selection, viewport, layoutStyle })
  callbacksRef.current = { onNodeSelect, onEdgeSelect, onNodeHover, onRenderComplete, onViewportChange }
  valuesRef.current = { data, filters, selection, viewport, layoutStyle }
  const accessibleData = useMemo(() => filterGraphData(data, filters), [data, filters])

  useEffect(() => {
    if (!containerRef.current) return undefined
    let cancelled = false
    let renderer: GraphRenderer | undefined
    const container = containerRef.current
    queueMicrotask(() => {
      if (cancelled) return
      renderer = (rendererFactory ?? ((events) => new G6GraphRenderer(events)))({
        onNodeSelect: (nodeId) => callbacksRef.current.onNodeSelect(nodeId),
        onEdgeSelect: (edgeId) => callbacksRef.current.onEdgeSelect(edgeId),
        onNodeHover: (nodeId) => callbacksRef.current.onNodeHover?.(nodeId),
        onRenderComplete: (metrics) => {
          container.dataset.renderDurationMs = metrics.durationMs.toFixed(2)
          container.dataset.renderNodeCount = String(metrics.nodeCount)
          container.dataset.renderEdgeCount = String(metrics.edgeCount)
          callbacksRef.current.onRenderComplete?.(metrics)
        },
        onViewportChange: (viewport) => {
          container.dataset.viewportScale = viewport.scale.toFixed(4)
          container.dataset.viewportPanX = viewport.panX.toFixed(2)
          container.dataset.viewportPanY = viewport.panY.toFixed(2)
          callbacksRef.current.onViewportChange?.(viewport)
        }
      })
      rendererRef.current = renderer
      renderer.mount(container)
      renderer.setLayoutStyle(valuesRef.current.layoutStyle)
      renderer.setFilters(valuesRef.current.filters)
      renderer.setData(valuesRef.current.data)
      renderer.setSelection(valuesRef.current.selection)
      if (valuesRef.current.viewport) renderer.setViewport(valuesRef.current.viewport)
    })
    return () => {
      cancelled = true
      renderer?.destroy()
      rendererRef.current = undefined
    }
  }, [rendererFactory])

  useEffect(() => { rendererRef.current?.setData(data) }, [data])
  useEffect(() => { rendererRef.current?.setFilters(filters) }, [filters])
  useEffect(() => { rendererRef.current?.setLayoutStyle(layoutStyle) }, [layoutStyle])
  useEffect(() => { rendererRef.current?.setSelection(selection) }, [selection])
  useEffect(() => { if (viewport) rendererRef.current?.setViewport(viewport) }, [viewport])
  useEffect(() => { if (selection.nodeId) rendererRef.current?.focusNode(selection.nodeId) }, [selection.nodeId])

  return (
    <div className="kg-canvas-shell">
      <div ref={containerRef} className="kg-canvas" data-testid="graph-canvas" role="img" aria-label={`${accessibleData.nodes.length} 个节点、${accessibleData.edges.length} 条关系的知识图谱`} />
      <button type="button" className="kg-fit-button" onClick={() => rendererRef.current?.fitView()} aria-label="适应图谱视图">适应视图</button>
    </div>
  )
}
