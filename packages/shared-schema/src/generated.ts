// Generated from omnilit-v1.schema.json. Do not edit.

export type JsonValue = unknown

export interface GraphEvidence {
  page: number
  bbox: Array<number>
  elementId?: string
  excerpt: string
  translatedText?: string
  source?: string
  recordId?: string
  section?: string
  extractionMethod?: string
  [key: string]: unknown
}

export interface GraphNode {
  id: string
  type: string
  label: string
  attributes: Record<string, unknown>
  metrics?: Record<string, number>
  evidence?: Array<GraphEvidence>
  [key: string]: unknown
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: string
  directed: boolean
  weight?: number
  attributes: Record<string, unknown>
  evidence?: Array<GraphEvidence>
  [key: string]: unknown
}

export interface Author {
  id?: string
  name: string
  orcid?: string
  affiliations?: Array<string>
  [key: string]: unknown
}

export interface Paper {
  id: string
  title: string
  abstract?: string
  year?: number
  doi?: string
  authors?: Array<string | Author>
  [key: string]: unknown
}

export interface GraphViewExploration {
  nodeIds: Array<string>
  edgeIds: Array<string>
  pages: Record<string, number>
  [key: string]: unknown
}

export interface GraphViewFilters {
  mode: string
  searchText: string
  density: string
  literatureSortKey: string
  literatureSortDescending: boolean
  facets: Record<string, string>
  nodeTypes: Array<string>
  needsReviewOnly: boolean
  [key: string]: unknown
}

export interface GraphViewSelection {
  nodeId: string
  edgeId: string
  [key: string]: unknown
}

export interface GraphViewPath {
  startId: string
  endId: string
  directed: boolean
  relationFilter: string
  [key: string]: unknown
}

export interface GraphViewViewport {
  displayStyle: "overview" | "academic" | "radial" | "focus"
  focusDepth: number
  reviewMode: boolean
  graphScale: number
  panX: number
  panY: number
  width?: number
  height?: number
  showArrows: boolean
  showLabels: boolean
  dimUnrelated: boolean
  textFadeThreshold: number
  nodeSizeScale: number
  linkThickness: number
  animateLayout: boolean
  [key: string]: unknown
}

export interface GraphViewState {
  protocolVersion: "1.0"
  version: 2
  id: string
  name: string
  recordId: string
  createdAt: string
  updatedAt: string
  graphFingerprint: string
  exploration: GraphViewExploration
  filters: GraphViewFilters
  selection: GraphViewSelection
  path: GraphViewPath
  viewport: GraphViewViewport
  [key: string]: unknown
}

export interface GraphViewSummary {
  id: string
  name: string
  recordId: string
  createdAt: string
  updatedAt: string
  graphFingerprint: string
  [key: string]: unknown
}

export interface GraphViewList {
  protocolVersion: "1.0"
  recordId: string
  views: Array<GraphViewSummary>
  [key: string]: unknown
}

export interface GraphViewSaveRequest {
  protocolVersion: "1.0"
  id?: string
  name: string
  graphFingerprint?: string
  exploration: GraphViewExploration
  filters: GraphViewFilters
  selection: GraphViewSelection
  path?: GraphViewPath
  viewport: GraphViewViewport
  [key: string]: unknown
}

export interface GraphViewReconciliation {
  missingNodes: number
  missingEdges: number
  [key: string]: unknown
}

export interface GraphViewRestore {
  protocolVersion: "1.0"
  recordId: string
  view: GraphViewState
  graph: GraphData
  reconciliation: GraphViewReconciliation
  [key: string]: unknown
}

export interface GraphViewMutationResult {
  protocolVersion: "1.0"
  recordId: string
  viewId: string
  deleted: boolean
  [key: string]: unknown
}

export interface GraphTimelinePaper {
  recordId: string
  nodeId: string
  title: string
  year: number
  topicId: string
  topicName: string
  keyScore: number
  citedByCount: number
  referenceCount: number
  representative: boolean
  reasons: Array<string>
  [key: string]: unknown
}

