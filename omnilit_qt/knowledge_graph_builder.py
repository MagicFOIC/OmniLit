from __future__ import annotations

import hashlib
import json
from typing import Any

from .knowledge_graph_core import _authors, _fallback_keywords, _keywords, _normalized, _split_values, _text
from .knowledge_graph_extractor import extract_entity_candidates
from .knowledge_graph_layout import academic_layout, adjacency_index
from .knowledge_graph_normalizer import REVIEW_CONFIDENCE_THRESHOLD, normalize_candidates
from .knowledge_graph_ontology import relation_label
from .knowledge_graph_precision import PRECISION_VERSION
from .knowledge_graph_quality import validate_graph
from .knowledge_graph_relation_extractor import extract_relation_candidates
from .knowledge_graph_schema import KnowledgeGraphDocument, KnowledgeGraphEdge, KnowledgeGraphEvidence, KnowledgeGraphNode


BUILDER_VERSION = 11


def source_fingerprint(record: dict[str, Any], index: dict[str, Any]) -> str:
    metadata = {
        key: record.get(key)
        for key in (
            "recordId", "id", "title", "abstract", "extracted_abstract", "contentSummary",
            "summaryText", "keywordsText", "matchedKeywordsText", "topicTagsText", "authors", "authorsText",
            "institutions", "institution", "affiliations", "affiliation",
            "year", "doi", "localPdfPath",
        )
    }
    extraction = {
        "precisionVersion": PRECISION_VERSION,
        "sourceSha256": index.get("sourceSha256"),
        "analyzedAt": index.get("analyzedAt"),
        "engine": index.get("engine"),
        "pageCount": index.get("pageCount", len(index.get("pages") or [])),
        "pages": [
            (
                page.get("page"),
                [
                    (block.get("blockNo"), block.get("text"), block.get("bbox"))
                    for block in page.get("textBlocks") or page.get("blocks") or []
                    if isinstance(block, dict)
                ],
            )
            for page in index.get("pages") or []
            if isinstance(page, dict)
        ],
        "elements": [
            (item.get("id"), item.get("type"), item.get("page"), item.get("caption"), item.get("text"))
            for item in index.get("elements") or []
            if isinstance(item, dict)
        ],
    }
    payload = json.dumps({"builder": BUILDER_VERSION, "metadata": metadata, "extraction": extraction}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_is_fresh(cached: dict[str, Any], record: dict[str, Any], index: dict[str, Any]) -> bool:
    return (
        int(cached.get("builder_version") or 1) >= BUILDER_VERSION
        and str(cached.get("source_fingerprint") or "") == source_fingerprint(record, index)
    )


def node_is_visible_at_density(node: dict[str, Any], density: str, query: str = "") -> bool:
    if density not in {"compact", "normal"} or query.strip():
        return True
    return (
        str(node.get("type") or "").casefold() == "paper"
        or (
            not bool(node.get("needs_review", node.get("needsReview", False)))
            and float(node.get("confidence", 1.0) or 0.0) >= REVIEW_CONFIDENCE_THRESHOLD
        )
    )


def _structural_edge(
    record_id: str,
    index: int,
    source: str,
    target: KnowledgeGraphNode,
    relation_type: str,
    evidence: list[KnowledgeGraphEvidence],
    method: str,
) -> KnowledgeGraphEdge:
    return KnowledgeGraphEdge(
        id=f"edge:{record_id}:{index}", source=source, target=target.id, type=relation_type,
        label=relation_label(relation_type), confidence=target.confidence,
        evidence=list(evidence), extraction_method=method,
        confidence_reason=[f"{method}_association"], source_section=target.source_section,
        needs_review=target.needs_review, relation_method=method,
        relation_evidence=list(evidence),
        direction_reason=f"{source} contains extracted {target.type} {target.id}",
    )


def build_document(record_id: str, metadata: dict, extraction_index: dict | None = None) -> KnowledgeGraphDocument:
    record = dict(metadata or {})
    index = dict(extraction_index or {})
    record_id = str(record_id or record.get("recordId") or record.get("id") or "record")
    title = _text(record.get("title")) or "Untitled"
    paper_id = f"paper:{record_id}"
    paper = {
        "title": title,
        "authors": _authors(record),
        "year": _text(record.get("year") or record.get("publicationYear") or record.get("publicationDate"))[:4],
        "doi": _text(record.get("doi")),
        "source": _text(record.get("journalTitle") or record.get("journalName") or record.get("source")),
        "pdf_path": _text(record.get("localPdfPath") or index.get("sourcePath")),
    }
    nodes = [KnowledgeGraphNode(
        paper_id, "paper", title, importance=1.0, tags=["paper"], details=paper,
        extraction_method="metadata", confidence_reason=["record_metadata"],
    )]
    edges: list[KnowledgeGraphEdge] = []

    def append_metadata_node(kind: str, label: str, relation: str, *, source: str, edge_source: str = paper_id) -> None:
        node_id = f"{kind}:{_normalized(label)}"
        if any(item.id == node_id for item in nodes):
            return
        evidence = [KnowledgeGraphEvidence(
            excerpt=label, source=source, record_id=record_id,
            section="Metadata", extraction_method="metadata",
        )]
        node = KnowledgeGraphNode(
            node_id, kind, label, importance=0.72, tags=[kind], evidence=evidence,
            extraction_method="metadata", confidence_reason=[source.replace(".", "_")],
        )
        nodes.append(node)
        edges.append(KnowledgeGraphEdge(
            id=f"edge:{record_id}:{len(edges) + 1}", source=edge_source, target=node_id,
            type=relation, label=relation_label(relation), confidence=1.0,
            evidence=evidence, relation_evidence=evidence, extraction_method="metadata",
            confidence_reason=[source.replace(".", "_")], relation_method="metadata",
            direction_reason=f"{source} links {edge_source} to {node_id}",
        ))

    for author in paper["authors"]:
        append_metadata_node("author", author, "AUTHOR_OF", source="metadata.authors", edge_source=f"author:{_normalized(author)}")
        # AUTHOR_OF points from the author to the paper, so replace the helper's
        # self-targeted edge with the declared semantic direction.
        edges[-1].target = paper_id
        edges[-1].canonical_id = f"relation:author_of:{edges[-1].source}:{paper_id}"
        edges[-1].direction_reason = f"metadata.authors identifies {edges[-1].source} as an author of {paper_id}"

    venue = _text(record.get("journalTitle") or record.get("journalName") or record.get("journal") or record.get("venue"))
    if venue:
        append_metadata_node("venue", venue, "PUBLISHED_IN", source="metadata.venue")

    institutions: list[str] = []
    for key in ("institutions", "institution", "affiliations", "affiliation"):
        institutions.extend(_split_values(record.get(key)))
    seen_institutions: set[str] = set()
    for institution in institutions:
        normalized = _normalized(institution)
        if normalized in seen_institutions:
            continue
        seen_institutions.add(normalized)
        append_metadata_node("institution", institution, "ASSOCIATED_WITH", source="metadata.affiliations")

    for author_value in record.get("authors") or []:
        if not isinstance(author_value, dict):
            continue
        nested_author = author_value.get("author") if isinstance(author_value.get("author"), dict) else {}
        author_name = _text(
            author_value.get("display_name") or author_value.get("displayName") or author_value.get("name")
            or author_value.get("authorName") or nested_author.get("display_name") or nested_author.get("name")
        )
        affiliations = author_value.get("institutions") or author_value.get("affiliations") or author_value.get("affiliation") or []
        if not author_name or not affiliations:
            continue
        if not isinstance(affiliations, list):
            affiliations = [affiliations]
        author_node_id = f"author:{_normalized(author_name)}"
        for affiliation in affiliations:
            if isinstance(affiliation, dict):
                institution_name = _text(affiliation.get("display_name") or affiliation.get("name") or affiliation.get("institution"))
            else:
                institution_name = _text(affiliation)
            if not institution_name:
                continue
            institution_node_id = f"institution:{_normalized(institution_name)}"
            evidence = [KnowledgeGraphEvidence(
                excerpt=f"{author_name} — {institution_name}", source="metadata.authors.affiliations",
                record_id=record_id, section="Metadata", extraction_method="metadata",
            )]
            if not any(item.id == institution_node_id for item in nodes):
                nodes.append(KnowledgeGraphNode(
                    institution_node_id, "institution", institution_name, importance=0.72, tags=["institution"],
                    evidence=evidence, extraction_method="metadata", confidence_reason=["metadata_authors_affiliations"],
                ))
            if not any(edge.type == "AFFILIATED_WITH" and edge.source == author_node_id and edge.target == institution_node_id for edge in edges):
                edges.append(KnowledgeGraphEdge(
                    id=f"edge:{record_id}:{len(edges) + 1}", source=author_node_id, target=institution_node_id,
                    type="AFFILIATED_WITH", label=relation_label("AFFILIATED_WITH"), confidence=1.0, evidence=evidence,
                    relation_evidence=evidence, extraction_method="metadata", confidence_reason=["metadata_authors_affiliations"],
                    relation_method="metadata", direction_reason="explicit author affiliation metadata links the author to the institution",
                ))

    keywords, keyword_source = _keywords(record)
    for keyword in keywords:
        evidence = [KnowledgeGraphEvidence(source=keyword_source, excerpt=keyword, record_id=record_id, section="Keywords", extraction_method="metadata")]
        node = KnowledgeGraphNode(
            f"concept:{_normalized(keyword)}", "concept", keyword, importance=0.65,
            tags=["concept", "keyword"], evidence=evidence, extraction_method="metadata",
            confidence_reason=["keyword_metadata"],
        )
        nodes.append(node)
        edges.append(_structural_edge(record_id, len(edges) + 1, paper_id, node, "MENTIONS", evidence, "metadata"))

    candidates, blocks = extract_entity_candidates(record_id, record, index)
    section_nodes: set[str] = set()
    for block in blocks:
        if not block.is_heading or not block.section or block.section in section_nodes:
            continue
        section_nodes.add(block.section)
        evidence = [KnowledgeGraphEvidence(
            page=block.page, bbox=list(block.bbox), element_id=block.block_id,
            excerpt=block.text, source=block.source, record_id=record_id,
            section=block.section or "", extraction_method="section",
        )]
        node = KnowledgeGraphNode(
            f"section:{record_id}:{_normalized(block.section)}", "section", block.section,
            summary=block.text, importance=0.8, tags=["structure"], evidence=evidence,
            extraction_method="section", confidence_reason=["recognized_section_heading"],
            source_section=block.section,
        )
        nodes.append(node)
        edges.append(_structural_edge(record_id, len(edges) + 1, paper_id, node, "HAS_SECTION", evidence, "section"))

    abstract = _text(record.get("abstract") or record.get("extracted_abstract"))
    content_summary = _text(record.get("contentSummary") or record.get("summaryText") or record.get("content_summary"))
    for section, text, source, importance in (
        ("Abstract", abstract, "metadata.abstract", 0.9),
        ("Summary", content_summary, "metadata.contentSummary", 0.82),
    ):
        if not text or section in section_nodes or (section == "Summary" and _normalized(text) == _normalized(abstract)):
            continue
        section_nodes.add(section)
        evidence = [KnowledgeGraphEvidence(excerpt=text[:800], source=source, record_id=record_id, section=section, extraction_method="metadata")]
        node = KnowledgeGraphNode(
            f"section:{record_id}:{_normalized(section)}", "section", section,
            summary=text, importance=importance, tags=["structure"], evidence=evidence,
            extraction_method="metadata", confidence_reason=[f"{section.casefold()}_metadata"],
            source_section=section,
        )
        nodes.append(node)
        edges.append(_structural_edge(record_id, len(edges) + 1, paper_id, node, "HAS_SECTION", evidence, "metadata"))

    entities = normalize_candidates(candidates)
    entity_nodes = [entity.to_node() for entity in entities]
    nodes.extend(entity_nodes)
    relations = extract_relation_candidates(record_id, entities)
    edges.extend(relation.to_edge(record_id, len(edges) + offset) for offset, relation in enumerate(relations, start=1))

    if len(nodes) == 1:
        for keyword in _fallback_keywords(record):
            evidence = [KnowledgeGraphEvidence(excerpt=title, source="metadata.title", record_id=record_id, section="Title", extraction_method="metadata")]
            node = KnowledgeGraphNode(
                f"concept:{_normalized(keyword)}", "concept", keyword, importance=0.5,
                confidence=0.5, tags=["concept", "needs_review"], evidence=evidence,
                extraction_method="metadata", confidence_reason=["fallback_keyword"], needs_review=True,
            )
            nodes.append(node)
            edges.append(_structural_edge(record_id, len(edges) + 1, paper_id, node, "MENTIONS", evidence, "metadata"))

    validation = validate_graph(nodes, edges)
    node_dicts = [node.to_dict() for node in nodes]
    edge_dicts = [edge.to_dict() for edge in edges]
    return KnowledgeGraphDocument(
        record_id=record_id,
        paper=paper,
        nodes=nodes,
        edges=edges,
        metadata={
            "source": {
                "pdfPath": paper["pdf_path"],
                "extractionEngine": _text(index.get("engine")),
                "sourceSha256": _text(index.get("sourceSha256")),
            },
            "summary": {"keywords": keywords, "contentSummary": content_summary, "abstract": abstract},
            "stats": {
                "nodes": len(nodes), "edges": len(edges),
                "evidence": sum(len(node.evidence) for node in nodes) + sum(len(edge.relation_evidence) for edge in edges),
                "entity_candidates": len(candidates), "normalized_entities": len(entities),
                "relation_candidates": len(relations),
                "needs_review": validation.summary["needs_review_count"] + validation.summary["relation_needs_review_count"],
            },
            "pipeline": [
                "precision_section_filter", "entity_candidates", "canonical_normalization",
                "relation_candidates", "confidence_scoring", "quality_validation",
            ],
            "extraction_quality": {
                "accepted_nodes": validation.summary["accepted_nodes"],
                "review_nodes": validation.summary["review_nodes"],
                "dropped_nodes": 0,
                "accepted_edges": validation.summary["accepted_edges"],
                "review_edges": validation.summary["review_edges"],
                "warnings": list(validation.summary.get("warnings") or []),
            },
            "review_mode": {
                "confidence_threshold": REVIEW_CONFIDENCE_THRESHOLD,
                "needs_review_nodes": validation.summary["needs_review_count"],
                "needs_review_edges": validation.summary["relation_needs_review_count"],
                "evidence_count": validation.summary["evidence_count"],
                "quality_warnings": list(validation.summary.get("warnings") or []),
            },
            "builder_version": BUILDER_VERSION,
            "source_fingerprint": source_fingerprint(record, index),
            "quality_summary": validation.summary,
            "quality_issues": validation.issues,
            "layout": academic_layout(node_dicts),
            "adjacency": adjacency_index(edge_dicts),
        },
    )


def build_knowledge_graph(record: dict, extraction_index: dict | None = None) -> dict:
    record_id = str((record or {}).get("recordId") or (record or {}).get("id") or "record")
    return build_document(record_id, record, extraction_index).to_dict()
