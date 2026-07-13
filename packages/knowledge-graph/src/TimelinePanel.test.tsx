import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { GraphTimeline } from "@omnilit/shared-schema"
import timelineJson from "@omnilit/shared-schema/fixtures/shared-timeline-v1.json"
import { nextTimelinePlaybackYear, TimelinePanel } from "./TimelinePanel"

describe("TimelinePanel", () => {
  it("advances playback only through known years inside the selected range", () => {
    expect(nextTimelinePlaybackYear([2020, 2022, 2024], 2020, 2024)).toBe(2022)
    expect(nextTimelinePlaybackYear([2020, 2022, 2024], 2022, 2024)).toBe(2024)
    expect(nextTimelinePlaybackYear([2020, 2022, 2024], 2024, 2024)).toBeUndefined()
  })
  it("renders chronological papers, milestones, key paths, and speed comparisons", () => {
    const html = renderToStaticMarkup(<TimelinePanel
      timeline={{ status: "ready", data: timelineJson as GraphTimeline }}
      onQuery={() => undefined}
      onRetry={() => undefined}
      onCancel={() => undefined}
      onSelectPaper={() => undefined}
    />)
    expect(html).toContain("知识演化时间轴")
    expect(html).toContain("Graph Foundations")
    expect(html).toContain("Local Agent 成为跨主题桥梁")
    expect(html).toContain("共享架构到 Local Agent")
    expect(html).toContain("Local Agent 主题增长速度更快")
  })

  it("exposes explicit loading, cancellation, and error recovery states", () => {
    const loading = renderToStaticMarkup(<TimelinePanel timeline={{ status: "loading" }} onQuery={() => undefined} onRetry={() => undefined} onCancel={() => undefined} onSelectPaper={() => undefined} />)
    const error = renderToStaticMarkup(<TimelinePanel timeline={{ status: "error", message: "cache unavailable" }} onQuery={() => undefined} onRetry={() => undefined} onCancel={() => undefined} onSelectPaper={() => undefined} />)
    expect(loading).toContain("取消更新")
    expect(error).toContain("cache unavailable")
    expect(error).toContain("重试")
  })
})
