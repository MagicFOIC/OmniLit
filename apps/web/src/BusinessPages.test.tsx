import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { MockPlatformBridge } from "@omnilit/platform-bridge"
import { AIWorkspacePage } from "./AIWorkspacePage"
import { BusinessSettingsPage } from "./BusinessSettingsPage"
import { ResearchWorkspacePage } from "./ResearchWorkspacePage"
import { StatisticsPage } from "./StatisticsPage"

const client = new ApiClient({ baseUrl: "https://fixture.invalid", retries: 0, transport: createFixtureTransport({}) })
const bridge = new MockPlatformBridge()

describe("shared research business pages", () => {
  it("renders the research comparison loading boundary", () => {
    const html = renderToStaticMarkup(<MemoryRouter><ResearchWorkspacePage client={client} bridge={bridge} /></MemoryRouter>)
    expect(html).toContain("研究工作空间")
    expect(html).toContain("正在加载比较文献")
    expect(html).toContain("导出比较")
  })

  it("renders the server-side statistics loading boundary", () => {
    const html = renderToStaticMarkup(<StatisticsPage client={client} bridge={bridge} />)
    expect(html).toContain("统计分析")
    expect(html).toContain("正在聚合文献统计")
    expect(html).toContain("导出 CSV")
  })

  it("renders the evidence-aware AI safety boundary", () => {
    const html = renderToStaticMarkup(<MemoryRouter><AIWorkspacePage client={client} bridge={bridge} /></MemoryRouter>)
    expect(html).toContain("AI 工作区")
    expect(html).toContain("默认只在本地生成可追溯证据简报")
    expect(html).toContain("正在加载研究证据")
  })

  it("renders shared settings without exposing a credential input", () => {
    const html = renderToStaticMarkup(<BusinessSettingsPage client={client} />)
    expect(html).toContain("业务设置")
    expect(html).toContain("正在加载业务设置")
    expect(html).not.toContain("API Key")
  })
})
