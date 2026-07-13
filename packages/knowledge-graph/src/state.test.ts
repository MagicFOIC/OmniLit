import { describe, expect, it } from "vitest"
import type { GraphData, GraphNode, GraphTimeline, GraphViewRestore } from "@omnilit/shared-schema"
import fixtureJson from "@omnilit/shared-schema/fixtures/shared-graph-v1.json"
import timelineJson from "@omnilit/shared-schema/fixtures/shared-timeline-v1.json"
import { createKnowledgeGraphState, filterGraphData, knowledgeGraphReducer, nodeTypeCounts } from "./state"
import { toG6Data } from "./G6GraphRenderer"

const fixture = fixtureJson as GraphData

function makeGraph(size: number): GraphData {
  const nodes: GraphNode[] = Array.from({ length: size }, (_, index) => ({
    id: `node-${index}`,
    type: index % 2 === 0 ? "paper" : "method",
    label: `Node ${index}`,
    attributes: {},
    metrics: { confidence: 1, importance: index / Math.max(1, size) }
  }))
  return {
    protocolVersion: "1.0", schemaVersion: 1, recordId: `scale-${size}`, metadata: {}, nodes,
    edges: Array.from({ length: Math.max(0, size - 1) }, (_, index) => ({
      id: `edge-${index}`, source: `node-${index}`, target: `node-${index + 1}`, type: "USES_METHOD", directed: true, attributes: {}
    }))
  }
}

