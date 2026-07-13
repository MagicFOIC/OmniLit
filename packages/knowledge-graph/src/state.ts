import type { GraphData, GraphEdge, GraphNode, GraphProjectionStatus, GraphTimeline, GraphViewRestore } from "@omnilit/shared-schema"

export interface GraphFilters {
  query: string
  nodeTypes: string[]
  needsReviewOnly: boolean
}

export interface GraphSelection {
  nodeId?: string
  edgeId?: string
}

export interface KnowledgeGraphState {
  data: GraphData
  filters: GraphFilters
  selection: GraphSelection
  hoveredNodeId?: string
  expansion: { status: "idle" | "loading" | "ready" | "empty" | "error"; nodeId?: string; mode: string; nextOffset: number; hasMore: boolean; message?: string }
  projection: { status: "idle" | "loading" | "ready" | "error"; density: "overview" | "normal" | "detail"; summary?: GraphProjectionStatus; message?: string }
  timeline: { status: "idle" | "loading" | "ready" | "empty" | "error"; data?: GraphTimeline; message?: string }
}

export type KnowledgeGraphAction =
  | { type: "set-data"; data: GraphData }
  | { type: "merge-data"; nodes: GraphNode[]; edges: GraphEdge[] }
  | { type: "expansion-loading"; nodeId: string; mode: string; offset: number }
  | { type: "expansion-result"; nodeId: string; mode: string; nextOffset: number; hasMore: boolean; empty: boolean }
  | { type: "expansion-error"; message: string }
  | { type: "expansion-cancelled" }
  | { type: "projection-loading"; density: "overview" | "normal" | "detail" }
  | { type: "projection-result"; density: "overview" | "normal" | "detail"; data: GraphData; summary: GraphProjectionStatus }
  | { type: "projection-error"; message: string }
  | { type: "projection-cancelled" }
  | { type: "timeline-loading" }
  | { type: "timeline-result"; data: GraphTimeline }
  | { type: "timeline-error"; message: string }
  | { type: "timeline-cancelled" }
  | { type: "restore-view"; result: GraphViewRestore }
  | { type: "set-query"; query: string }
  | { type: "toggle-node-type"; nodeType: string }
  | { type: "set-needs-review"; value: boolean }
  | { type: "select-node"; nodeId?: string }
  | { type: "select-edge"; edgeId?: string }
  | { type: "hover-node"; nodeId?: string }
  | { type: "clear-filters" }

export const DEFAULT_GRAPH_FILTERS: GraphFilters = { query: "", nodeTypes: [], needsReviewOnly: false }

export function createKnowledgeGraphState(data: GraphData): KnowledgeGraphState {
  return { data, filters: DEFAULT_GRAPH_FILTERS, selection: {}, expansion: { status: "idle", mode: "all", nextOffset: 0, hasMore: false }, projection: { status: "idle", density: "normal" }, timeline: { status: "idle" } }
}

function mergeGraphData(data: GraphData, nodes: GraphNode[], edges: GraphEdge[]): GraphData {
  const nodeMap = new Map(data.nodes.map((node) => [node.id, node]))
  const edgeMap = new Map(data.edges.map((edge) => [edge.id, edge]))
  for (const node of nodes) nodeMap.set(node.id, node)
  for (const edge of edges) edgeMap.set(edge.id, edge)
  return { ...data, nodes: [...nodeMap.values()], edges: [...edgeMap.values()] }
}

function nodeNeedsReview(node: GraphNode): boolean {
  const confidence = node.metrics?.confidence ?? 1
  return node.needsReview === true || node.attributes.needsReview === true || confidence < 0.6
}

export function filterGraphData(data: GraphData, filters: GraphFilters): GraphData {
  const query = filters.query.trim().toLocaleLowerCase()
  const allowedTypes = new Set(filters.nodeTypes.map((value) => value.toLocaleLowerCase()))
  const nodes = data.nodes.filter((node) => {
    const type = node.type.toLocaleLowerCase()
    if (allowedTypes.size > 0 && !allowedTypes.has(type)) return false
    if (filters.needsReviewOnly && !nodeNeedsReview(node)) return false
    if (query && !`${node.label} ${node.type}`.toLocaleLowerCase().includes(query)) return false
    return true
  })
  const nodeIds = new Set(nodes.map((node) => node.id))
  const edges = data.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
  return { ...data, nodes, edges }
}

export function nodeTypeCounts(data: GraphData): Array<{ type: string; count: number }> {
  const counts = new Map<string, number>()
  for (const node of data.nodes) counts.set(node.type, (counts.get(node.type) ?? 0) + 1)
  return [...counts].map(([type, count]) => ({ type, count })).sort((left, right) => left.type.localeCompare(right.type))
}