export interface GraphTimelineTopicEvent {
  topicId: string
  name: string
  newCount: number
  cumulative: number
  paperIds: Array<string>
  representativePaper: Record<string, unknown>
  [key: string]: unknown
}

export interface GraphTimelineTurningPoint {
  year: number
  type: "topic_emergence" | "topic_expansion" | "cross_topic_bridge" | "topic_split_signal" | "topic_merge_signal" | "topic_decline"
  score: number
  title: string
  explanation: string
  paperIds: Array<string>
  topicIds: Array<string>
  [key: string]: unknown
}

export interface GraphTimelineCitation {
  source: string
  target: string
  sourceYear: number | string
  targetYear: number | string
  crossTopic: boolean
  directionStatus: "valid" | "chronology_conflict" | "unknown_year"
  explanation: string
  [key: string]: unknown
}

export interface GraphTimelineEvent {
  year: number
  papers: Array<GraphTimelinePaper>
  topics: Array<GraphTimelineTopicEvent>
  citations: Array<GraphTimelineCitation>
  turningPoints: Array<GraphTimelineTurningPoint>
  [key: string]: unknown
}

export interface GraphTimelinePoint {
  year: number
  count: number
  cumulative: number
  paperIds: Array<string>
  representativePaper: Record<string, unknown>
  [key: string]: unknown
}

export interface GraphTimelineTopicSeries {
  topicId: string
  name: string
  colorIndex: number
  firstYear: number | string
  lastYear: number | string
  peakYear: number | string
  peakCount: number
  points: Array<GraphTimelinePoint>
  paperCount: number
  growthSpeed: number
  growthExplanation: string
  [key: string]: unknown
}

export interface GraphTimelineKeyPath {
  id: string
  label: string
  paperIds: Array<string>
  years: Array<number>
  score: number
  length: number
  yearSpan: number
  explanation: string
  [key: string]: unknown
}

export interface GraphTimelineSpeedComparison {
  leftTopicId: string
  rightTopicId: string
  leftSpeed: number
  rightSpeed: number
  fasterTopicId: string
  difference: number
  explanation: string
  [key: string]: unknown
}

export interface GraphTimelineYearRange {
  minimum: number
  maximum: number
  years: Array<number>
  knownYearCount: number
  missingYearCount: number
  [key: string]: unknown
}

export interface GraphTimelineSelection {
  startYear: number
  endYear: number
  playbackYear: number
  effectiveEndYear: number
  [key: string]: unknown
}

export interface GraphTimelineDiagnostics {
  paperCount: number
  citationCount: number
  validCitationCount: number
  chronologyConflictCount: number
  unknownCitationYearCount: number
  sameYearCycleBreakCount: number
  splitSignalCount: number
  mergeSignalCount: number
  declineSignalCount: number
  keyPathCount: number
  method: string
  [key: string]: unknown
}

export interface GraphTimelineQuery {
  protocolVersion: "1.0"
  startYear?: number
  endYear?: number
  playbackYear?: number
  viewport: Record<string, unknown>
  pinnedNodeIds?: Array<string>
  [key: string]: unknown
}

export interface GraphTimeline {
  protocolVersion: "1.0"
  schemaVersion: 1
  timelineVersion: 2
  timelineKey: string
  status: "ready" | "empty"
  generatedAt: string
  selection: GraphTimelineSelection
  yearRange: GraphTimelineYearRange
  events: Array<GraphTimelineEvent>
  topicSeries: Array<GraphTimelineTopicSeries>
  keyPaths: Array<GraphTimelineKeyPath>
  turningPoints: Array<GraphTimelineTurningPoint>
  topicSpeedComparisons: Array<GraphTimelineSpeedComparison>
  diagnostics: GraphTimelineDiagnostics
  graph: GraphData
  projection: GraphProjectionStatus
  [key: string]: unknown
}

export interface TaskProgress {
  completed: number
  total: number
  unit: string
  message?: string
  [key: string]: unknown
}

export interface Task {
  protocolVersion: "1.0"
  id: string
  type: string
  status: "created" | "queued" | "running" | "stopping" | "succeeded" | "completed" | "cancelled" | "failed"
  cancellable: boolean
  progress: TaskProgress
  message?: string
  createdAt?: string
  startedAt?: string
  finishedAt?: string
  resultRef?: string
  result?: unknown
  error?: APIError
  [key: string]: unknown
}

