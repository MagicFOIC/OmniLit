from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .knowledge_graph_core import _text
from .knowledge_graph_schema import KnowledgeGraphEvidence


SECTION_NAMES = {
    "abstract": "Abstract", "introduction": "Introduction", "background": "Introduction",
    "method": "Method", "methods": "Method", "methodology": "Method",
    "experiment": "Experiment", "experiments": "Experiment",
    "result": "Results", "results": "Results", "discussion": "Discussion",
    "conclusion": "Conclusion", "conclusions": "Conclusion",
    "摘要": "Abstract", "引言": "Introduction", "方法": "Method", "实验": "Experiment",
    "结果": "Results", "讨论": "Discussion", "结论": "Conclusion",
}

ENTITY_PATTERNS = (
    ("contribution", re.compile(r"\b(?:we|this (?:paper|work)) (?:propose|introduce|present|contribute)\b|本文(?:提出|贡献|设计)", re.I)),
    ("researchgap", re.compile(r"\b(?:however|remains? (?:unclear|unknown|challenging)|lack(?:s|ing)?|few studies)\b|(?:然而|仍不清楚|研究空白|缺乏研究)", re.I)),
    ("problem", re.compile(r"\b(?:problem|challenge|bottleneck|difficulty)\b|(?:问题|挑战|瓶颈|难点)", re.I)),
    ("result", re.compile(r"\b(?:results? (?:show|indicate|demonstrate)|outperform|achieve|improve)\b|(?:结果表明|优于|达到|提升)", re.I)),
    ("limitation", re.compile(r"\b(?:limitation|limited by|drawback)\b|(?:局限|不足|缺点)", re.I)),
    ("futurework", re.compile(r"\b(?:future work|future research|in the future)\b|(?:未来工作|未来研究|后续工作)", re.I)),
    ("dataset", re.compile(r"\b(?:dataset|corpus|benchmark|database|cohort)\b|(?:数据集|语料库|基准数据|队列)", re.I)),
    ("metric", re.compile(r"\b(?:accuracy|precision|recall|f1(?:-score)?|auc|rmse|mae|bleu|rouge|latency|throughput)\b|(?:准确率|精确率|召回率|误差|延迟|吞吐量)", re.I)),
    ("experiment", re.compile(r"\b(?:experiment|evaluation|ablation|control group|randomized)\b|(?:实验|评估|消融|对照组|随机试验)", re.I)),
    ("method", re.compile(r"\b(?:we use|we employ|method|algorithm|model|framework|architecture|large language model|language model|LLM)\b|(?:方法|模型|算法|框架)", re.I)),
    ("citation", re.compile(r"\[(?:\d+[,-]?\s*)+\]|\b[A-Z][A-Za-z-]+\s+et\s+al\.?(?:,?\s*\d{4})?", re.I)),
)

METRIC_PATTERN = re.compile(r"\b(?:accuracy|precision|recall|f1(?:-score)?|auc|rmse|mae|bleu|rouge|latency|throughput)\b|(?:准确率|精确率|召回率|误差|延迟|吞吐量)", re.I)
METHOD_ALIAS_PATTERN = re.compile(r"\b(?:large language model|language model|LLM)\b", re.I)


@dataclass
class SectionTextBlock:
    page: int
    block_id: str
    text: str
    bbox: list[float] = field(default_factory=list)
    section: str | None = None
    source: str = "extraction_index.pages"
    is_heading: bool = False
    origin: str = "pdf"


@dataclass
class EntityCandidate:
    id: str
    record_id: str
    kind: str
    label: str
    text: str
    evidence: list[KnowledgeGraphEvidence]
    confidence: float
    confidence_reason: list[str]
    extraction_method: str
    source_section: str | None
    page: int
    block_id: str
    sentence_index: int
    origin: str
    details: dict[str, Any] = field(default_factory=dict)


def clean_text(value: Any) -> str:
    text = _text(value).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def sentences(text: str) -> list[str]:
    result = []
    for item in re.split(r"(?<=[.!?。！？])\s*|[\r\n]+", clean_text(text)):
        value = item.strip()
        minimum = 12 if re.search(r"[\u3400-\u9fff]", value) else 25
        if minimum <= len(value) <= 600:
            result.append(value)
    return result


