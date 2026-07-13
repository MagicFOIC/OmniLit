import { ApiClient, createFixtureTransport } from "@omnilit/api-client"
import { createPlatformBridge } from "@omnilit/platform-bridge"
import { GRAPH_SCHEMA_VERSION, PROTOCOL_VERSION, type AuditEventPage, type AuthSession, type BusinessSettings, type BusinessSettingsUpdateRequest, type CloudGraphSyncRequest, type CloudGraphSyncResult, type CloudServiceMetrics, type CollaborationEvent, type CollaborationMutationRequest, type GraphData, type GraphNeighborPage, type GraphProjection, type GraphTimeline, type GraphTimelineQuery, type GraphViewList, type GraphViewMutationResult, type GraphViewRestore, type GraphViewSaveRequest, type GraphViewState, type LibraryMutationRequest, type LibraryMutationResult, type LibraryPage, type LibraryQuery, type LibraryRecordDetail, type LibraryRecordSummary, type LibraryState, type LibrarySyncRequest, type LibrarySyncResult, type LiteraturePage, type LiteratureRow, type PublicSubmission, type PublicSubmissionCreateRequest, type PublicSubmissionList, type ResearchBriefRequest, type ResearchBriefResult, type ResearchStatistics, type ResearchStatisticsBucket, type ResearchWorkspace, type ResourcePermissionList, type ResourcePermissionMutation, type ShareCreateRequest, type ShareLink, type Task, type TeamInviteCreateRequest, type TeamMemberList, type UserAccount } from "@omnilit/shared-schema"
import demoGraphJson from "@omnilit/shared-schema/fixtures/shared-graph-v1.json"
import demoTimelineJson from "@omnilit/shared-schema/fixtures/shared-timeline-v1.json"
import { cloudAccessToken, readCloudSession } from "./cloudSession"
import { configureWebDiagnosticSink } from "./diagnostics"
import { readLocalAgentConnection } from "./localAgentConfig"

export const demoGraph = demoGraphJson as GraphData
export const demoTimeline = demoTimelineJson as GraphTimeline

const demoLibraryRecords: LibraryRecordSummary[] = [
  { recordId: "paper-001", title: "Contract-First Knowledge Graphs", authorsText: "Ada Example, Lin Researcher", source: "OpenAlex", year: "2024", publicationDate: "2024-05-20", journalTitle: "Journal of Research Systems", journalType: "field_journal", journalTypeLabel: "专业领域", impactFactorText: "8.2", keywordsText: "knowledge graph; contracts", summaryText: "A contract-first approach to interoperable research graphs.", topicTagsText: "Knowledge Graph", pdfStatus: "downloaded", relevanceLabel: "严格相关", relevanceScore: 0.96, matchedKeywordsText: "knowledge graph", keywordGroupKeys: ["knowledge graph"], downloaded: true, hasExtraction: true },
  { recordId: "paper-002", title: "Evidence-Aware Scientific Discovery", authorsText: "Mira Chen", source: "Crossref", year: "2022", publicationDate: "2022-08-10", journalTitle: "Open Science", journalType: "oa_journal", journalTypeLabel: "开放获取", impactFactorText: "4.1", keywordsText: "evidence; discovery", summaryText: "Evidence provenance for scientific discovery systems.", topicTagsText: "Evidence", pdfStatus: "no_candidate", relevanceLabel: "均衡相关", relevanceScore: 0.78, matchedKeywordsText: "evidence", keywordGroupKeys: ["evidence"], downloaded: false, hasExtraction: false }
]

let fixtureLibraryState: LibraryState = { protocolVersion: PROTOCOL_VERSION, revision: 0, updatedAt: "", syncState: "local_only", collections: [{ id: "to_read", name: "待读精读", builtIn: true, recordCount: 0 }, { id: "core", name: "核心文献", builtIn: true, recordCount: 0 }], favorites: {}, workspace: { compareRecordIds: ["paper-001", "paper-002"] } }
let fixtureBusinessSettings: BusinessSettings = { protocolVersion: PROTOCOL_VERSION, revision: 0, themeMode: "system", density: "comfortable", reduceMotion: false, highContrast: false, startPage: "graph", defaultLibrarySort: "relevance_desc", aiEvidenceLimit: 4, aiEndpoint: "", aiModel: "", allowRemoteResearchContent: false, aiCredentialConfigured: false, updatedAt: "" }

let fixtureCloudAccount: UserAccount = { protocolVersion: PROTOCOL_VERSION, id: "fixture-user", tenantId: "fixture-tenant", workspaceId: "fixture-workspace", accountStatus: "active", email: "researcher@example.com", displayName: "演示研究者", roles: ["owner"], dataControls: { uploadLocalPdfs: false, syncAnnotations: false, syncFullText: false, useCloudAi: false, retainCloudTaskData: false, allowTeamAccess: false, allowShareLinks: false, shareDiagnostics: false }, createdAt: "2026-01-01T00:00:00Z" }
let fixtureCloudRevision = 0
let fixtureCloudState = fixtureLibraryState
let fixtureCloudGraphRevision = 0
let fixtureCloudGraph = demoGraph
const fixtureCloudSession = (): AuthSession => ({ protocolVersion: PROTOCOL_VERSION, accessToken: "fixture-session", expiresAt: "2099-01-01T00:00:00Z", user: fixtureCloudAccount })
const fixtureTeam: TeamMemberList = { protocolVersion: PROTOCOL_VERSION, tenantId: "fixture-tenant", members: [{ id: "fixture-user", email: "researcher@example.com", displayName: "演示研究者", role: "owner", joinedAt: "2026-01-01T00:00:00Z" }] }
let fixturePermissions: ResourcePermissionList = { protocolVersion: PROTOCOL_VERSION, resourceType: "library_state", resourceId: "current", permissions: [] }
const fixtureCloudLibrary = (): LibrarySyncResult => ({ protocolVersion: PROTOCOL_VERSION, status: "synced", cloudRevision: fixtureCloudRevision, syncedAt: fixtureCloudRevision ? new Date().toISOString() : "", serverState: fixtureCloudState })

