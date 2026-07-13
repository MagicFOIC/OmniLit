import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { GraphViewSaveRequest } from "@omnilit/shared-schema"
import { SavedViewsPanel, type SavedViewsDataSource } from "./SavedViewsPanel"

const dataSource: SavedViewsDataSource = {
  listViews: async () => ({ protocolVersion: "1.0", recordId: "paper-001", views: [] }),
  saveView: async () => { throw new Error("not used during SSR") },
  restoreView: async () => { throw new Error("not used during SSR") },
  deleteView: async () => undefined
}

const createView = (name: string): GraphViewSaveRequest => ({
  protocolVersion: "1.0", name, exploration: { nodeIds: [], edgeIds: [], pages: {} },
  filters: { mode: "all", searchText: "", density: "normal", literatureSortKey: "relevance", literatureSortDescending: true, facets: {}, nodeTypes: [], needsReviewOnly: false },
  selection: { nodeId: "", edgeId: "" },
  viewport: { displayStyle: "academic", focusDepth: 0, reviewMode: false, graphScale: 1, panX: 0, panY: 0, showArrows: true, showLabels: true, dimUnrelated: true, textFadeThreshold: 1.15, nodeSizeScale: 1, linkThickness: 1, animateLayout: false }
})

describe("SavedViewsPanel", () => {
  it("renders an accessible named save form and loading state", () => {
    const html = renderToStaticMarkup(<SavedViewsPanel recordId="paper-001" dataSource={dataSource} createView={createView} onRestore={() => undefined} layoutStyle="snowflake" onLayoutStyleChange={() => undefined} />)
    expect(html).toContain("图谱视图与布局")
    expect(html).toContain("雪花式")
    expect(html).toContain("分层树")
    expect(html).toContain("同心圆")
    expect(html).toContain("网格")
    expect(html).toContain("视图名称")
    expect(html).toContain("正在读取保存的视图")
  })
})