describe("knowledge graph state", () => {
  it("uses the authoritative fixture and preserves graph counts", () => {
    expect(fixture.nodes).toHaveLength(6)
    expect(fixture.edges).toHaveLength(5)
    expect(nodeTypeCounts(fixture)).toEqual([
      { type: "author", count: 1 }, { type: "citation", count: 1 }, { type: "dataset", count: 1 }, { type: "method", count: 1 },
      { type: "paper", count: 1 }, { type: "result", count: 1 }
    ])
  })

  it("merges progressive pages by id without duplicating nodes or edges", () => {
    const initial = { ...fixture, nodes: fixture.nodes.slice(0, 1), edges: [] }
    let state = createKnowledgeGraphState(initial)
    state = knowledgeGraphReducer(state, { type: "merge-data", nodes: fixture.nodes, edges: fixture.edges })
    state = knowledgeGraphReducer(state, { type: "merge-data", nodes: fixture.nodes, edges: fixture.edges })
    expect(state.data.nodes).toHaveLength(6)
    expect(state.data.edges).toHaveLength(5)
  })

  it("replaces render data with a server projection while preserving projection diagnostics", () => {
    let state = createKnowledgeGraphState(fixture)
    state = knowledgeGraphReducer(state, { type: "projection-loading", density: "overview" })
    expect(state.projection).toMatchObject({ status: "loading", density: "overview" })
    const projected = { ...fixture, nodes: fixture.nodes.slice(0, 2), edges: fixture.edges.slice(0, 1) }
    state = knowledgeGraphReducer(state, {
      type: "projection-result", density: "overview", data: projected,
      summary: { status: "ready", level: "overview", budget: 240, totalSemanticNodes: 1_000, renderedNodes: 2, realNodes: 1, aggregateNodes: 1, aggregatedNodes: 999, culledNodes: 0, renderedEdges: 1, totalSemanticEdges: 999, degraded: true, latencyMs: 12, latencyBudgetMs: 120, budgetExceeded: false, performanceStatus: "ready", message: "overview" }
    })
    expect(state.data.nodes).toHaveLength(2)
    expect(state.projection.summary?.aggregatedNodes).toBe(999)
  })

  it("replaces the graph and preserves timeline diagnostics for a playback window", () => {
    const timeline = timelineJson as GraphTimeline
    let state = knowledgeGraphReducer(createKnowledgeGraphState(fixture), { type: "timeline-loading" })
    expect(state.timeline.status).toBe("loading")
    state = knowledgeGraphReducer(state, { type: "timeline-result", data: timeline })
    expect(state.data.recordId).toBe("timeline:demo-timeline")
    expect(state.timeline.data?.selection.effectiveEndYear).toBe(2024)
    expect(state.timeline.data?.keyPaths[0]?.length).toBe(3)
  })

  it("restores graph data, filters, selection, and density from a shared saved view", () => {
    const result: GraphViewRestore = {
      protocolVersion: "1.0", recordId: fixture.recordId, graph: fixture, reconciliation: { missingNodes: 0, missingEdges: 0 },
      view: {
        protocolVersion: "1.0", version: 2, id: "view-1", name: "Authors", recordId: fixture.recordId,
        createdAt: "2026-07-13T00:00:00Z", updatedAt: "2026-07-13T00:00:00Z", graphFingerprint: "fixture",
        exploration: { nodeIds: fixture.nodes.map((node) => node.id), edgeIds: fixture.edges.map((edge) => edge.id), pages: {} },
        filters: { mode: "authors", searchText: "Ada", density: "detail", literatureSortKey: "relevance", literatureSortDescending: true, facets: {}, nodeTypes: ["author"], needsReviewOnly: false },
        selection: { nodeId: "author:ada-example", edgeId: "" }, path: { startId: "", endId: "", directed: false, relationFilter: "ALL" },
        viewport: { displayStyle: "academic", focusDepth: 0, reviewMode: false, graphScale: 1.5, panX: 20, panY: -10, showArrows: true, showLabels: true, dimUnrelated: true, textFadeThreshold: 1.15, nodeSizeScale: 1, linkThickness: 1, animateLayout: false }
      }
    }
    const state = knowledgeGraphReducer(createKnowledgeGraphState({ ...fixture, nodes: fixture.nodes.slice(0, 1), edges: [] }), { type: "restore-view", result })
    expect(state.filters).toEqual({ query: "Ada", nodeTypes: ["author"], needsReviewOnly: false })
    expect(state.selection.nodeId).toBe("author:ada-example")
    expect(state.projection.density).toBe("detail")
  })

  it("filters nodes and only retains edges with two visible endpoints", () => {
    const result = filterGraphData(fixture, { query: "", nodeTypes: ["paper", "method"], needsReviewOnly: false })
    expect(result.nodes.map((node) => node.type).sort()).toEqual(["method", "paper"])
    expect(result.edges.map((edge) => edge.type)).toEqual(["USES_METHOD"])
    expect(filterGraphData(fixture, { query: "ada", nodeTypes: [], needsReviewOnly: false }).nodes[0]?.id).toBe("author:ada-example")
  })

  it("keeps selection centralized and clears it when filters hide the node", () => {
    let state = createKnowledgeGraphState(fixture)
    state = knowledgeGraphReducer(state, { type: "select-node", nodeId: "author:ada-example" })
    expect(state.selection.nodeId).toBe("author:ada-example")
    state = knowledgeGraphReducer(state, { type: "toggle-node-type", nodeType: "paper" })
    expect(state.selection).toEqual({})
  })

  it("maps business DTOs into G6 data without changing the shared protocol", () => {
    const mapped = toG6Data(fixture)
    expect(mapped.nodes?.[0]?.id).toBe(fixture.nodes[0]?.id)
    expect(mapped.nodes?.[0]?.data?.businessType).toBe("paper")
    expect(mapped.edges?.[0]?.data?.businessType).toBe("USES_METHOD")
    expect(fixture.nodes[0]?.attributes).toEqual({ recordId: "paper-001" })
  })

  for (const size of [100, 1_000, 5_000, 10_000]) {
    it(`filters ${size.toLocaleString()} nodes within the state baseline`, () => {
      const graph = makeGraph(size)
      const started = performance.now()
      const result = filterGraphData(graph, { query: "node", nodeTypes: ["paper"], needsReviewOnly: false })
      const elapsed = performance.now() - started
      expect(result.nodes).toHaveLength(Math.ceil(size / 2))
      expect(elapsed).toBeLessThan(500)
    })
  }
})