async function fixtureCloudSync(request: Request): Promise<LibrarySyncResult> {
  const input = await request.json() as LibrarySyncRequest
  if (input.baseCloudRevision !== fixtureCloudRevision) return { ...fixtureCloudLibrary(), status: "conflict", conflictId: "fixture-conflict" }
  fixtureCloudRevision += 1
  fixtureCloudState = { ...input.state, syncState: "synced" }
  return fixtureCloudLibrary()
}

async function fixtureCloudControls(request: Request): Promise<UserAccount> {
  fixtureCloudAccount = { ...fixtureCloudAccount, dataControls: await request.json() as UserAccount["dataControls"] }
  return fixtureCloudAccount
}

async function fixturePublicSubmissions(request: Request): Promise<PublicSubmissionList | PublicSubmission> {
  if (request.method === "GET") return { protocolVersion: PROTOCOL_VERSION, submissions: [] }
  const input = await request.json() as PublicSubmissionCreateRequest
  return { protocolVersion: PROTOCOL_VERSION, id: "fixture-submission", status: "draft", revision: 1, sourceResourceId: input.sourceResourceId, record: input.record, contentHash: "fixture", license: input.license, publicDisplayName: input.publicDisplayName, reviewNote: "", createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }
}

async function fixtureCloudShare(request: Request): Promise<ShareLink> {
  const input = await request.json() as ShareCreateRequest
  return { protocolVersion: PROTOCOL_VERSION, id: "fixture-share", resourceType: input.resourceType, resourceId: input.resourceId, permission: input.permission, createdAt: new Date().toISOString(), expiresAt: "2099-01-01T00:00:00Z", revoked: false, url: "https://fixture.omnilit.invalid/#/share/one-time-token" }
}

async function fixtureTeamInvite(request: Request) {
  const input = await request.json() as TeamInviteCreateRequest
  return { protocolVersion: PROTOCOL_VERSION, id: "fixture-invite", tenantId: "fixture-tenant", email: input.email, role: input.role, createdAt: new Date().toISOString(), expiresAt: "2099-01-01T00:00:00Z", accepted: false, url: "https://fixture.omnilit.invalid/#/invite/fixture-invitation-token-value" }
}

async function fixturePermissionMutation(request: Request): Promise<ResourcePermissionList> {
  const input = await request.json() as ResourcePermissionMutation
  const remaining = fixturePermissions.permissions.filter((item) => !(item.principalType === input.principalType && item.principalId === input.principalId))
  fixturePermissions = { ...fixturePermissions, permissions: input.permission === "none" ? remaining : [...remaining, { id: "fixture-permission", resourceType: input.resourceType, resourceId: input.resourceId, principalType: input.principalType, principalId: input.principalId, permission: input.permission, updatedAt: new Date().toISOString() }] }
  return fixturePermissions
}

async function fixtureCloudGraphSync(request: Request): Promise<CloudGraphSyncResult> {
  const input = await request.json() as CloudGraphSyncRequest
  if (input.baseCloudRevision !== fixtureCloudGraphRevision) return { protocolVersion: PROTOCOL_VERSION, status: "conflict", recordId: input.graph.recordId, cloudRevision: fixtureCloudGraphRevision, syncedAt: "", serverGraph: fixtureCloudGraph, conflictId: "fixture-graph-conflict" }
  fixtureCloudGraphRevision += 1
  fixtureCloudGraph = input.graph
  return { protocolVersion: PROTOCOL_VERSION, status: "synced", recordId: input.graph.recordId, cloudRevision: fixtureCloudGraphRevision, syncedAt: new Date().toISOString(), serverGraph: fixtureCloudGraph }
}

async function fixtureLibrary(request: Request): Promise<LibraryPage> {
  const query = await request.json() as LibraryQuery
  const needle = (query.query ?? "").toLocaleLowerCase()
  let records = demoLibraryRecords.filter((record) => !needle || `${record.title} ${record.authorsText} ${record.summaryText}`.toLocaleLowerCase().includes(needle))
  if (query.collectionId && query.collectionId !== "all") records = records.filter((record) => (fixtureLibraryState.favorites[record.recordId] ?? []).includes(query.collectionId ?? ""))
  if (query.pdfStatus === "downloaded") records = records.filter((record) => record.downloaded)
  if (query.sort === "year_asc") records = [...records].sort((left, right) => Number(left.year) - Number(right.year))
  else if (query.sort === "year_desc") records = [...records].sort((left, right) => Number(right.year) - Number(left.year))
  const offset = query.offset ?? 0
  const limit = query.limit ?? 100
  const page = records.slice(offset, offset + limit)
  return { protocolVersion: PROTOCOL_VERSION, status: page.length ? "ready" : "empty", records: page, offset, nextOffset: offset + page.length, total: records.length, hasMore: offset + page.length < records.length, cacheAvailable: true, facets: { relevance: { strict: 1, balanced: 1 }, pdfStatus: { downloaded: 1, no_candidate: 1 }, journalType: { field_journal: 1, oa_journal: 1 }, keywordGroups: { "knowledge graph": 1, evidence: 1 } }, message: page.length ? "" : "No literature records match the current filters." }
}