export interface APIError {
  protocolVersion: "1.0"
  code: string
  message: string
  retryable: boolean
  details?: Record<string, unknown>
  requestId?: string
  [key: string]: unknown
}

export interface GraphNeighborPage {
  protocolVersion: "1.0"
  schemaVersion: 1
  recordId: string
  nodeId: string
  relationMode: "all" | "references" | "cited_by" | "authors" | "institutions" | "topics" | "venues"
  status: "ready" | "empty"
  nodes: Array<GraphNode>
  edges: Array<GraphEdge>
  offset: number
  nextOffset: number
  revealed: number
  total: number
  hasMore: boolean
  [key: string]: unknown
}

export interface GraphProjectionStatus {
  status: "ready" | "empty"
  level: "overview" | "normal" | "detail"
  layoutStyle?: string
  spatialCulling?: boolean
  budget: number
  totalSemanticNodes: number
  viewportCandidates?: number
  renderedNodes: number
  realNodes: number
  aggregateNodes: number
  aggregatedNodes: number
  culledNodes: number
  renderedEdges: number
  totalSemanticEdges: number
  degraded: boolean
  latencyMs: number
  latencyBudgetMs: number
  budgetExceeded: boolean
  performanceStatus: "ready" | "over_budget"
  message: string
  [key: string]: unknown
}

export interface GraphProjection {
  protocolVersion: "1.0"
  schemaVersion: 1
  recordId: string
  graph: GraphData
  layout: Record<string, Record<string, number>>
  status: GraphProjectionStatus
  [key: string]: unknown
}

export interface LiteratureRow {
  nodeId: string
  recordId: string
  kind: "paper" | "citation"
  title: string
  year: string
  authors: string
  venue: string
  citations: number
  importance: number
  confidence: number
  evidenceCount: number
  selected: boolean
  hovered: boolean
  searchText: string
  relevance: number
  [key: string]: unknown
}

export interface LiteraturePage {
  protocolVersion: "1.0"
  recordId: string
  rows: Array<LiteratureRow>
  offset: number
  nextOffset: number
  total: number
  hasMore: boolean
  [key: string]: unknown
}

export interface LibraryQuery {
  protocolVersion: "1.0"
  query?: string
  relevance?: "all" | "keyword_only" | "loose" | "balanced" | "strict" | "very_strict"
  pdfStatus?: string
  sort?: "relevance_desc" | "relevance_asc" | "year_desc" | "year_asc" | "downloaded_first" | "title_asc"
  journalType?: string
  collectionId?: string
  keywordGroups?: Array<string>
  offset?: number
  limit?: number
  [key: string]: unknown
}

export interface LibraryRecordSummary {
  recordId: string
  title: string
  authorsText: string
  source: string
  year: string
  publicationDate?: string
  journalTitle: string
  journalType: string
  journalTypeLabel: string
  impactFactorText: string
  keywordsText: string
  summaryText: string
  topicTagsText: string
  pdfStatus: string
  relevanceLabel: string
  relevanceScore: number
  matchedKeywordsText: string
  keywordGroupKeys?: Array<string>
  downloaded: boolean
  hasExtraction: boolean
  [key: string]: unknown
}

export interface LibraryRecordDetail {
  protocolVersion: "1.0"
  recordId: string
  title: string
  abstract: string
  authorsText: string
  doi: string
  source: string
  year: string
  publicationDate?: string
  journalTitle: string
  impactFactorText?: string
  impactFactorSource?: string
  impactFactorMetric?: string
  impactFactorYear?: string
  impactFactorQuartile?: string
  keywordsText: string
  summaryText: string
  topicTagsText: string
  pdfStatus: string
  relevanceLabel: string
  relevanceScore: number
  matchedKeywordsText: string
  matchedFieldsText: string
  relevanceReasonsText: string
  downloaded: boolean
  hasExtraction: boolean
  [key: string]: unknown
}

