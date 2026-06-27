from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .knowledge_graph_precision import invalid_label_reason
from .knowledge_graph_schema import KnowledgeGraphEdge, KnowledgeGraphNode


REVIEW_CONFIDENCE_THRESHOLD = 0.6
EVIDENCE_EXEMPT_TYPES = {"paper", "section", "metadata"}
GENERIC_REVIEW_TYPES = {"concept", "researchgap", "problem", "contribution", "method", "dataset", "metric", "experiment", "result", "limitation", "futurework", "domainentity", "material"}


@dataclass
class GraphQualityValidation:
    summary: dict[str, Any]
    issues: list[str]


def validate_graph(nodes: list[KnowledgeGraphNode], edges: list[KnowledgeGraphEdge]) -> GraphQualityValidation:
    issues: list[str] = []
    warnings: list[str] = []
    degree: dict[str, int] = {node.id: 0 for node in nodes}
    for edge in edges:
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1

    for node in nodes:
        if node.confidence < REVIEW_CONFIDENCE_THRESHOLD:
            node.needs_review = True
            node.review_reasons = list(dict.fromkeys(node.review_reasons + ["low_confidence"]))
        if node.needs_review and "needs_review" not in node.tags:
            node.tags.append("needs_review")
        if node.type not in EVIDENCE_EXEMPT_TYPES and not node.evidence:
            node.needs_review = True
            if "needs_review" not in node.tags:
                node.tags.append("needs_review")
            node.confidence_reason = list(dict.fromkeys(node.confidence_reason + ["missing_evidence"]))
            node.review_reasons = list(dict.fromkeys(node.review_reasons + ["missing_evidence"]))
            issues.append(f"node_without_evidence:{node.id}")
        if node.type not in EVIDENCE_EXEMPT_TYPES:
            for index, evidence in enumerate(node.evidence):
                if not evidence.excerpt:
                    node.needs_review = True
                    node.review_reasons = list(dict.fromkeys(node.review_reasons + ["evidence_missing_excerpt"]))
                    issues.append(f"node_evidence_without_excerpt:{node.id}:{index}")
                if not evidence.source or not evidence.record_id:
                    node.needs_review = True
                    node.review_reasons = list(dict.fromkeys(node.review_reasons + ["evidence_missing_source"]))
                    issues.append(f"node_evidence_without_source:{node.id}:{index}")
        label_reason = invalid_label_reason(node.label)
        if node.type.casefold() in GENERIC_REVIEW_TYPES and label_reason:
            node.needs_review = True
            node.review_reasons = list(dict.fromkeys(node.review_reasons + [label_reason]))
            if node.importance >= 0.7 and node.confidence >= REVIEW_CONFIDENCE_THRESHOLD:
                warnings.append(f"generic_label_high_visible:{node.id}")

    for edge in edges:
        if not edge.relation_evidence and edge.evidence:
            edge.relation_evidence = list(edge.evidence)
        if not edge.relation_evidence:
            edge.needs_review = True
            edge.confidence_reason = list(dict.fromkeys(edge.confidence_reason + ["missing_relation_evidence"]))
            edge.review_reasons = list(dict.fromkeys(edge.review_reasons + ["missing_relation_evidence"]))
            issues.append(f"edge_without_relation_evidence:{edge.id}")
        for index, evidence in enumerate(edge.relation_evidence):
            if not evidence.excerpt:
                edge.needs_review = True
                edge.review_reasons = list(dict.fromkeys(edge.review_reasons + ["relation_evidence_missing_excerpt"]))
                issues.append(f"edge_evidence_without_excerpt:{edge.id}:{index}")
        if not edge.direction_reason:
            edge.needs_review = True
            edge.review_reasons = list(dict.fromkeys(edge.review_reasons + ["missing_direction_reason"]))
            issues.append(f"edge_without_direction_reason:{edge.id}")
        if edge.relation_method == "same_section" and not edge.needs_review:
            edge.needs_review = True
            edge.review_reasons = list(dict.fromkeys(edge.review_reasons + ["same_section_only_relation"]))
            issues.append(f"same_section_relation_without_review:{edge.id}")
        if edge.confidence < REVIEW_CONFIDENCE_THRESHOLD and not edge.needs_review:
            edge.needs_review = True
            edge.review_reasons = list(dict.fromkeys(edge.review_reasons + ["low_confidence"]))

    evidence_nodes = [node for node in nodes if node.type != "paper"]
    evidence_edges = [edge for edge in edges if edge.type != "MENTIONS" or edge.relation_evidence]
    semantic_nodes = [node for node in nodes if node.type not in {"paper", "section"}]
    isolated_ratio = round(sum(degree.get(node.id, 0) == 0 for node in semantic_nodes) / max(1, len(semantic_nodes)), 3)
    citation_ratio = round(sum(node.type == "citation" for node in semantic_nodes) / max(1, len(semantic_nodes)), 3)
    if isolated_ratio > 0.35:
        warnings.append(f"isolated_node_ratio:{isolated_ratio}")
    if citation_ratio > 0.25:
        warnings.append(f"citation_node_ratio:{citation_ratio}")
    summary = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "evidence_count": sum(len(node.evidence) for node in nodes),
        "evidence_coverage": round(sum(bool(node.evidence) for node in evidence_nodes) / max(1, len(evidence_nodes)), 3),
        "edge_evidence_coverage": round(sum(bool(edge.relation_evidence) for edge in evidence_edges) / max(1, len(evidence_edges)), 3),
        "average_confidence": round(sum(node.confidence for node in evidence_nodes) / max(1, len(evidence_nodes)), 3),
        "needs_review_count": sum(node.needs_review for node in evidence_nodes),
        "relation_needs_review_count": sum(edge.needs_review for edge in edges),
        "isolated_node_ratio": isolated_ratio,
        "citation_node_ratio": citation_ratio,
        "accepted_nodes": sum(not node.needs_review for node in evidence_nodes),
        "review_nodes": sum(node.needs_review for node in evidence_nodes),
        "accepted_edges": sum(not edge.needs_review for edge in edges),
        "review_edges": sum(edge.needs_review for edge in edges),
        "warnings": warnings,
        "validation_issue_count": len(issues),
    }
    return GraphQualityValidation(summary=summary, issues=issues)
