"""Generated from omnilit-v1.schema.json. Do not edit."""
from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

class GraphEvidence(TypedDict):
    page: int
    bbox: list[float]
    elementId: NotRequired[str]
    excerpt: str
    translatedText: NotRequired[str]
    source: NotRequired[str]
    recordId: NotRequired[str]
    section: NotRequired[str]
    extractionMethod: NotRequired[str]

class GraphNode(TypedDict):
    id: str
    type: str
    label: str
    attributes: dict[str, Any]
    metrics: NotRequired[dict[str, float]]
    evidence: NotRequired[list[GraphEvidence]]

class GraphEdge(TypedDict):
    id: str
    source: str
    target: str
    type: str
    directed: bool
    weight: NotRequired[float]
    attributes: dict[str, Any]
    evidence: NotRequired[list[GraphEvidence]]

class Author(TypedDict):
    id: NotRequired[str]
    name: str
    orcid: NotRequired[str]
    affiliations: NotRequired[list[str]]

class Paper(TypedDict):
    id: str
    title: str
    abstract: NotRequired[str]
    year: NotRequired[int]
    doi: NotRequired[str]
    authors: NotRequired[list[str | Author]]

class GraphViewExploration(TypedDict):
    nodeIds: list[str]
    edgeIds: list[str]
    pages: dict[str, int]

class GraphViewFilters(TypedDict):
    mode: str
    searchText: str
    density: str
    literatureSortKey: str
    literatureSortDescending: bool
    facets: dict[str, str]
    nodeTypes: list[str]
    needsReviewOnly: bool

class GraphViewSelection(TypedDict):
    nodeId: str
    edgeId: str

class GraphViewPath(TypedDict):
    startId: str
    endId: str
    directed: bool
    relationFilter: str

class GraphViewViewport(TypedDict):
    displayStyle: Literal['overview', 'academic', 'radial', 'focus']
    focusDepth: int
    reviewMode: bool
    graphScale: float
    panX: float
    panY: float
    width: NotRequired[float]
    height: NotRequired[float]
    showArrows: bool
    showLabels: bool
    dimUnrelated: bool
    textFadeThreshold: float
    nodeSizeScale: float
    linkThickness: float
    animateLayout: bool

class GraphViewState(TypedDict):
    protocolVersion: Literal['1.0']
    version: Literal[2]
    id: str
    name: str
    recordId: str
    createdAt: str
    updatedAt: str
    graphFingerprint: str
    exploration: GraphViewExploration
    filters: GraphViewFilters
    selection: GraphViewSelection
    path: GraphViewPath
    viewport: GraphViewViewport

class GraphViewSummary(TypedDict):
    id: str
    name: str
    recordId: str
    createdAt: str
    updatedAt: str
    graphFingerprint: str