export interface LibraryFacets {
  relevance: Record<string, number>
  pdfStatus: Record<string, number>
  journalType: Record<string, number>
  keywordGroups: Record<string, number>
  [key: string]: unknown
}

export interface LibraryPage {
  protocolVersion: "1.0"
  status: "ready" | "empty" | "unavailable"
  records: Array<LibraryRecordSummary>
  offset: number
  nextOffset: number
  total: number
  hasMore: boolean
  cacheAvailable: boolean
  facets: LibraryFacets
  message: string
  [key: string]: unknown
}

export interface ResearchCollection {
  id: string
  name: string
  builtIn: boolean
  recordCount: number
  [key: string]: unknown
}

export interface LibraryWorkspaceState {
  compareRecordIds: Array<string>
  [key: string]: unknown
}

export interface LibraryState {
  protocolVersion: "1.0"
  revision: number
  updatedAt: string
  syncState: "local_only" | "pending_sync" | "synced" | "conflict" | "deleting"
  collections: Array<ResearchCollection>
  favorites: Record<string, Array<string>>
  workspace: LibraryWorkspaceState
  [key: string]: unknown
}

export interface LibraryMutationRequest {
  protocolVersion: "1.0"
  action: "create_collection" | "rename_collection" | "delete_collection" | "toggle_collection_record" | "toggle_compare_record" | "remove_compare_record" | "clear_compare"
  expectedRevision: number
  collectionId?: string
  name?: string
  recordId?: string
  [key: string]: unknown
}

export interface LibraryMutationResult {
  protocolVersion: "1.0"
  changed: boolean
  message: string
  state: LibraryState
  [key: string]: unknown
}

export interface ResearchWorkspaceRecord {
  recordId: string
  title: string
  authorsText: string
  year: string
  journalTitle: string
  source: string
  abstract: string
  keywordsText: string
  pdfStatus: string
  downloaded: boolean
  hasExtraction: boolean
  collectionIds: Array<string>
  [key: string]: unknown
}

export interface ResearchWorkspace {
  protocolVersion: "1.0"
  status: "ready" | "empty" | "unavailable"
  records: Array<ResearchWorkspaceRecord>
  compareLimit: number
  message: string
  [key: string]: unknown
}

export interface ResearchStatisticsBucket {
  key: string
  label: string
  count: number
  [key: string]: unknown
}

export interface ResearchStatistics {
  protocolVersion: "1.0"
  status: "ready" | "empty" | "unavailable"
  totalRecords: number
  downloadedRecords: number
  extractedRecords: number
  compareRecords: number
  yearBuckets: Array<ResearchStatisticsBucket>
  sourceBuckets: Array<ResearchStatisticsBucket>
  pdfStatusBuckets: Array<ResearchStatisticsBucket>
  topKeywords: Array<ResearchStatisticsBucket>
  collectionBuckets: Array<ResearchStatisticsBucket>
  message: string
  [key: string]: unknown
}

export interface BusinessSettings {
  protocolVersion: "1.0"
  revision: number
  themeMode: "system" | "light" | "dark"
  density: "comfortable" | "compact"
  reduceMotion: boolean
  highContrast: boolean
  startPage: "graph" | "library" | "collections" | "workspace" | "statistics" | "ai"
  defaultLibrarySort: "relevance_desc" | "year_desc" | "year_asc" | "downloaded_first" | "title_asc"
  aiEvidenceLimit: number
  aiEndpoint: string
  aiModel: string
  allowRemoteResearchContent: boolean
  aiCredentialConfigured: boolean
  updatedAt: string
  [key: string]: unknown
}

export interface BusinessSettingsUpdateRequest {
  protocolVersion: "1.0"
  expectedRevision: number
  themeMode: "system" | "light" | "dark"
  density: "comfortable" | "compact"
  reduceMotion: boolean
  highContrast: boolean
  startPage: "graph" | "library" | "collections" | "workspace" | "statistics" | "ai"
  defaultLibrarySort: "relevance_desc" | "year_desc" | "year_asc" | "downloaded_first" | "title_asc"
  aiEvidenceLimit: number
  aiEndpoint: string
  aiModel: string
  allowRemoteResearchContent: boolean
  [key: string]: unknown
}

