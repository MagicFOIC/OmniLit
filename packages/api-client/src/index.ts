import type { APIError, AuditEventPage, AuthSession, BusinessSettings, BusinessSettingsUpdateRequest, CloudDataControls, CloudGraphList, CloudGraphSyncRequest, CloudGraphSyncResult, CloudServiceMetrics, CollaborationEvent, CollaborationEventPage, CollaborationMutationRequest, CollaborationMutationResult, CollaborationSnapshot, DiagnosticReceipt, DiagnosticReportCreateRequest, GraphData, GraphNeighborPage, GraphProjection, GraphTimeline, GraphTimelineQuery, GraphViewList, GraphViewMutationResult, GraphViewRestore, GraphViewSaveRequest, GraphViewState, LibraryMutationRequest, LibraryMutationResult, LibraryPage, LibraryQuery, LibraryRecordDetail, LibraryState, LibrarySyncRequest, LibrarySyncResult, LiteraturePage, PublicLibraryPage, PublicLibraryQuery, PublicModerationDecision, PublicSubmission, PublicSubmissionCreateRequest, PublicSubmissionList, RegistrationResult, ResearchStatistics, ResearchWorkspace, ResourcePermissionList, ResourcePermissionMutation, ShareCreateRequest, ShareLink, Task, TeamInvite, TeamInviteAcceptRequest, TeamInviteCreateRequest, TeamMemberList, UserAccount, WorkspaceChangePage, WorkspaceSummary, WorkspaceSyncBatch, WorkspaceSyncPreferences, WorkspaceSyncResult, WorkspaceSyncStatus } from "@omnilit/shared-schema"
import { PROTOCOL_VERSION } from "@omnilit/shared-schema"

export type ApiTransport = (request: Request) => Promise<Response>

export interface ApiClientOptions {
  baseUrl: string
  accessToken?: () => string | undefined
  timeoutMs?: number
  retries?: number
  transport?: ApiTransport
}

export class ApiClientError extends Error {
  readonly payload: APIError

  constructor(payload: APIError) {
    super(payload.message)
    this.name = "ApiClientError"
    this.payload = payload
  }
}

function apiError(code: string, message: string, retryable: boolean, details: Record<string, unknown> = {}): APIError {
  return { protocolVersion: PROTOCOL_VERSION, code, message, retryable, details }
}

export class ApiClient {
  readonly #baseUrl: string
  readonly #accessToken?: () => string | undefined
  readonly #timeoutMs: number
  readonly #retries: number
  readonly #transport: ApiTransport

  constructor(options: ApiClientOptions) {
    this.#baseUrl = options.baseUrl.replace(/\/$/, "")
    this.#accessToken = options.accessToken
    this.#timeoutMs = options.timeoutMs ?? 15_000
    this.#retries = Math.max(0, options.retries ?? 1)
    // Some Chromium/Qt WebEngine builds require the native fetch receiver to
    // remain Window. Keeping a bare reference and invoking it later can throw
    // "Illegal invocation", so resolve and call it through globalThis.
    this.#transport = options.transport ?? ((request) => globalThis.fetch(request))
  }

