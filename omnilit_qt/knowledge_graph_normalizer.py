from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .knowledge_graph_extractor import EntityCandidate
from .knowledge_graph_precision import canonical_label as precision_canonical_label
from .knowledge_graph_precision import invalid_label_reason, is_generic_label, semantic_key
from .knowledge_graph_schema import KnowledgeGraphEvidence, KnowledgeGraphNode


REVIEW_CONFIDENCE_THRESHOLD = 0.6
GENERIC_REVIEW_TYPES = {"concept", "researchgap", "problem", "researchquestion", "contribution", "method", "model", "dataset", "metric", "experiment", "result", "conclusion", "limitation", "futurework", "domainentity", "material"}

METRIC_ALIASES = {
    "accuracy": "Accuracy", "auc": "AUC", "bleu": "BLEU", "f1": "F1",
    "f1score": "F1", "latency": "Latency", "mae": "MAE", "precision": "Precision",
    "recall": "Recall", "rmse": "RMSE", "rouge": "ROUGE", "throughput": "Throughput",
    "准确率": "Accuracy", "精确率": "Precision", "召回率": "Recall",
}

METHOD_ALIASES = {
    "llm": "LLM",
    "largelanguagemodel": "LLM",
    "largelanguagemodels": "LLM",
    "languagemodel": "LLM",
    "languagemodels": "LLM",
}


def normalized_text(value: str) -> str:
    return semantic_key(value)


def canonical_label(kind: str, label: str) -> str:
    if kind == "metric":
        labels = []
        for part in re.split(r"\s*/\s*", label):
            key = normalized_text(part)
            labels.append(METRIC_ALIASES.get(key, part.strip()))
        return " / ".join(dict.fromkeys(labels))
    if kind == "method":
        normalized = normalized_text(label)
        return METHOD_ALIASES.get(normalized, precision_canonical_label(kind, label))
    return precision_canonical_label(kind, label)


@dataclass
class NormalizedEntity:
    record_id: str
    kind: str
    label: str
    normalized_label: str
    canonical_id: str
    node_id: str
    candidates: list[EntityCandidate] = field(default_factory=list)

    @property
    def evidence(self) -> list[KnowledgeGraphEvidence]:
        result: list[KnowledgeGraphEvidence] = []
        seen: set[str] = set()
        for candidate in self.candidates:
            for item in candidate.evidence:
                key = json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
        return result

    @property
    def confidence(self) -> float:
        best = max((candidate.confidence for candidate in self.candidates), default=0.0)
        corroboration = min(0.08, 0.02 * max(0, len(self.candidates) - 1))
        value = min(0.98, best + corroboration)
        if self.kind in GENERIC_REVIEW_TYPES and is_generic_label(self.label):
            value = min(value, 0.55)
        if len({candidate.record_id for candidate in self.candidates}) > 1:
            value = min(value, 0.55)
        return round(value, 3)

    @property
    def confidence_reason(self) -> list[str]:
        reasons = list(dict.fromkeys(reason for candidate in self.candidates for reason in candidate.confidence_reason))
        if len(self.candidates) > 1:
            reasons.append("canonical_alias_corroboration")
        return reasons

    @property
    def source_section(self) -> str | None:
        sections = list(dict.fromkeys(candidate.source_section for candidate in self.candidates if candidate.source_section))
        return sections[0] if len(sections) == 1 else None

    @property
    def extraction_method(self) -> str:
        methods = {candidate.extraction_method for candidate in self.candidates}
        return next(iter(methods)) if len(self.candidates) == 1 else "merged"

    @property
    def review_reasons(self) -> list[str]:
        reasons = list(dict.fromkeys(reason for candidate in self.candidates for reason in candidate.review_reasons))
        label_reason = invalid_label_reason(self.label) if self.kind in GENERIC_REVIEW_TYPES else ""
        if label_reason:
            reasons.append(label_reason)
        if len({candidate.record_id for candidate in self.candidates}) > 1:
            reasons.append("cross_record_merge_conflict")
        if self.confidence < REVIEW_CONFIDENCE_THRESHOLD:
            reasons.append("low_confidence")
        return list(dict.fromkeys(reasons))

    def to_node(self) -> KnowledgeGraphNode:
        confidence = self.confidence
        tags = [self.kind, "semantic"]
        review_reasons = self.review_reasons
        needs_review = bool(review_reasons) or confidence < REVIEW_CONFIDENCE_THRESHOLD
        if needs_review:
            tags.append("needs_review")
        first = self.candidates[0]
        importance = 0.84 if self.kind in {"contribution", "result", "researchgap"} else 0.74
        if self.kind in {"figure", "table", "equation", "paragraph"}:
            importance = 0.7
        details = dict(first.details)
        if self.source_section:
            details["section"] = self.source_section
        details["candidate_ids"] = [candidate.id for candidate in self.candidates]
        node_type = "researchquestion" if self.kind in {"problem", "researchgap"} else self.kind
        details["semanticSubtype"] = self.kind
        return KnowledgeGraphNode(
            self.node_id, node_type, self.label, summary=first.text, importance=importance,
            confidence=confidence, tags=tags, evidence=self.evidence, details=details,
            normalized_label=self.normalized_label, canonical_id=self.canonical_id,
            extraction_method=self.extraction_method, confidence_reason=self.confidence_reason,
            source_section=self.source_section, needs_review=needs_review,
            review_reasons=review_reasons,
        )


def normalize_candidates(candidates: list[EntityCandidate]) -> list[NormalizedEntity]:
    grouped: dict[tuple[str, str, str], NormalizedEntity] = {}
    for candidate in candidates:
        label = canonical_label(candidate.kind, candidate.label)
        normalized = normalized_text(label)
        key = (candidate.record_id, candidate.kind, normalized or normalized_text(candidate.text[:120]))
        if key not in grouped:
            canonical_id = f"{candidate.kind}:{key[2]}"
            grouped[key] = NormalizedEntity(
                record_id=candidate.record_id, kind=candidate.kind, label=label,
                normalized_label=key[2], canonical_id=canonical_id,
                node_id=f"{candidate.kind}:{candidate.record_id}:{key[2]}",
            )
        grouped[key].candidates.append(candidate)
    return list(grouped.values())
