import type { GraphData, GraphNode } from "@omnilit/shared-schema"

export function createGraphBenchmark(size: number): GraphData {
  const count = Math.max(1, Math.min(10_000, Math.trunc(size)))
  const nodes: GraphNode[] = Array.from({ length: count }, (_, index) => ({
    id: `benchmark:${index}`,
    type: index === 0 ? "paper" : index % 5 === 0 ? "citation" : index % 3 === 0 ? "author" : "topic",
    label: index === 0 ? `${count.toLocaleString()} node browser benchmark` : `Benchmark node ${index}`,
    attributes: { benchmark: true },
    metrics: { importance: 1 - index / count, confidence: 1 }
  }))
  return {
    protocolVersion: "1.0",
    schemaVersion: 1,
    recordId: `benchmark-${count}`,
    nodes,
    edges: Array.from({ length: count - 1 }, (_, index) => ({
      id: `benchmark-edge:${index}`,
      source: "benchmark:0",
      target: `benchmark:${index + 1}`,
      type: "MENTIONS",
      directed: true,
      attributes: {}
    })),
    metadata: { benchmark: true, count }
  }
}
