from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .knowledge_graph_ontology import RELATION_CONFIG
from .knowledge_graph_schema import (
    KnowledgeGraphDocument,
    KnowledgeGraphEdge,
    KnowledgeGraphEvidence,
    KnowledgeGraphNode,
)
from .shared_protocol_models import GRAPH_SCHEMA_VERSION, PROTOCOL_VERSION, GraphData


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "packages" / "shared-schema" / "schemas" / "omnilit-v1.schema.json"


class SharedProtocolError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _check_protocol_version(payload: dict[str, Any]) -> None:
    protocol_version = str(payload.get("protocolVersion") or "")
    try:
        major = int(protocol_version.split(".", 1)[0])
    except (TypeError, ValueError):
        major = -1
    if major != int(PROTOCOL_VERSION.split(".", 1)[0]):
        raise SharedProtocolError(
            "unsupported_protocol_version",
            f"Unsupported OmniLit protocol version {protocol_version!r}; expected major version 1.",
        )


def _check_versions(payload: dict[str, Any]) -> None:
    _check_protocol_version(payload)
    if payload.get("schemaVersion") != GRAPH_SCHEMA_VERSION:
        raise SharedProtocolError(
            "unsupported_graph_schema_version",
            f"Unsupported graph schema version {payload.get('schemaVersion')!r}; expected {GRAPH_SCHEMA_VERSION}.",
        )


def _validate_definition(payload: dict[str, Any], definition: str, code: str) -> None:
    if not isinstance(payload, dict):
        raise SharedProtocolError(code, f"{definition} must be a JSON object.")
    _check_protocol_version(payload)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    target = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"}
    errors = sorted(Draft202012Validator(target).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.path) or definition
        raise SharedProtocolError(code, f"Invalid {definition} at {location}: {error.message}")


