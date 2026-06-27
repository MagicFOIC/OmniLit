from __future__ import annotations

import re
import unicodedata
from typing import Any


PRECISION_VERSION = 1

GENERIC_LABELS = {
    "approach", "architecture", "dataset", "experiment", "framework", "method",
    "model", "result", "results", "system", "task", "technique",
    "方法", "模型", "框架", "数据集", "结果", "实验", "系统",
}

CORE_TYPES = {
    "concept", "researchgap", "problem", "contribution", "method", "dataset",
    "metric", "experiment", "result", "limitation", "futurework", "citation",
    "figure", "table", "equation", "domainentity", "material",
}

SECTION_ALIASES = {
    "abstract": "Abstract",
    "摘要": "Abstract",
    "introduction": "Introduction",
    "background": "Introduction",
    "引言": "Introduction",
    "绪论": "Introduction",
    "method": "Method",
    "methods": "Method",
    "methodology": "Method",
    "materials and methods": "Method",
    "方法": "Method",
    "材料与方法": "Method",
    "experiment": "Experiment",
    "experiments": "Experiment",
    "experimental setup": "Experiment",
    "evaluation": "Experiment",
    "实验": "Experiment",
    "实验设置": "Experiment",
    "result": "Results",
    "results": "Results",
    "结果": "Results",
    "discussion": "Discussion",
    "讨论": "Discussion",
    "limitation": "Limitation",
    "limitations": "Limitation",
    "局限": "Limitation",
    "局限性": "Limitation",
    "conclusion": "Conclusion",
    "conclusions": "Conclusion",
    "结论": "Conclusion",
    "future work": "Future Work",
    "future research": "Future Work",
    "展望": "Future Work",
    "未来工作": "Future Work",
    "references": "References",
    "reference": "References",
    "bibliography": "References",
    "参考文献": "References",
}

REFERENCE_SECTIONS = {"References", "Bibliography"}

LIMITATION_RE = re.compile(
    r"\b(?:limitation|limitations|limited by|drawback|weakness|constraint|fail(?:s|ure)?|cannot|unable)\b|"
    r"(?:局限|不足|缺点|受限|无法|不能)",
    re.I,
)

FUTURE_RE = re.compile(r"\b(?:future work|future research|in the future|will explore|will investigate)\b|(?:未来工作|未来研究|后续工作|将进一步)", re.I)

CUE_VERBS = {
    "PROPOSES": re.compile(r"\b(?:propose|proposes|proposed|introduce|introduces|present|presents|use|uses|using|employ|employs)\b|(?:提出|引入|采用|使用)", re.I),
    "EVALUATES_ON": re.compile(r"\b(?:evaluate|evaluates|evaluated|test|tests|tested|train|trained|on|using|with)\b|(?:评估|测试|训练|在.+上)", re.I),
    "MEASURED_BY": re.compile(r"\b(?:measure|measured|metric|score|accuracy|precision|recall|f1|auc|rmse|mae|latency)\b|(?:指标|准确率|精确率|召回率|延迟)", re.I),
    "ACHIEVES": re.compile(r"\b(?:achieve|achieves|achieved|improve|improves|improved|outperform|outperforms|show|shows|demonstrate|demonstrates|reduce|reduced)\b|(?:达到|提升|优于|表明|降低|减少)", re.I),
    "LIMITS": LIMITATION_RE,
    "SUPPORTS": re.compile(r"\b(?:figure|fig\.|table|caption|show|shows|illustrate|illustrates|support|supports)\b|(?:图|表|显示|说明|支持)", re.I),
    "USES": re.compile(r"\b(?:use|uses|using|employ|employs|apply|applies|based on)\b|(?:使用|采用|应用|基于)", re.I),
    "CITES": re.compile(r"\[[\d,\-\s]+\]|\bet\s+al\.?\b", re.I),
}

NUMERIC_RESULT_RE = re.compile(
    r"\b(?:accuracy|precision|recall|f1(?:-score)?|auc|rmse|mae|bleu|rouge|latency|throughput)\s*(?:=|of|is|was|reaches?|achieves?)\s*\d+(?:\.\d+)?\s*%?\b|"
    r"\b(?:improv(?:e|ed|es)|reduc(?:e|ed|es)|increas(?:e|ed|es))\s+(?:by\s+)?\d+(?:\.\d+)?\s*%?\b|"
    r"(?:准确率|精确率|召回率|延迟|吞吐量).{0,12}(?:提升|降低|达到|为)\s*\d+(?:\.\d+)?%?",
    re.I,
)

ACRONYM_RE = re.compile(r"\b([A-Za-z][A-Za-z][A-Za-z\s-]{4,80}?)\s*\(([A-Z][A-Z0-9-]{1,12})\)")


def fold_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    text = text.replace("α", "alpha").replace("β", "beta").replace("γ", "gamma").replace("δ", "delta")
    return re.sub(r"\s+", " ", text).strip()


def semantic_key(value: Any) -> str:
    text = fold_text(value).casefold()
    text = re.sub(r"\b(models|methods|frameworks|datasets|results)\b", lambda m: m.group(1)[:-1], text)
    text = re.sub(r"[\s_-]+", "", text)
    return re.sub(r"[^\w\u3400-\u9fff]+", "", text)


def canonical_label(kind: str, label: str) -> str:
    text = fold_text(label)
    acronym = ACRONYM_RE.search(text)
    if acronym:
        return acronym.group(2)
    if kind == "method":
        key = semantic_key(text)
        if key in {"llm", "largelanguagemodel", "largelanguagemodels", "languagemodel", "languagemodels"}:
            return "LLM"
    return text


def section_heading(text: str) -> str | None:
    value = fold_text(text).strip()
    if not value or len(value) > 90:
        return None
    value = re.sub(r"^\s*(?:chapter\s+)?(?:[ivxlcdm]+|\d+)(?:\.\d+)*[\).\s:-]+", "", value, flags=re.I)
    value = value.strip(" :：.-").casefold()
    value = re.sub(r"\s+", " ", value)
    return SECTION_ALIASES.get(value)


def is_reference_section(section: str | None) -> bool:
    return str(section or "") in REFERENCE_SECTIONS


def is_generic_label(label: str) -> bool:
    return semantic_key(label) in {semantic_key(item) for item in GENERIC_LABELS}


def invalid_label_reason(label: str) -> str:
    text = fold_text(label)
    key = semantic_key(text)
    if not key:
        return "empty_label"
    if len(key) < 3 and not re.search(r"[\u3400-\u9fff]", text):
        return "label_too_short"
    if re.fullmatch(r"[\d\W_]+", text):
        return "non_semantic_label"
    if is_generic_label(text):
        return "generic_label"
    return ""


def has_limitation_context(text: str) -> bool:
    return bool(LIMITATION_RE.search(fold_text(text)))


def has_future_context(text: str) -> bool:
    return bool(FUTURE_RE.search(fold_text(text)))


def has_numeric_result(text: str) -> bool:
    return bool(NUMERIC_RESULT_RE.search(fold_text(text)))


def relation_has_cue(relation_type: str, text: str) -> bool:
    pattern = CUE_VERBS.get(relation_type)
    return bool(pattern and pattern.search(fold_text(text)))
