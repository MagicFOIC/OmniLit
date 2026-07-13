import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { GraphData } from "@omnilit/shared-schema"
import fixtureJson from "@omnilit/shared-schema/fixtures/shared-graph-v1.json"
import timelineJson from "@omnilit/shared-schema/fixtures/shared-timeline-v1.json"
import { KnowledgeGraphPage, projectionViewport } from "./KnowledgeGraphPage"

describe("KnowledgeGraphPage", () => {
  it("projects relative to the live renderer viewport", () => {
    expect(projectionViewport({ width: 1280, height: 720, scale: 1.5, panX: 42, panY: -18 }, "overview")).toEqual({
      width: 1280, height: 720, scale: 0.75, panX: 42, panY: -18, overscan: 120
    })
    expect(projectionViewport({ width: 1280, height: 720, scale: 1.5, panX: 42, panY: -18 }, "detail").scale).toBe(3)
  })

  it("renders the graph summary, legend filters, accessible list, and detail prompt", () => {
    const html = renderToStaticMarkup(<KnowledgeGraphPage data={fixtureJson as GraphData} graphOptions={[{ recordId: "paper-001", title: "Contract-First Knowledge Graphs", nodeCount: 6, edgeCount: 5 }]} selectedGraphIds={["paper-001"]} onGraphToggle={() => undefined} />)
    expect(html).toContain("6</strong> 节点")
    expect(html).toContain("5</strong> 关系")
    expect(html).toContain("节点思维导图")
    expect(html).toContain("选择加入画布的文献")
    expect(html).toContain("筛选文献")
    expect(html).toContain("每行显示")
    expect(html).toContain("Contract-First Knowledge Graphs")
    expect(html).toContain("6 节点 · 5 关系")
    expect(html).toContain("已加入画布")
    expect(html).toContain("Ada Example")
    expect(html).toContain("选择画布、节点列表或文献列表中的条目")
    expect(html).toContain("data-testid=\"graph-canvas\"")
  })

  it("starts with no local graph added to the canvas", () => {
    const empty = { ...(fixtureJson as GraphData), recordId: "multi-selection", nodes: [], edges: [] }
    const html = renderToStaticMarkup(<KnowledgeGraphPage data={empty} graphOptions={[{ recordId: "paper-001", title: "Paper", nodeCount: 6, edgeCount: 5 }]} selectedGraphIds={[]} onGraphToggle={() => undefined} />)
    expect(html).toContain("已选择 0 篇")
    expect(html).toContain("尚未向画布添加文献")
    expect(html).toContain("点击加入画布")
  })

  it("windows the accessible node list for large graphs", () => {
    const base = fixtureJson as GraphData
    const large: GraphData = {
      ...base,
      recordId: "large-list",
      nodes: Array.from({ length: 150 }, (_, index) => ({ id: `node-${index}`, type: "topic", label: `Node ${index}`, attributes: {} })),
      edges: []
    }
    const html = renderToStaticMarkup(<KnowledgeGraphPage data={large} />)
    expect(html).toContain("显示 100 / 150")
    expect(html).toContain("再显示 50 个节点")
    expect(html).toContain("Node 99")
    expect(html).not.toContain("Node 100")
  })

  it("does not expose single-paper saved views while a timeline graph is active", () => {
    const timeline = timelineJson as { graph: GraphData }
    const html = renderToStaticMarkup(<KnowledgeGraphPage data={timeline.graph} dataSource={{
      expandNeighbors: async () => { throw new Error("unused") },
      loadLiterature: async () => ({ protocolVersion: "1.0", recordId: "timeline", rows: [], offset: 0, nextOffset: 0, total: 0, hasMore: false }),
      savedViews: {
        listViews: async () => ({ protocolVersion: "1.0", recordId: "timeline", views: [] }),
        saveView: async () => { throw new Error("unused") }, restoreView: async () => { throw new Error("unused") }, deleteView: async () => { throw new Error("unused") }
      },
      collaboration: {
        getSnapshot: async () => ({ protocolVersion: "1.0", recordId: "timeline", revision: 0, canEdit: true, syncEnabled: true, annotations: [] }),
        mutate: async () => { throw new Error("unused") }, subscribe: async () => 0
      }
    }} />)
    expect(html).not.toContain("保存的图谱视图")
    expect(html).not.toContain("共享批注")
  })

  it("mounts collaboration in the real single-graph entry when a cloud data source exists", () => {
    const html = renderToStaticMarkup(<KnowledgeGraphPage data={fixtureJson as GraphData} dataSource={{
      expandNeighbors: async () => { throw new Error("unused") },
      loadLiterature: async () => ({ protocolVersion: "1.0", recordId: "paper-001", rows: [], offset: 0, nextOffset: 0, total: 0, hasMore: false }),
      collaboration: {
        getSnapshot: async () => ({ protocolVersion: "1.0", recordId: "paper-001", revision: 0, canEdit: true, syncEnabled: true, annotations: [] }),
        mutate: async () => { throw new Error("unused") }, subscribe: async () => 0
      }
    }} />)
    expect(html).toContain("共享批注")
  })
})