export interface ResearchBriefRequest {
  protocolVersion: "1.0"
  recordIds: Array<string>
  focus: "overview" | "methods" | "findings" | "gaps"
  question: string
  mode: "evidence_only" | "model"
  [key: string]: unknown
}

export interface ResearchBriefSection {
  heading: string
  body: string
  evidenceRecordIds: Array<string>
  [key: string]: unknown
}

export interface ResearchBriefResult {
  protocolVersion: "1.0"
  mode: "evidence_only" | "model"
  generatedAt: string
  title: string
  sections: Array<ResearchBriefSection>
  warnings: Array<string>
  [key: string]: unknown
}

export interface CloudDataControls {
  uploadLocalPdfs: boolean
  syncAnnotations: boolean
  syncFullText: boolean
  useCloudAi: boolean
  retainCloudTaskData: boolean
  allowTeamAccess: boolean
  allowShareLinks: boolean
  shareDiagnostics: boolean
  [key: string]: unknown
}

export interface WorkspaceTargetSelection {
  privateSync: boolean
  publicSubmission: boolean
  [key: string]: unknown
}

export interface WorkspaceSummary {
  protocolVersion: "1.0"
  id: string
  kind: "personal" | "public"
  name: string
  quotaBytes: number
  usedBytes: number
  resourceCount: number
  createdAt: string
  [key: string]: unknown
}

export interface WorkspaceSyncPreferences {
  protocolVersion: "1.0"
  enabled: boolean
  updatedAt: string
  categories: Record<string, boolean>
  [key: string]: unknown
}

export interface WorkspaceSyncStatus {
  protocolVersion: "1.0"
  workspaceId: string
  enabled: boolean
  cursor: number
  resourceCount: number
  pendingChanges: number
  conflictCount: number
  lastSyncedAt: string
  [key: string]: unknown
}

export interface WorkspaceChange {
  cursor?: number
  resourceType: "literature_record" | "library_state" | "business_settings" | "graph" | "graph_view" | "annotation"
  resourceId: string
  operation: "upsert" | "delete"
  baseRevision?: number
  revision?: number
  clientMutationId: string
  payloadHash?: string
  payload?: Record<string, unknown>
  occurredAt?: string
  [key: string]: unknown
}

export interface WorkspaceConflict {
  resourceType: string
  resourceId: string
  localRevision: number
  cloudRevision: number
  cloudPayload: Record<string, unknown>
  [key: string]: unknown
}

export interface WorkspaceSyncBatch {
  protocolVersion: "1.0"
  deviceId: string
  cursor: number
  changes: Array<WorkspaceChange>
  [key: string]: unknown
}

export interface WorkspaceSyncResult {
  protocolVersion: "1.0"
  workspaceId: string
  cursor: number
  applied: Array<WorkspaceChange>
  conflicts: Array<WorkspaceConflict>
  [key: string]: unknown
}

export interface WorkspaceChangePage {
  protocolVersion: "1.0"
  workspaceId: string
  cursor: number
  changes: Array<WorkspaceChange>
  hasMore: boolean
  [key: string]: unknown
}

export interface PublicLicenseDeclaration {
  code: "cc-by" | "cc-by-sa" | "cc0" | "public-domain" | "publisher-oa" | "author-redistribution"
  url: string
  rightsStatement: string
  [key: string]: unknown
}

export interface PublicSubmission {
  protocolVersion: "1.0"
  id: string
  status: "draft" | "pending_review" | "changes_requested" | "approved" | "rejected" | "withdrawal_requested" | "withdrawn" | "takedown"
  revision: number
  sourceResourceId: string
  record: Record<string, unknown>
  contentHash: string
  license: PublicLicenseDeclaration
  publicDisplayName: string
  reviewNote: string
  createdAt: string
  updatedAt: string
  [key: string]: unknown
}

export interface PublicSubmissionCreateRequest {
  protocolVersion: "1.0"
  sourceResourceId: string
  record: Record<string, unknown>
  license: PublicLicenseDeclaration
  publicDisplayName: string
  [key: string]: unknown
}

