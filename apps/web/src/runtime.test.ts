import { describe, expect, it, vi } from "vitest"
import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { MockPlatformBridge, PlatformCapabilityError, QtWebChannelPlatformBridge } from "@omnilit/platform-bridge"
import type { GraphViewSaveRequest } from "@omnilit/shared-schema"

describe("shared web runtime", () => {
  it("uses the minimal Qt WebChannel bridge without moving graph payloads", async () => {
    const opened: string[] = []
    const bridge = new QtWebChannelPlatformBridge("2.0.0", async () => ({
      getAppInfo: (callback) => callback({ name: "OmniLit", version: "2.0.0", platform: "qt-desktop" }),
      getLocalServiceStatus: (callback) => callback({ available: true }),
      openExternalUrl: (url, callback) => { opened.push(url); callback(true) }
    }))
    await expect(bridge.getAppInfo()).resolves.toMatchObject({ platform: "qt-desktop" })
    await expect(bridge.getLocalServiceStatus()).resolves.toEqual({ available: true })
    await bridge.openExternalUrl("https://example.org/paper")
    expect(opened).toEqual(["https://example.org/paper"])
    await expect(bridge.openLocalFiles()).rejects.toBeInstanceOf(PlatformCapabilityError)
    await expect(bridge.openExternalUrl("file:///private.txt")).rejects.toBeInstanceOf(PlatformCapabilityError)
  })

  it("loads fixture data through the unified API client", async () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", transport: createFixtureTransport({ "/v1/value": { ok: true } }) })
    await expect(client.request<{ ok: boolean }>("/v1/value")).resolves.toEqual({ ok: true })
  })

  it("keeps the Window receiver when using native fetch", async () => {
    const native = vi.fn(function (this: typeof globalThis, _request: Request) {
      if (this !== globalThis) throw new TypeError("Illegal invocation")
      return Promise.resolve(Response.json({ ok: true }))
    })
    vi.stubGlobal("fetch", native)
    try {
      const client = new ApiClient({ baseUrl: "http://127.0.0.1:8765", retries: 0 })
      await expect(client.request<{ ok: boolean }>("/v1/health")).resolves.toEqual({ ok: true })
      expect(native).toHaveBeenCalledOnce()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("normalizes missing fixture responses", async () => {
    const client = new ApiClient({ baseUrl: "https://fixture.invalid", retries: 0, transport: createFixtureTransport({}) })
    await expect(client.request("/missing")).rejects.toMatchObject({ payload: { code: "not_found", retryable: false } })
  })

  it("sends auth and JSON headers to Local Agent graph queries", async () => {
    let captured: Request | undefined
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:9090",
      accessToken: () => "secret-token",
      retries: 0,
      transport: async (request) => {
        captured = request
        return Response.json({ protocolVersion: "1.0", recordId: "paper-001", rows: [], offset: 0, nextOffset: 0, total: 0, hasMore: false })
      }
    })
    await client.getGraphLiterature("paper-001", { visibleNodeIds: ["paper:paper-001"] })
    expect(captured?.headers.get("Authorization")).toBe("Bearer secret-token")
    expect(captured?.headers.get("Content-Type")).toBe("application/json")
    expect(await captured?.json()).toEqual({ visibleNodeIds: ["paper:paper-001"] })
  })

  it("normalizes caller cancellation for progressive graph queries", async () => {
    const controller = new AbortController()
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:9090", retries: 0, transport: (request) => new Promise((_resolve, reject) => request.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))) })
    const pending = client.getGraphNeighbors("paper-001", "paper:paper-001", { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toMatchObject({ payload: { code: "request_cancelled", retryable: false } })
  })

  it("uses the unified client for task creation, polling, cancellation, and results", async () => {
    const requests: Array<{ method: string; path: string }> = []
    const task = { protocolVersion: "1.0", id: "task-1", type: "graph.audit", status: "queued", cancellable: true, progress: { completed: 0, total: 1, unit: "task" } }
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:9090",
      retries: 0,
      transport: async (request) => {
        requests.push({ method: request.method, path: new URL(request.url).pathname })
        return Response.json(request.url.endsWith("/result") ? { nodeCount: 6 } : request.url.endsWith("/metrics") ? { protocolVersion: "1.0", status: "ready", uptimeSeconds: 1, tenantUsers: 1, cloudGraphs: 1, tasksByStatus: {}, auditEvents: 1 } : task)
      }
    })
    await client.createTask("graph.audit", { recordId: "paper-001" })
    await client.getTask("task-1")
    await client.cancelTask("task-1")
    await expect(client.getTaskResult("task-1")).resolves.toEqual({ nodeCount: 6 })
    await client.getCloudMetrics()
    expect(requests).toEqual([
      { method: "POST", path: "/v1/tasks" },
      { method: "GET", path: "/v1/tasks/task-1" },
      { method: "POST", path: "/v1/tasks/task-1:cancel" },
      { method: "GET", path: "/v1/tasks/task-1/result" },
      { method: "GET", path: "/v1/metrics" }
    ])
  })

  it("uses REST view endpoints for list, save, restore, and delete", async () => {
    const requests: Array<{ method: string; path: string }> = []
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:9090", retries: 0, transport: async (request) => {
      requests.push({ method: request.method, path: new URL(request.url).pathname })
      return Response.json({ protocolVersion: "1.0", recordId: "paper-001", views: [], deleted: true })
    } })
    const view: GraphViewSaveRequest = {
      protocolVersion: "1.0", name: "Methods", exploration: { nodeIds: [], edgeIds: [], pages: {} },
      filters: { mode: "all", searchText: "", density: "normal", literatureSortKey: "relevance", literatureSortDescending: true, facets: {}, nodeTypes: [], needsReviewOnly: false },
      selection: { nodeId: "", edgeId: "" }, viewport: { displayStyle: "academic", focusDepth: 0, reviewMode: false, graphScale: 1, panX: 0, panY: 0, showArrows: true, showLabels: true, dimUnrelated: true, textFadeThreshold: 1.15, nodeSizeScale: 1, linkThickness: 1, animateLayout: false }
    }
    await client.listGraphViews("paper-001")
    await client.saveGraphView("paper-001", view)
    await client.restoreGraphView("paper-001", "view-1")
    await client.deleteGraphView("paper-001", "view-1")
    expect(requests).toEqual([
      { method: "GET", path: "/v1/graphs/paper-001/views" }, { method: "POST", path: "/v1/graphs/paper-001/views" },
      { method: "GET", path: "/v1/graphs/paper-001/views/view-1" }, { method: "DELETE", path: "/v1/graphs/paper-001/views/view-1" }
    ])
  })

  it("parses authenticated collaboration SSE events and reset frames", async () => {
    let captured: Request | undefined
    const events: number[] = []
    const resets: number[] = []
    const client = new ApiClient({ baseUrl: "https://cloud.example", accessToken: () => "cloud-session", retries: 0, transport: async (request) => {
      captured = request
      const annotation = { protocolVersion: "1.0", id: "note-1", recordId: "paper-001", targetType: "node", targetId: "paper:paper-001", body: "Review", authorId: "user-1", authorDisplayName: "Owner", revision: 2, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z" }
      const event = { protocolVersion: "1.0", recordId: "paper-001", revision: 2, clientMutationId: "mutation-1", action: "annotation.upserted", annotationId: "note-1", annotation, actorId: "user-1", occurredAt: "2026-01-01T00:00:00Z" }
      return new Response(`event: reset\ndata: {"currentRevision":1}\n\nid: 2\nevent: collaboration\ndata: ${JSON.stringify(event)}\n\n`, { headers: { "Content-Type": "text/event-stream" } })
    } })
    await expect(client.streamCollaborationEvents("paper-001", 0, { onEvent: (event) => events.push(event.revision), onReset: (revision) => resets.push(revision) })).resolves.toBe(2)
    expect(captured?.headers.get("Authorization")).toBe("Bearer cloud-session")
    expect(captured?.headers.get("Last-Event-ID")).toBe("0")
    expect(new URL(captured?.url ?? "").pathname).toBe("/v1/graphs/paper-001/collaboration/events/stream")
    expect(events).toEqual([2])
    expect(resets).toEqual([1])
  })

  it("uses unified REST methods for collaboration snapshot, mutation, and recovery pages", async () => {
    const requests: Array<{ method: string; path: string }> = []
    const client = new ApiClient({ baseUrl: "https://cloud.example", retries: 0, transport: async (request) => {
      const url = new URL(request.url)
      requests.push({ method: request.method, path: `${url.pathname}${url.search}` })
      if (url.pathname.endsWith("/events")) return Response.json({ protocolVersion: "1.0", recordId: "paper/001", afterRevision: 0, currentRevision: 0, events: [], hasMore: false, resetRequired: false })
      if (request.method === "POST") return Response.json({ protocolVersion: "1.0", recordId: "paper/001", revision: 1, event: {} })
      return Response.json({ protocolVersion: "1.0", recordId: "paper/001", revision: 0, canEdit: true, syncEnabled: true, annotations: [] })
    } })
    await client.getCollaborationSnapshot("paper/001")
    await client.mutateCollaboration("paper/001", { protocolVersion: "1.0", baseRevision: 0, clientMutationId: "m1", action: "upsert", targetType: "graph", targetId: "paper/001", body: "Review" })
    await client.getCollaborationEvents("paper/001", 0)
    expect(requests).toEqual([
      { method: "GET", path: "/v1/graphs/paper%2F001/collaboration" },
      { method: "POST", path: "/v1/graphs/paper%2F001/collaboration" },
      { method: "GET", path: "/v1/graphs/paper%2F001/collaboration/events?afterRevision=0&limit=200" }
    ])
  })

  it("posts timeline selection and viewport through the unified API client", async () => {
    let captured: Request | undefined
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:9090", retries: 0, transport: async (request) => {
      captured = request
      return Response.json({ protocolVersion: "1.0", timelineKey: "demo-timeline", status: "empty" })
    } })
    await client.getGraphTimeline("demo timeline", { protocolVersion: "1.0", startYear: 2020, endYear: 2024, playbackYear: 2022, viewport: { width: 1280, height: 720, scale: 1 } })
    expect(captured?.method).toBe("POST")
    expect(new URL(captured?.url ?? "http://invalid").pathname).toBe("/v1/timelines/demo%20timeline/query")
    expect(await captured?.json()).toMatchObject({ playbackYear: 2022, viewport: { width: 1280, height: 720 } })
  })

  it("queries the shared desktop library and loads a record detail", async () => {
    const requests: Array<{ method: string; path: string; body?: unknown }> = []
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:9090", retries: 0, transport: async (request) => {
      requests.push({ method: request.method, path: new URL(request.url).pathname, body: request.method === "POST" ? await request.json() : undefined })
      return Response.json(request.method === "POST"
        ? { protocolVersion: "1.0", status: "empty", records: [], offset: 0, nextOffset: 0, total: 0, hasMore: false, cacheAvailable: true, facets: { relevance: {}, pdfStatus: {}, journalType: {}, keywordGroups: {} }, message: "" }
        : { protocolVersion: "1.0", recordId: "paper-001", title: "Paper", abstract: "", authorsText: "", doi: "", source: "", year: "", journalTitle: "", keywordsText: "", summaryText: "", topicTagsText: "", pdfStatus: "", relevanceLabel: "", relevanceScore: 0, matchedKeywordsText: "", matchedFieldsText: "", relevanceReasonsText: "", downloaded: false, hasExtraction: false })
    } })
    await client.queryLibrary({ protocolVersion: "1.0", query: "graph", sort: "year_desc" })
    await client.getLibraryRecord("paper-001")
    expect(requests).toEqual([
      { method: "POST", path: "/v1/library/query", body: { protocolVersion: "1.0", query: "graph", sort: "year_desc" } },
      { method: "GET", path: "/v1/library/records/paper-001", body: undefined }
    ])
  })

  it("reads and mutates versioned collection workspace state", async () => {
    const requests: Array<{ method: string; path: string; body?: unknown }> = []
    const state = { protocolVersion: "1.0", revision: 4, updatedAt: "", syncState: "local_only", collections: [], favorites: {}, workspace: { compareRecordIds: [] } }
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:9090", retries: 0, transport: async (request) => {
      const body = request.method === "POST" ? await request.json() : undefined
      requests.push({ method: request.method, path: new URL(request.url).pathname, body })
      return Response.json(request.method === "POST" ? { protocolVersion: "1.0", changed: true, message: "updated", state: { ...state, revision: 5, workspace: { compareRecordIds: ["paper-001"] } } } : state)
    } })
    await expect(client.getLibraryState()).resolves.toMatchObject({ revision: 4 })
    await client.mutateLibraryState({ protocolVersion: "1.0", action: "toggle_compare_record", expectedRevision: 4, recordId: "paper-001" })
    expect(requests).toEqual([
      { method: "GET", path: "/v1/library/state", body: undefined },
      { method: "POST", path: "/v1/library/state/mutations", body: { protocolVersion: "1.0", action: "toggle_compare_record", expectedRevision: 4, recordId: "paper-001" } }
    ])
  })

  it("uses Cloud API account, sync, sharing, audit, export, and deletion routes", async () => {
    const requests: Array<{ method: string; path: string }> = []
    const state = { protocolVersion: "1.0" as const, revision: 0, updatedAt: "", syncState: "local_only" as const, collections: [], favorites: {}, workspace: { compareRecordIds: [] } }
    const client = new ApiClient({ baseUrl: "https://cloud.example", accessToken: () => "cloud-token", retries: 0, transport: async (request) => {
      const path = new URL(request.url).pathname
      requests.push({ method: request.method, path })
      if (path === "/v1/sync/library") return Response.json({ protocolVersion: "1.0", status: "conflict", cloudRevision: 2, syncedAt: "", serverState: state, conflictId: "c1" }, { status: 409 })
      if (path === "/v1/auth/login") return Response.json({ protocolVersion: "1.0", accessToken: "token", expiresAt: "2099-01-01", user: {} })
      if (path === "/v1/shares") return Response.json({ protocolVersion: "1.0", id: "s1" })
      if (path === "/v1/audit/events") return Response.json({ protocolVersion: "1.0", events: [] })
      return Response.json({ protocolVersion: "1.0", revoked: true, deleted: true })
    } })
    await client.login({ email: "u@example.com", password: "password-value" })
    await expect(client.syncLibrary({ protocolVersion: "1.0", deviceId: "web", baseCloudRevision: 1, state })).resolves.toMatchObject({ status: "conflict", cloudRevision: 2 })
    await client.createShare({ protocolVersion: "1.0", resourceType: "library_state", resourceId: "current", permission: "viewer" })
    await client.revokeShare("s1")
    await client.getAuditEvents()
    await client.submitDiagnostic({ protocolVersion: "1.0", occurredAt: "2026-01-01T00:00:00Z", source: "react", code: "render_error", exceptionType: "Error", fingerprint: "01234567", severity: "error", appVersion: "0.1.0" })
    await client.exportAccount()
    await client.deleteAccount("u@example.com")
    expect(requests).toEqual([
      { method: "POST", path: "/v1/auth/login" }, { method: "POST", path: "/v1/sync/library" },
      { method: "POST", path: "/v1/shares" }, { method: "DELETE", path: "/v1/shares/s1" },
      { method: "GET", path: "/v1/audit/events" }, { method: "POST", path: "/v1/diagnostics" }, { method: "GET", path: "/v1/account/export" },
      { method: "DELETE", path: "/v1/account" }
    ])
  })

  it("uses unified team invitation, membership, and ACL routes", async () => {
    const requests: Array<{ method: string; path: string }> = []
    const client = new ApiClient({ baseUrl: "https://cloud.example", retries: 0, transport: async (request) => {
      const path = new URL(request.url).pathname
      requests.push({ method: request.method, path })
      if (path.endsWith("invites:accept")) return Response.json({ protocolVersion: "1.0", accessToken: "token", expiresAt: "2099-01-01", user: {} })
      if (path.endsWith("/invites")) return Response.json({ protocolVersion: "1.0", id: "invite" })
      if (path.startsWith("/v1/permissions")) return Response.json({ protocolVersion: "1.0", resourceType: "library_state", resourceId: "current", permissions: [] })
      return Response.json({ protocolVersion: "1.0", tenantId: "tenant", members: [], removed: true })
    } })
    await client.listTeamMembers()
    await client.createTeamInvite({ protocolVersion: "1.0", email: "member@example.com", role: "member" })
    await client.acceptTeamInvite({ protocolVersion: "1.0", token: "long-enough-invitation-token", displayName: "Member", password: "password-value" })
    await client.updateTeamMemberRole("member-1", "admin")
    await client.removeTeamMember("member-1")
    await client.listResourcePermissions("library_state", "current")
    await client.setResourcePermission({ protocolVersion: "1.0", resourceType: "library_state", resourceId: "current", principalType: "user", principalId: "member-1", permission: "viewer" })
    expect(requests).toEqual([
      { method: "GET", path: "/v1/team/members" }, { method: "POST", path: "/v1/team/invites" },
      { method: "POST", path: "/v1/team/invites:accept" }, { method: "PATCH", path: "/v1/team/members/member-1" },
      { method: "DELETE", path: "/v1/team/members/member-1" }, { method: "GET", path: "/v1/permissions/library_state/current" },
      { method: "POST", path: "/v1/permissions" }
    ])
  })

  it("lists and revision-syncs cloud graphs without swallowing conflicts", async () => {
    const requests: Array<{ method: string; path: string }> = []
    const graph = { protocolVersion: "1.0" as const, schemaVersion: 1 as const, recordId: "paper-001", nodes: [], edges: [], metadata: {} }
    const client = new ApiClient({ baseUrl: "https://cloud.example", retries: 0, transport: async (request) => {
      requests.push({ method: request.method, path: new URL(request.url).pathname })
      if (request.method === "GET") return Response.json({ protocolVersion: "1.0", graphs: [] })
      return Response.json({ protocolVersion: "1.0", status: "conflict", recordId: "paper-001", cloudRevision: 3, syncedAt: "", serverGraph: graph, conflictId: "graph-conflict" }, { status: 409 })
    } })
    await client.listCloudGraphs()
    await expect(client.syncCloudGraph("paper-001", { protocolVersion: "1.0", deviceId: "desktop", baseCloudRevision: 2, graph })).resolves.toMatchObject({ status: "conflict", cloudRevision: 3 })
    expect(requests).toEqual([{ method: "GET", path: "/v1/graphs" }, { method: "POST", path: "/v1/graphs/paper-001/sync" }])
  })

  it("mock bridge exposes browser boundaries and task subscriptions", async () => {
    const bridge = new MockPlatformBridge()
    const events: string[] = []
    const unsubscribe = bridge.subscribeTaskProgress((event) => events.push(event.taskId))
    bridge.emitTaskProgress({ taskId: "task-1", progress: { completed: 1, total: 2, unit: "papers" } })
    unsubscribe()
    bridge.emitTaskProgress({ taskId: "task-2", progress: { completed: 2, total: 2, unit: "papers" } })
    expect(events).toEqual(["task-1"])
    await expect(bridge.revealInFileManager("C:/secret")).rejects.toBeInstanceOf(PlatformCapabilityError)
  })

  it("blocks non-web external URL schemes", async () => {
    const bridge = new MockPlatformBridge()
    await expect(bridge.openExternalUrl("file:///etc/passwd")).rejects.toMatchObject({ capability: "openExternalUrl" })
  })
})
