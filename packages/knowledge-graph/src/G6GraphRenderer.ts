import { EdgeEvent, Graph, GraphEvent, NodeEvent, type IElementDragEvent, type IElementEvent, type Point, type GraphData as G6Data } from "@antv/g6"
import { colors, graphColors } from "@omnilit/design-tokens"
import type { GraphData, GraphEdge, GraphNode } from "@omnilit/shared-schema"
import { filterGraphData, type GraphFilters, type GraphSelection, DEFAULT_GRAPH_FILTERS } from "./state"
import type { ExportOptions, FitViewOptions, GraphDataChange, GraphLayoutStyle, GraphRenderer, GraphRendererEvents, GraphViewport } from "./renderer"

function nodeColor(type: string): string {
  return graphColors[type.toLocaleLowerCase() as keyof typeof graphColors] ?? graphColors.relation
}

function compactCanvasLabel(value: unknown, maxLength: number): string {
  const text = String(value ?? "")
  return text.length > maxLength ? `${text.slice(0, Math.max(1, maxLength - 1)).trimEnd()}…` : text
}

function dataUrlToBlob(dataUrl: string): Blob {
  const [header = "", encoded = ""] = dataUrl.split(",", 2)
  const mimeType = header.match(/data:([^;]+)/)?.[1] ?? "image/png"
  const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0))
  return new Blob([bytes], { type: mimeType })
}

interface GraphPartition {
  recordId: string
  rootNodeId: string
  nodeIds: string[]
}

interface LayoutPosition { x: number; y: number; role: "root" | "member" | "shared" }

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))
const CONCENTRIC_TYPE_PHASE = Math.PI / Math.sqrt(2)

function graphPartitions(data: GraphData): GraphPartition[] {
  const raw = data.metadata.graphPartitions
  if (!Array.isArray(raw)) return []
  return raw.flatMap((value) => {
    if (!value || typeof value !== "object") return []
    const item = value as Record<string, unknown>
    if (typeof item.recordId !== "string" || typeof item.rootNodeId !== "string" || !Array.isArray(item.nodeIds)) return []
    return [{ recordId: item.recordId, rootNodeId: item.rootNodeId, nodeIds: item.nodeIds.filter((id): id is string => typeof id === "string") }]
  })
}

/** Deterministic rooted clusters keep each paper and its neighborhood spatially distinct. */
export function rootDragFactors(data: GraphData, rootNodeId: string): Map<string, number> {
  const partitions = graphPartitions(data)
  const selected = partitions.find((partition) => partition.rootNodeId === rootNodeId)
  if (!selected) return new Map([[rootNodeId, 1]])
  const ownerCounts = new Map<string, number>()
  partitions.forEach((partition) => partition.nodeIds.forEach((nodeId) => ownerCounts.set(nodeId, (ownerCounts.get(nodeId) ?? 0) + 1)))
  return new Map(selected.nodeIds.map((nodeId) => [nodeId, nodeId === rootNodeId ? 1 : 1 / Math.max(1, ownerCounts.get(nodeId) ?? 1)]))
}

export function visibleRootDragFactors(data: GraphData, rootNodeId: string, visibleNodeIds: ReadonlySet<string>): Map<string, number> {
  return new Map([...rootDragFactors(data, rootNodeId)].filter(([nodeId]) => visibleNodeIds.has(nodeId)))
}

