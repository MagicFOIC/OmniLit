import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { CollectionsPage } from "./CollectionsPage"

describe("research collections page", () => {
  it("renders collection creation and a bounded workspace loading state", () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({}) })
    const html = renderToStaticMarkup(<CollectionsPage client={client} />)
    expect(html).toContain("研究集合")
    expect(html).toContain("新建集合")
    expect(html).toContain("正在加载研究集合")
    expect(html).toContain("<form")
  })
})