export function selectedNode(state: KnowledgeGraphState): GraphNode | undefined {
  return state.data.nodes.find((node) => node.id === state.selection.nodeId)
}

export function selectedEdge(state: KnowledgeGraphState): GraphEdge | undefined {
  return state.data.edges.find((edge) => edge.id === state.selection.edgeId)
}

function clearHiddenSelection(state: KnowledgeGraphState): KnowledgeGraphState {
  const visible = filterGraphData(state.data, state.filters)
  const nodeVisible = !state.selection.nodeId || visible.nodes.some((node) => node.id === state.selection.nodeId)
  const edgeVisible = !state.selection.edgeId || visible.edges.some((edge) => edge.id === state.selection.edgeId)
  return nodeVisible && edgeVisible ? state : { ...state, selection: {} }
}

export function knowledgeGraphReducer(state: KnowledgeGraphState, action: KnowledgeGraphAction): KnowledgeGraphState {
  switch (action.type) {
    case "set-data":
      return clearHiddenSelection({ ...state, data: action.data })
    case "merge-data":
      return { ...state, data: mergeGraphData(state.data, action.nodes, action.edges) }
    case "expansion-loading":
      return { ...state, expansion: { status: "loading", nodeId: action.nodeId, mode: action.mode, nextOffset: action.offset, hasMore: false } }
    case "expansion-result":
      return { ...state, expansion: { status: action.empty ? "empty" : "ready", nodeId: action.nodeId, mode: action.mode, nextOffset: action.nextOffset, hasMore: action.hasMore } }
    case "expansion-error":
      return { ...state, expansion: { ...state.expansion, status: "error", message: action.message } }
    case "expansion-cancelled":
      return { ...state, expansion: { ...state.expansion, status: "idle", message: undefined } }
    case "projection-loading":
      return { ...state, projection: { ...state.projection, status: "loading", density: action.density, message: undefined } }
    case "projection-result":
      return clearHiddenSelection({ ...state, data: action.data, projection: { status: "ready", density: action.density, summary: action.summary } })
    case "projection-error":
      return { ...state, projection: { ...state.projection, status: "error", message: action.message } }
    case "projection-cancelled":
      return { ...state, projection: { ...state.projection, status: "idle", message: undefined } }
    case "timeline-loading":
      return { ...state, timeline: { ...state.timeline, status: "loading", message: undefined } }
    case "timeline-result":
      return clearHiddenSelection({ ...state, data: action.data.graph, timeline: { status: action.data.status, data: action.data } })
    case "timeline-error":
      return { ...state, timeline: { ...state.timeline, status: "error", message: action.message } }
    case "timeline-cancelled":
      return { ...state, timeline: { ...state.timeline, status: state.timeline.data?.status ?? "idle", message: undefined } }
    case "restore-view": {
      const { view, graph } = action.result
      const density = ["overview", "normal", "detail"].includes(view.filters.density) ? view.filters.density as "overview" | "normal" | "detail" : "normal"
      const restored = {
        ...state,
        data: graph,
        filters: { query: view.filters.searchText, nodeTypes: [...view.filters.nodeTypes], needsReviewOnly: view.filters.needsReviewOnly },
        selection: view.selection.nodeId ? { nodeId: view.selection.nodeId } : view.selection.edgeId ? { edgeId: view.selection.edgeId } : {},
        projection: { ...state.projection, status: "ready" as const, density }
      }
      return clearHiddenSelection(restored)
    }
    case "set-query":
      return clearHiddenSelection({ ...state, filters: { ...state.filters, query: action.query } })
    case "toggle-node-type": {
      const exists = state.filters.nodeTypes.includes(action.nodeType)
      const nodeTypes = exists
        ? state.filters.nodeTypes.filter((value) => value !== action.nodeType)
        : [...state.filters.nodeTypes, action.nodeType]
      return clearHiddenSelection({ ...state, filters: { ...state.filters, nodeTypes } })
    }
    case "set-needs-review":
      return clearHiddenSelection({ ...state, filters: { ...state.filters, needsReviewOnly: action.value } })
    case "select-node":
      return { ...state, selection: action.nodeId ? { nodeId: action.nodeId } : {} }
    case "select-edge":
      return { ...state, selection: action.edgeId ? { edgeId: action.edgeId } : {} }
    case "hover-node":
      return { ...state, hoveredNodeId: action.nodeId }
    case "clear-filters":
      return { ...state, filters: DEFAULT_GRAPH_FILTERS, selection: {} }
  }
}