export function rootedGraphPositions(data: GraphData, clusterOffsets: ReadonlyMap<string, { x: number; y: number }> = new Map(), layoutStyle: GraphLayoutStyle = "snowflake"): Map<string, LayoutPosition> {
  const partitions = graphPartitions(data)
  const effectivePartitions = partitions.length ? partitions : [{
    recordId: data.recordId,
    rootNodeId: data.nodes.find((node) => node.type === "paper")?.id ?? data.nodes[0]?.id ?? "",
    nodeIds: data.nodes.map((node) => node.id)
  }]
  const columnCount = Math.max(1, Math.ceil(Math.sqrt(effectivePartitions.length)))
  const rowCount = Math.ceil(effectivePartitions.length / columnCount)
  const typeGroupedLayout = layoutStyle === "snowflake" || layoutStyle === "concentric"
  const spacingX = typeGroupedLayout ? 1100 : 680
  const spacingY = typeGroupedLayout ? 900 : 600
  const nodeById = new Map(data.nodes.map((node) => [node.id, node]))
  const centers = effectivePartitions.map((partition, index) => {
    const offset = clusterOffsets.get(partition.rootNodeId)
    return {
      x: (index % columnCount - (columnCount - 1) / 2) * spacingX + (offset?.x ?? 0),
      y: (Math.floor(index / columnCount) - (rowCount - 1) / 2) * spacingY + (offset?.y ?? 0)
    }
  })
  const owners = new Map<string, number[]>()
  effectivePartitions.forEach((partition, index) => partition.nodeIds.forEach((nodeId) => {
    const current = owners.get(nodeId) ?? []
    current.push(index)
    owners.set(nodeId, current)
  }))
  const positions = new Map<string, LayoutPosition>()
  effectivePartitions.forEach((partition, partitionIndex) => {
    const center = centers[partitionIndex] ?? { x: 0, y: 0 }
    const rootPosition = layoutStyle === "hierarchy" ? { x: center.x, y: center.y - 260 } : layoutStyle === "grid" ? { x: center.x - 225, y: center.y - 190 } : center
    if (partition.rootNodeId) positions.set(partition.rootNodeId, { ...rootPosition, role: "root" })
    const members = partition.nodeIds.filter((nodeId) => nodeId !== partition.rootNodeId && (owners.get(nodeId)?.length ?? 0) === 1).sort()
    const membersByType = new Map<string, string[]>()
    members.forEach((nodeId) => {
      const type = nodeById.get(nodeId)?.type ?? "unknown"
      membersByType.set(type, [...(membersByType.get(type) ?? []), nodeId])
    })
    const typeGroups = [...membersByType].sort(([left], [right]) => left.localeCompare(right))
    const typePlacement = new Map(typeGroups.flatMap(([type, nodeIds], typeIndex) => nodeIds.map((nodeId, itemIndex) => [nodeId, { type, typeIndex, itemIndex, count: nodeIds.length }] as const)))
    members.forEach((nodeId, index) => {
      if (layoutStyle === "hierarchy") {
        const columns = Math.min(6, Math.max(1, Math.ceil(Math.sqrt(members.length))))
        const row = Math.floor(index / columns)
        const column = index % columns
        const rowSize = Math.min(columns, members.length - row * columns)
        positions.set(nodeId, { x: center.x + (column - (rowSize - 1) / 2) * 145, y: rootPosition.y + 165 + row * 135, role: "member" })
      } else if (layoutStyle === "grid") {
        const columns = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(members.length + 1))))
        const slot = index + 1
        positions.set(nodeId, { x: rootPosition.x + (slot % columns) * 150, y: rootPosition.y + Math.floor(slot / columns) * 125, role: "member" })
      } else if (layoutStyle === "snowflake") {
        const placement = typePlacement.get(nodeId) ?? { typeIndex: 0, itemIndex: index, count: members.length }
        const angle = -Math.PI / 2 + (Math.PI * 2 * placement.typeIndex) / Math.max(1, typeGroups.length)
        const radius = 165 + placement.itemIndex * 115
        positions.set(nodeId, { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius, role: "member" })
      } else {
        const placement = typePlacement.get(nodeId) ?? { typeIndex: 0, itemIndex: index, count: members.length }
        const radius = 165 + placement.typeIndex * 125
        const angle = -Math.PI / 2 + placement.typeIndex * CONCENTRIC_TYPE_PHASE + placement.itemIndex * GOLDEN_ANGLE
        positions.set(nodeId, { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius, role: "member" })
      }
    })
  })
  const sharedIds = [...owners.entries()].filter(([, indices]) => indices.length > 1).map(([nodeId]) => nodeId).sort()
  sharedIds.forEach((nodeId, index) => {
    const ownerIndices = owners.get(nodeId) ?? []
    const center = ownerIndices.reduce((total, ownerIndex) => ({ x: total.x + (centers[ownerIndex]?.x ?? 0), y: total.y + (centers[ownerIndex]?.y ?? 0) }), { x: 0, y: 0 })
    const angle = (Math.PI * 2 * index) / Math.max(1, sharedIds.length)
    const radius = sharedIds.length > 1 ? 55 + Math.floor(index / 8) * 45 : 0
    positions.set(nodeId, { x: center.x / ownerIndices.length + Math.cos(angle) * radius, y: center.y / ownerIndices.length + Math.sin(angle) * radius, role: "shared" })
  })
  data.nodes.filter((node) => !positions.has(node.id)).forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, data.nodes.length)
    positions.set(node.id, { x: Math.cos(angle) * 320, y: Math.sin(angle) * 320, role: "member" })
  })
  return positions
}

