import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { TeamPanel } from "./TeamPanel"

describe("TeamPanel", () => {
  it("shows owner invitation and least-privilege team controls", () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({}) })
    const account = { protocolVersion: "1.0" as const, id: "owner", tenantId: "tenant", workspaceId: "workspace", accountStatus: "active" as const, email: "owner@example.com", displayName: "Owner", roles: ["owner" as const], dataControls: { uploadLocalPdfs: false, syncAnnotations: false, syncFullText: false, useCloudAi: false, retainCloudTaskData: false, allowTeamAccess: false, allowShareLinks: false, shareDiagnostics: false }, createdAt: "" }
    const html = renderToStaticMarkup(<TeamPanel client={client} account={account} />)
    expect(html).toContain("团队与文献库权限")
    expect(html).toContain("邀请邮箱")
    expect(html).toContain("团队访问总开关关闭")
    expect(html).toContain("正在加载团队成员")
  })
})
