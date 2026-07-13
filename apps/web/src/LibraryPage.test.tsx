import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { LibraryPage } from "./LibraryPage"

describe("shared literature library", () => {
  it("renders semantic search and filter controls while server data loads", () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({}) })
    const html = renderToStaticMarkup(<LibraryPage client={client} />)
    expect(html).toContain("文献库")
    expect(html).toContain("标题、作者、摘要、DOI")
    expect(html).toContain("正在加载文献库")
    expect(html).toContain("比较工作区")
    expect(html).toContain("研究集合")
    expect(html).toContain("<form")
    expect(html).toContain("<label")
  })
})