async function fixtureLibraryMutation(request: Request): Promise<LibraryMutationResult> {
  const mutation = await request.json() as LibraryMutationRequest
  if (mutation.expectedRevision !== fixtureLibraryState.revision) throw new Error("Library state conflict")
  const favorites = { ...fixtureLibraryState.favorites }
  const compare = [...fixtureLibraryState.workspace.compareRecordIds]
  let collections = [...fixtureLibraryState.collections]
  let changed = true
  if (mutation.action === "toggle_collection_record" && mutation.recordId && mutation.collectionId) {
    const values = [...(favorites[mutation.recordId] ?? [])]
    const nextValues = values.includes(mutation.collectionId) ? values.filter((value) => value !== mutation.collectionId) : [...values, mutation.collectionId]
    if (nextValues.length) favorites[mutation.recordId] = nextValues
    else delete favorites[mutation.recordId]
  } else if (mutation.action === "toggle_compare_record" && mutation.recordId) {
    if (compare.includes(mutation.recordId)) compare.splice(compare.indexOf(mutation.recordId), 1)
    else if (compare.length < 4) compare.push(mutation.recordId)
    else throw new Error("Compare workspace is full")
  } else if (mutation.action === "clear_compare") compare.splice(0)
  else if (mutation.action === "create_collection" && mutation.name) collections = [...collections, { id: `collection-${collections.length + 1}`, name: mutation.name, builtIn: false, recordCount: 0 }]
  else if (mutation.action === "rename_collection" && mutation.collectionId && mutation.name) collections = collections.map((collection) => collection.id === mutation.collectionId ? { ...collection, name: mutation.name ?? collection.name } : collection)
  else if (mutation.action === "delete_collection" && mutation.collectionId) {
    collections = collections.filter((collection) => collection.id !== mutation.collectionId || collection.builtIn)
    Object.keys(favorites).forEach((recordId) => {
      favorites[recordId] = (favorites[recordId] ?? []).filter((value) => value !== mutation.collectionId)
      if (!favorites[recordId]?.length) delete favorites[recordId]
    })
  } else if (mutation.action === "remove_compare_record" && mutation.recordId) {
    if (compare.includes(mutation.recordId)) compare.splice(compare.indexOf(mutation.recordId), 1)
    else changed = false
  }
  else changed = false
  const counts = new Map<string, number>()
  Object.values(favorites).flat().forEach((id) => counts.set(id, (counts.get(id) ?? 0) + 1))
  collections = collections.map((collection) => ({ ...collection, recordCount: counts.get(collection.id) ?? 0 }))
  fixtureLibraryState = { ...fixtureLibraryState, revision: changed ? fixtureLibraryState.revision + 1 : fixtureLibraryState.revision, updatedAt: changed ? new Date().toISOString() : fixtureLibraryState.updatedAt, collections, favorites, workspace: { compareRecordIds: compare } }
  return { protocolVersion: PROTOCOL_VERSION, changed, message: changed ? "updated" : "unchanged", state: fixtureLibraryState }
}

function fixtureLibraryDetail(request: Request): LibraryRecordDetail {
  const recordId = decodeURIComponent(new URL(request.url).pathname.split("/records/")[1] ?? "")
  const record = demoLibraryRecords.find((item) => item.recordId === recordId)
  if (!record) throw new Error("Literature record not found")
  return { ...record, protocolVersion: PROTOCOL_VERSION, abstract: record.summaryText, doi: recordId === "paper-001" ? "10.1000/contract-graphs" : "", matchedFieldsText: "title, abstract", relevanceReasonsText: "Matched shared fixture keywords." }
}

function fixtureResearchWorkspace(): ResearchWorkspace {
  const records = fixtureLibraryState.workspace.compareRecordIds.flatMap((recordId) => {
    const record = demoLibraryRecords.find((item) => item.recordId === recordId)
    return record ? [{ recordId, title: record.title, authorsText: record.authorsText, year: record.year, journalTitle: record.journalTitle, source: record.source, abstract: record.summaryText, keywordsText: record.keywordsText, pdfStatus: record.pdfStatus, downloaded: record.downloaded, hasExtraction: record.hasExtraction, collectionIds: fixtureLibraryState.favorites[recordId] ?? [] }] : []
  })
  return { protocolVersion: PROTOCOL_VERSION, status: records.length ? "ready" : "empty", records, compareLimit: 4, message: records.length ? "共享比较工作区已就绪。" : "从文献库选择最多四篇文献开始比较。" }
}

function fixtureBuckets(values: string[], fallback = "未知"): ResearchStatisticsBucket[] {
  const counts = new Map<string, number>()
  values.forEach((value) => counts.set(value || fallback, (counts.get(value || fallback) ?? 0) + 1))
  return [...counts.entries()].map(([key, count]) => ({ key, label: key, count })).sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
}