def section_aware_text_blocks(index: dict[str, Any]) -> list[SectionTextBlock]:
    raw: list[tuple[int, float, dict[str, Any]]] = []
    page_count = len(index.get("pages") or [])
    for page in index.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page") or 0)
        page_height = float(page.get("height") or 0.0)
        for block in page.get("textBlocks") or page.get("blocks") or []:
            if isinstance(block, dict) and clean_text(block.get("text")):
                raw.append((page_number, page_height, block))

    repeated: Counter[str] = Counter()
    for _, page_height, block in raw:
        text = clean_text(block.get("text"))
        bbox = block.get("bbox") or []
        in_margin = len(bbox) >= 4 and page_height > 0 and (float(bbox[1]) <= page_height * 0.12 or float(bbox[3]) >= page_height * 0.88)
        if in_margin and 2 <= len(text) <= 120:
            repeated[text.casefold()] += 1
    threshold = max(3, int(page_count * 0.30 + 0.999))

    current_section: str | None = None
    result: list[SectionTextBlock] = []
    for page, _, block in raw:
        text = clean_text(block.get("text"))
        if repeated[text.casefold()] >= threshold:
            continue
        compact = re.sub(r"^[\d.\s]+", "", text).strip().rstrip(":：").casefold()
        heading = SECTION_NAMES.get(compact)
        if heading:
            current_section = heading
        block_no = int(block.get("blockNo", len(result)) or 0)
        result.append(SectionTextBlock(
            page=page,
            block_id=f"page-{page}-block-{block_no}",
            text=text,
            bbox=[float(item) for item in block.get("bbox") or []],
            section=current_section,
            is_heading=bool(heading),
        ))
    return result


def _confidence(kind: str, sentence: str, section: str | None, bbox: list[float]) -> tuple[float, list[str]]:
    value = 0.58
    reasons = ["rule_pattern_match"]
    section_name = section or ""
    if section_name.casefold() in {"method", "experiment", "results", "discussion", "conclusion"}:
        value += 0.08
        reasons.append("domain_section")
    if kind in section_name.casefold() or (kind == "result" and section_name in {"Results", "Conclusion"}):
        value += 0.10
        reasons.append("type_section_match")
    if re.search(r"\b(?:we|our|this (?:paper|study|work))\b|(?:本文|本研究)", sentence, re.I):
        value += 0.08
        reasons.append("author_claim_language")
    if len(bbox) >= 4:
        value += 0.05
        reasons.append("locatable_bbox")
    return round(min(0.95, value), 3), reasons


def _candidate_label(kind: str, sentence: str) -> str:
    if kind == "metric":
        matches = METRIC_PATTERN.findall(sentence)
        if matches:
            return " / ".join(dict.fromkeys(matches))
    if kind == "method":
        alias = METHOD_ALIAS_PATTERN.search(sentence)
        if alias:
            return alias.group(0)
        named = re.search(r"\b([A-Z][A-Za-z0-9_-]{2,})\s+(?:framework|model|method|algorithm|architecture)\b", sentence)
        if named:
            return named.group(1)
        generic = re.search(r"\b(?:a|an|the)?\s*([a-z][a-z0-9_-]+)\s+(?:framework|model|method|algorithm|architecture)\b", sentence, re.I)
        if generic:
            return generic.group(1)
    if kind == "dataset":
        match = re.search(r"(?:[A-Za-z0-9_-]+\s+){0,3}(?:dataset|corpus|benchmark|database|cohort)|[\u3400-\u9fffA-Za-z0-9_-]{0,12}(?:数据集|语料库|基准数据|队列)", sentence, re.I)
        if match:
            return match.group(0).strip()
    if kind == "citation":
        match = dict(ENTITY_PATTERNS)[kind].search(sentence)
        if match:
            return match.group(0).strip()
    prefix = {
        "contribution": "Contribution", "researchgap": "Research gap", "problem": "Problem",
        "experiment": "Experiment", "result": "Result", "limitation": "Limitation",
        "futurework": "Future work",
    }.get(kind, kind.title())
    excerpt = sentence[:72] + ("..." if len(sentence) > 72 else "")
    return f"{prefix} · {excerpt}"


