import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { GraphData } from "@omnilit/shared-schema"
import fixtureJson from "@omnilit/shared-schema/fixtures/shared-graph-v1.json"
import { GraphCanvas } from "./GraphCanvas"

describe("GraphCanvas accessibility", () => {
  it("announces filtered counts rather than the unfiltered semantic graph", () => {
    const html = renderToStaticMarkup(<GraphCanvas
      data={fixtureJson as GraphData}
      filters={{ query: "Ada", nodeTypes: [], needsReviewOnly: false }}
      selection={{}}
      onNodeSelect={() => undefined}
      onEdgeSelect={() => undefined}
    />)
    expect(html).toContain('aria-label="1 个节点、0 条关系的知识图谱"')
  })
})