function fixtureResearchStatistics(): ResearchStatistics {
  const keywords = demoLibraryRecords.flatMap((record) => record.keywordsText.split(/[;,]/).map((value) => value.trim()).filter(Boolean))
  const collectionNames = new Map(fixtureLibraryState.collections.map((collection) => [collection.id, collection.name]))
  const collections = Object.values(fixtureLibraryState.favorites).flat().map((id) => collectionNames.get(id) ?? id)
  return { protocolVersion: PROTOCOL_VERSION, status: demoLibraryRecords.length ? "ready" : "empty", totalRecords: demoLibraryRecords.length, downloadedRecords: demoLibraryRecords.filter((record) => record.downloaded).length, extractedRecords: demoLibraryRecords.filter((record) => record.hasExtraction).length, compareRecords: fixtureLibraryState.workspace.compareRecordIds.length, yearBuckets: fixtureBuckets(demoLibraryRecords.map((record) => record.year)), sourceBuckets: fixtureBuckets(demoLibraryRecords.map((record) => record.source)), pdfStatusBuckets: fixtureBuckets(demoLibraryRecords.map((record) => record.pdfStatus)), topKeywords: fixtureBuckets(keywords).slice(0, 12), collectionBuckets: fixtureBuckets(collections), message: "基于当前演示文献目录聚合。" }
}

async function fixtureBusinessSettingsRoute(request: Request): Promise<BusinessSettings> {
  if (request.method === "GET") return fixtureBusinessSettings
  const input = await request.json() as BusinessSettingsUpdateRequest
  if (input.expectedRevision !== fixtureBusinessSettings.revision) throw new Error("Business settings conflict")
  fixtureBusinessSettings = { ...input, revision: fixtureBusinessSettings.revision + 1, aiCredentialConfigured: false, updatedAt: new Date().toISOString() }
  return fixtureBusinessSettings
}

const seedId = demoGraph.nodes.find((node) => node.type === "paper")?.id
const initialDemoGraph: GraphData = { ...demoGraph, nodes: demoGraph.nodes.filter((node) => node.id === seedId), edges: [], metadata: { ...demoGraph.metadata, projection: "seed", timelineKey: "demo-timeline" } }

function fixtureNeighbors(request: Request): GraphNeighborPage {
  const url = new URL(request.url)
  const encoded = url.pathname.split("/nodes/")[1]?.replace(/:neighbors$/, "") ?? ""
  const nodeId = decodeURIComponent(encoded)
  const mode = url.searchParams.get("mode") ?? "all"
  const offset = Math.max(0, Number(url.searchParams.get("offset") ?? 0))
  const limit = Math.max(1, Number(url.searchParams.get("limit") ?? 12))
  const relationTypes: Record<string, string[]> = { references: ["CITES"], cited_by: ["CITES"], authors: ["AUTHOR_OF", "WRITTEN_BY"], topics: ["HAS_TOPIC", "MENTIONS", "HAS_KEYWORD"] }
  const incident = demoGraph.edges.filter((edge) => {
    if (edge.source !== nodeId && edge.target !== nodeId) return false
    if (mode === "references") return edge.source === nodeId && edge.type === "CITES"
    if (mode === "cited_by") return edge.target === nodeId && edge.type === "CITES"
    return mode === "all" || (relationTypes[mode] ?? []).includes(edge.type)
  })
  const neighborIds = incident.map((edge) => edge.source === nodeId ? edge.target : edge.source)
  const ids = neighborIds.slice(offset, offset + limit)
  const edges = incident.filter((edge) => ids.includes(edge.source === nodeId ? edge.target : edge.source))
  return { protocolVersion: PROTOCOL_VERSION, schemaVersion: GRAPH_SCHEMA_VERSION, recordId: demoGraph.recordId, nodeId, relationMode: mode as GraphNeighborPage["relationMode"], status: ids.length ? "ready" : "empty", nodes: demoGraph.nodes.filter((node) => ids.includes(node.id)), edges, offset, nextOffset: offset + ids.length, revealed: ids.length, total: neighborIds.length, hasMore: offset + ids.length < neighborIds.length }
}

async function fixtureLiterature(request: Request): Promise<LiteraturePage> {
  const body = await request.json() as { visibleNodeIds?: string[]; selectedNodeId?: string }
  const visible = new Set(body.visibleNodeIds ?? [])
  const rows: LiteratureRow[] = demoGraph.nodes.filter((node) => visible.has(node.id) && ["paper", "citation"].includes(node.type)).map((node) => {
    const attributes = node.attributes as Record<string, unknown>
    return { nodeId: node.id, recordId: String(attributes.recordId ?? ""), kind: node.type as "paper" | "citation", title: String(attributes.title ?? node.label), year: String(attributes.year ?? demoGraph.paper?.year ?? ""), authors: Array.isArray(attributes.authors) ? attributes.authors.join(", ") : String(attributes.authors ?? demoGraph.paper?.authors?.join(", ") ?? ""), venue: String(attributes.venue ?? ""), citations: 0, importance: node.metrics?.importance ?? 0.5, confidence: node.metrics?.confidence ?? 1, evidenceCount: node.evidence?.length ?? 0, selected: body.selectedNodeId === node.id, hovered: false, searchText: node.label, relevance: node.metrics?.importance ?? 0.5 }
  })
  return { protocolVersion: PROTOCOL_VERSION, recordId: demoGraph.recordId, rows, offset: 0, nextOffset: rows.length, total: rows.length, hasMore: false }
}

