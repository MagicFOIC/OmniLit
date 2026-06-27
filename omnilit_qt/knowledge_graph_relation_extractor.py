from __future__ import annotations

import json
from dataclasses import dataclass

from .knowledge_graph_normalizer import NormalizedEntity
from .knowledge_graph_precision import relation_has_cue
from .knowledge_graph_schema import KnowledgeGraphEdge, KnowledgeGraphEvidence


ROOT_RELATIONS: dict[str, tuple[str, bool]] = {
    "contribution": ("PROPOSES", True),
    "researchgap": ("PROPOSES", True),
    "problem": ("PROPOSES", True),
    "method": ("USES", True),
    "experiment": ("USES", True),
    "dataset": ("EVALUATES_ON", True),
    "metric": ("MEASURED_BY", True),
    "result": ("ACHIEVES", True),
    "limitation": ("LIMITS", False),
    "futurework": ("PROPOSES", True),
    "citation": ("CITES", True),
    "figure": ("SUPPORTS", False),
    "table": ("SUPPORTS", False),
    "paragraph": ("SUPPORTS", False),
    "equation": ("USES", True),
}

PAIR_RELATIONS: dict[tuple[str, str], str] = {
    ("contribution", "method"): "PROPOSES",
    ("method", "dataset"): "EVALUATES_ON",
    ("experiment", "dataset"): "EVALUATES_ON",
    ("result", "metric"): "MEASURED_BY",
    ("method", "result"): "ACHIEVES",
    ("limitation", "method"): "LIMITS",
    ("limitation", "result"): "LIMITS",
    ("figure", "result"): "SUPPORTS",
    ("table", "result"): "SUPPORTS",
    ("paragraph", "result"): "SUPPORTS",
    ("method", "equation"): "USES",
}

CONTEXT_CONFIDENCE = {
    "same_sentence": 1.0,
    "same_block": 0.95,
    "metadata": 0.90,
    "caption": 0.88,
    "same_section": 0.82,
}


@dataclass
class RelationCandidate:
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    relation_method: str
    evidence: list[KnowledgeGraphEvidence]
    direction_reason: str
    source_section: str | None
    confidence_reason: list[str]
    extraction_method: str = "rule"
    needs_review: bool = False
    review_reasons: list[str] | None = None

    def to_edge(self, record_id: str, index: int) -> KnowledgeGraphEdge:
        return KnowledgeGraphEdge(
            id=f"edge:{record_id}:{index}", source=self.source_id, target=self.target_id,
            type=self.relation_type, label=self.relation_type.replace("_", " ").lower(),
            confidence=self.confidence, evidence=list(self.evidence),
            extraction_method=self.extraction_method, confidence_reason=list(self.confidence_reason),
            source_section=self.source_section, needs_review=self.needs_review or self.confidence < 0.6,
            relation_method=self.relation_method, relation_evidence=list(self.evidence),
            direction_reason=self.direction_reason,
            review_reasons=list(self.review_reasons or []),
        )


def _dedupe_evidence(*groups: list[KnowledgeGraphEvidence]) -> list[KnowledgeGraphEvidence]:
    result: list[KnowledgeGraphEvidence] = []
    seen: set[str] = set()
    for item in (item for group in groups for item in group):
        key = json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _ordinal(entity: NormalizedEntity) -> int:
    try:
        return min(int(candidate.id.rsplit(":", 1)[-1]) for candidate in entity.candidates)
    except (ValueError, TypeError):
        return 0


def _best_context(source: NormalizedEntity, target: NormalizedEntity) -> str | None:
    contexts: list[str] = []
    for left in source.candidates:
        for right in target.candidates:
            if left.origin == right.origin == "metadata" and left.block_id == right.block_id:
                contexts.append("metadata")
            if left.block_id == right.block_id and left.sentence_index == right.sentence_index:
                contexts.append("same_sentence")
            elif left.block_id == right.block_id:
                contexts.append("same_block")
            elif "caption" in {left.origin, right.origin} and left.source_section and left.source_section == right.source_section:
                contexts.append("caption")
            elif left.source_section and left.source_section == right.source_section:
                contexts.append("same_section")
    return max(contexts, key=lambda value: CONTEXT_CONFIDENCE[value], default=None)