  async request<T>(path: string, init: RequestInit = {}, acceptedStatuses: readonly number[] = []): Promise<T> {
    const method = (init.method ?? "GET").toUpperCase()
    const attempts = method === "GET" || method === "HEAD" ? this.#retries + 1 : 1
    let lastError: ApiClientError | undefined
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        return await this.#requestOnce<T>(path, init, acceptedStatuses)
      } catch (error) {
        const converted = error instanceof ApiClientError
          ? error
          : new ApiClientError(apiError("network_error", error instanceof Error ? error.message : "Network request failed", true))
        lastError = converted
        if (!converted.payload.retryable || attempt + 1 >= attempts) throw converted
      }
    }
    throw lastError ?? new ApiClientError(apiError("request_failed", "Request failed", false))
  }

  getGraph(recordId: string, signal?: AbortSignal): Promise<GraphData> {
    return this.request<GraphData>(`/v1/graphs/${encodeURIComponent(recordId)}`, { signal })
  }

  listGraphs(signal?: AbortSignal): Promise<CloudGraphList> {
    return this.request<CloudGraphList>("/v1/graphs", { signal })
  }

  getGraphNeighbors(recordId: string, nodeId: string, options: { mode?: string; offset?: number; limit?: number; signal?: AbortSignal } = {}): Promise<GraphNeighborPage> {
    const query = new URLSearchParams({
      mode: options.mode ?? "all",
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 12)
    })
    return this.request<GraphNeighborPage>(`/v1/graphs/${encodeURIComponent(recordId)}/nodes/${encodeURIComponent(nodeId)}:neighbors?${query}`, { signal: options.signal })
  }

  getGraphLiterature(recordId: string, request: Record<string, unknown>, signal?: AbortSignal): Promise<LiteraturePage> {
    return this.request<LiteraturePage>(`/v1/graphs/${encodeURIComponent(recordId)}/literature/query`, {
      method: "POST",
      body: JSON.stringify(request),
      signal
    })
  }

  queryLibrary(query: LibraryQuery, signal?: AbortSignal): Promise<LibraryPage> {
    return this.request<LibraryPage>("/v1/library/query", { method: "POST", body: JSON.stringify(query), signal })
  }

  getLibraryRecord(recordId: string, signal?: AbortSignal): Promise<LibraryRecordDetail> {
    return this.request<LibraryRecordDetail>(`/v1/library/records/${encodeURIComponent(recordId)}`, { signal })
  }

  getLibraryState(signal?: AbortSignal): Promise<LibraryState> {
    return this.request<LibraryState>("/v1/library/state", { signal })
  }

  mutateLibraryState(mutation: LibraryMutationRequest, signal?: AbortSignal): Promise<LibraryMutationResult> {
    return this.request<LibraryMutationResult>("/v1/library/state/mutations", { method: "POST", body: JSON.stringify(mutation), signal })
  }

  getResearchWorkspace(signal?: AbortSignal): Promise<ResearchWorkspace> {
    return this.request<ResearchWorkspace>("/v1/workspace", { signal })
  }

  getResearchStatistics(signal?: AbortSignal): Promise<ResearchStatistics> {
    return this.request<ResearchStatistics>("/v1/statistics", { signal })
  }

  getBusinessSettings(signal?: AbortSignal): Promise<BusinessSettings> {
    return this.request<BusinessSettings>("/v1/settings/business", { signal })
  }

  updateBusinessSettings(settings: BusinessSettingsUpdateRequest, signal?: AbortSignal): Promise<BusinessSettings> {
    return this.request<BusinessSettings>("/v1/settings/business", { method: "POST", body: JSON.stringify(settings), signal })
  }

  registerAccount(input: { email: string; password: string; displayName: string; tenantName: string; turnstileToken?: string }, signal?: AbortSignal): Promise<AuthSession | RegistrationResult> {
    return this.request<AuthSession | RegistrationResult>("/v1/auth/register", { method: "POST", body: JSON.stringify(input), signal })
  }

  verifyEmail(token: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; verified: boolean }> {
    return this.request("/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ token }), signal })
  }

  resendVerification(email: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; accepted: boolean }> {
    return this.request("/v1/auth/resend-verification", { method: "POST", body: JSON.stringify({ email }), signal })
  }

  requestPasswordReset(email: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; accepted: boolean }> {
    return this.request("/v1/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }), signal })
  }

  resetPassword(token: string, newPassword: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; reset: boolean }> {
    return this.request("/v1/auth/reset-password", { method: "POST", body: JSON.stringify({ token, newPassword }), signal })
  }

  login(input: { email: string; password: string }, signal?: AbortSignal): Promise<AuthSession> {
    return this.request<AuthSession>("/v1/auth/login", { method: "POST", body: JSON.stringify(input), signal })
  }

  logout(signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; loggedOut: boolean }> {
    return this.request("/v1/auth/logout", { method: "POST", signal })
  }

  changePassword(currentPassword: string, newPassword: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; changed: boolean }> {
    return this.request("/v1/account/password", { method: "POST", body: JSON.stringify({ currentPassword, newPassword }), signal })
  }

  listDevices(signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; devices: Array<{ id: string; createdAt: string; expiresAt: string }> }> {
    return this.request("/v1/account/devices", { signal })
  }

  revokeDevice(deviceId: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; revoked: boolean }> {
    return this.request(`/v1/account/devices/${encodeURIComponent(deviceId)}`, { method: "DELETE", signal })
  }

  getAccount(signal?: AbortSignal): Promise<UserAccount> {
    return this.request<UserAccount>("/v1/account/me", { signal })
  }

  updateCloudDataControls(controls: CloudDataControls, signal?: AbortSignal): Promise<UserAccount> {
    return this.request<UserAccount>("/v1/account/data-controls", { method: "PATCH", body: JSON.stringify(controls), signal })
  }

  getWorkspaceSummary(signal?: AbortSignal): Promise<WorkspaceSummary> {
    return this.request<WorkspaceSummary>("/v1/workspaces/me", { signal })
  }

  getWorkspaceSyncPreferences(signal?: AbortSignal): Promise<WorkspaceSyncPreferences> {
    return this.request<WorkspaceSyncPreferences>("/v1/sync/workspace/preferences", { signal })
  }

  updateWorkspaceSyncPreferences(preferences: WorkspaceSyncPreferences, signal?: AbortSignal): Promise<WorkspaceSyncPreferences> {
    return this.request<WorkspaceSyncPreferences>("/v1/sync/workspace/preferences", { method: "PATCH", body: JSON.stringify(preferences), signal })
  }

  getWorkspaceSyncStatus(signal?: AbortSignal): Promise<WorkspaceSyncStatus> {
    return this.request<WorkspaceSyncStatus>("/v1/sync/workspace/status", { signal })
  }

  pullWorkspaceChanges(cursor: number, limit = 200, signal?: AbortSignal): Promise<WorkspaceChangePage> {
    return this.request<WorkspaceChangePage>(`/v1/sync/workspace/changes?cursor=${Math.max(0, Math.floor(cursor))}&limit=${Math.max(1, Math.min(500, Math.floor(limit)))}`, { signal })
  }

  pushWorkspaceChanges(batch: WorkspaceSyncBatch, signal?: AbortSignal): Promise<WorkspaceSyncResult> {
    return this.request<WorkspaceSyncResult>("/v1/sync/workspace/push", { method: "POST", body: JSON.stringify(batch), signal })
  }

  queryPublicLibrary(query: PublicLibraryQuery, signal?: AbortSignal): Promise<PublicLibraryPage> {
    return this.request<PublicLibraryPage>("/v1/public/library/query", { method: "POST", body: JSON.stringify(query), signal })
  }

  reportPublicRecord(recordId: string, reason: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; id: string; status: string }> {
    return this.request("/v1/public/reports", { method: "POST", body: JSON.stringify({ recordId, reason }), signal })
  }

  requestPublicTakedown(request: { recordId: string; reason: string; evidenceUrl?: string; contact?: string }, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; id: string; status: string }> {
    return this.request("/v1/public/takedown-requests", { method: "POST", body: JSON.stringify(request), signal })
  }

  listPublicTakedownRequests(signal?: AbortSignal): Promise<Record<string, unknown>> {
    return this.request("/v1/admin/takedown-requests", { signal })
  }

  decidePublicTakedownRequest(id: string, decision: "dismiss" | "hide", note: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
    return this.request(`/v1/admin/takedown-requests/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify({ decision, note }), signal })
  }

  setAccountQuota(userId: string, quotaBytes: number, signal?: AbortSignal): Promise<Record<string, unknown>> {
    return this.request(`/v1/admin/accounts/${encodeURIComponent(userId)}/quota`, { method: "PATCH", body: JSON.stringify({ quotaBytes }), signal })
  }

  createPublicSubmission(request: PublicSubmissionCreateRequest, signal?: AbortSignal): Promise<PublicSubmission> {
    return this.request<PublicSubmission>("/v1/public/submissions", { method: "POST", body: JSON.stringify(request), signal })
  }

  listPublicSubmissions(signal?: AbortSignal): Promise<PublicSubmissionList> {
    return this.request<PublicSubmissionList>("/v1/public/submissions", { signal })
  }

  submitPublicSubmission(id: string, signal?: AbortSignal): Promise<PublicSubmission> {
    return this.request<PublicSubmission>(`/v1/public/submissions/${encodeURIComponent(id)}:submit`, { method: "POST", signal })
  }

  requestPublicSubmissionWithdrawal(id: string, signal?: AbortSignal): Promise<PublicSubmission> {
    return this.request<PublicSubmission>(`/v1/public/submissions/${encodeURIComponent(id)}:withdraw`, { method: "POST", signal })
  }

  listPublicModerationQueue(signal?: AbortSignal): Promise<PublicSubmissionList> {
    return this.request<PublicSubmissionList>("/v1/admin/public-submissions", { signal })
  }

  moderatePublicSubmission(id: string, decision: PublicModerationDecision, signal?: AbortSignal): Promise<PublicSubmission> {
    return this.request<PublicSubmission>(`/v1/admin/public-submissions/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify(decision), signal })
  }

  initializeAssetUpload(input: { scope: "private" | "public_submission"; submissionId?: string; filename: string; mediaType: "application/pdf" | "text/plain" | "application/json"; sizeBytes: number; sha256: string }, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; uploadId: string; chunkSize: number; receivedBytes: number; expiresAt: string }> {
    return this.request("/v1/assets/uploads", { method: "POST", body: JSON.stringify(input), signal })
  }

  uploadAssetChunk(uploadId: string, offset: number, chunk: ArrayBuffer | Uint8Array, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; uploadId: string; receivedBytes: number; complete: boolean }> {
    const body = chunk instanceof Uint8Array ? new Blob([chunk as BlobPart]) : new Blob([chunk])
    return this.request(`/v1/assets/uploads/${encodeURIComponent(uploadId)}/chunks/${Math.max(0, Math.floor(offset))}`, { method: "PUT", headers: { "Content-Type": "application/octet-stream" }, body, signal })
  }

  completeAssetUpload(uploadId: string, signal?: AbortSignal): Promise<Record<string, unknown>> {
    return this.request(`/v1/assets/uploads/${encodeURIComponent(uploadId)}:complete`, { method: "POST", signal })
  }

  submitDiagnostic(report: DiagnosticReportCreateRequest, signal?: AbortSignal): Promise<DiagnosticReceipt> {
    return this.request<DiagnosticReceipt>("/v1/diagnostics", { method: "POST", body: JSON.stringify(report), signal })
  }

  syncLibrary(request: LibrarySyncRequest, signal?: AbortSignal): Promise<LibrarySyncResult> {
    return this.request<LibrarySyncResult>("/v1/sync/library", { method: "POST", body: JSON.stringify(request), signal }, [409])
  }

  getCloudLibrary(signal?: AbortSignal): Promise<LibrarySyncResult> {
    return this.request<LibrarySyncResult>("/v1/sync/library", { signal })
  }

  createShare(request: ShareCreateRequest, signal?: AbortSignal): Promise<ShareLink> {
    return this.request<ShareLink>("/v1/shares", { method: "POST", body: JSON.stringify(request), signal })
  }

  revokeShare(shareId: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; revoked: boolean }> {
    return this.request(`/v1/shares/${encodeURIComponent(shareId)}`, { method: "DELETE", signal })
  }

  getAuditEvents(signal?: AbortSignal): Promise<AuditEventPage> {
    return this.request<AuditEventPage>("/v1/audit/events", { signal })
  }

  getCloudMetrics(signal?: AbortSignal): Promise<CloudServiceMetrics> {
    return this.request<CloudServiceMetrics>("/v1/metrics", { signal })
  }

  getCollaborationSnapshot(recordId: string, signal?: AbortSignal): Promise<CollaborationSnapshot> {
    return this.request<CollaborationSnapshot>(`/v1/graphs/${encodeURIComponent(recordId)}/collaboration`, { signal })
  }

  mutateCollaboration(recordId: string, mutation: CollaborationMutationRequest, signal?: AbortSignal): Promise<CollaborationMutationResult> {
    return this.request<CollaborationMutationResult>(`/v1/graphs/${encodeURIComponent(recordId)}/collaboration`, { method: "POST", body: JSON.stringify(mutation), signal })
  }

  getCollaborationEvents(recordId: string, afterRevision: number, signal?: AbortSignal): Promise<CollaborationEventPage> {
    return this.request<CollaborationEventPage>(`/v1/graphs/${encodeURIComponent(recordId)}/collaboration/events?afterRevision=${Math.max(0, Math.floor(afterRevision))}&limit=200`, { signal })
  }

  async streamCollaborationEvents(recordId: string, afterRevision: number, handlers: { onEvent: (event: CollaborationEvent) => void; onReset: (currentRevision: number) => void }, signal?: AbortSignal): Promise<number> {
    const timeout = new AbortController()
    const timer = globalThis.setTimeout(() => timeout.abort("timeout"), Math.max(this.#timeoutMs, 30_000))
    const combined = signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal
    const headers = new Headers({ Accept: "text/event-stream", "X-OmniLit-Protocol-Version": PROTOCOL_VERSION, "Last-Event-ID": String(Math.max(0, Math.floor(afterRevision))) })
    const token = this.#accessToken?.()
    if (token) headers.set("Authorization", `Bearer ${token}`)
    let latest = afterRevision
    try {
      const query = `afterRevision=${Math.max(0, Math.floor(afterRevision))}&limit=200&waitSeconds=25`
      const response = await this.#transport(new Request(`${this.#baseUrl}/v1/graphs/${encodeURIComponent(recordId)}/collaboration/events/stream?${query}`, { headers, signal: combined }))
      if (!response.ok) {
        const body = await response.json().catch(() => undefined) as Partial<APIError> | undefined
        throw new ApiClientError(apiError(body?.code ?? `http_${response.status}`, body?.message ?? `Request failed with HTTP ${response.status}`, body?.retryable ?? response.status >= 500, body?.details ?? { status: response.status }))
      }
      if (!response.body) throw new ApiClientError(apiError("stream_unavailable", "Collaboration event stream is unavailable", true))
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      const processFrame = (frame: string): void => {
        let eventName = "message"
        let data = ""
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim()
          else if (line.startsWith("data:")) data += line.slice(5).trim()
        }
        if (!data) return
        if (eventName === "collaboration") {
          const event = JSON.parse(data) as CollaborationEvent
          latest = Math.max(latest, event.revision)
          handlers.onEvent(event)
        } else if (eventName === "reset") {
          const reset = JSON.parse(data) as { currentRevision?: number }
          handlers.onReset(Math.max(0, Number(reset.currentRevision ?? 0)))
        }
      }
      while (true) {
        const { done, value } = await reader.read()
        buffer += decoder.decode(value, { stream: !done })
        buffer = buffer.replace(/\r\n/g, "\n")
        let boundary = buffer.indexOf("\n\n")
        while (boundary >= 0) {
          processFrame(buffer.slice(0, boundary))
          buffer = buffer.slice(boundary + 2)
          boundary = buffer.indexOf("\n\n")
        }
        if (done) break
      }
      if (buffer.trim()) processFrame(buffer)
      return latest
    } catch (error) {
      if (combined.aborted) {
        const cancelled = signal?.aborted === true
        throw new ApiClientError(apiError(cancelled ? "request_cancelled" : "request_timeout", cancelled ? "Request cancelled" : "Request timed out", !cancelled))
      }
      throw error
    } finally {
      globalThis.clearTimeout(timer)
    }
  }

  exportAccount(signal?: AbortSignal): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("/v1/account/export", { signal })
  }

  deleteAccount(confirmation: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; deleted: boolean }> {
    return this.request("/v1/account", { method: "DELETE", body: JSON.stringify({ confirmation }), signal })
  }

  listTeamMembers(signal?: AbortSignal): Promise<TeamMemberList> {
    return this.request<TeamMemberList>("/v1/team/members", { signal })
  }

  createTeamInvite(request: TeamInviteCreateRequest, signal?: AbortSignal): Promise<TeamInvite> {
    return this.request<TeamInvite>("/v1/team/invites", { method: "POST", body: JSON.stringify(request), signal })
  }

  acceptTeamInvite(request: TeamInviteAcceptRequest, signal?: AbortSignal): Promise<AuthSession> {
    return this.request<AuthSession>("/v1/team/invites:accept", { method: "POST", body: JSON.stringify(request), signal })
  }

  updateTeamMemberRole(memberId: string, role: "admin" | "member", signal?: AbortSignal): Promise<TeamMemberList> {
    return this.request<TeamMemberList>(`/v1/team/members/${encodeURIComponent(memberId)}`, { method: "PATCH", body: JSON.stringify({ role }), signal })
  }

  removeTeamMember(memberId: string, signal?: AbortSignal): Promise<{ protocolVersion: "1.0"; removed: boolean }> {
    return this.request(`/v1/team/members/${encodeURIComponent(memberId)}`, { method: "DELETE", signal })
  }

  listResourcePermissions(resourceType: ResourcePermissionMutation["resourceType"], resourceId: string, signal?: AbortSignal): Promise<ResourcePermissionList> {
    return this.request<ResourcePermissionList>(`/v1/permissions/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceId)}`, { signal })
  }

  setResourcePermission(request: ResourcePermissionMutation, signal?: AbortSignal): Promise<ResourcePermissionList> {
    return this.request<ResourcePermissionList>("/v1/permissions", { method: "POST", body: JSON.stringify(request), signal })
  }

  listCloudGraphs(signal?: AbortSignal): Promise<CloudGraphList> {
    return this.listGraphs(signal)
  }

  syncCloudGraph(recordId: string, request: CloudGraphSyncRequest, signal?: AbortSignal): Promise<CloudGraphSyncResult> {
    return this.request<CloudGraphSyncResult>(`/v1/graphs/${encodeURIComponent(recordId)}/sync`, { method: "POST", body: JSON.stringify(request), signal }, [409])
  }

  getGraphProjection(recordId: string, request: Record<string, unknown>, signal?: AbortSignal): Promise<GraphProjection> {
    return this.request<GraphProjection>(`/v1/graphs/${encodeURIComponent(recordId)}/projection`, {
      method: "POST",
      body: JSON.stringify(request),
      signal
    })
  }

  getGraphTimeline(timelineKey: string, query: GraphTimelineQuery, signal?: AbortSignal): Promise<GraphTimeline> {
    return this.request<GraphTimeline>(`/v1/timelines/${encodeURIComponent(timelineKey)}/query`, {
      method: "POST",
      body: JSON.stringify(query),
      signal
    })
  }

  listGraphViews(recordId: string, signal?: AbortSignal): Promise<GraphViewList> {
    return this.request<GraphViewList>(`/v1/graphs/${encodeURIComponent(recordId)}/views`, { signal })
  }

  saveGraphView(recordId: string, view: GraphViewSaveRequest, signal?: AbortSignal): Promise<GraphViewState> {
    return this.request<GraphViewState>(`/v1/graphs/${encodeURIComponent(recordId)}/views`, { method: "POST", body: JSON.stringify(view), signal })
  }

  restoreGraphView(recordId: string, viewId: string, signal?: AbortSignal): Promise<GraphViewRestore> {
    return this.request<GraphViewRestore>(`/v1/graphs/${encodeURIComponent(recordId)}/views/${encodeURIComponent(viewId)}`, { signal })
  }

  deleteGraphView(recordId: string, viewId: string, signal?: AbortSignal): Promise<GraphViewMutationResult> {
    return this.request<GraphViewMutationResult>(`/v1/graphs/${encodeURIComponent(recordId)}/views/${encodeURIComponent(viewId)}`, { method: "DELETE", signal })
  }

  getTask(taskId: string, signal?: AbortSignal): Promise<Task> {
    return this.request<Task>(`/v1/tasks/${encodeURIComponent(taskId)}`, { signal })
  }

  createTask(type: string, input: Record<string, unknown>, signal?: AbortSignal): Promise<Task> {
    return this.request<Task>("/v1/tasks", { method: "POST", body: JSON.stringify({ type, input }), signal })
  }

  cancelTask(taskId: string, signal?: AbortSignal): Promise<Task> {
    return this.request<Task>(`/v1/tasks/${encodeURIComponent(taskId)}:cancel`, { method: "POST", body: "{}", signal })
  }

  getTaskResult<T extends Record<string, unknown>>(taskId: string, signal?: AbortSignal): Promise<T> {
    return this.request<T>(`/v1/tasks/${encodeURIComponent(taskId)}/result`, { signal })
  }

  async #requestOnce<T>(path: string, init: RequestInit, acceptedStatuses: readonly number[]): Promise<T> {
    const timeout = new AbortController()
    const timer = globalThis.setTimeout(() => timeout.abort("timeout"), this.#timeoutMs)
    const signal = init.signal ? AbortSignal.any([init.signal, timeout.signal]) : timeout.signal
    const headers = new Headers(init.headers)
    headers.set("Accept", "application/json")
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")
    headers.set("X-OmniLit-Protocol-Version", PROTOCOL_VERSION)
    const token = this.#accessToken?.()
    if (token) headers.set("Authorization", `Bearer ${token}`)
    try {
      const response = await this.#transport(new Request(`${this.#baseUrl}${path}`, { ...init, headers, signal }))
      const body = await response.json().catch(() => undefined) as unknown
      if (!response.ok && !acceptedStatuses.includes(response.status)) {
        const candidate = body as Partial<APIError> | undefined
        throw new ApiClientError(apiError(
          candidate?.code ?? `http_${response.status}`,
          candidate?.message ?? `Request failed with HTTP ${response.status}`,
          candidate?.retryable ?? response.status >= 500,
          candidate?.details ?? { status: response.status }
        ))
      }
      return body as T
    } catch (error) {
      if (signal.aborted) {
        const cancelled = init.signal?.aborted === true
        throw new ApiClientError(apiError(cancelled ? "request_cancelled" : "request_timeout", cancelled ? "Request cancelled" : "Request timed out", !cancelled))
      }
      throw error
    } finally {
      globalThis.clearTimeout(timer)
    }
  }
}

export type FixtureRoute = unknown | ((request: Request) => unknown | Promise<unknown>)

export function createFixtureTransport(routes: Record<string, FixtureRoute>): ApiTransport {
  return async (request) => {
    const path = new URL(request.url).pathname
    const routeKey = path in routes ? path : Object.keys(routes).find((key) => key.endsWith("/*") && path.startsWith(key.slice(0, -1)))
    if (!routeKey) {
      return Response.json(apiError("not_found", `No fixture for ${path}`, false), { status: 404 })
    }
    const route = routes[routeKey]
    const result = typeof route === "function" ? await route(request) : route
    return result instanceof Response ? result : Response.json(result)
  }
}
