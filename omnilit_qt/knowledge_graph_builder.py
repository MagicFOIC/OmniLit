from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from .knowledge_graph_core import _authors, _fallback_keywords, _keywords, _normalized, _text
from .knowledge_graph_schema import KnowledgeGraphDocument, KnowledgeGraphEdge, KnowledgeGraphEvidence, KnowledgeGraphNode
from .knowledge_graph_layout import academic_layout, adjacency_index


BUILDER_VERSION = 3


SECTION_NAMES = {
    "abstract": "Abstract", "introduction": "Introduction", "background": "Introduction",
    "method": "Method", "methods": "Method", "methodology": "Method",
    "experiment": "Experiment", "experiments": "Experiment",
    "result": "Results", "results": "Results", "discussion": "Discussion",
    "conclusion": "Conclusion", "conclusions": "Conclusion",
    "摘要": "Abstract", "引言": "Introduction", "方法": "Method", "实验": "Experiment",
    "结果": "Results", "讨论": "Discussion", "结论": "Conclusion",
}
CLAIM_PATTERNS = (
    ("Contribution", re.compile(r"\b(?:we|this (?:paper|work)) (?:propose|introduce|present|contribute)\b|本文(?:提出|贡献|设计)", re.I)),
    ("Result", re.compile(r"\b(?:results? (?:show|indicate|demonstrate)|outperform|achieve|improve)\b|(?:结果表明|优于|达到|提升)", re.I)),
    ("Limitation", re.compile(r"\b(?:limitation|limited by|future work)\b|(?:局限|不足|未来工作)", re.I)),
    ("Method", re.compile(r"\b(?:we use|we employ|method|algorithm|model|framework|architecture)\b|(?:方法|模型|算法|框架)", re.I)),
)

ENTITY_PATTERNS = (
    ("Contribution", CLAIM_PATTERNS[0][1], "PROPOSES"),
    ("ResearchGap", re.compile(r"\b(?:however|remains? (?:unclear|unknown|challenging)|lack(?:s|ing)?|few studies)\b|(?:然而|仍不清楚|研究空白|缺乏研究)", re.I), "ADDRESSES_GAP"),
    ("Problem", re.compile(r"\b(?:problem|challenge|bottleneck|difficulty)\b|(?:问题|挑战|瓶颈|难点)", re.I), "SOLVES"),
    ("Result", CLAIM_PATTERNS[1][1], "ACHIEVES"),
    ("Limitation", re.compile(r"\b(?:limitation|limited by|drawback)\b|(?:局限|不足|缺点)", re.I), "HAS_LIMITATION"),
    ("FutureWork", re.compile(r"\b(?:future work|future research|in the future)\b|(?:未来工作|未来研究|后续工作)", re.I), "SUGGESTS_FUTURE_WORK"),
    ("Dataset", re.compile(r"\b(?:dataset|corpus|benchmark|database|cohort)\b|(?:数据集|语料库|基准数据|队列)", re.I), "EVALUATES_ON"),
    ("Metric", re.compile(r"\b(?:accuracy|precision|recall|f1(?:-score)?|auc|rmse|mae|bleu|rouge|latency|throughput)\b|(?:准确率|精确率|召回率|误差|延迟|吞吐量)", re.I), "MEASURED_BY"),
    ("Experiment", re.compile(r"\b(?:experiment|evaluation|ablation|control group|randomized)\b|(?:实验|评估|消融|对照组|随机试验)", re.I), "USES"),
    ("Method", CLAIM_PATTERNS[3][1], "USES"),
    ("Citation", re.compile(r"\[(?:\d+[,-]?\s*)+\]|\b[A-Z][A-Za-z-]+\s+et\s+al\.?(?:,?\s*\d{4})?", re.I), "CITES"),
)


