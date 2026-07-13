import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import type { UserAccount } from "@omnilit/shared-schema"
import { CloudTaskPanel } from "./CloudTaskPanel"

describe("CloudTaskPanel", () => {
  it("renders a bounded graph audit form and owner metrics state without exposing credentials", () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({}) })
    const account = { protocolVersion: "1.0", id: "owner", tenantId: "tenant", workspaceId: "workspace", accountStatus: "active", email: "owner@example.com", displayName: "Owner", roles: ["owner"], dataControls: { uploadLocalPdfs: false, syncAnnotations: false, syncFullText: false, useCloudAi: false, retainCloudTaskData: false, allowTeamAccess: false, allowShareLinks: false, shareDiagnostics: false }, createdAt: "2026-01-01T00:00:00Z" } satisfies UserAccount
    const html = renderToStaticMarkup(<CloudTaskPanel client={client} account={account} />)
    expect(html).toContain("创建图谱审计")
    expect(html).toContain("尚未创建云端任务")
    expect(html).toContain("正在加载运行指标")
    expect(html).not.toContain("Authorization")
  })
})
