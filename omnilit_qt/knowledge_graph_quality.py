from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .knowledge_graph_schema import KnowledgeGraphEdge, KnowledgeGraphNode


REVIEW_CONFIDENCE_THRESHOLD = 0.6
EVIDENCE_EXEMPT_TYPES = {"paper", "section", "metadata"}


@dataclass
class GraphQualityValidation:
    summary: dict[str, Any]
    issues: list[str]


def validate_graph(nodes: list[KnowledgeGraphNode], edges: list[KnowledgeGraphEdge]) -> GraphQualityValidation:
    issues: list[str] = []
    for node in nodes:
        if node.confidence < REVIEW_CONFIDENCE_THRESHOLD:
            node.needs_review = True
        if node.needs_review and "needs_review" not in node.tags:
            node.tags.append("needs_review")
        if node.type not in EVIDENCE_EXEMPT_TYPES and not node.evidence:
            node.needs_review = True
            if "needs_review" not in node.tags:
                node.tags.append("needs_review")
            node.confidence_reason = list(dict.fromkeys(node.confidence_reason + ["missing_evidence"]))
            issues.append(f"node_without_evidence:{node.id}")

    for edge in edges:
        if not edge.relation_evidence and edge.evidence:
            edge.relation_evidence = list(edge.evidence)
        if not edge.relation_evidence:
            edge.needs_review = True
            edge.confidence_reason = list(dict.fromkeys(edge.confidence_reason + ["missing_relation_evidence"]))
            issues.append(f"edge_without_relation_evidence:{edge.id}")
        if not edge.direction_reason:
            edge.needs_review = True
            issues.append(f"edge_without_direction_reason:{edge.id}")

    evidence_nodes = [node for node in nodes if node.type != "paper"]
    evidence_edges = [edge for edge in edges if edge.type != "MENTIONS" or edge.relation_evidence]
    summary = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "evidence_count": sum(len(node.evidence) for node in nodes),
        "evidence_coverage": round(sum(bool(node.evidence) for node in evidence_nodes) / max(1, len(evidence_nodes)), 3),
        "edge_evidence_coverage": round(sum(bool(edge.relation_evidence) for edge in evidence_edges) / max(1, len(evidence_edges)), 3),
        "average_confidence": round(sum(node.confidence for node in evidence_nodes) / max(1, len(evidence_nodes)), 3),
        "needs_review_count": sum(node.needs_review for node in evidence_nodes),
        "relation_needs_review_count": sum(edge.needs_review for edge in edges),
        "validation_issue_count": len(issues),
    }
    return GraphQualityValidation(summary=summary, issues=issues)