function fixtureProjection(): GraphProjection {
  return {
    protocolVersion: PROTOCOL_VERSION, schemaVersion: GRAPH_SCHEMA_VERSION, recordId: demoGraph.recordId,
    graph: demoGraph, layout: {},
    status: { status: "ready", level: "detail", layoutStyle: "academic", spatialCulling: false, budget: demoGraph.nodes.length, totalSemanticNodes: demoGraph.nodes.length, viewportCandidates: demoGraph.nodes.length, renderedNodes: demoGraph.nodes.length, realNodes: demoGraph.nodes.length, aggregateNodes: 0, aggregatedNodes: 0, culledNodes: 0, renderedEdges: demoGraph.edges.length, totalSemanticEdges: demoGraph.edges.length, degraded: false, latencyMs: 0, latencyBudgetMs: 120, budgetExceeded: false, performanceStatus: "ready", message: `detail 层级：渲染 ${demoGraph.nodes.length} / ${demoGraph.nodes.length} 个节点` }
  }
}

async function fixtureTimeline(request: Request): Promise<GraphTimeline> {
  const query = await request.json() as GraphTimelineQuery
  const years = demoTimeline.yearRange.years
  const minimumYear = years[0] ?? demoTimeline.yearRange.minimum
  const maximumYear = years[years.length - 1] ?? demoTimeline.yearRange.maximum
  const requestedStart = query.startYear ?? minimumYear
  const requestedEnd = query.endYear ?? maximumYear
  const startYear = Math.min(requestedStart, requestedEnd)
  const endYear = Math.max(requestedStart, requestedEnd)
  const rangeYears = years.filter((year) => year >= startYear && year <= endYear)
  const targetPlayback = query.playbackYear ?? endYear
  const playbackYear = rangeYears.reduce((best, year) => Math.abs(year - targetPlayback) < Math.abs(best - targetPlayback) ? year : best, rangeYears[rangeYears.length - 1] ?? endYear)
  const effectiveEndYear = Math.min(endYear, playbackYear)
  const events = demoTimeline.events.filter((event) => event.year >= startYear && event.year <= effectiveEndYear)
  const paperIds = new Set(events.flatMap((event) => event.papers.map((paper) => paper.nodeId)))
  const topicIds = new Set(demoTimeline.graph.edges.filter((edge) => edge.type === "HAS_TOPIC" && paperIds.has(edge.source)).map((edge) => edge.target))
  const nodeIds = new Set([...paperIds, ...topicIds])
  const nodes = demoTimeline.graph.nodes.filter((node) => nodeIds.has(node.id))
  const edges = demoTimeline.graph.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
  const keyPaths = demoTimeline.keyPaths.flatMap((path) => {
    const pairs = path.paperIds.flatMap((paperId, index) => {
      const year = path.years[index]
      return year !== undefined && year >= startYear && year <= effectiveEndYear ? [{ paperId, year }] : []
    })
    if (pairs.length < 2) return []
    const pathYears = pairs.map(({ year }) => year)
    return [{ ...path, label: `${path.label}（${startYear}–${effectiveEndYear}）`, paperIds: pairs.map(({ paperId }) => paperId), years: pathYears, length: pairs.length, yearSpan: Math.max(...pathYears) - Math.min(...pathYears), explanation: `当前窗口保留 ${pairs.length} 篇论文，顺序与原始有向引用链一致。`, originalExplanation: path.explanation }]
  })
  const renderedNodes = nodes.length
  const renderedEdges = edges.length
  return {
    ...demoTimeline,
    status: events.length ? "ready" : "empty",
    selection: { startYear, endYear, playbackYear, effectiveEndYear },
    events,
    topicSeries: demoTimeline.topicSeries.map((series) => ({ ...series, points: series.points.filter((point) => point.year >= startYear && point.year <= effectiveEndYear) })).filter((series) => series.points.some((point) => point.count > 0)),
    keyPaths,
    turningPoints: demoTimeline.turningPoints.filter((point) => point.year >= startYear && point.year <= effectiveEndYear),
    graph: { ...demoTimeline.graph, nodes, edges, metadata: { ...demoTimeline.graph.metadata, time_start: startYear, time_end: effectiveEndYear } },
    projection: { ...demoTimeline.projection, totalSemanticNodes: renderedNodes, viewportCandidates: renderedNodes, renderedNodes, realNodes: renderedNodes, renderedEdges, totalSemanticEdges: renderedEdges, message: `normal 层级：渲染 ${renderedNodes} / ${renderedNodes} 个节点` }
  }
}

let fixtureViews: GraphViewState[] = []

async function fixtureViewCollection(request: Request): Promise<GraphViewList | GraphViewState> {
  if (request.method === "GET") return { protocolVersion: PROTOCOL_VERSION, recordId: demoGraph.recordId, views: fixtureViews.map(({ id, name, recordId, createdAt, updatedAt, graphFingerprint }) => ({ id, name, recordId, createdAt, updatedAt, graphFingerprint })) }
  const body = await request.json() as GraphViewSaveRequest
  const existing = fixtureViews.find((view) => view.name.toLocaleLowerCase() === body.name.toLocaleLowerCase())
  const now = new Date().toISOString()
  const view: GraphViewState = { ...body, protocolVersion: PROTOCOL_VERSION, version: 2, id: existing?.id ?? `view-${fixtureViews.length + 1}`, recordId: demoGraph.recordId, createdAt: existing?.createdAt ?? now, updatedAt: now, graphFingerprint: body.graphFingerprint ?? "fixture" , path: body.path ?? { startId: "", endId: "", directed: false, relationFilter: "ALL" } }
  fixtureViews = existing ? fixtureViews.map((item) => item.id === existing.id ? view : item) : [...fixtureViews, view]
  return view
}

