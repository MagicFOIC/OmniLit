import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { GraphData, LiteratureRow } from "@omnilit/shared-schema"
import { CitationNetwork, buildCitationNetwork } from "./CitationNetwork"

describe("CitationNetwork", () => {
  it("draws only real citation relationships between literature nodes", () => {
    const rows = [
      { nodeId: "paper:one", recordId: "one", kind: "paper", title: "One" },
      { nodeId: "paper:two", recordId: "two", kind: "paper", title: "Two" }
    ] as LiteratureRow[]
    const data = { protocolVersion: "1.0", schemaVersion: 1, recordId: "multi", metadata: {}, nodes: [], edges: [
      { id: "citation", source: "paper:one", target: "paper:two", type: "cites", directed: true, attributes: {} },
      { id: "unrelated", source: "paper:one", target: "paper:two", type: "same_topic", directed: false, attributes: {} }
    ] } as GraphData
    expect(buildCitationNetwork(data, rows).links.map((link) => link.id)).toEqual(["citation"])
    const html = renderToStaticMarkup(<CitationNetwork data={data} rows={rows} loading={false} error="" onSelect={() => undefined} />)
    expect(html).toContain("引用关系网络")
    expect(html).toContain("marker-end=\"url(#kg-citation-arrow)\"")
    expect(html).toContain("2 篇文献、1 条引用关系")
  })
})
