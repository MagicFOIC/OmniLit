import { describe, expect, it } from "vitest"
import { createGraphBenchmark } from "./benchmark"

describe("graph browser benchmark fixture", () => {
  it("creates a deterministic 1k star graph without service dependencies", () => {
    const graph = createGraphBenchmark(1_000)
    expect(graph.nodes).toHaveLength(1_000)
    expect(graph.edges).toHaveLength(999)
    expect(new Set(graph.nodes.map((node) => node.id)).size).toBe(1_000)
    expect(graph.edges.every((edge) => edge.source === "benchmark:0")).toBe(true)
  })
})