export function toG6Data(data: GraphData, clusterOffsets?: ReadonlyMap<string, { x: number; y: number }>, layoutStyle?: GraphLayoutStyle): G6Data {
  const positions = rootedGraphPositions(data, clusterOffsets, layoutStyle)
  return {
    nodes: data.nodes.map((node) => {
      const position = positions.get(node.id)
      return {
        id: node.id,
        data: { ...node, businessType: node.type, layoutRole: position?.role },
        style: { fill: nodeColor(node.type), x: position?.x ?? 0, y: position?.y ?? 0 }
      }
    }),
    edges: data.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      data: { ...edge, businessType: edge.type }
    }))
  }
}

function mergeById<T extends { id: string }>(current: T[], additions: T[] = [], updates: T[] = [], removals: string[] = []): T[] {
  const removed = new Set(removals)
  const values = new Map(current.filter((item) => !removed.has(item.id)).map((item) => [item.id, item]))
  for (const item of [...additions, ...updates]) values.set(item.id, item)
  return [...values.values()]
}

export class G6GraphRenderer implements GraphRenderer {
  #graph?: Graph
  #data?: GraphData
  #filters: GraphFilters = DEFAULT_GRAPH_FILTERS
  #selection: GraphSelection = {}
  #renderRevision = 0
  #operations: Promise<void> = Promise.resolve()
  #destroyed = false
  #dragFactors = new Map<string, number>()
  #dragRootId = ""
  #clusterOffsets = new Map<string, { x: number; y: number }>()
  #layoutStyle: GraphLayoutStyle = "snowflake"

  constructor(private readonly events: GraphRendererEvents = {}) {}

