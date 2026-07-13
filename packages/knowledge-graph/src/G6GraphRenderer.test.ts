import { describe, expect, it } from "vitest"
import type { GraphData } from "@omnilit/shared-schema"
import { rootDragFactors, rootedGraphPositions, toG6Data, visibleRootDragFactors } from "./G6GraphRenderer"

describe("rooted graph layout", () => {
  it("separates paper roots and places shared nodes between their clusters", () => {
    const data: GraphData = {
      protocolVersion: "1.0", schemaVersion: 1, recordId: "multi-selection", metadata: {
        graphPartitions: [
          { recordId: "one", rootNodeId: "paper:one", nodeIds: ["paper:one", "result:one", "result:one-b", "author:one", "topic:shared"] },
          { recordId: "two", rootNodeId: "paper:two", nodeIds: ["paper:two", "result:two", "topic:shared"] }
        ]
      },
      nodes: [
        { id: "paper:one", type: "paper", label: "One", attributes: {} },
        { id: "result:one", type: "result", label: "One result", attributes: {} },
        { id: "result:one-b", type: "result", label: "Another result", attributes: {} },
        { id: "author:one", type: "author", label: "Author One", attributes: {} },
        { id: "paper:two", type: "paper", label: "Two", attributes: {} },
        { id: "result:two", type: "result", label: "Two result", attributes: {} },
        { id: "topic:shared", type: "topic", label: "Shared", attributes: {} }
      ],
      edges: []
    }
    const positions = rootedGraphPositions(data)
    const firstRoot = positions.get("paper:one")
    const secondRoot = positions.get("paper:two")
    const shared = positions.get("topic:shared")
    expect(firstRoot?.role).toBe("root")
    expect(secondRoot?.role).toBe("root")
    expect(Math.abs((secondRoot?.x ?? 0) - (firstRoot?.x ?? 0))).toBeGreaterThanOrEqual(600)
    expect(shared).toMatchObject({ role: "shared", x: 0, y: 0 })
    expect(Math.abs((positions.get("result:one")?.x ?? 0) - (firstRoot?.x ?? 0))).toBeLessThan(250)
    expect(Math.abs((positions.get("result:two")?.x ?? 0) - (secondRoot?.x ?? 0))).toBeLessThan(250)
    const rendered = toG6Data(data)
    expect(rendered.nodes?.find((node) => node.id === "paper:one")?.data?.layoutRole).toBe("root")
    expect(rendered.nodes?.find((node) => node.id === "topic:shared")?.data?.layoutRole).toBe("shared")
    expect([...rootDragFactors(data, "paper:one")]).toEqual([
      ["paper:one", 1], ["result:one", 1], ["result:one-b", 1], ["author:one", 1], ["topic:shared", 0.5]
    ])
    expect([...visibleRootDragFactors(data, "paper:one", new Set(["paper:one", "topic:shared"]))]).toEqual([
      ["paper:one", 1], ["topic:shared", 0.5]
    ])
    const moved = rootedGraphPositions(data, new Map([["paper:one", { x: 100, y: 40 }]]))
    expect(moved.get("paper:one")?.x).toBe((firstRoot?.x ?? 0) + 100)
    expect(moved.get("result:one")?.x).toBe((positions.get("result:one")?.x ?? 0) + 100)
    expect(moved.get("topic:shared")?.x).toBe((shared?.x ?? 0) + 50)
    const hierarchy = rootedGraphPositions(data, new Map(), "hierarchy")
    const grid = rootedGraphPositions(data, new Map(), "grid")
    const concentric = rootedGraphPositions(data, new Map(), "concentric")
    expect(hierarchy.get("paper:one")?.y).not.toBe(firstRoot?.y)
    expect(grid.get("paper:one")?.x).not.toBe(firstRoot?.x)
    const rootX = firstRoot?.x ?? 0
    const rootY = firstRoot?.y ?? 0
    const resultA = positions.get("result:one")
    const resultB = positions.get("result:one-b")
    expect(((resultA?.x ?? 0) - rootX) * ((resultB?.y ?? 0) - rootY) - ((resultA?.y ?? 0) - rootY) * ((resultB?.x ?? 0) - rootX)).toBeCloseTo(0, 6)
    const radius = (point: { x: number; y: number } | undefined) => Math.hypot((point?.x ?? 0) - rootX, (point?.y ?? 0) - rootY)
    expect(radius(concentric.get("result:one"))).toBeCloseTo(radius(concentric.get("result:one-b")), 6)
    expect(radius(concentric.get("author:one"))).not.toBeCloseTo(radius(concentric.get("result:one")), 6)
    const angle = (point: { x: number; y: number } | undefined) => Math.atan2((point?.y ?? 0) - rootY, (point?.x ?? 0) - rootX)
    const rawAngleDifference = Math.abs(angle(concentric.get("result:one")) - angle(concentric.get("result:one-b")))
    const angleDifference = Math.min(rawAngleDifference, Math.PI * 2 - rawAngleDifference)
    expect(Math.abs(angleDifference - Math.PI)).toBeGreaterThan(0.2)
  })
})
