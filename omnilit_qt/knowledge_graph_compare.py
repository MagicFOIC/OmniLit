from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from .knowledge_graph_core import _normalized
from .knowledge_graph_schema import KnowledgeGraphDocument, KnowledgeGraphEdge, KnowledgeGraphEvidence, KnowledgeGraphNode
from .knowledge_graph_layout import academic_layout, adjacency_index


COMPARISON_DIMENSIONS = ("problem", "method", "dataset", "metric", "baseline", "result", "contribution", "limitation", "futurework")


def compare_documents(documents: list[KnowledgeGraphDocument], comparison_id: str = "") -> KnowledgeGraphDocument:
    docs = [document for document in documents if isinstance(document, KnowledgeGraphDocument)]
    if not comparison_id:
        digest = hashlib.sha1("\n".join(sorted(item.record_id for item in docs)).encode("utf-8")).hexdigest()[:12]
        comparison_id = f"comparison_{digest}"
    nodes: list[KnowledgeGraphNode] = []
    edges: list[KnowledgeGraphEdge] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    occurrences: dict[tuple[str, str], list[tuple[str, KnowledgeGraphNode]]] = defaultdict(list)

    for document in docs:
        for node in document.nodes:
            copied = KnowledgeGraphNode.from_dict(node.to_dict())
            copied.details.setdefault("paper_ids", []).append(document.record_id)
            if copied.id not in node_ids:
                nodes.append(copied)
                node_ids.add(copied.id)
            else:
                existing = next(item for item in nodes if item.id == copied.id)
                paper_ids = existing.details.setdefault("paper_ids", [])
                if document.record_id not in paper_ids:
                    paper_ids.append(document.record_id)
                existing.details["common"] = True
                existing.evidence.extend(item for item in copied.evidence if item.to_dict() not in [value.to_dict() for value in existing.evidence])
            if copied.type.casefold() != "paper":
                occurrences[(copied.type.casefold(), _normalized(copied.label))].append((document.record_id, copied))
        for edge in document.edges:
            copied_edge = KnowledgeGraphEdge.from_dict(edge.to_dict())
            if copied_edge.id in edge_ids:
                copied_edge.id = f"{copied_edge.id}:{document.record_id}"
            edge_ids.add(copied_edge.id)
            edges.append(copied_edge)

    edge_index = len(edges)
    for (kind, normalized_label), values in occurrences.items():
        paper_ids = sorted({paper_id for paper_id, _ in values})
        if len(paper_ids) < 2 or len(values) < 2:
            continue
        comparison_node_id = f"comparison:{kind}:{normalized_label}"
        if comparison_node_id not in node_ids:
            nodes.append(KnowledgeGraphNode(comparison_node_id, "comparison", values[0][1].label, summary="多篇文献中的共同概念", importance=0.9, tags=["common", kind], evidence=[evidence for _, node in values for evidence in node.evidence], details={"paper_ids": paper_ids, "common": True, "dimension": kind}))
            node_ids.add(comparison_node_id)
        for _, node in values:
            edge_index += 1
            edges.append(KnowledgeGraphEdge(f"compare-edge:{edge_index}", node.id, comparison_node_id, "SAME_AS", "共同概念", confidence=0.9, evidence=list(node.evidence)))

    semantic = [(paper_id, node) for values in occurrences.values() for paper_id, node in values if node.type.casefold() in {"concept", "method", "dataset", "metric", "result", "contribution", "limitation"}]
    for left_index, (left_paper, left) in enumerate(semantic):
        left_tokens = set(_normalized(left.label).split("_"))
        for right_paper, right in semantic[left_index + 1:]:
            if left_paper == right_paper or left.type.casefold() != right.type.casefold() or left.id == right.id:
                continue
            right_tokens = set(_normalized(right.label).split("_"))
            similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
            if similarity >= 0.60:
                edge_index += 1
                edges.append(KnowledgeGraphEdge(f"compare-edge:{edge_index}", left.id, right.id, "SIMILAR_TO", "相似概念", confidence=similarity, evidence=list(left.evidence) + list(right.evidence), details={"paper_ids": [left_paper, right_paper]}))

            if left.type.casefold() == "result":
                positive = ("improve", "outperform", "increase", "higher", "提升", "优于", "增加")
                negative = ("not ", "underperform", "decrease", "lower", "降低", "不显著", "未提升")
                left_text = f"{left.label} {left.summary}".casefold()
                right_text = f"{right.label} {right.summary}".casefold()
                opposite = (any(token in left_text for token in positive) and any(token in right_text for token in negative)) or (any(token in right_text for token in positive) and any(token in left_text for token in negative))
                if opposite and similarity >= 0.25:
                    conflict_id = f"conflict:{_normalized(left.id)}:{_normalized(right.id)}"
                    evidence = list(left.evidence) + list(right.evidence)
                    if conflict_id not in node_ids:
                        nodes.append(KnowledgeGraphNode(conflict_id, "conflict", "结果表述可能冲突", summary=f"{left.label} / {right.label}", importance=0.9, confidence=min(0.75, max(0.5, similarity)), tags=["conflict", "result"], evidence=evidence, details={"paper_ids": [left_paper, right_paper]}))
                        node_ids.add(conflict_id)
                    edge_index += 1
                    edges.append(KnowledgeGraphEdge(f"compare-edge:{edge_index}", left.id, right.id, "CONTRADICTS", "可能冲突", confidence=min(0.75, max(0.5, similarity)), evidence=evidence))

    for document in docs:
        available = {node.type.casefold().replace("_", "") for node in document.nodes}
        for dimension in COMPARISON_DIMENSIONS:
            if dimension in available:
                continue
            node_id = f"missing:{document.record_id}:{dimension}"
            evidence = [KnowledgeGraphEvidence(source="comparison.missing_dimension", excerpt=f"图谱中未识别到 {dimension} 节点", record_id=document.record_id)]
            nodes.append(KnowledgeGraphNode(node_id, "missinginfo", f"缺失：{dimension}", summary=f"{document.paper.get('title', document.record_id)} 未识别到 {dimension} 信息", importance=0.35, confidence=1.0, tags=["missing", dimension], evidence=evidence, details={"paper_ids": [document.record_id], "dimension": dimension, "only_in": document.record_id}))
            edge_index += 1
            edges.append(KnowledgeGraphEdge(f"compare-edge:{edge_index}", f"paper:{document.record_id}", node_id, "MISSING", "缺失信息", evidence=evidence))

    for node in nodes:
        paper_ids = node.details.get("paper_ids") or []
        if len(paper_ids) == 1 and node.type.casefold() != "paper":
            node.details.setdefault("only_in", paper_ids[0])

    node_dicts = [node.to_dict() for node in nodes]
    edge_dicts = [edge.to_dict() for edge in edges]
    return KnowledgeGraphDocument(
        record_id=comparison_id,
        paper={"title": f"对比知识图谱（{len(docs)} 篇）", "authors": [], "year": "", "doi": "", "source": "comparison", "pdf_path": ""},
        nodes=nodes,
        edges=edges,
        metadata={
            "comparison": True,
            "comparison_record_ids": [item.record_id for item in docs],
            "summary": {"keywords": [], "contentSummary": "", "abstract": ""},
            "source": {"pdfPath": "", "extractionEngine": "mixed", "sourceSha256": ""},
            "builder_version": 2,
            "quality_summary": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "evidence_coverage": round(sum(bool(node.evidence) for node in nodes if node.type != "paper") / max(1, sum(node.type != "paper" for node in nodes)), 3),
            },
            "layout": academic_layout(node_dicts, comparison=True),
            "adjacency": adjacency_index(edge_dicts),
        },
    )


def compare_graph_dicts(graphs: list[dict], comparison_id: str = "") -> dict[str, Any]:
    result = compare_documents([KnowledgeGraphDocument.from_dict(graph) for graph in graphs], comparison_id).to_dict()
    result["comparisonRecordIds"] = list((result.get("metadata") or {}).get("comparison_record_ids") or [])
    return result