export interface PublicSubmissionList {
  protocolVersion: "1.0"
  submissions: Array<PublicSubmission>
  [key: string]: unknown
}

export interface PublicModerationDecision {
  protocolVersion: "1.0"
  decision: "approve" | "reject" | "request_changes" | "withdraw" | "takedown"
  note: string
  [key: string]: unknown
}

export interface PublicLibraryRecord {
  id: string
  version: number
  record: Record<string, unknown>
  license: PublicLicenseDeclaration
  contributorName: string
  approvedAt: string
  [key: string]: unknown
}

export interface PublicLibraryQuery {
  protocolVersion: "1.0"
  searchText?: string
  offset?: number
  limit?: number
  [key: string]: unknown
}

export interface PublicLibraryPage {
  protocolVersion: "1.0"
  records: Array<PublicLibraryRecord>
  offset: number
  total: number
  hasMore: boolean
  [key: string]: unknown
}

export interface DiagnosticReportCreateRequest {
  protocolVersion: "1.0"
  occurredAt: string
  source: "react" | "window" | "promise" | "startup" | "qt_main" | "qt_worker" | "qml" | "webengine" | "local_agent" | "cloud_api"
  code: string
  exceptionType: string
  fingerprint: string
  severity: "error" | "fatal"
  appVersion: string
  [key: string]: unknown
}

export interface DiagnosticReceipt {
  protocolVersion: "1.0"
  accepted: true
  reportId: string
  retainedUntil: string
  [key: string]: unknown
}

export interface UserAccount {
  protocolVersion: "1.0"
  id: string
  tenantId: string
  workspaceId: string
  accountStatus: "pending_verification" | "active" | "suspended"
  email: string
  displayName: string
  roles: Array<"owner" | "admin" | "member">
  dataControls: CloudDataControls
  createdAt: string
  [key: string]: unknown
}

export interface AuthSession {
  protocolVersion: "1.0"
  accessToken: string
  expiresAt: string
  user: UserAccount
  [key: string]: unknown
}

export interface RegistrationResult {
  protocolVersion: "1.0"
  verificationRequired: true
  email: string
  [key: string]: unknown
}

export interface LibrarySyncRequest {
  protocolVersion: "1.0"
  deviceId: string
  baseCloudRevision: number
  state: LibraryState
  [key: string]: unknown
}

export interface LibrarySyncResult {
  protocolVersion: "1.0"
  status: "synced" | "conflict"
  cloudRevision: number
  syncedAt: string
  serverState: LibraryState
  conflictId?: string
  [key: string]: unknown
}

export interface ShareCreateRequest {
  protocolVersion: "1.0"
  resourceType: "library_state" | "collection" | "graph" | "graph_view"
  resourceId: string
  permission: "viewer" | "editor"
  expiresAt?: string
  [key: string]: unknown
}

export interface ShareLink {
  protocolVersion: "1.0"
  id: string
  resourceType: "library_state" | "collection" | "graph" | "graph_view"
  resourceId: string
  permission: "viewer" | "editor"
  createdAt: string
  expiresAt: string
  revoked: boolean
  url: string
  [key: string]: unknown
}

export interface AuditEvent {
  id: string
  occurredAt: string
  actorId: string
  action: string
  resourceType: string
  resourceId: string
  requestId: string
  [key: string]: unknown
}

export interface AuditEventPage {
  protocolVersion: "1.0"
  events: Array<AuditEvent>
  [key: string]: unknown
}

export interface TeamMember {
  id: string
  email: string
  displayName: string
  role: "owner" | "admin" | "member"
  joinedAt: string
  [key: string]: unknown
}

export interface TeamMemberList {
  protocolVersion: "1.0"
  tenantId: string
  members: Array<TeamMember>
  [key: string]: unknown
}

export interface TeamInviteCreateRequest {
  protocolVersion: "1.0"
  email: string
  role: "admin" | "member"
  expiresInHours?: number
  [key: string]: unknown
}

export interface TeamInviteAcceptRequest {
  protocolVersion: "1.0"
  token: string
  displayName: string
  password: string
  [key: string]: unknown
}