def validate_graph_data(payload: dict[str, Any]) -> None:
    """Validate a GraphData boundary payload while tolerating future fields."""
    if not isinstance(payload, dict):
        raise SharedProtocolError("invalid_graph_data", "GraphData must be a JSON object.")
    _check_versions(payload)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        required = {"recordId", "nodes", "edges", "metadata"}
        missing = sorted(required.difference(payload))
        if missing or not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
            detail = ", ".join(missing) if missing else "nodes and edges must be arrays"
            raise SharedProtocolError("invalid_graph_data", f"Invalid GraphData: {detail}.")
        return

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    graph_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/GraphData",
    }
    errors = sorted(Draft202012Validator(graph_schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.path) or "GraphData"
        raise SharedProtocolError("invalid_graph_data", f"Invalid GraphData at {location}: {error.message}")


def validate_task(payload: dict[str, Any]) -> None:
    """Validate a cross-process long-task status payload."""
    if not isinstance(payload, dict):
        raise SharedProtocolError("invalid_task", "Task must be a JSON object.")
    _check_protocol_version(payload)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        required = {"id", "type", "status", "cancellable", "progress"}
        missing = sorted(required.difference(payload))
        if missing or not isinstance(payload.get("progress"), dict):
            detail = ", ".join(missing) if missing else "progress must be an object"
            raise SharedProtocolError("invalid_task", f"Invalid Task: {detail}.")
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    task_schema = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/Task"}
    errors = sorted(Draft202012Validator(task_schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.path) or "Task"
        raise SharedProtocolError("invalid_task", f"Invalid Task at {location}: {error.message}")


def validate_graph_projection(payload: dict[str, Any]) -> None:
    """Validate an LOD projection response at the service boundary."""
    if not isinstance(payload, dict):
        raise SharedProtocolError("invalid_graph_projection", "GraphProjection must be a JSON object.")
    _check_versions(payload)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        required = {"recordId", "graph", "layout", "status"}
        missing = sorted(required.difference(payload))
        if missing or not isinstance(payload.get("graph"), dict) or not isinstance(payload.get("status"), dict):
            detail = ", ".join(missing) if missing else "graph and status must be objects"
            raise SharedProtocolError("invalid_graph_projection", f"Invalid GraphProjection: {detail}.")
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    projection_schema = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/GraphProjection"}
    errors = sorted(Draft202012Validator(projection_schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.path) or "GraphProjection"
        raise SharedProtocolError("invalid_graph_projection", f"Invalid GraphProjection at {location}: {error.message}")


def validate_graph_neighbor_page(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphNeighborPage", "invalid_graph_neighbor_page")


def validate_literature_page(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LiteraturePage", "invalid_literature_page")


def validate_graph_view_state(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphViewState", "invalid_graph_view_state")


def validate_graph_view_save_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphViewSaveRequest", "invalid_graph_view_save_request")


def validate_graph_view_list(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphViewList", "invalid_graph_view_list")


def validate_graph_view_restore(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphViewRestore", "invalid_graph_view_restore")


def validate_graph_view_mutation(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphViewMutationResult", "invalid_graph_view_mutation")


def validate_graph_timeline_query(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphTimelineQuery", "invalid_graph_timeline_query")


def validate_graph_timeline(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "GraphTimeline", "invalid_graph_timeline")


def validate_library_query(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibraryQuery", "invalid_library_query")


def validate_library_page(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibraryPage", "invalid_library_page")


def validate_library_record_detail(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibraryRecordDetail", "invalid_library_record_detail")


def validate_library_state(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibraryState", "invalid_library_state")


def validate_library_mutation_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibraryMutationRequest", "invalid_library_mutation_request")


def validate_library_mutation_result(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibraryMutationResult", "invalid_library_mutation_result")


def validate_research_workspace(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "ResearchWorkspace", "invalid_research_workspace")


def validate_research_statistics(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "ResearchStatistics", "invalid_research_statistics")


def validate_business_settings(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "BusinessSettings", "invalid_business_settings")


def validate_business_settings_update_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "BusinessSettingsUpdateRequest", "invalid_business_settings_update")


def validate_research_brief_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "ResearchBriefRequest", "invalid_research_brief_request")


def validate_research_brief_result(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "ResearchBriefResult", "invalid_research_brief_result")


def validate_library_sync_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibrarySyncRequest", "invalid_library_sync_request")


def validate_library_sync_result(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "LibrarySyncResult", "invalid_library_sync_result")


def validate_user_account(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "UserAccount", "invalid_user_account")


def validate_auth_session(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "AuthSession", "invalid_auth_session")


def validate_share_link(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "ShareLink", "invalid_share_link")


def validate_audit_event_page(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "AuditEventPage", "invalid_audit_event_page")


def validate_team_member_list(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "TeamMemberList", "invalid_team_member_list")


def validate_team_invite_create(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "TeamInviteCreateRequest", "invalid_team_invite_create")


def validate_team_invite_accept(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "TeamInviteAcceptRequest", "invalid_team_invite_accept")


def validate_team_invite(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "TeamInvite", "invalid_team_invite")


def validate_resource_permission_mutation(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "ResourcePermissionMutation", "invalid_resource_permission_mutation")


def validate_resource_permission_list(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "ResourcePermissionList", "invalid_resource_permission_list")


def validate_cloud_graph_sync_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CloudGraphSyncRequest", "invalid_cloud_graph_sync_request")


def validate_cloud_graph_sync_result(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CloudGraphSyncResult", "invalid_cloud_graph_sync_result")


def validate_cloud_graph_list(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CloudGraphList", "invalid_cloud_graph_list")


def validate_collaboration_annotation(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CollaborationAnnotation", "invalid_collaboration_annotation")


def validate_collaboration_snapshot(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CollaborationSnapshot", "invalid_collaboration_snapshot")


def validate_collaboration_mutation_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CollaborationMutationRequest", "invalid_collaboration_mutation_request")


def validate_collaboration_mutation_result(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CollaborationMutationResult", "invalid_collaboration_mutation_result")


def validate_collaboration_event_page(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CollaborationEventPage", "invalid_collaboration_event_page")


def validate_cloud_service_metrics(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "CloudServiceMetrics", "invalid_cloud_service_metrics")


def validate_diagnostic_report_create_request(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "DiagnosticReportCreateRequest", "invalid_diagnostic_report")


def validate_diagnostic_receipt(payload: dict[str, Any]) -> None:
    _validate_definition(payload, "DiagnosticReceipt", "invalid_diagnostic_receipt")


def _evidence_to_shared(evidence: KnowledgeGraphEvidence) -> dict[str, Any]:
    return {
        "page": evidence.page,
        "bbox": list(evidence.bbox),
        "elementId": evidence.element_id,
        "excerpt": evidence.excerpt,
        "translatedText": evidence.translated_text,
        "source": evidence.source,
        "recordId": evidence.record_id,
        "section": evidence.section,
        "extractionMethod": evidence.extraction_method,
    }


def _evidence_from_shared(value: dict[str, Any]) -> KnowledgeGraphEvidence:
    return KnowledgeGraphEvidence.from_dict(value)


def _node_to_shared(node: KnowledgeGraphNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "type": node.type,
        "label": node.label,
        "attributes": dict(node.details),
        "metrics": {"importance": node.importance, "confidence": node.confidence},
        "evidence": [_evidence_to_shared(item) for item in node.evidence],
        "summary": node.summary,
        "tags": list(node.tags),
        "pinned": node.pinned,
        "normalizedLabel": node.normalized_label,
        "canonicalId": node.canonical_id,
        "extractionMethod": node.extraction_method,
        "confidenceReason": list(node.confidence_reason),
        "sourceSection": node.source_section,
        "needsReview": node.needs_review,
        "reviewReasons": list(node.review_reasons),
    }


def _edge_to_shared(edge: KnowledgeGraphEdge) -> dict[str, Any]:
    relation = RELATION_CONFIG.get(edge.type.upper()) or {}
    return {
        "id": edge.id,
        "source": edge.source,
        "target": edge.target,
        "type": edge.type,
        "directed": not bool(relation.get("symmetric", False)),
        "weight": edge.confidence,
        "attributes": dict(edge.details),
        "evidence": [_evidence_to_shared(item) for item in edge.evidence],
        "label": edge.label,
        "normalizedLabel": edge.normalized_label,
        "canonicalId": edge.canonical_id,
        "extractionMethod": edge.extraction_method,
        "confidenceReason": list(edge.confidence_reason),
        "sourceSection": edge.source_section,
        "needsReview": edge.needs_review,
        "relationMethod": edge.relation_method,
        "relationEvidence": [_evidence_to_shared(item) for item in edge.relation_evidence],
        "directionReason": edge.direction_reason,
        "reviewReasons": list(edge.review_reasons),
    }


def _paper_to_shared(paper: dict[str, Any], record_id: str) -> dict[str, Any]:
    result = {key: value for key, value in paper.items() if value is not None}
    result["id"] = str(result.get("id") or result.get("recordId") or record_id)
    result["title"] = str(result.get("title") or "Untitled")
    if "year" in result:
        try:
            result["year"] = int(result["year"])
        except (TypeError, ValueError):
            result.pop("year", None)
    authors = []
    for author in result.get("authors") or []:
        if isinstance(author, dict):
            normalized = {key: value for key, value in author.items() if value is not None}
            normalized["name"] = str(
                normalized.get("name") or normalized.get("fullName") or normalized.get("full_name") or ""
            )
            authors.append(normalized)
        else:
            authors.append(str(author))
    if "authors" in result:
        result["authors"] = authors
    return result


def to_shared_graph_data(document: KnowledgeGraphDocument | dict[str, Any], *, view_state: dict[str, Any] | None = None) -> GraphData:
    source = document if isinstance(document, KnowledgeGraphDocument) else KnowledgeGraphDocument.from_dict(document)
    paper = _paper_to_shared(source.paper, source.record_id)
    result: GraphData = {
        "protocolVersion": PROTOCOL_VERSION,
        "schemaVersion": GRAPH_SCHEMA_VERSION,
        "recordId": source.record_id,
        "generatedAt": source.generated_at,
        "paper": paper,  # type: ignore[typeddict-item]
        "nodes": [_node_to_shared(item) for item in source.nodes],  # type: ignore[typeddict-item]
        "edges": [_edge_to_shared(item) for item in source.edges],  # type: ignore[typeddict-item]
        "metadata": dict(source.metadata),
    }
    if view_state is not None:
        result["viewState"] = dict(view_state)  # type: ignore[typeddict-item]
    validate_graph_data(result)
    return result


def from_shared_graph_data(payload: dict[str, Any]) -> KnowledgeGraphDocument:
    validate_graph_data(payload)
    nodes: list[KnowledgeGraphNode] = []
    for value in payload.get("nodes") or []:
        metrics = dict(value.get("metrics") or {})
        nodes.append(KnowledgeGraphNode(
            id=str(value.get("id") or ""),
            type=str(value.get("type") or "Concept"),
            label=str(value.get("label") or ""),
            summary=str(value.get("summary") or ""),
            importance=float(metrics.get("importance", 0.5) or 0.0),
            confidence=float(metrics.get("confidence", 1.0) or 0.0),
            tags=[str(item) for item in value.get("tags") or []],
            evidence=[_evidence_from_shared(item) for item in value.get("evidence") or [] if isinstance(item, dict)],
            details=dict(value.get("attributes") or {}),
            pinned=bool(value.get("pinned", False)),
            normalized_label=str(value.get("normalizedLabel") or ""),
            canonical_id=str(value.get("canonicalId") or ""),
            extraction_method=str(value.get("extractionMethod") or "legacy"),
            confidence_reason=[str(item) for item in value.get("confidenceReason") or []],
            source_section=value.get("sourceSection"),
            needs_review=bool(value.get("needsReview", False)),
            review_reasons=[str(item) for item in value.get("reviewReasons") or []],
        ))
    edges: list[KnowledgeGraphEdge] = []
    for value in payload.get("edges") or []:
        edges.append(KnowledgeGraphEdge(
            id=str(value.get("id") or ""),
            source=str(value.get("source") or ""),
            target=str(value.get("target") or ""),
            type=str(value.get("type") or "MENTIONS"),
            label=str(value.get("label") or ""),
            confidence=float(value.get("weight", 1.0) or 0.0),
            evidence=[_evidence_from_shared(item) for item in value.get("evidence") or [] if isinstance(item, dict)],
            details=dict(value.get("attributes") or {}),
            normalized_label=str(value.get("normalizedLabel") or ""),
            canonical_id=str(value.get("canonicalId") or ""),
            extraction_method=str(value.get("extractionMethod") or "legacy"),
            confidence_reason=[str(item) for item in value.get("confidenceReason") or []],
            source_section=value.get("sourceSection"),
            needs_review=bool(value.get("needsReview", False)),
            relation_method=str(value.get("relationMethod") or "legacy"),
            relation_evidence=[_evidence_from_shared(item) for item in value.get("relationEvidence") or [] if isinstance(item, dict)],
            direction_reason=str(value.get("directionReason") or ""),
            review_reasons=[str(item) for item in value.get("reviewReasons") or []],
        ))
    paper = dict(payload.get("paper") or {})
    paper.pop("id", None)
    return KnowledgeGraphDocument(
        record_id=str(payload.get("recordId") or ""),
        paper=paper,
        nodes=nodes,
        edges=edges,
        schema_version=GRAPH_SCHEMA_VERSION,
        generated_at=str(payload.get("generatedAt") or ""),
        metadata=dict(payload.get("metadata") or {}),
    )
