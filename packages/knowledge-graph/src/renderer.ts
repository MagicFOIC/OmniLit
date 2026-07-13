import type { GraphData, GraphEdge, GraphNode } from "@omnilit/shared-schema"
import type { GraphFilters, GraphSelection } from "./state"

export interface GraphDataChange {
  addNodes?: GraphNode[]
  updateNodes?: GraphNode[]
  removeNodeIds?: string[]
  addEdges?: GraphEdge[]
  updateEdges?: GraphEdge[]
  removeEdgeIds?: string[]
}

export interface FitViewOptions { padding?: number }
export interface ExportOptions { background?: string; pixelRatio?: number }
export interface GraphRenderMetrics { durationMs: number; completedAtMs: number; nodeCount: number; edgeCount: number }
export interface GraphViewport { width: number; height: number; scale: number; panX: number; panY: number }
export type GraphLayoutStyle = "snowflake" | "hierarchy" | "concentric" | "grid"

export interface GraphRenderer {
  mount(container: HTMLElement): void
  setData(data: GraphData): void
  updateData(change: GraphDataChange): void
  setSelection(selection: GraphSelection): void
  setFilters(filters: GraphFilters): void
  setLayoutStyle(style: GraphLayoutStyle): void
  setViewport(viewport: GraphViewport): void
  focusNode(nodeId: string): void
  fitView(options?: FitViewOptions): void
  exportImage(options?: ExportOptions): Promise<Blob>
  destroy(): void
}

export interface GraphRendererEvents {
  onNodeSelect?: (nodeId: string) => void
  onEdgeSelect?: (edgeId: string) => void
  onNodeHover?: (nodeId?: string) => void
  onRenderComplete?: (metrics: GraphRenderMetrics) => void
  onViewportChange?: (viewport: GraphViewport) => void
}

export type GraphRendererFactory = (events: GraphRendererEvents) => GraphRenderer