function fixtureViewItem(request: Request): GraphViewRestore | GraphViewMutationResult {
  const viewId = decodeURIComponent(new URL(request.url).pathname.split("/views/")[1] ?? "")
  const view = fixtureViews.find((item) => item.id === viewId)
  if (!view) throw new Error("Saved view not found")
  if (request.method === "DELETE") {
    fixtureViews = fixtureViews.filter((item) => item.id !== viewId)
    return { protocolVersion: PROTOCOL_VERSION, recordId: demoGraph.recordId, viewId, deleted: true }
  }
  const nodeIds = new Set(view.exploration.nodeIds)
  const edgeIds = new Set(view.exploration.edgeIds)
  const nodes = nodeIds.size ? demoGraph.nodes.filter((node) => nodeIds.has(node.id)) : initialDemoGraph.nodes
  const restoredNodeIds = new Set(nodes.map((node) => node.id))
  const edges = demoGraph.edges.filter((edge) => restoredNodeIds.has(edge.source) && restoredNodeIds.has(edge.target) && (!edgeIds.size || edgeIds.has(edge.id)))
  return { protocolVersion: PROTOCOL_VERSION, recordId: demoGraph.recordId, view, graph: { ...demoGraph, nodes, edges, viewState: view, metadata: { ...demoGraph.metadata, projection: "saved-view" } }, reconciliation: { missingNodes: 0, missingEdges: 0 } }
}

const agentUrl = import.meta.env.VITE_LOCAL_AGENT_URL as string | undefined
const agentToken = import.meta.env.VITE_LOCAL_AGENT_TOKEN as string | undefined
const sessionAgent = readLocalAgentConnection()
const hashQuery = typeof window === "undefined" ? "" : (window.location.hash.split("?")[1] ?? "")
const embeddedParameters = new URLSearchParams(hashQuery)
const loopbackHost = typeof window !== "undefined" && ["127.0.0.1", "::1", "localhost"].includes(window.location.hostname)
export const qtEmbedded = embeddedParameters.get("embedded") === "1" && loopbackHost
export const localAgentConfigured = qtEmbedded || Boolean(sessionAgent || (agentUrl && agentToken))
const cloudApiUrl = import.meta.env.VITE_CLOUD_API_URL as string | undefined
export const cloudApiConfigured = Boolean(cloudApiUrl)
export const activeTimelineKey = embeddedParameters.get("timelineKey") || (import.meta.env.VITE_TIMELINE_KEY as string | undefined) || (localAgentConfigured || cloudApiConfigured ? "" : "demo-timeline")

export const apiClient = localAgentConfigured
  ? new ApiClient({
      baseUrl: qtEmbedded ? window.location.origin : sessionAgent?.baseUrl ?? agentUrl as string,
      accessToken: qtEmbedded ? undefined : () => sessionAgent?.token ?? agentToken,
      timeoutMs: 15_000,
      retries: 1
    })
  : new ApiClient({ baseUrl: "https://fixture.omnilit.invalid", timeoutMs: 2_000, retries: 0, transport: createFixtureTransport({
      "/v1/graphs/paper-001": initialDemoGraph,
      "/v1/library/query": fixtureLibrary,
      "/v1/library/records/*": fixtureLibraryDetail,
      "/v1/library/state": () => fixtureLibraryState,
      "/v1/library/state/mutations": fixtureLibraryMutation,
      "/v1/workspace": fixtureResearchWorkspace,
      "/v1/statistics": fixtureResearchStatistics,
      "/v1/settings/business": fixtureBusinessSettingsRoute,
      "/v1/tasks": fixtureCloudTaskCollection,
      "/v1/tasks/*": fixtureCloudTaskItem,
      "/v1/graphs/paper-001/nodes/paper%3Apaper-001:neighbors": fixtureNeighbors,
      "/v1/graphs/paper-001/projection": fixtureProjection,
      "/v1/timelines/demo-timeline/query": fixtureTimeline,
      "/v1/graphs/paper-001/views": fixtureViewCollection,
      "/v1/graphs/paper-001/views/*": fixtureViewItem,
      "/v1/graphs/paper-001/literature/query": fixtureLiterature
    }) })

const fixtureAudit: AuditEventPage = { protocolVersion: PROTOCOL_VERSION, events: [{ id: "audit-1", occurredAt: "2026-01-01T00:00:00Z", actorId: "fixture-user", action: "account.login", resourceType: "session", resourceId: "self", requestId: "fixture-request" }] }
let fixtureCloudTask: Task = { protocolVersion: PROTOCOL_VERSION, id: "fixture-cloud-task", type: "graph.audit", status: "queued", cancellable: true, progress: { completed: 0, total: 1, unit: "task", message: "Queued" }, createdAt: "2026-01-01T00:00:00Z" }
const fixtureCloudMetrics = (): CloudServiceMetrics => ({ protocolVersion: PROTOCOL_VERSION, status: "ready", uptimeSeconds: 120, tenantUsers: 1, cloudGraphs: fixtureCloudGraphRevision ? 1 : 0, collaborationEvents: 0, tasksByStatus: { [fixtureCloudTask.status]: 1 }, auditEvents: fixtureAudit.events.length })

