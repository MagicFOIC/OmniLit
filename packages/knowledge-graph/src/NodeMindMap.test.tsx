import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { GraphData } from "@omnilit/shared-schema"
import { NodeMindMap, buildMindMapBranches } from "./NodeMindMap"

describe("NodeMindMap", () => {
  const data: GraphData = {
    protocolVersion: "1.0", schemaVersion: 1, recordId: "multi-selection", metadata: { graphPartitions: [
      { recordId: "one", rootNodeId: "paper:one", nodeIds: ["paper:one", "result:one", "topic:shared"] },
      { recordId: "two", rootNodeId: "paper:two", nodeIds: ["paper:two", "topic:shared"] }
    ] },
    nodes: [
      { id: "paper:one", type: "paper", label: "Paper One", attributes: {} },
      { id: "result:one", type: "result", label: "Result One", attributes: {} },
      { id: "paper:two", type: "paper", label: "Paper Two", attributes: {} },
      { id: "topic:shared", type: "topic", label: "Shared Topic", attributes: {} }
    ], edges: []
  }

  it("groups neighbors under paper roots and marks intersections", () => {
    const branches = buildMindMapBranches(data, data.nodes)
    expect(branches).toHaveLength(2)
    expect(branches[0]?.groups.map((group) => group.label)).toEqual(["结果", "文献交集"])
    const html = renderToStaticMarkup(<NodeMindMap data={data} nodes={data.nodes} totalCount={data.nodes.length} onSelect={() => undefined} />)
    expect(html).toContain("节点思维导图")
    expect(html).toContain("Paper One")
    expect(html).toContain("文献交集")
    expect(html).toContain("Shared Topic")
    expect(html).toContain("XMind 式结构视图")
    expect(html).toContain("aria-expanded=\"true\"")
    expect(html).not.toContain("拖动画布节点可移动整簇")
  })
})
