import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { InvitePage } from "./InvitePage"

describe("InvitePage", () => {
  it("renders the single-use invitation acceptance form", () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({}) })
    const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/invite/long-enough-invitation-token"]}><Routes><Route path="/invite/:token" element={<InvitePage client={client} />} /></Routes></MemoryRouter>)
    expect(html).toContain("加入 OmniLit 研究团队")
    expect(html).toContain("设置密码")
    expect(html).toContain("接受邀请")
  })
})