async function fixtureCloudTaskCollection(request: Request): Promise<Task> {
  const input = await request.json() as { type?: string; input?: ResearchBriefRequest }
  const taskType = input.type || "graph.audit"
  const total = taskType === "research.brief" ? Math.max(1, input.input?.recordIds.length ?? 1) : Math.max(1, fixtureCloudGraph.nodes.length + fixtureCloudGraph.edges.length)
  fixtureCloudTask = { ...fixtureCloudTask, type: taskType, status: "queued", cancellable: true, progress: { completed: 0, total, unit: taskType === "research.brief" ? "records" : "elements", message: "Queued" }, resultRef: undefined, finishedAt: undefined }
  return fixtureCloudTask
}

function fixtureCloudTaskItem(request: Request): Task | Record<string, unknown> {
  const path = new URL(request.url).pathname
  if (path.endsWith("/result") && fixtureCloudTask.type === "research.brief") {
    const workspace = fixtureResearchWorkspace()
    const result: ResearchBriefResult = { protocolVersion: PROTOCOL_VERSION, mode: "evidence_only", generatedAt: new Date().toISOString(), title: "研究证据简报", sections: workspace.records.map((record) => ({ heading: record.title, body: record.abstract || "摘要证据不可用。", evidenceRecordIds: [record.recordId] })), warnings: ["这是确定性演示证据编排，不是生成式模型输出，也不替代全文核验。"] }
    return result
  }
  if (path.endsWith("/result")) return { protocolVersion: PROTOCOL_VERSION, recordId: fixtureCloudGraph.recordId, nodeCount: fixtureCloudGraph.nodes.length, edgeCount: fixtureCloudGraph.edges.length, nodeTypes: {}, relationTypes: {} }
  if (path.endsWith(":cancel")) {
    fixtureCloudTask = { ...fixtureCloudTask, status: "cancelled", cancellable: false, message: "Cancelled", finishedAt: new Date().toISOString() }
    return fixtureCloudTask
  }
  const total = Math.max(1, fixtureCloudTask.progress.total)
  fixtureCloudTask = { ...fixtureCloudTask, status: "succeeded", cancellable: false, progress: { ...fixtureCloudTask.progress, completed: total, total, message: "Succeeded" }, message: "Succeeded", finishedAt: new Date().toISOString(), resultRef: `/v1/tasks/${fixtureCloudTask.id}/result` }
  return fixtureCloudTask
}

