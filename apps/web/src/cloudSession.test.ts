import { describe, expect, it } from "vitest"
import { clearCloudSession, cloudAccessToken, readCloudSession, updateCloudSessionUser, writeCloudSession } from "./cloudSession"

describe("cloud session", () => {
  it("keeps the current-tab token behind a session accessor", () => {
    clearCloudSession()
    expect(readCloudSession()).toBeUndefined()
    writeCloudSession({ protocolVersion: "1.0", accessToken: "secret", expiresAt: "2099-01-01T00:00:00Z", user: { protocolVersion: "1.0", id: "u", tenantId: "t", workspaceId: "w", accountStatus: "active", email: "u@example.com", displayName: "User", roles: ["owner"], dataControls: { uploadLocalPdfs: false, syncAnnotations: false, syncFullText: false, useCloudAi: false, retainCloudTaskData: false, allowTeamAccess: false, allowShareLinks: false, shareDiagnostics: false }, createdAt: "2026-01-01T00:00:00Z" } })
    expect(cloudAccessToken()).toBe("secret")
    const current = readCloudSession()
    if (!current) throw new Error("session missing")
    updateCloudSessionUser({ ...current.user, dataControls: { ...current.user.dataControls, shareDiagnostics: true } })
    expect(readCloudSession()?.user.dataControls.shareDiagnostics).toBe(true)
    clearCloudSession()
    expect(cloudAccessToken()).toBeUndefined()
  })
})
