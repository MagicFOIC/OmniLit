from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any


def _normalized_label(value: Any) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", str(value or "").casefold())


@dataclass
class KnowledgeGraphEvidence:
    page: int = -1
    bbox: list[float] = field(default_factory=list)
    element_id: str = ""
    excerpt: str = ""
    translated_text: str = ""
    source: str = ""
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict | None) -> "KnowledgeGraphEvidence":
        data = dict(value or {})
        return cls(
            page=int(data.get("page", -1) if data.get("page") is not None else -1),
            bbox=[float(item) for item in data.get("bbox") or []],
            element_id=str(data.get("element_id") or data.get("elementId") or ""),
            excerpt=str(data.get("excerpt") or data.get("text_excerpt") or ""),
            translated_text=str(data.get("translated_text") or ""),
            source=str(data.get("source") or ""),
            record_id=str(data.get("record_id") or data.get("recordId") or ""),
        )


@dataclass
class KnowledgeGraphNode:
    id: str
    type: str
    label: str
    summary: str = ""
    importance: float = 0.5
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    evidence: list[KnowledgeGraphEvidence] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    pinned: bool = False
    normalized_label: str = ""
    canonical_id: str = ""
    extraction_method: str = "unknown"
    confidence_reason: list[str] = field(default_factory=list)
    source_section: str | None = None
    needs_review: bool = False

    def __post_init__(self) -> None:
        self.normalized_label = self.normalized_label or _normalized_label(self.label)
        self.canonical_id = self.canonical_id or f"{self.type.casefold()}:{self.normalized_label or self.id}"
        if self.extraction_method == "unknown":
            if self.type.casefold() in {"comparison", "conflict", "missinginfo"}:
                self.extraction_method = "merged"
            elif self.type.casefold() == "paper" or not self.evidence:
                self.extraction_method = "metadata"
            else:
                self.extraction_method = "rule"
        if not self.confidence_reason:
            self.confidence_reason = [f"{self.extraction_method}_construction"]
        if self.source_section is None and self.details.get("section"):
            self.source_section = str(self.details["section"])
        self.needs_review = self.needs_review or self.confidence < 0.6 or "needs_review" in self.tags

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = [item.to_dict() for item in self.evidence]
        result["weight"] = self.importance
        return result

    @classmethod
    def from_dict(cls, value: dict) -> "KnowledgeGraphNode":
        data = dict(value or {})
        details = dict(data.get("details") or {})
        legacy_evidence = data.get("evidence")
        if isinstance(legacy_evidence, str):
            legacy_evidence = [{"source": legacy_evidence}]
        if not legacy_evidence and any(key in details for key in ("page", "bbox", "element_id", "elementId")):
            legacy_evidence = [details]
        return cls(
            id=str(data.get("id") or ""),
            type=str(data.get("type") or "Concept"),
            label=str(data.get("label") or ""),
            summary=str(data.get("summary") or details.get("text") or details.get("caption") or ""),
            importance=float(data.get("importance", data.get("weight", 0.5)) or 0.0),
            confidence=float(data.get("confidence", 1.0) or 0.0),
            tags=[str(item) for item in data.get("tags") or []],
            evidence=[KnowledgeGraphEvidence.from_dict(item) for item in legacy_evidence or [] if isinstance(item, dict)],
            details=details,
            pinned=bool(data.get("pinned", False)),
            normalized_label=str(data.get("normalized_label") or data.get("normalizedLabel") or ""),
            canonical_id=str(data.get("canonical_id") or data.get("canonicalId") or ""),
            extraction_method=str(data.get("extraction_method") or data.get("extractionMethod") or details.get("extraction_method") or "legacy"),
            confidence_reason=[str(item) for item in data.get("confidence_reason") or data.get("confidenceReason") or []],
            source_section=data.get("source_section", data.get("sourceSection", details.get("section"))),
            needs_review=bool(data.get("needs_review", data.get("needsReview", False))),
        )