def _candidate_from_sentence(
    record_id: str,
    kind: str,
    sentence: str,
    block: SectionTextBlock,
    sentence_index: int,
    ordinal: int,
) -> EntityCandidate:
    confidence, reasons = _confidence(kind, sentence, block.section, block.bbox)
    evidence = [KnowledgeGraphEvidence(
        page=block.page, bbox=list(block.bbox), element_id=block.block_id,
        excerpt=sentence[:800], source=block.source, record_id=record_id,
    )]
    return EntityCandidate(
        id=f"candidate:{record_id}:{ordinal}", record_id=record_id, kind=kind,
        label=_candidate_label(kind, sentence), text=sentence, evidence=evidence,
        confidence=confidence, confidence_reason=reasons,
        extraction_method="metadata" if block.origin == "metadata" else "rule",
        source_section=block.section, page=block.page, block_id=block.block_id,
        sentence_index=sentence_index, origin=block.origin,
    )


def extract_entity_candidates(record_id: str, record: dict[str, Any], index: dict[str, Any]) -> tuple[list[EntityCandidate], list[SectionTextBlock]]:
    blocks = section_aware_text_blocks(index)
    metadata_blocks = []
    for source, section, value in (
        ("metadata.abstract", "Abstract", record.get("abstract") or record.get("extracted_abstract")),
        ("metadata.contentSummary", "Summary", record.get("contentSummary") or record.get("summaryText") or record.get("content_summary")),
    ):
        text = clean_text(value)
        if text:
            metadata_blocks.append(SectionTextBlock(-1, source, text, section=section, source=source))
    for block in metadata_blocks:
        block.origin = "metadata"
    for block in blocks:
        block.origin = "pdf"

    candidates: list[EntityCandidate] = []
    seen: set[tuple[str, str]] = set()
    for block in blocks + metadata_blocks:
        if block.is_heading:
            continue
        for sentence_index, sentence in enumerate(sentences(block.text)):
            matched_kinds: set[str] = set()
            for kind, pattern in ENTITY_PATTERNS:
                if not pattern.search(sentence):
                    continue
                if kind == "method" and "result" in matched_kinds:
                    continue
                key = (kind, re.sub(r"\W+", "", sentence.casefold())[:180])
                if key in seen:
                    continue
                seen.add(key)
                matched_kinds.add(kind)
                candidates.append(_candidate_from_sentence(record_id, kind, sentence, block, sentence_index, len(candidates) + 1))

    for element in index.get("elements") or []:
        if not isinstance(element, dict):
            continue
        raw_type = _text(element.get("type")).casefold()
        kind = {"formula": "equation", "chart": "figure"}.get(raw_type, raw_type)
        if kind not in {"figure", "table", "equation", "paragraph"}:
            continue
        element_id = _text(element.get("id")) or f"{kind}-{len(candidates) + 1}"
        excerpt = clean_text(element.get("caption") or element.get("text") or element.get("markdown") or element.get("latex"))
        confidence = float(element.get("confidence", 1.0) or 0.0)
        page = int(element.get("page") or 0)
        section = next((block.section for block in reversed(blocks) if block.page <= page and block.section), None)
        evidence = [KnowledgeGraphEvidence(
            page=page, bbox=[float(item) for item in element.get("bbox") or []],
            element_id=element_id, excerpt=excerpt[:800], source="extraction_index.elements", record_id=record_id,
        )]
        candidates.append(EntityCandidate(
            id=f"candidate:{record_id}:{len(candidates) + 1}", record_id=record_id, kind=kind,
            label=_text(element.get("label") or element.get("caption")) or f"{kind.title()} {element_id}",
            text=excerpt, evidence=evidence, confidence=confidence,
            confidence_reason=["extraction_element_confidence"], extraction_method="rule",
            source_section=section, page=page, block_id=element_id, sentence_index=0,
            origin="caption" if element.get("caption") else "element",
            details={key: element.get(key) for key in ("markdown", "latex", "pngPath", "csvPath") if element.get(key)},
        ))
    return candidates, blocks