def source_fingerprint(record: dict[str, Any], index: dict[str, Any]) -> str:
    metadata = {key: record.get(key) for key in ("recordId", "id", "title", "abstract", "extracted_abstract", "contentSummary", "summaryText", "keywordsText", "matchedKeywordsText", "topicTagsText", "authorsText", "year", "doi", "localPdfPath")}
    extraction = {
        "sourceSha256": index.get("sourceSha256"),
        "analyzedAt": index.get("analyzedAt"),
        "engine": index.get("engine"),
        "pageCount": index.get("pageCount", len(index.get("pages") or [])),
        "elements": [(item.get("id"), item.get("type"), item.get("page")) for item in index.get("elements") or [] if isinstance(item, dict)],
    }
    payload = json.dumps({"builder": BUILDER_VERSION, "metadata": metadata, "extraction": extraction}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evidence(record_id: str, page: int, bbox: Any, element_id: str, excerpt: str, source: str) -> KnowledgeGraphEvidence:
    return KnowledgeGraphEvidence(page=page, bbox=[float(item) for item in bbox or []], element_id=element_id, excerpt=excerpt[:800], source=source, record_id=record_id)


def _page_blocks(index: dict) -> list[tuple[int, dict]]:
    raw: list[tuple[int, float, dict]] = []
    page_count = len(index.get("pages") or [])
    for page in index.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page") or 0)
        page_height = float(page.get("height") or 0.0)
        blocks = page.get("textBlocks") or page.get("blocks") or []
        for block in blocks:
            if isinstance(block, dict) and _text(block.get("text")):
                raw.append((page_number, page_height, block))
    repeated: Counter[str] = Counter()
    for _, page_height, block in raw:
        text = _clean_text(block.get("text"))
        bbox = block.get("bbox") or []
        margin = len(bbox) >= 4 and page_height > 0 and (float(bbox[1]) <= page_height * 0.12 or float(bbox[3]) >= page_height * 0.88)
        if margin and 2 <= len(text) <= 120:
            repeated[text.casefold()] += 1
    threshold = max(3, int(page_count * 0.30 + 0.999))
    return [
        (page_number, block)
        for page_number, _, block in raw
        if repeated[_clean_text(block.get("text")).casefold()] < threshold
    ]


def _clean_text(value: Any) -> str:
    text = _text(value).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    result = []
    for item in re.split(r"(?<=[.!?。！？])\s*|[\r\n]+", _clean_text(text)):
        value = item.strip()
        minimum = 12 if re.search(r"[\u3400-\u9fff]", value) else 25
        if minimum <= len(value) <= 600:
            result.append(value)
    return result


def _confidence(kind: str, sentence: str, section: str, block: dict[str, Any]) -> float:
    value = 0.58
    if section.casefold() in {"method", "experiment", "results", "discussion", "conclusion"}:
        value += 0.08
    if kind.casefold() in section.casefold() or (kind == "Result" and section in {"Results", "Conclusion"}):
        value += 0.10
    if re.search(r"\b(?:we|our|this (?:paper|study|work))\b|(?:本文|本研究)", sentence, re.I):
        value += 0.08
    if len(block.get("bbox") or []) >= 4:
        value += 0.05
    return round(min(0.95, value), 3)


def _entity_label(kind: str, sentence: str) -> str:
    if kind == "Metric":
        matches = re.findall(r"\b(?:accuracy|precision|recall|f1(?:-score)?|auc|rmse|mae|bleu|rouge|latency|throughput)\b|(?:准确率|精确率|召回率|误差|延迟|吞吐量)", sentence, re.I)
        if matches:
            return " / ".join(dict.fromkeys(match.upper() if match.isascii() and len(match) <= 6 else match for match in matches))
    if kind == "Dataset":
        match = re.search(r"(?:[A-Za-z0-9_-]+\s+){0,3}(?:dataset|corpus|benchmark|database|cohort)|[\u3400-\u9fffA-Za-z0-9_-]{0,12}(?:数据集|语料库|基准数据|队列)", sentence, re.I)
        if match:
            return match.group(0).strip()
    prefix = {"ResearchGap": "研究空白", "Problem": "研究问题", "Contribution": "主要贡献", "Method": "研究方法", "Experiment": "实验设计", "Result": "关键结果", "Limitation": "研究局限", "FutureWork": "未来工作"}.get(kind, kind)
    excerpt = sentence[:72] + ("…" if len(sentence) > 72 else "")
    return f"{prefix} · {excerpt}"


def build_document(record_id: str, metadata: dict, extraction_index: dict | None = None) -> KnowledgeGraphDocument:
    record = dict(metadata or {})
    index = dict(extraction_index or {})
    record_id = str(record_id or record.get("recordId") or record.get("id") or "record")
    title = _text(record.get("title")) or "Untitled"
    paper_id = f"paper:{record_id}"
    paper = {
        "title": title, "authors": _authors(record),
        "year": _text(record.get("year") or record.get("publicationYear") or record.get("publicationDate"))[:4],
        "doi": _text(record.get("doi")),
        "source": _text(record.get("journalTitle") or record.get("journalName") or record.get("source")),
        "pdf_path": _text(record.get("localPdfPath") or index.get("sourcePath")),
    }
    nodes = [KnowledgeGraphNode(paper_id, "paper", title, importance=1.0, tags=["paper"], details=paper)]
    edges: list[KnowledgeGraphEdge] = []
    node_ids = {paper_id}
    edge_count = 0

    def add_node(node: KnowledgeGraphNode, relation: str = "MENTIONS", source: str = paper_id, edge_evidence: list[KnowledgeGraphEvidence] | None = None) -> None:
        nonlocal edge_count
        if node.id not in node_ids:
            nodes.append(node)
            node_ids.add(node.id)
        edge_count += 1
        edges.append(KnowledgeGraphEdge(f"edge:{record_id}:{edge_count}", source, node.id, relation, relation.replace("_", " ").lower(), evidence=list(edge_evidence or node.evidence)))

    keywords, keyword_source = _keywords(record)
    for keyword in keywords:
        evidence = [KnowledgeGraphEvidence(source=keyword_source, excerpt=keyword, record_id=record_id)]
        add_node(KnowledgeGraphNode(f"concept:{_normalized(keyword)}", "concept", keyword, importance=0.65, tags=["concept", "keyword"], evidence=evidence), "MENTIONS")

    section_nodes: dict[str, str] = {}
    blocks = _page_blocks(index)
    for page, block in blocks:
        text = _text(block.get("text"))
        compact = re.sub(r"^[\d.\s]+", "", text).strip().rstrip(":：").casefold()
        canonical = SECTION_NAMES.get(compact)
        if canonical and canonical not in section_nodes:
            evidence = [_evidence(record_id, page, block.get("bbox"), f"page-{page}-block-{block.get('blockNo', 0)}", text, "extraction_index.pages")]
            node_id = f"section:{record_id}:{_normalized(canonical)}"
            section_nodes[canonical] = node_id
            add_node(KnowledgeGraphNode(node_id, "section", canonical, summary=text, importance=0.8, tags=["structure"], evidence=evidence), "HAS_SECTION")

    abstract = _text(record.get("abstract") or record.get("extracted_abstract"))
    content_summary = _text(record.get("contentSummary") or record.get("summaryText") or record.get("content_summary"))
    if abstract and "Abstract" not in section_nodes:
        evidence = [KnowledgeGraphEvidence(excerpt=abstract[:800], source="metadata.abstract", record_id=record_id)]
        node_id = f"section:{record_id}:abstract"
        section_nodes["Abstract"] = node_id
        add_node(KnowledgeGraphNode(node_id, "section", "Abstract", summary=abstract, importance=0.9, tags=["structure"], evidence=evidence), "HAS_SECTION")

    if content_summary and _normalized(content_summary) != _normalized(abstract):
        evidence = [KnowledgeGraphEvidence(excerpt=content_summary[:800], source="metadata.contentSummary", record_id=record_id)]
        node_id = f"section:{record_id}:summary"
        section_nodes["Summary"] = node_id
        add_node(KnowledgeGraphNode(node_id, "section", "Summary", summary=content_summary, importance=0.82, tags=["structure"], evidence=evidence), "HAS_SECTION")

    claim_counts: Counter[str] = Counter()
    section_pages = sorted(
        (int(node.evidence[0].page), node.label)
        for node in nodes if node.type == "section" and node.evidence and node.evidence[0].page >= 0
    )
    seen_semantic: set[tuple[str, str]] = set()
    for page, block in blocks:
        section = next((label for section_page, label in reversed(section_pages) if section_page <= page), "")
        for sentence in _sentences(block.get("text")):
            matched_kinds: set[str] = set()
            for kind, pattern, relation in ENTITY_PATTERNS:
                if not pattern.search(sentence):
                    continue
                if kind == "Method" and "Result" in matched_kinds:
                    continue
                key = (kind.casefold(), _normalized(sentence[:180]))
                if key in seen_semantic:
                    continue
                seen_semantic.add(key)
                matched_kinds.add(kind)
                claim_counts[kind] += 1
                evidence = [_evidence(record_id, page, block.get("bbox"), f"page-{page}-block-{block.get('blockNo', 0)}", sentence, "extraction_index.pages")]
                node_id = f"{kind.casefold()}:{record_id}:{claim_counts[kind]}"
                confidence = _confidence(kind, sentence, section, block)
                importance = 0.84 if kind in {"Contribution", "Result", "ResearchGap"} else 0.74
                label = _entity_label(kind, sentence)
                add_node(KnowledgeGraphNode(node_id, kind.casefold(), label, summary=sentence, importance=importance, confidence=confidence, tags=[kind.casefold(), "semantic"] + (["needs_review"] if confidence < 0.6 else []), evidence=evidence, details={"section": section}), relation)

    for source_name, section, metadata_text in (
        ("metadata.abstract", "Abstract", abstract),
        ("metadata.contentSummary", "Summary", content_summary),
    ):
        for sentence in _sentences(metadata_text):
            matched_kinds: set[str] = set()
            for kind, pattern, relation in ENTITY_PATTERNS:
                if not pattern.search(sentence) or (kind == "Method" and "Result" in matched_kinds):
                    continue
                key = (kind.casefold(), _normalized(sentence[:180]))
                if key in seen_semantic:
                    continue
                seen_semantic.add(key)
                matched_kinds.add(kind)
                claim_counts[kind] += 1
                evidence = [KnowledgeGraphEvidence(page=-1, excerpt=sentence[:800], source=source_name, record_id=record_id)]
                node_id = f"{kind.casefold()}:{record_id}:{claim_counts[kind]}"
                confidence = _confidence(kind, sentence, section, {})
                importance = 0.84 if kind in {"Contribution", "Result", "ResearchGap"} else 0.74
                add_node(KnowledgeGraphNode(node_id, kind.casefold(), _entity_label(kind, sentence), summary=sentence, importance=importance, confidence=confidence, tags=[kind.casefold(), "semantic", "metadata"], evidence=evidence, details={"section": section}), relation)

    element_counts: Counter[str] = Counter()
    for element in index.get("elements") or []:
        if not isinstance(element, dict):
            continue
        raw_type = _text(element.get("type")).casefold()
        kind = {"formula": "equation", "chart": "figure"}.get(raw_type, raw_type)
        if kind not in {"figure", "table", "equation", "section", "paragraph"}:
            continue
        element_counts[kind] += 1
        element_id = _text(element.get("id")) or f"{kind}_{element_counts[kind]}"
        excerpt = _text(element.get("caption") or element.get("text") or element.get("markdown") or element.get("latex"))
        label = _text(element.get("label") or element.get("caption")) or f"{kind.title()} {element_counts[kind]}"
        evidence = [_evidence(record_id, int(element.get("page") or 0), element.get("bbox"), element_id, excerpt, "extraction_index.elements")]
        node_id = f"{kind}:{record_id}:{_normalized(element_id)}"
        add_node(KnowledgeGraphNode(node_id, kind, label, summary=excerpt, importance=0.7, confidence=float(element.get("confidence", 1.0) or 0.0), tags=[kind, "evidence"], evidence=evidence, details={key: element.get(key) for key in ("markdown", "latex", "pngPath", "csvPath") if element.get(key)}), f"HAS_{kind.upper()}")

    def first_page(node: KnowledgeGraphNode) -> int:
        return node.evidence[0].page if node.evidence and node.evidence[0].page >= 0 else 10**6

    semantic_links = {
        "contribution": ({"problem", "researchgap"}, "ADDRESSES_GAP"),
        "method": ({"problem", "researchgap"}, "SOLVES"),
        "experiment": ({"method", "contribution"}, "VALIDATED_BY"),
        "dataset": ({"experiment", "method"}, "EVALUATES_ON"),
        "metric": ({"experiment", "result"}, "MEASURED_BY"),
        "result": ({"method", "experiment"}, "PRODUCES"),
        "limitation": ({"result", "method"}, "HAS_LIMITATION"),
        "futurework": ({"limitation", "researchgap"}, "SUGGESTS_FUTURE_WORK"),
        "figure": ({"result", "method"}, "SUPPORTED_BY"),
        "table": ({"result", "experiment"}, "SUPPORTED_BY"),
        "equation": ({"method", "model"}, "DEFINED_BY"),
        "citation": ({"paper"}, "CITES"),
    }
    existing_links = {(edge.source, edge.target, edge.type) for edge in edges}
    for target in nodes:
        target_kind = target.type.casefold()
        if target_kind not in semantic_links:
            continue
        source_types, relation = semantic_links[target_kind]
        candidates = [node for node in nodes if node.type.casefold() in source_types and node.id != target.id]
        if not candidates:
            continue
        source = min(candidates, key=lambda node: (abs(first_page(node) - first_page(target)), -node.importance, node.id))
        if first_page(source) < 10**6 and first_page(target) < 10**6 and abs(first_page(source) - first_page(target)) > 2:
            continue
        key = (source.id, target.id, relation)
        if key in existing_links:
            continue
        edge_count += 1
        edges.append(KnowledgeGraphEdge(f"edge:{record_id}:{edge_count}", source.id, target.id, relation, relation.replace("_", " ").lower(), confidence=min(source.confidence, target.confidence), evidence=list(target.evidence)))
        existing_links.add(key)

    if len(nodes) == 1:
        for keyword in _fallback_keywords(record):
            add_node(KnowledgeGraphNode(f"concept:{_normalized(keyword)}", "concept", keyword, importance=0.5, confidence=0.5, tags=["concept"]), "MENTIONS")

    evidence_nodes = [node for node in nodes if node.type != "paper"]
    evidence_edges = [edge for edge in edges if edge.type not in {"MENTIONS"} or edge.evidence]
    average_confidence = sum(node.confidence for node in evidence_nodes) / max(1, len(evidence_nodes))
    quality = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "evidence_count": sum(len(node.evidence) for node in nodes),
        "evidence_coverage": round(sum(bool(node.evidence) for node in evidence_nodes) / max(1, len(evidence_nodes)), 3),
        "edge_evidence_coverage": round(sum(bool(edge.evidence) for edge in evidence_edges) / max(1, len(evidence_edges)), 3),
        "average_confidence": round(average_confidence, 3),
        "needs_review_count": sum(node.confidence < 0.6 for node in evidence_nodes),
    }
    node_dicts = [node.to_dict() for node in nodes]
    edge_dicts = [edge.to_dict() for edge in edges]
    return KnowledgeGraphDocument(
        record_id=record_id, paper=paper, nodes=nodes, edges=edges,
        metadata={
            "source": {"pdfPath": paper["pdf_path"], "extractionEngine": _text(index.get("engine")), "sourceSha256": _text(index.get("sourceSha256"))},
            "summary": {"keywords": keywords, "contentSummary": content_summary, "abstract": abstract},
            "stats": {"nodes": len(nodes), "edges": len(edges), "evidence": sum(len(node.evidence) for node in nodes) + sum(len(edge.evidence) for edge in edges)},
            "builder_version": BUILDER_VERSION,
            "source_fingerprint": source_fingerprint(record, index),
            "quality_summary": quality,
            "layout": academic_layout(node_dicts),
            "adjacency": adjacency_index(edge_dicts),
        },
    )


def build_knowledge_graph(record: dict, extraction_index: dict | None = None) -> dict:
    record_id = str((record or {}).get("recordId") or (record or {}).get("id") or "record")
    return build_document(record_id, record, extraction_index).to_dict()