def _context_text(source: NormalizedEntity, target: NormalizedEntity, context: str) -> str:
    excerpts: list[str] = []
    for left in source.candidates:
        for right in target.candidates:
            same_sentence = left.block_id == right.block_id and left.sentence_index == right.sentence_index
            same_block = left.block_id == right.block_id
            same_section = bool(left.source_section and left.source_section == right.source_section)
            if context == "same_sentence" and same_sentence:
                excerpts.extend([left.text, right.text])
            elif context == "same_block" and same_block:
                excerpts.extend([left.text, right.text])
            elif context == "same_section" and same_section:
                excerpts.extend([left.text, right.text])
            elif context in {"metadata", "caption"}:
                excerpts.extend([left.text, right.text])
    return " ".join(dict.fromkeys(item for item in excerpts if item))


def _root_relation(paper_id: str, entity: NormalizedEntity) -> RelationCandidate | None:
    specification = ROOT_RELATIONS.get(entity.kind)
    if not specification:
        return None
    relation_type, paper_is_source = specification
    source_id, target_id = (paper_id, entity.node_id) if paper_is_source else (entity.node_id, paper_id)
    origins = {candidate.origin for candidate in entity.candidates}
    method = "metadata" if origins == {"metadata"} else ("caption" if "caption" in origins else "direct_extraction")
    return RelationCandidate(
        source_id=source_id, target_id=target_id, relation_type=relation_type,
        confidence=entity.confidence, relation_method=method, evidence=entity.evidence,
        direction_reason=(
            f"paper declares {relation_type} toward extracted {entity.kind}"
            if paper_is_source else f"extracted {entity.kind} semantically {relation_type} the paper claim"
        ),
        source_section=entity.source_section,
        confidence_reason=["typed_root_relation", method],
        extraction_method=entity.extraction_method,
    )


def extract_relation_candidates(record_id: str, entities: list[NormalizedEntity]) -> list[RelationCandidate]:
    paper_id = f"paper:{record_id}"
    relations = [relation for entity in entities if (relation := _root_relation(paper_id, entity))]
    existing = {(relation.source_id, relation.target_id, relation.relation_type) for relation in relations}
    section_fallbacks: dict[tuple[str, str], tuple[int, NormalizedEntity, NormalizedEntity, str]] = {}

    for source in entities:
        for target in entities:
            relation_type = PAIR_RELATIONS.get((source.kind, target.kind))
            if not relation_type or source.node_id == target.node_id:
                continue
            context = _best_context(source, target)
            if not context:
                continue
            distance = abs(_ordinal(source) - _ordinal(target))
            cue_text = _context_text(source, target, context)
            has_cue = relation_has_cue(relation_type, cue_text)
            if context == "same_section":
                if not has_cue:
                    continue
                key = (target.node_id, relation_type)
                current = section_fallbacks.get(key)
                if current is None or distance < current[0]:
                    section_fallbacks[key] = (distance, source, target, context)
                continue
            if context in {"same_sentence", "same_block"} and not has_cue:
                continue
            _append_context_relation(relations, existing, source, target, relation_type, context)

    for _, source, target, context in section_fallbacks.values():
        _append_context_relation(relations, existing, source, target, PAIR_RELATIONS[(source.kind, target.kind)], context)
    return relations


def _append_context_relation(
    relations: list[RelationCandidate],
    existing: set[tuple[str, str, str]],
    source: NormalizedEntity,
    target: NormalizedEntity,
    relation_type: str,
    context: str,
) -> None:
    key = (source.node_id, target.node_id, relation_type)
    if key in existing:
        return
    existing.add(key)
    confidence = round(min(source.confidence, target.confidence) * CONTEXT_CONFIDENCE[context], 3)
    relations.append(RelationCandidate(
        source_id=source.node_id, target_id=target.node_id, relation_type=relation_type,
        confidence=confidence if context != "same_section" else min(confidence, 0.58),
        relation_method=context,
        evidence=_dedupe_evidence(source.evidence, target.evidence),
        direction_reason=f"typed {source.kind} -> {target.kind} relation supported by {context}",
        source_section=target.source_section or source.source_section,
        confidence_reason=["typed_entity_pair", context], extraction_method="rule",
        needs_review=context == "same_section",
        review_reasons=["same_section_only_relation"] if context == "same_section" else [],
    ))
