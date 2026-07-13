import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { AccountPage } from "./AccountPage"
import { clearCloudSession } from "./cloudSession"

describe("AccountPage", () => {
  it("renders a semantic account entry without exposing a token", () => {
    clearCloudSession()
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({}) })
    const html = renderToStaticMarkup(<AccountPage cloudClient={client} localClient={client} cloudConfigured={false} localGraphSourceAvailable={false} />)
    expect(html).toContain("登录 OmniLit")
    expect(html).toContain("本地演示服务")
    expect(html).toContain('type="password"')
    expect(html).not.toContain("accessToken")
  })
})
