from __future__ import annotations

from typing import Any


ONTOLOGY_VERSION = 1

RELATION_CONFIG: dict[str, dict[str, Any]] = {
    "AUTHOR_OF": {"label": "作者", "symmetric": False},
    "AFFILIATED_WITH": {"label": "任职于", "symmetric": False},
    "PUBLISHED_IN": {"label": "发表于", "symmetric": False},
    "CITES": {"label": "引用", "symmetric": False},
    "HAS_TOPIC": {"label": "研究主题", "symmetric": False},
    "ADDRESSES": {"label": "解决问题", "symmetric": False},
    "USES_METHOD": {"label": "使用方法", "symmetric": False},
    "USES_MODEL": {"label": "使用模型", "symmetric": False},
    "USES_DATASET": {"label": "使用数据集", "symmetric": False},
    "EVALUATED_BY": {"label": "评价指标", "symmetric": False},
    "REPORTS_RESULT": {"label": "报告结果", "symmetric": False},
    "SUPPORTS": {"label": "支持", "symmetric": False},
    "CONTRADICTS": {"label": "矛盾", "symmetric": True},
    "EXTENDS": {"label": "扩展", "symmetric": False},
    "IMPROVES_ON": {"label": "改进自", "symmetric": False},
    # Supported extensions retained by OmniLit beyond the minimum contract.
    "PROPOSES": {"label": "提出", "symmetric": False},
    "LIMITS": {"label": "限制", "symmetric": False},
    "MENTIONS": {"label": "提及", "symmetric": False},
    "SIMILAR_TO": {"label": "相似", "symmetric": True},
    "SAME_AS": {"label": "同一概念", "symmetric": True},
    "MISSING": {"label": "缺失信息", "symmetric": False},
    "ASSOCIATED_WITH": {"label": "关联机构", "symmetric": False},
}

MINIMUM_RELATIONS = (
    "AUTHOR_OF", "AFFILIATED_WITH", "PUBLISHED_IN", "CITES", "HAS_TOPIC", "ADDRESSES",
    "USES_METHOD", "USES_MODEL", "USES_DATASET", "EVALUATED_BY", "REPORTS_RESULT",
    "SUPPORTS", "CONTRADICTS", "EXTENDS", "IMPROVES_ON",
)


ROOT_RELATIONS: dict[str, tuple[str, bool]] = {
    "contribution": ("PROPOSES", True),
    "researchgap": ("ADDRESSES", True),
    "problem": ("ADDRESSES", True),
    "method": ("USES_METHOD", True),
    "model": ("USES_MODEL", True),
    "experiment": ("USES_METHOD", True),
    "dataset": ("USES_DATASET", True),
    "metric": ("EVALUATED_BY", True),
    "result": ("REPORTS_RESULT", True),
    "conclusion": ("REPORTS_RESULT", True),
    "limitation": ("LIMITS", False),
    "futurework": ("PROPOSES", True),
    "citation": ("CITES", True),
    "figure": ("SUPPORTS", False),
    "table": ("SUPPORTS", False),
    "paragraph": ("SUPPORTS", False),
    "equation": ("USES_METHOD", True),
}

PAIR_RELATIONS: dict[tuple[str, str], str] = {
    ("contribution", "method"): "PROPOSES",
    ("method", "dataset"): "USES_DATASET",
    ("model", "dataset"): "USES_DATASET",
    ("experiment", "dataset"): "USES_DATASET",
    ("result", "metric"): "EVALUATED_BY",
    ("method", "result"): "SUPPORTS",
    ("model", "result"): "SUPPORTS",
    ("limitation", "method"): "LIMITS",
    ("limitation", "model"): "LIMITS",
    ("limitation", "result"): "LIMITS",
    ("figure", "result"): "SUPPORTS",
    ("table", "result"): "SUPPORTS",
    ("paragraph", "result"): "SUPPORTS",
    ("method", "equation"): "USES_METHOD",
}


def relation_label(relation_type: str) -> str:
    value = str(relation_type or "MENTIONS").upper()
    return str((RELATION_CONFIG.get(value) or {}).get("label") or value.replace("_", " ").title())


def canonical_relation_type(
    relation_type: str, source_type: str = "", target_type: str = "", source_id: str = "", target_id: str = "",
) -> str:
    value = str(relation_type or "MENTIONS").upper()
    source = str(source_type or "").casefold().replace("_", "")
    target = str(target_type or "").casefold().replace("_", "")
    if value == "PROPOSES" and source == "paper" and target in {"problem", "researchgap", "researchquestion"}:
        return "ADDRESSES"
    if value == "USES":
        if target == "model": return "USES_MODEL"
        if target == "dataset": return "USES_DATASET"
        return "USES_METHOD"
    if value == "EVALUATES_ON":
        return "USES_DATASET"
    if value == "MEASURED_BY":
        return "EVALUATED_BY"
    if value == "ACHIEVES":
        return "REPORTS_RESULT" if source in {"", "paper"} else "SUPPORTS"
    if value == "BELONGS_TO_TOPIC" and (target == "topic" or str(target_id).startswith("evolution-topic:")):
        return "HAS_TOPIC"
    return value


def canonical_relation_filter(relation_type: str) -> str:
    """Migrate a persisted relation filter without requiring graph node context."""
    value = str(relation_type or "all").upper()
    if value in {"", "ALL"}:
        return "all"
    return canonical_relation_type(value)


def canonicalize_edge_dict(edge: dict[str, Any], node_types: dict[str, str]) -> dict[str, Any]:
    result = dict(edge or {})
    source = str(result.get("source") or "")
    target = str(result.get("target") or "")
    original = str(result.get("type") or "MENTIONS").upper()
    canonical = canonical_relation_type(original, node_types.get(source, ""), node_types.get(target, ""), source, target)
    if canonical != original:
        details = dict(result.get("details") or {})
        details.setdefault("legacyRelationType", original)
        details["ontologyMigrationVersion"] = ONTOLOGY_VERSION
        result["details"] = details
        result["type"] = canonical
        result["label"] = relation_label(canonical)
    elif not result.get("label") or str(result.get("label")).upper() == original:
        result["label"] = relation_label(canonical)
    return result