  mount(container: HTMLElement): void {
    if (this.#graph) throw new Error("G6GraphRenderer is already mounted")
    const dark = globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false
    const palette = dark ? colors.dark : colors.light
    this.#graph = new Graph({
      container,
      autoResize: true,
      autoFit: "view",
      padding: 36,
      animation: false,
      data: { nodes: [], edges: [] },
      layout: { type: "preset" },
      behaviors: ["drag-canvas", "zoom-canvas"],
      node: {
        type: "circle",
        style: (datum) => {
          const business = datum.data ?? {}
          const metrics = business.metrics as Record<string, number> | undefined
          const importance = Number(metrics?.importance ?? 0.5)
          const layoutRole = String(business.layoutRole ?? "member")
          return {
            size: layoutRole === "root" ? 52 : layoutRole === "shared" ? 44 : 28 + Math.max(0, Math.min(1, importance)) * 18,
            fill: nodeColor(String(business.businessType ?? "")),
            stroke: palette.borderStrong,
            lineWidth: layoutRole === "root" ? 3 : 2,
            labelText: (this.#data?.nodes.length ?? 0) > 250 && importance < 0.98 ? "" : compactCanvasLabel(business.label ?? datum.id, layoutRole === "root" ? 64 : 42),
            labelFill: palette.text,
            labelFontSize: 11,
            labelPlacement: "bottom",
            labelOffsetY: 6,
            cursor: "pointer"
          }
        },
        state: {
          selected: { stroke: palette.accent, lineWidth: 4, shadowColor: palette.accent, shadowBlur: 14 },
          hover: { stroke: palette.warning, lineWidth: 3 }
        }
      },
      edge: {
        type: "line",
        style: { stroke: palette.textMuted, strokeOpacity: 0.55, lineWidth: 1.25, endArrow: true },
        state: { selected: { stroke: palette.accent, strokeOpacity: 1, lineWidth: 2.5 } }
      }
    })
    this.#graph.on(NodeEvent.CLICK, (event: IElementEvent) => this.events.onNodeSelect?.(String(event.target.id)))
    this.#graph.on(NodeEvent.POINTER_ENTER, (event: IElementEvent) => {
      const id = String(event.target.id)
      this.events.onNodeHover?.(id)
      void this.#graph?.setElementState(id, ["hover"], false)
    })
    this.#graph.on(NodeEvent.POINTER_LEAVE, (event: IElementEvent) => {
      const id = String(event.target.id)
      this.events.onNodeHover?.()
      void this.#graph?.setElementState(id, this.#selection.nodeId === id ? ["selected"] : [], false)
    })
    this.#graph.on(EdgeEvent.CLICK, (event: IElementEvent) => this.events.onEdgeSelect?.(String(event.target.id)))
    this.#graph.on(NodeEvent.DRAG_START, (event: IElementDragEvent) => this.#startNodeDrag(String(event.target.id)))
    this.#graph.on(NodeEvent.DRAG, (event: IElementDragEvent) => this.#moveNodeDrag(event))
    this.#graph.on(NodeEvent.DRAG_END, () => this.#endNodeDrag())
    const emitViewport = () => {
      const graph = this.#graph
      if (!graph) return
      const bounds = container.getBoundingClientRect()
      let scale = 1
      let panX = 0
      let panY = 0
      try {
        scale = graph.getZoom()
        const position = graph.getPosition()
        panX = Number(position[0] ?? 0)
        panY = Number(position[1] ?? 0)
      } catch {
        // G6 does not expose its camera until the first canvas render completes.
      }
      this.events.onViewportChange?.({
        width: Math.max(1, container.clientWidth || bounds.width || 960),
        height: Math.max(1, container.clientHeight || bounds.height || 640),
        scale,
        panX,
        panY
      })
    }
    this.#graph.on(GraphEvent.AFTER_TRANSFORM, emitViewport)
    this.#graph.on(GraphEvent.AFTER_SIZE_CHANGE, emitViewport)
    emitViewport()
    if (this.#data) this.#enqueue(() => this.#render())
  }

  setData(data: GraphData): void {
    this.#data = data
    if (this.#graph) this.#enqueue(() => this.#render())
  }

  updateData(change: GraphDataChange): void {
    if (!this.#data) return
    this.#data = {
      ...this.#data,
      nodes: mergeById(this.#data.nodes, change.addNodes, change.updateNodes, change.removeNodeIds),
      edges: mergeById(this.#data.edges, change.addEdges, change.updateEdges, change.removeEdgeIds)
    }
    if (this.#graph) this.#enqueue(() => this.#render())
  }

  setSelection(selection: GraphSelection): void {
    this.#selection = selection
    if (this.#graph) this.#enqueue(() => this.#applySelection())
  }

  setFilters(filters: GraphFilters): void {
    this.#filters = filters
    if (this.#graph && this.#data) this.#enqueue(() => this.#render())
  }

  setLayoutStyle(style: GraphLayoutStyle): void {
    if (style === this.#layoutStyle) return
    this.#layoutStyle = style
    this.#clusterOffsets.clear()
    if (this.#graph && this.#data) this.#enqueue(async () => {
      await this.#render()
      await this.#graph?.fitView({ when: "always", direction: "both" }, { duration: 180 })
    })
  }

  setViewport(viewport: GraphViewport): void {
    this.#enqueue(async () => {
      if (!this.#graph) return
      await this.#graph.zoomTo(Math.max(0.05, viewport.scale), false)
      const position = this.#graph.getPosition()
      const zoom = this.#graph.getZoom()
      await this.#graph.translateBy([(viewport.panX - Number(position[0] ?? 0)) * zoom, (viewport.panY - Number(position[1] ?? 0)) * zoom], false)
      await new Promise<void>((resolve) => {
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => resolve())
        else queueMicrotask(resolve)
      })
      if (!this.#graph) return
      const settled = this.#graph.getPosition()
      const deltaX = viewport.panX - Number(settled[0] ?? 0)
      const deltaY = viewport.panY - Number(settled[1] ?? 0)
      if (Math.abs(deltaX) > 0.01 || Math.abs(deltaY) > 0.01) {
        const settledZoom = this.#graph.getZoom()
        await this.#graph.translateBy([deltaX * settledZoom, deltaY * settledZoom], false)
      }
    })
  }

  focusNode(nodeId: string): void { this.#enqueue(async () => { await this.#graph?.focusElement(nodeId, { duration: 180 }) }) }
  fitView(_options: FitViewOptions = {}): void { this.#enqueue(async () => { await this.#graph?.fitView({ when: "always", direction: "both" }, { duration: 180 }) }) }

  async exportImage(_options: ExportOptions = {}): Promise<Blob> {
    if (!this.#graph) throw new Error("Graph renderer is not mounted")
    await this.#operations
    if (!this.#graph) throw new Error("Graph renderer was destroyed")
    const dataUrl = await this.#graph.toDataURL({ mode: "overall", type: "image/png" })
    return dataUrlToBlob(dataUrl)
  }

  destroy(): void {
    if (this.#destroyed) return
    this.#destroyed = true
    this.#renderRevision += 1
    const graph = this.#graph
    this.#graph = undefined
    void this.#operations.finally(() => {
      if (graph && !graph.destroyed) graph.destroy()
    })
  }

  #enqueue(operation: () => Promise<void>): void {
    this.#operations = this.#operations.then(async () => {
      if (!this.#destroyed && this.#graph) await operation()
    })
  }

  async #render(): Promise<void> {
    if (!this.#graph || !this.#data) return
    const started = globalThis.performance?.now() ?? Date.now()
    const revision = ++this.#renderRevision
    const visible = filterGraphData(this.#data, this.#filters)
    this.#graph.setData(toG6Data(visible, this.#clusterOffsets, this.#layoutStyle))
    await this.#graph.render()
    if (revision === this.#renderRevision) {
      await this.#applySelection()
      const finished = globalThis.performance?.now() ?? Date.now()
      this.events.onRenderComplete?.({ durationMs: Math.max(0, finished - started), completedAtMs: finished, nodeCount: visible.nodes.length, edgeCount: visible.edges.length })
    }
  }

  async #applySelection(): Promise<void> {
    if (!this.#graph) return
    const data = this.#graph.getData()
    const states: Record<string, string[]> = {}
    for (const node of data.nodes ?? []) states[String(node.id)] = node.id === this.#selection.nodeId ? ["selected"] : []
    for (const edge of data.edges ?? []) states[String(edge.id)] = edge.id === this.#selection.edgeId ? ["selected"] : []
    await this.#graph.setElementState(states, false)
  }

  #startNodeDrag(nodeId: string): void {
    if (!this.#data || !this.#graph) return
    const visibleNodeIds = new Set((this.#graph.getData().nodes ?? []).map((node) => String(node.id)))
    this.#dragFactors = visibleRootDragFactors(this.#data, nodeId, visibleNodeIds)
    this.#dragRootId = this.#dragFactors.size > 1 ? nodeId : ""
  }

  #moveNodeDrag(event: IElementDragEvent): void {
    const graph = this.#graph
    if (!graph || this.#dragFactors.size === 0) return
    const zoom = Math.max(0.05, graph.getZoom())
    const dx = event.dx / zoom
    const dy = event.dy / zoom
    const offsets = Object.fromEntries([...this.#dragFactors].map(([nodeId, factor]) => [nodeId, [dx * factor, dy * factor] as Point]))
    void graph.translateElementBy(offsets, false)
    if (this.#dragRootId) {
      const current = this.#clusterOffsets.get(this.#dragRootId) ?? { x: 0, y: 0 }
      this.#clusterOffsets.set(this.#dragRootId, { x: current.x + dx, y: current.y + dy })
    }
  }

  #endNodeDrag(): void {
    this.#dragFactors.clear()
    this.#dragRootId = ""
  }
}