@dataclass
class KnowledgeGraphEdge:
    id: str
    source: str
    target: str
    type: str
    label: str = ""
    confidence: float = 1.0
    evidence: list[KnowledgeGraphEvidence] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    normalized_label: str = ""
    canonical_id: str = ""
    extraction_method: str = "unknown"
    confidence_reason: list[str] = field(default_factory=list)
    source_section: str | None = None
    needs_review: bool = False
    relation_method: str = "unknown"
    relation_evidence: list[KnowledgeGraphEvidence] = field(default_factory=list)
    direction_reason: str = ""

    def __post_init__(self) -> None:
        self.normalized_label = self.normalized_label or _normalized_label(self.label or self.type)
        self.canonical_id = self.canonical_id or f"relation:{self.type.casefold()}:{self.source}:{self.target}"
        if self.extraction_method == "unknown":
            self.extraction_method = "merged" if self.type in {"SAME_AS", "SIMILAR_TO", "CONTRADICTS", "MISSING"} else "rule"
        if not self.confidence_reason:
            self.confidence_reason = [f"{self.extraction_method}_relation"]
        if self.relation_method == "unknown":
            self.relation_method = "comparison_rule" if self.extraction_method == "merged" else "declared_relation"
        if not self.direction_reason:
            self.direction_reason = f"declared direction from {self.source} to {self.target} for {self.type}"
        self.needs_review = self.needs_review or self.confidence < 0.6
        if not self.relation_evidence and self.evidence:
            self.relation_evidence = list(self.evidence)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = [item.to_dict() for item in self.evidence]
        result["relation_evidence"] = [item.to_dict() for item in self.relation_evidence]
        result["weight"] = self.confidence
        return result

    @classmethod
    def from_dict(cls, value: dict, index: int = 0) -> "KnowledgeGraphEdge":
        data = dict(value or {})
        evidence = data.get("evidence")
        if isinstance(evidence, str):
            evidence = [{"source": evidence}]
        relation_evidence = data.get("relation_evidence") or data.get("relationEvidence")
        if isinstance(relation_evidence, str):
            relation_evidence = [{"source": relation_evidence}]
        source = str(data.get("source") or "")
        target = str(data.get("target") or "")
        edge_type = str(data.get("type") or "MENTIONS")
        return cls(
            id=str(data.get("id") or f"edge:{index}:{source}:{target}:{edge_type}"),
            source=source,
            target=target,
            type=edge_type,
            label=str(data.get("label") or edge_type),
            confidence=float(data.get("confidence", data.get("weight", 1.0)) or 0.0),
            evidence=[KnowledgeGraphEvidence.from_dict(item) for item in evidence or [] if isinstance(item, dict)],
            details=dict(data.get("details") or {}),
            normalized_label=str(data.get("normalized_label") or data.get("normalizedLabel") or ""),
            canonical_id=str(data.get("canonical_id") or data.get("canonicalId") or ""),
            extraction_method=str(data.get("extraction_method") or data.get("extractionMethod") or "legacy"),
            confidence_reason=[str(item) for item in data.get("confidence_reason") or data.get("confidenceReason") or []],
            source_section=data.get("source_section", data.get("sourceSection")),
            needs_review=bool(data.get("needs_review", data.get("needsReview", False))),
            relation_method=str(data.get("relation_method") or data.get("relationMethod") or "legacy"),
            relation_evidence=[KnowledgeGraphEvidence.from_dict(item) for item in relation_evidence or [] if isinstance(item, dict)],
            direction_reason=str(data.get("direction_reason") or data.get("directionReason") or ""),
        )


@dataclass
class KnowledgeGraphDocument:
    record_id: str
    paper: dict[str, Any]
    nodes: list[KnowledgeGraphNode] = field(default_factory=list)
    edges: list[KnowledgeGraphEdge] = field(default_factory=list)
    schema_version: int = 1
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        title = str(self.paper.get("title") or "Untitled")
        result = {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "paper": dict(self.paper),
            "generated_at": self.generated_at,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "metadata": dict(self.metadata),
        }
        result.update({
            "version": self.schema_version,
            "recordId": self.record_id,
            "title": title,
            "generatedAt": self.generated_at,
            "source": dict(self.metadata.get("source") or {}),
            "summary": dict(self.metadata.get("summary") or {}),
            "builder_version": int(self.metadata.get("builder_version") or 1),
            "source_fingerprint": str(self.metadata.get("source_fingerprint") or ""),
            "quality_summary": dict(self.metadata.get("quality_summary") or {}),
            "layout": dict(self.metadata.get("layout") or {}),
            "adjacency": dict(self.metadata.get("adjacency") or {}),
        })
        return result

    @classmethod
    def from_dict(cls, value: dict) -> "KnowledgeGraphDocument":
        data = dict(value or {})
        record_id = str(data.get("record_id") or data.get("recordId") or "")
        paper = dict(data.get("paper") or {})
        if not paper:
            paper = {"title": data.get("title", ""), "pdf_path": (data.get("source") or {}).get("pdfPath", "")}
        metadata = dict(data.get("metadata") or {})
        metadata.setdefault("source", dict(data.get("source") or {}))
        metadata.setdefault("summary", dict(data.get("summary") or {}))
        for key in ("builder_version", "source_fingerprint", "quality_summary", "layout", "adjacency"):
            if key in data:
                metadata.setdefault(key, data.get(key))
        return cls(
            record_id=record_id,
            paper=paper,
            nodes=[KnowledgeGraphNode.from_dict(item) for item in data.get("nodes") or [] if isinstance(item, dict)],
            edges=[KnowledgeGraphEdge.from_dict(item, index) for index, item in enumerate(data.get("edges") or []) if isinstance(item, dict)],
            schema_version=int(data.get("schema_version") or data.get("version") or 1),
            generated_at=str(data.get("generated_at") or data.get("generatedAt") or ""),
            metadata=metadata,
        )
