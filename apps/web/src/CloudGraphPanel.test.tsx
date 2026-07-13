import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { CloudGraphPanel } from "./CloudGraphPanel"

describe("CloudGraphPanel", () => {
  it("does not offer fixture upload when a real browser has no Local Agent", () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({}) })
    const html = renderToStaticMarkup(<MemoryRouter><CloudGraphPanel cloudClient={client} localClient={client} localSourceAvailable={false} /></MemoryRouter>)
    expect(html).toContain("云图谱与共享视图")
    expect(html).toContain("不能把演示数据上传")
    expect(html).not.toContain("同步到云端")
  })
})
