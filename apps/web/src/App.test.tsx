import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import type { GraphData } from "@omnilit/shared-schema"
import { App, combineGraphs, mergeCachedGraph } from "./App"

describe("OmniLit web shell", () => {
  it("merges selected graphs and de-duplicates shared nodes and edges", () => {
    const first: GraphData = { protocolVersion: "1.0", schemaVersion: 1, recordId: "one", nodes: [{ id: "paper:one", type: "paper", label: "One", attributes: {} }, { id: "author:shared", type: "author", label: "Shared", attributes: {} }], edges: [{ id: "edge:one", source: "author:shared", target: "paper:one", type: "authored", directed: true, attributes: {} }], metadata: {} }
    const second: GraphData = { protocolVersion: "1.0", schemaVersion: 1, recordId: "two", nodes: [{ id: "paper:two", type: "paper", label: "Two", attributes: {} }, { id: "author:shared", type: "author", label: "Shared", attributes: {} }], edges: [{ id: "edge:two", source: "author:shared", target: "paper:two", type: "authored", directed: true, attributes: {} }], metadata: {} }
    const merged = combineGraphs(["one", "two"], { one: first, two: second })
    expect(merged.recordId).toBe("multi-selection")
    expect(merged.nodes.map((node) => node.id)).toEqual(["paper:one", "author:shared", "paper:two"])
    expect(merged.edges).toHaveLength(2)
    expect(merged.metadata.selectedRecordIds).toEqual(["one", "two"])
    expect(merged.metadata.graphPartitions).toEqual([
      { recordId: "one", rootNodeId: "paper:one", nodeIds: ["paper:one", "author:shared"], edgeIds: ["edge:one"] },
      { recordId: "two", rootNodeId: "paper:two", nodeIds: ["paper:two", "author:shared"], edgeIds: ["edge:two"] }
    ])
  })

  it("preserves expanded neighbors when another graph is added", () => {
    const first: GraphData = { protocolVersion: "1.0", schemaVersion: 1, recordId: "one", nodes: [{ id: "paper:one", type: "paper", label: "One", attributes: {} }], edges: [], metadata: {} }
    const second: GraphData = { protocolVersion: "1.0", schemaVersion: 1, recordId: "two", nodes: [{ id: "paper:two", type: "paper", label: "Two", attributes: {} }], edges: [], metadata: {} }
    const expanded = mergeCachedGraph(first, [{ id: "author:one", type: "author", label: "Author", attributes: {} }], [{ id: "edge:author", source: "author:one", target: "paper:one", type: "authored", directed: true, attributes: {} }])
    const merged = combineGraphs(["one", "two"], { one: expanded, two: second })
    expect(merged.nodes.map((node) => node.id)).toEqual(["paper:one", "author:one", "paper:two"])
    expect(merged.edges.map((edge) => edge.id)).toEqual(["edge:author"])
  })

  it("renders navigation and a loading state without Qt", () => {
    const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/graph"]}><App /></MemoryRouter>)
    expect(html).toContain("OmniLit")
    expect(html).toContain("知识图谱")
    expect(html).toContain("研究工作空间")
    expect(html).toContain("统计分析")
    expect(html).toContain("AI 工作区")
    expect(html).toContain("业务设置")
    expect(html).toContain("正在加载知识图谱")
    expect(html).not.toContain("window.qt")
  })

  it("routes to the explicit browser capability page", () => {
    const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/about"]}><App /></MemoryRouter>)
    expect(html).toContain("普通浏览器运行")
    expect(html).toContain("明确能力边界")
  })
})