class GraphViewList(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    views: list[GraphViewSummary]

class GraphViewSaveRequest(TypedDict):
    protocolVersion: Literal['1.0']
    id: NotRequired[str]
    name: str
    graphFingerprint: NotRequired[str]
    exploration: GraphViewExploration
    filters: GraphViewFilters
    selection: GraphViewSelection
    path: NotRequired[GraphViewPath]
    viewport: GraphViewViewport

class GraphViewReconciliation(TypedDict):
    missingNodes: int
    missingEdges: int

class GraphViewRestore(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    view: GraphViewState
    graph: GraphData
    reconciliation: GraphViewReconciliation

class GraphViewMutationResult(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    viewId: str
    deleted: bool

class GraphTimelinePaper(TypedDict):
    recordId: str
    nodeId: str
    title: str
    year: int
    topicId: str
    topicName: str
    keyScore: float
    citedByCount: int
    referenceCount: int
    representative: bool
    reasons: list[str]

class GraphTimelineTopicEvent(TypedDict):
    topicId: str
    name: str
    newCount: int
    cumulative: int
    paperIds: list[str]
    representativePaper: dict[str, Any]

class GraphTimelineTurningPoint(TypedDict):
    year: int
    type: Literal['topic_emergence', 'topic_expansion', 'cross_topic_bridge', 'topic_split_signal', 'topic_merge_signal', 'topic_decline']
    score: float
    title: str
    explanation: str
    paperIds: list[str]
    topicIds: list[str]

class GraphTimelineCitation(TypedDict):
    source: str
    target: str
    sourceYear: int | str
    targetYear: int | str
    crossTopic: bool
    directionStatus: Literal['valid', 'chronology_conflict', 'unknown_year']
    explanation: str

class GraphTimelineEvent(TypedDict):
    year: int
    papers: list[GraphTimelinePaper]
    topics: list[GraphTimelineTopicEvent]
    citations: list[GraphTimelineCitation]
    turningPoints: list[GraphTimelineTurningPoint]

class GraphTimelinePoint(TypedDict):
    year: int
    count: int
    cumulative: int
    paperIds: list[str]
    representativePaper: dict[str, Any]

class GraphTimelineTopicSeries(TypedDict):
    topicId: str
    name: str
    colorIndex: int
    firstYear: int | str
    lastYear: int | str
    peakYear: int | str
    peakCount: int
    points: list[GraphTimelinePoint]
    paperCount: int
    growthSpeed: float
    growthExplanation: str

class GraphTimelineKeyPath(TypedDict):
    id: str
    label: str
    paperIds: list[str]
    years: list[int]
    score: float
    length: int
    yearSpan: int
    explanation: str

class GraphTimelineSpeedComparison(TypedDict):
    leftTopicId: str
    rightTopicId: str
    leftSpeed: float
    rightSpeed: float
    fasterTopicId: str
    difference: float
    explanation: str

class GraphTimelineYearRange(TypedDict):
    minimum: int
    maximum: int
    years: list[int]
    knownYearCount: int
    missingYearCount: int

class GraphTimelineSelection(TypedDict):
    startYear: int
    endYear: int
    playbackYear: int
    effectiveEndYear: int

class GraphTimelineDiagnostics(TypedDict):
    paperCount: int
    citationCount: int
    validCitationCount: int
    chronologyConflictCount: int
    unknownCitationYearCount: int
    sameYearCycleBreakCount: int
    splitSignalCount: int
    mergeSignalCount: int
    declineSignalCount: int
    keyPathCount: int
    method: str

class GraphTimelineQuery(TypedDict):
    protocolVersion: Literal['1.0']
    startYear: NotRequired[int]
    endYear: NotRequired[int]
    playbackYear: NotRequired[int]
    viewport: dict[str, Any]
    pinnedNodeIds: NotRequired[list[str]]

class GraphTimeline(TypedDict):
    protocolVersion: Literal['1.0']
    schemaVersion: Literal[1]
    timelineVersion: Literal[2]
    timelineKey: str
    status: Literal['ready', 'empty']
    generatedAt: str
    selection: GraphTimelineSelection
    yearRange: GraphTimelineYearRange
    events: list[GraphTimelineEvent]
    topicSeries: list[GraphTimelineTopicSeries]
    keyPaths: list[GraphTimelineKeyPath]
    turningPoints: list[GraphTimelineTurningPoint]
    topicSpeedComparisons: list[GraphTimelineSpeedComparison]
    diagnostics: GraphTimelineDiagnostics
    graph: GraphData
    projection: GraphProjectionStatus

class TaskProgress(TypedDict):
    completed: float
    total: float
    unit: str
    message: NotRequired[str]

class Task(TypedDict):
    protocolVersion: Literal['1.0']
    id: str
    type: str
    status: Literal['created', 'queued', 'running', 'stopping', 'succeeded', 'completed', 'cancelled', 'failed']
    cancellable: bool
    progress: TaskProgress
    message: NotRequired[str]
    createdAt: NotRequired[str]
    startedAt: NotRequired[str]
    finishedAt: NotRequired[str]
    resultRef: NotRequired[str]
    result: NotRequired[Any]
    error: NotRequired[APIError]

class APIError(TypedDict):
    protocolVersion: Literal['1.0']
    code: str
    message: str
    retryable: bool
    details: NotRequired[dict[str, Any]]
    requestId: NotRequired[str]

class GraphNeighborPage(TypedDict):
    protocolVersion: Literal['1.0']
    schemaVersion: Literal[1]
    recordId: str
    nodeId: str
    relationMode: Literal['all', 'references', 'cited_by', 'authors', 'institutions', 'topics', 'venues']
    status: Literal['ready', 'empty']
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    offset: int
    nextOffset: int
    revealed: int
    total: int
    hasMore: bool

class GraphProjectionStatus(TypedDict):
    status: Literal['ready', 'empty']
    level: Literal['overview', 'normal', 'detail']
    layoutStyle: NotRequired[str]
    spatialCulling: NotRequired[bool]
    budget: int
    totalSemanticNodes: int
    viewportCandidates: NotRequired[int]
    renderedNodes: int
    realNodes: int
    aggregateNodes: int
    aggregatedNodes: int
    culledNodes: int
    renderedEdges: int
    totalSemanticEdges: int
    degraded: bool
    latencyMs: float
    latencyBudgetMs: float
    budgetExceeded: bool
    performanceStatus: Literal['ready', 'over_budget']
    message: str

class GraphProjection(TypedDict):
    protocolVersion: Literal['1.0']
    schemaVersion: Literal[1]
    recordId: str
    graph: GraphData
    layout: dict[str, dict[str, float]]
    status: GraphProjectionStatus

class LiteratureRow(TypedDict):
    nodeId: str
    recordId: str
    kind: Literal['paper', 'citation']
    title: str
    year: str
    authors: str
    venue: str
    citations: int
    importance: float
    confidence: float
    evidenceCount: int
    selected: bool
    hovered: bool
    searchText: str
    relevance: float

class LiteraturePage(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    rows: list[LiteratureRow]
    offset: int
    nextOffset: int
    total: int
    hasMore: bool

class LibraryQuery(TypedDict):
    protocolVersion: Literal['1.0']
    query: NotRequired[str]
    relevance: NotRequired[Literal['all', 'keyword_only', 'loose', 'balanced', 'strict', 'very_strict']]
    pdfStatus: NotRequired[str]
    sort: NotRequired[Literal['relevance_desc', 'relevance_asc', 'year_desc', 'year_asc', 'downloaded_first', 'title_asc']]
    journalType: NotRequired[str]
    collectionId: NotRequired[str]
    keywordGroups: NotRequired[list[str]]
    offset: NotRequired[int]
    limit: NotRequired[int]

class LibraryRecordSummary(TypedDict):
    recordId: str
    title: str
    authorsText: str
    source: str
    year: str
    publicationDate: NotRequired[str]
    journalTitle: str
    journalType: str
    journalTypeLabel: str
    impactFactorText: str
    keywordsText: str
    summaryText: str
    topicTagsText: str
    pdfStatus: str
    relevanceLabel: str
    relevanceScore: float
    matchedKeywordsText: str
    keywordGroupKeys: NotRequired[list[str]]
    downloaded: bool
    hasExtraction: bool

class LibraryRecordDetail(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    title: str
    abstract: str
    authorsText: str
    doi: str
    source: str
    year: str
    publicationDate: NotRequired[str]
    journalTitle: str
    impactFactorText: NotRequired[str]
    impactFactorSource: NotRequired[str]
    impactFactorMetric: NotRequired[str]
    impactFactorYear: NotRequired[str]
    impactFactorQuartile: NotRequired[str]
    keywordsText: str
    summaryText: str
    topicTagsText: str
    pdfStatus: str
    relevanceLabel: str
    relevanceScore: float
    matchedKeywordsText: str
    matchedFieldsText: str
    relevanceReasonsText: str
    downloaded: bool
    hasExtraction: bool

class LibraryFacets(TypedDict):
    relevance: dict[str, int]
    pdfStatus: dict[str, int]
    journalType: dict[str, int]
    keywordGroups: dict[str, int]

class LibraryPage(TypedDict):
    protocolVersion: Literal['1.0']
    status: Literal['ready', 'empty', 'unavailable']
    records: list[LibraryRecordSummary]
    offset: int
    nextOffset: int
    total: int
    hasMore: bool
    cacheAvailable: bool
    facets: LibraryFacets
    message: str

class ResearchCollection(TypedDict):
    id: str
    name: str
    builtIn: bool
    recordCount: int

class LibraryWorkspaceState(TypedDict):
    compareRecordIds: list[str]

class LibraryState(TypedDict):
    protocolVersion: Literal['1.0']
    revision: int
    updatedAt: str
    syncState: Literal['local_only', 'pending_sync', 'synced', 'conflict', 'deleting']
    collections: list[ResearchCollection]
    favorites: dict[str, list[str]]
    workspace: LibraryWorkspaceState

class LibraryMutationRequest(TypedDict):
    protocolVersion: Literal['1.0']
    action: Literal['create_collection', 'rename_collection', 'delete_collection', 'toggle_collection_record', 'toggle_compare_record', 'remove_compare_record', 'clear_compare']
    expectedRevision: int
    collectionId: NotRequired[str]
    name: NotRequired[str]
    recordId: NotRequired[str]

class LibraryMutationResult(TypedDict):
    protocolVersion: Literal['1.0']
    changed: bool
    message: str
    state: LibraryState

class ResearchWorkspaceRecord(TypedDict):
    recordId: str
    title: str
    authorsText: str
    year: str
    journalTitle: str
    source: str
    abstract: str
    keywordsText: str
    pdfStatus: str
    downloaded: bool
    hasExtraction: bool
    collectionIds: list[str]

class ResearchWorkspace(TypedDict):
    protocolVersion: Literal['1.0']
    status: Literal['ready', 'empty', 'unavailable']
    records: list[ResearchWorkspaceRecord]
    compareLimit: int
    message: str

class ResearchStatisticsBucket(TypedDict):
    key: str
    label: str
    count: int

class ResearchStatistics(TypedDict):
    protocolVersion: Literal['1.0']
    status: Literal['ready', 'empty', 'unavailable']
    totalRecords: int
    downloadedRecords: int
    extractedRecords: int
    compareRecords: int
    yearBuckets: list[ResearchStatisticsBucket]
    sourceBuckets: list[ResearchStatisticsBucket]
    pdfStatusBuckets: list[ResearchStatisticsBucket]
    topKeywords: list[ResearchStatisticsBucket]
    collectionBuckets: list[ResearchStatisticsBucket]
    message: str

class BusinessSettings(TypedDict):
    protocolVersion: Literal['1.0']
    revision: int
    themeMode: Literal['system', 'light', 'dark']
    density: Literal['comfortable', 'compact']
    reduceMotion: bool
    highContrast: bool
    startPage: Literal['graph', 'library', 'collections', 'workspace', 'statistics', 'ai']
    defaultLibrarySort: Literal['relevance_desc', 'year_desc', 'year_asc', 'downloaded_first', 'title_asc']
    aiEvidenceLimit: int
    aiEndpoint: str
    aiModel: str
    allowRemoteResearchContent: bool
    aiCredentialConfigured: bool
    updatedAt: str

class BusinessSettingsUpdateRequest(TypedDict):
    protocolVersion: Literal['1.0']
    expectedRevision: int
    themeMode: Literal['system', 'light', 'dark']
    density: Literal['comfortable', 'compact']
    reduceMotion: bool
    highContrast: bool
    startPage: Literal['graph', 'library', 'collections', 'workspace', 'statistics', 'ai']
    defaultLibrarySort: Literal['relevance_desc', 'year_desc', 'year_asc', 'downloaded_first', 'title_asc']
    aiEvidenceLimit: int
    aiEndpoint: str
    aiModel: str
    allowRemoteResearchContent: bool

class ResearchBriefRequest(TypedDict):
    protocolVersion: Literal['1.0']
    recordIds: list[str]
    focus: Literal['overview', 'methods', 'findings', 'gaps']
    question: str
    mode: Literal['evidence_only', 'model']

class ResearchBriefSection(TypedDict):
    heading: str
    body: str
    evidenceRecordIds: list[str]

class ResearchBriefResult(TypedDict):
    protocolVersion: Literal['1.0']
    mode: Literal['evidence_only', 'model']
    generatedAt: str
    title: str
    sections: list[ResearchBriefSection]
    warnings: list[str]

class CloudDataControls(TypedDict):
    uploadLocalPdfs: bool
    syncAnnotations: bool
    syncFullText: bool
    useCloudAi: bool
    retainCloudTaskData: bool
    allowTeamAccess: bool
    allowShareLinks: bool
    shareDiagnostics: bool

class WorkspaceTargetSelection(TypedDict):
    privateSync: bool
    publicSubmission: bool

class WorkspaceSummary(TypedDict):
    protocolVersion: Literal['1.0']
    id: str
    kind: Literal['personal', 'public']
    name: str
    quotaBytes: int
    usedBytes: int
    resourceCount: int
    createdAt: str

class WorkspaceSyncPreferences(TypedDict):
    protocolVersion: Literal['1.0']
    enabled: bool
    updatedAt: str
    categories: dict[str, bool]

class WorkspaceSyncStatus(TypedDict):
    protocolVersion: Literal['1.0']
    workspaceId: str
    enabled: bool
    cursor: int
    resourceCount: int
    pendingChanges: int
    conflictCount: int
    lastSyncedAt: str

class WorkspaceChange(TypedDict):
    cursor: NotRequired[int]
    resourceType: Literal['literature_record', 'library_state', 'business_settings', 'graph', 'graph_view', 'annotation']
    resourceId: str
    operation: Literal['upsert', 'delete']
    baseRevision: NotRequired[int]
    revision: NotRequired[int]
    clientMutationId: str
    payloadHash: NotRequired[str]
    payload: NotRequired[dict[str, Any]]
    occurredAt: NotRequired[str]

class WorkspaceConflict(TypedDict):
    resourceType: str
    resourceId: str
    localRevision: int
    cloudRevision: int
    cloudPayload: dict[str, Any]

class WorkspaceSyncBatch(TypedDict):
    protocolVersion: Literal['1.0']
    deviceId: str
    cursor: int
    changes: list[WorkspaceChange]

class WorkspaceSyncResult(TypedDict):
    protocolVersion: Literal['1.0']
    workspaceId: str
    cursor: int
    applied: list[WorkspaceChange]
    conflicts: list[WorkspaceConflict]

class WorkspaceChangePage(TypedDict):
    protocolVersion: Literal['1.0']
    workspaceId: str
    cursor: int
    changes: list[WorkspaceChange]
    hasMore: bool

class PublicLicenseDeclaration(TypedDict):
    code: Literal['cc-by', 'cc-by-sa', 'cc0', 'public-domain', 'publisher-oa', 'author-redistribution']
    url: str
    rightsStatement: str

class PublicSubmission(TypedDict):
    protocolVersion: Literal['1.0']
    id: str
    status: Literal['draft', 'pending_review', 'changes_requested', 'approved', 'rejected', 'withdrawal_requested', 'withdrawn', 'takedown']
    revision: int
    sourceResourceId: str
    record: dict[str, Any]
    contentHash: str
    license: PublicLicenseDeclaration
    publicDisplayName: str
    reviewNote: str
    createdAt: str
    updatedAt: str

class PublicSubmissionCreateRequest(TypedDict):
    protocolVersion: Literal['1.0']
    sourceResourceId: str
    record: dict[str, Any]
    license: PublicLicenseDeclaration
    publicDisplayName: str

class PublicSubmissionList(TypedDict):
    protocolVersion: Literal['1.0']
    submissions: list[PublicSubmission]

class PublicModerationDecision(TypedDict):
    protocolVersion: Literal['1.0']
    decision: Literal['approve', 'reject', 'request_changes', 'withdraw', 'takedown']
    note: str

class PublicLibraryRecord(TypedDict):
    id: str
    version: int
    record: dict[str, Any]
    license: PublicLicenseDeclaration
    contributorName: str
    approvedAt: str

class PublicLibraryQuery(TypedDict):
    protocolVersion: Literal['1.0']
    searchText: NotRequired[str]
    offset: NotRequired[int]
    limit: NotRequired[int]

class PublicLibraryPage(TypedDict):
    protocolVersion: Literal['1.0']
    records: list[PublicLibraryRecord]
    offset: int
    total: int
    hasMore: bool

class DiagnosticReportCreateRequest(TypedDict):
    protocolVersion: Literal['1.0']
    occurredAt: str
    source: Literal['react', 'window', 'promise', 'startup', 'qt_main', 'qt_worker', 'qml', 'webengine', 'local_agent', 'cloud_api']
    code: str
    exceptionType: str
    fingerprint: str
    severity: Literal['error', 'fatal']
    appVersion: str

class DiagnosticReceipt(TypedDict):
    protocolVersion: Literal['1.0']
    accepted: Literal[True]
    reportId: str
    retainedUntil: str

class UserAccount(TypedDict):
    protocolVersion: Literal['1.0']
    id: str
    tenantId: str
    workspaceId: str
    accountStatus: Literal['pending_verification', 'active', 'suspended']
    email: str
    displayName: str
    roles: list[Literal['owner', 'admin', 'member']]
    dataControls: CloudDataControls
    createdAt: str

class AuthSession(TypedDict):
    protocolVersion: Literal['1.0']
    accessToken: str
    expiresAt: str
    user: UserAccount

class RegistrationResult(TypedDict):
    protocolVersion: Literal['1.0']
    verificationRequired: Literal[True]
    email: str

class LibrarySyncRequest(TypedDict):
    protocolVersion: Literal['1.0']
    deviceId: str
    baseCloudRevision: int
    state: LibraryState

class LibrarySyncResult(TypedDict):
    protocolVersion: Literal['1.0']
    status: Literal['synced', 'conflict']
    cloudRevision: int
    syncedAt: str
    serverState: LibraryState
    conflictId: NotRequired[str]

class ShareCreateRequest(TypedDict):
    protocolVersion: Literal['1.0']
    resourceType: Literal['library_state', 'collection', 'graph', 'graph_view']
    resourceId: str
    permission: Literal['viewer', 'editor']
    expiresAt: NotRequired[str]

class ShareLink(TypedDict):
    protocolVersion: Literal['1.0']
    id: str
    resourceType: Literal['library_state', 'collection', 'graph', 'graph_view']
    resourceId: str
    permission: Literal['viewer', 'editor']
    createdAt: str
    expiresAt: str
    revoked: bool
    url: str

class AuditEvent(TypedDict):
    id: str
    occurredAt: str
    actorId: str
    action: str
    resourceType: str
    resourceId: str
    requestId: str

class AuditEventPage(TypedDict):
    protocolVersion: Literal['1.0']
    events: list[AuditEvent]

class TeamMember(TypedDict):
    id: str
    email: str
    displayName: str
    role: Literal['owner', 'admin', 'member']
    joinedAt: str

class TeamMemberList(TypedDict):
    protocolVersion: Literal['1.0']
    tenantId: str
    members: list[TeamMember]

class TeamInviteCreateRequest(TypedDict):
    protocolVersion: Literal['1.0']
    email: str
    role: Literal['admin', 'member']
    expiresInHours: NotRequired[int]

class TeamInviteAcceptRequest(TypedDict):
    protocolVersion: Literal['1.0']
    token: str
    displayName: str
    password: str

class TeamInvite(TypedDict):
    protocolVersion: Literal['1.0']
    id: str
    tenantId: str
    email: str
    role: Literal['admin', 'member']
    createdAt: str
    expiresAt: str
    accepted: bool
    url: str

class ResourcePermission(TypedDict):
    id: str
    resourceType: Literal['library_state', 'collection', 'graph', 'graph_view']
    resourceId: str
    principalType: Literal['user', 'team']
    principalId: str
    permission: Literal['viewer', 'editor']
    updatedAt: str

class ResourcePermissionMutation(TypedDict):
    protocolVersion: Literal['1.0']
    resourceType: Literal['library_state', 'collection', 'graph', 'graph_view']
    resourceId: str
    principalType: Literal['user', 'team']
    principalId: str
    permission: Literal['none', 'viewer', 'editor']

class ResourcePermissionList(TypedDict):
    protocolVersion: Literal['1.0']
    resourceType: Literal['library_state', 'collection', 'graph', 'graph_view']
    resourceId: str
    permissions: list[ResourcePermission]

class CloudGraphSyncRequest(TypedDict):
    protocolVersion: Literal['1.0']
    deviceId: str
    baseCloudRevision: int
    graph: GraphData

class CloudGraphSyncResult(TypedDict):
    protocolVersion: Literal['1.0']
    status: Literal['synced', 'conflict']
    recordId: str
    cloudRevision: int
    syncedAt: str
    serverGraph: GraphData
    conflictId: NotRequired[str]

class CloudGraphSummary(TypedDict):
    recordId: str
    cloudRevision: int
    updatedAt: str
    nodeCount: int
    edgeCount: int

class CloudGraphList(TypedDict):
    protocolVersion: Literal['1.0']
    graphs: list[CloudGraphSummary]

class CollaborationAnnotation(TypedDict):
    protocolVersion: Literal['1.0']
    id: str
    recordId: str
    targetType: Literal['graph', 'node', 'edge']
    targetId: str
    body: str
    authorId: str
    authorDisplayName: str
    revision: int
    createdAt: str
    updatedAt: str

class CollaborationEvent(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    revision: int
    clientMutationId: str
    action: Literal['annotation.upserted', 'annotation.deleted']
    annotationId: str
    annotation: NotRequired[CollaborationAnnotation]
    actorId: str
    occurredAt: str

class CollaborationSnapshot(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    revision: int
    canEdit: bool
    syncEnabled: bool
    annotations: list[CollaborationAnnotation]

class CollaborationMutationRequest(TypedDict):
    protocolVersion: Literal['1.0']
    baseRevision: int
    clientMutationId: str
    action: Literal['upsert', 'delete']
    annotationId: NotRequired[str]
    targetType: Literal['graph', 'node', 'edge']
    targetId: str
    body: NotRequired[str]

class CollaborationMutationResult(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    revision: int
    event: CollaborationEvent

class CollaborationEventPage(TypedDict):
    protocolVersion: Literal['1.0']
    recordId: str
    afterRevision: int
    currentRevision: int
    events: list[CollaborationEvent]
    hasMore: bool
    resetRequired: bool

class CloudServiceMetrics(TypedDict):
    protocolVersion: Literal['1.0']
    status: Literal['ready', 'degraded']
    uptimeSeconds: float
    tenantUsers: int
    cloudGraphs: int
    collaborationEvents: int
    tasksByStatus: dict[str, int]
    auditEvents: int

class GraphData(TypedDict):
    protocolVersion: Literal['1.0']
    schemaVersion: Literal[1]
    recordId: str
    generatedAt: NotRequired[str]
    paper: NotRequired[Paper]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    metadata: dict[str, Any]
    viewState: NotRequired[GraphViewState]

PROTOCOL_VERSION: Literal["1.0"] = "1.0"
GRAPH_SCHEMA_VERSION: Literal[1] = 1