export const cloudApiClient = cloudApiConfigured
  ? new ApiClient({ baseUrl: cloudApiUrl as string, accessToken: cloudAccessToken, timeoutMs: 15_000, retries: 1 })
  : new ApiClient({ baseUrl: "https://fixture-cloud.omnilit.invalid", accessToken: cloudAccessToken, retries: 0, transport: createFixtureTransport({
      "/v1/auth/register": fixtureCloudSession,
      "/v1/auth/login": fixtureCloudSession,
      "/v1/account/me": () => fixtureCloudAccount,
      "/v1/account/data-controls": fixtureCloudControls,
      "/v1/workspaces/me": { protocolVersion: PROTOCOL_VERSION, id: "fixture-workspace", kind: "personal", name: "Fixture Workspace", quotaBytes: 5368709120, usedBytes: 0, resourceCount: 0, createdAt: "2026-01-01T00:00:00Z" },
      "/v1/sync/workspace/preferences": { protocolVersion: PROTOCOL_VERSION, enabled: false, categories: { literature: false, collections: false, graphs: false, views: false, settings: false, annotations: false, pdfs: false, fullText: false, extractions: false }, updatedAt: "" },
      "/v1/sync/workspace/status": { protocolVersion: PROTOCOL_VERSION, workspaceId: "fixture-workspace", enabled: false, cursor: 0, resourceCount: 0, pendingChanges: 0, conflictCount: 0, lastSyncedAt: "" },
      "/v1/sync/workspace/changes": { protocolVersion: PROTOCOL_VERSION, workspaceId: "fixture-workspace", cursor: 0, changes: [], hasMore: false },
      "/v1/sync/workspace/push": { protocolVersion: PROTOCOL_VERSION, workspaceId: "fixture-workspace", cursor: 1, applied: [], conflicts: [] },
      "/v1/public/library/query": { protocolVersion: PROTOCOL_VERSION, records: [], offset: 0, total: 0, hasMore: false },
      "/v1/public/submissions": fixturePublicSubmissions,
      "/v1/public/submissions/*": { protocolVersion: PROTOCOL_VERSION, id: "fixture-submission", status: "pending_review", revision: 2, sourceResourceId: "paper-001", record: demoLibraryRecords[0], contentHash: "fixture", license: { code: "cc-by", url: "https://creativecommons.org/licenses/by/4.0/", rightsStatement: "Fixture open license declaration." }, publicDisplayName: "Fixture", reviewNote: "", createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z" },
      "/v1/diagnostics": { protocolVersion: PROTOCOL_VERSION, accepted: true, reportId: "fixture-diagnostic", retainedUntil: "2099-01-01T00:00:00Z" },
      "/v1/account/export": () => ({ protocolVersion: PROTOCOL_VERSION, account: fixtureCloudAccount, library: fixtureCloudState }),
      "/v1/account": { protocolVersion: PROTOCOL_VERSION, deleted: true },
      "/v1/sync/library": (request: Request) => request.method === "POST" ? fixtureCloudSync(request) : fixtureCloudLibrary(),
      "/v1/shares": fixtureCloudShare,
      "/v1/shares/*": { protocolVersion: PROTOCOL_VERSION, revoked: true },
      "/v1/audit/events": fixtureAudit,
      "/v1/metrics": fixtureCloudMetrics,
      "/v1/tasks": fixtureCloudTaskCollection,
      "/v1/tasks/*": fixtureCloudTaskItem,
      "/v1/team/members": () => fixtureTeam,
      "/v1/team/members/*": () => fixtureTeam,
      "/v1/team/invites": fixtureTeamInvite,
      "/v1/team/invites:accept": fixtureCloudSession,
      "/v1/permissions": fixturePermissionMutation,
      "/v1/permissions/*": () => fixturePermissions,
      "/v1/graphs": () => ({ protocolVersion: PROTOCOL_VERSION, graphs: fixtureCloudGraphRevision ? [{ recordId: fixtureCloudGraph.recordId, cloudRevision: fixtureCloudGraphRevision, updatedAt: new Date().toISOString(), nodeCount: fixtureCloudGraph.nodes.length, edgeCount: fixtureCloudGraph.edges.length }] : [] }),
      "/v1/graphs/paper-001": () => fixtureCloudGraph,
      "/v1/graphs/paper-001/sync": fixtureCloudGraphSync,
      "/v1/graphs/paper-001/nodes/*": fixtureNeighbors,
      "/v1/graphs/paper-001/literature/query": fixtureLiterature,
      "/v1/graphs/paper-001/views": fixtureViewCollection,
      "/v1/graphs/paper-001/views/*": fixtureViewItem
    }) })

export const businessApiClient = cloudApiConfigured && !qtEmbedded ? cloudApiClient : apiClient

configureWebDiagnosticSink(cloudApiConfigured ? async (event) => {
  const session = readCloudSession()
  if (!session?.user.dataControls.shareDiagnostics) return
  await cloudApiClient.submitDiagnostic({
    protocolVersion: PROTOCOL_VERSION,
    occurredAt: event.occurredAt,
    source: event.source,
    code: event.code,
    exceptionType: event.exceptionType,
    fingerprint: event.fingerprint,
    severity: "error",
    appVersion: import.meta.env.VITE_APP_VERSION ?? "0.1.0"
  })
} : undefined)

export const graphApiClient = qtEmbedded ? apiClient : cloudApiConfigured ? cloudApiClient : localAgentConfigured ? apiClient : apiClient
const baseGraphDataSource = {
  expandNeighbors: ({ recordId, nodeId, mode, offset, limit, signal }: { recordId: string; nodeId: string; mode: string; offset: number; limit: number; signal: AbortSignal }) => graphApiClient.getGraphNeighbors(recordId, nodeId, { mode, offset, limit, signal }),
  loadLiterature: ({ recordId, signal, ...request }: { recordId: string; visibleNodeIds: string[]; selectedNodeId?: string; hoveredNodeId?: string; signal: AbortSignal }) => graphApiClient.getGraphLiterature(recordId, request, signal),
  savedViews: {
    listViews: ({ recordId, signal }: { recordId: string; signal: AbortSignal }) => graphApiClient.listGraphViews(recordId, signal),
    saveView: ({ recordId, view, signal }: { recordId: string; view: GraphViewSaveRequest; signal: AbortSignal }) => graphApiClient.saveGraphView(recordId, view, signal),
    restoreView: ({ recordId, viewId, signal }: { recordId: string; viewId: string; signal: AbortSignal }) => graphApiClient.restoreGraphView(recordId, viewId, signal),
    deleteView: ({ recordId, viewId, signal }: { recordId: string; viewId: string; signal: AbortSignal }) => graphApiClient.deleteGraphView(recordId, viewId, signal)
  },
  collaboration: cloudApiConfigured ? {
    getSnapshot: ({ recordId, signal }: { recordId: string; signal: AbortSignal }) => cloudApiClient.getCollaborationSnapshot(recordId, signal),
    mutate: ({ recordId, mutation, signal }: { recordId: string; mutation: CollaborationMutationRequest; signal: AbortSignal }) => cloudApiClient.mutateCollaboration(recordId, mutation, signal),
    subscribe: ({ recordId, afterRevision, onEvent, onReset, signal }: { recordId: string; afterRevision: number; onEvent: (event: CollaborationEvent) => void; onReset: (currentRevision: number) => void; signal: AbortSignal }) => cloudApiClient.streamCollaborationEvents(recordId, afterRevision, { onEvent, onReset }, signal)
  } : undefined
}
export const graphDataSource = cloudApiConfigured && !localAgentConfigured ? baseGraphDataSource : {
  ...baseGraphDataSource,
  projectGraph: ({ recordId, signal, ...request }: { recordId: string; viewport: Record<string, number>; pinnedNodeIds?: string[]; pinnedEdgeIds?: string[]; layoutStyle?: string; signal: AbortSignal }) => graphApiClient.getGraphProjection(recordId, request, signal),
  loadTimeline: ({ timelineKey, signal, ...query }: { timelineKey: string; protocolVersion: "1.0"; startYear?: number; endYear?: number; playbackYear?: number; viewport: Record<string, number>; pinnedNodeIds?: string[]; signal: AbortSignal }) => graphApiClient.getGraphTimeline(timelineKey, query, signal)
}

export const platformBridge = createPlatformBridge(import.meta.env.VITE_APP_VERSION ?? "0.1.0", qtEmbedded)