export interface TeamInvite {
  protocolVersion: "1.0"
  id: string
  tenantId: string
  email: string
  role: "admin" | "member"
  createdAt: string
  expiresAt: string
  accepted: boolean
  url: string
  [key: string]: unknown
}

export interface ResourcePermission {
  id: string
  resourceType: "library_state" | "collection" | "graph" | "graph_view"
  resourceId: string
  principalType: "user" | "team"
  principalId: string
  permission: "viewer" | "editor"
  updatedAt: string
  [key: string]: unknown
}

export interface ResourcePermissionMutation {
  protocolVersion: "1.0"
  resourceType: "library_state" | "collection" | "graph" | "graph_view"
  resourceId: string
  principalType: "user" | "team"
  principalId: string
  permission: "none" | "viewer" | "editor"
  [key: string]: unknown
}

export interface ResourcePermissionList {
  protocolVersion: "1.0"
  resourceType: "library_state" | "collection" | "graph" | "graph_view"
  resourceId: string
  permissions: Array<ResourcePermission>
  [key: string]: unknown
}

export interface CloudGraphSyncRequest {
  protocolVersion: "1.0"
  deviceId: string
  baseCloudRevision: number
  graph: GraphData
  [key: string]: unknown
}

export interface CloudGraphSyncResult {
  protocolVersion: "1.0"
  status: "synced" | "conflict"
  recordId: string
  cloudRevision: number
  syncedAt: string
  serverGraph: GraphData
  conflictId?: string
  [key: string]: unknown
}

export interface CloudGraphSummary {
  recordId: string
  cloudRevision: number
  updatedAt: string
  nodeCount: number
  edgeCount: number
  [key: string]: unknown
}

export interface CloudGraphList {
  protocolVersion: "1.0"
  graphs: Array<CloudGraphSummary>
  [key: string]: unknown
}

export interface CollaborationAnnotation {
  protocolVersion: "1.0"
  id: string
  recordId: string
  targetType: "graph" | "node" | "edge"
  targetId: string
  body: string
  authorId: string
  authorDisplayName: string
  revision: number
  createdAt: string
  updatedAt: string
  [key: string]: unknown
}

export interface CollaborationEvent {
  protocolVersion: "1.0"
  recordId: string
  revision: number
  clientMutationId: string
  action: "annotation.upserted" | "annotation.deleted"
  annotationId: string
  annotation?: CollaborationAnnotation
  actorId: string
  occurredAt: string
  [key: string]: unknown
}

export interface CollaborationSnapshot {
  protocolVersion: "1.0"
  recordId: string
  revision: number
  canEdit: boolean
  syncEnabled: boolean
  annotations: Array<CollaborationAnnotation>
  [key: string]: unknown
}

export interface CollaborationMutationRequest {
  protocolVersion: "1.0"
  baseRevision: number
  clientMutationId: string
  action: "upsert" | "delete"
  annotationId?: string
  targetType: "graph" | "node" | "edge"
  targetId: string
  body?: string
  [key: string]: unknown
}

export interface CollaborationMutationResult {
  protocolVersion: "1.0"
  recordId: string
  revision: number
  event: CollaborationEvent
  [key: string]: unknown
}

export interface CollaborationEventPage {
  protocolVersion: "1.0"
  recordId: string
  afterRevision: number
  currentRevision: number
  events: Array<CollaborationEvent>
  hasMore: boolean
  resetRequired: boolean
  [key: string]: unknown
}

export interface CloudServiceMetrics {
  protocolVersion: "1.0"
  status: "ready" | "degraded"
  uptimeSeconds: number
  tenantUsers: number
  cloudGraphs: number
  collaborationEvents: number
  tasksByStatus: Record<string, number>
  auditEvents: number
  [key: string]: unknown
}

export interface GraphData {
  protocolVersion: "1.0"
  schemaVersion: 1
  recordId: string
  generatedAt?: string
  paper?: Paper
  nodes: Array<GraphNode>
  edges: Array<GraphEdge>
  metadata: Record<string, unknown>
  viewState?: GraphViewState
  [key: string]: unknown
}

export const PROTOCOL_VERSION = "1.0" as const
export const GRAPH_SCHEMA_VERSION = 1 as const
