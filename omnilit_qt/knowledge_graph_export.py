from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .knowledge_graph_schema import KnowledgeGraphDocument


def export_json(document: KnowledgeGraphDocument, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_markdown(document: KnowledgeGraphDocument, path: Path, comparison: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter(node.type for node in document.nodes)
    lines = [f"# {document.paper.get('title') or '知识图谱'}", ""]
    if comparison:
        lines.extend(["## 1. 对比文献"])
        lines.extend(f"- {node.label}" for node in document.nodes if node.type.casefold() == "paper")
        semantic = document.metadata.get("semantic_comparison") or {}
        dimensions = semantic.get("dimensions") or []
        papers = semantic.get("papers") or []
        if dimensions and papers:
            lines.extend(["", "## ORKG 语义比较矩阵", ""])
            lines.append("| 维度 | " + " | ".join(str(item.get("title") or item.get("recordId") or "文献").replace("|", "/") for item in papers) + " |")
            lines.append("| --- | " + " | ".join("---" for _ in papers) + " |")
            for dimension in dimensions:
                key = str(dimension.get("key") or "")
                values = []
                for paper in papers:
                    cell = next((item for item in paper.get("cells") or [] if str(item.get("dimension") or "") == key), {})
                    labels = [str(item.get("label") or "").replace("|", "/") for item in cell.get("items") or [] if str(item.get("label") or "")]
                    value = "；".join(labels) if labels else "未识别（不等于不存在）"
                    source = "人工审阅" if (cell.get("review") or {}).get("action") else "自动抽取"
                    values.append(f"{value}<br>{source} · 置信 {float(cell.get('confidence') or 0):.0%} · 证据 {int(cell.get('evidenceCount') or 0)}")
                lines.append(f"| {str(dimension.get('label') or key).replace('|', '/')} | " + " | ".join(values) + " |")
        sections = (("## 2. 共同研究问题", "common"), ("## 3. 方法差异", "method"), ("## 4. 数据集与实验设置", "dataset"), ("## 5. 指标与结果", "result"), ("## 6. 主要贡献", "contribution"), ("## 7. 局限与未来工作", "limitation"), ("## 8. 冲突或不一致结论", "conflict"), ("## 9. 可继续阅读的问题", "missing"))
        for heading, tag in sections:
            lines.extend(["", heading])
            matches = [node for node in document.nodes if tag in [item.casefold() for item in node.tags] or node.type.casefold() == tag]
            lines.extend([f"- {node.label}" for node in matches] or ["- 暂无可靠证据"])
    else:
        lines.extend(["## 关键词"])
        lines.extend(f"- {node.label}" for node in document.nodes if "keyword" in node.tags)
        lines.extend(["", "## 节点统计"])
        lines.extend(f"- {kind}: {count}" for kind, count in sorted(counts.items()))
        lines.extend(["", "## 证据化节点"])
        for node in document.nodes:
            if node.type.casefold() == "paper":
                continue
            evidence = node.evidence[0] if node.evidence else None
            location = f"（第 {evidence.page + 1} 页）" if evidence and evidence.page >= 0 else ""
            lines.append(f"- **{node.label}** [{node.type}]{location}: {node.summary}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def export_mermaid(document: KnowledgeGraphDocument, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_ids = {node.id: f"N{index}" for index, node in enumerate(document.nodes)}
    lines = ["```mermaid", "graph LR"]
    for node in document.nodes:
        label = node.label.replace('"', "'").replace("\n", " ")[:80]
        lines.append(f'    {safe_ids[node.id]}["{label}"]')
    for edge in document.edges:
        if edge.source in safe_ids and edge.target in safe_ids:
            label = (edge.label or edge.type).replace('"', "'").replace("|", "/")
            lines.append(f'    {safe_ids[edge.source]} -->|"{label}"| {safe_ids[edge.target]}')
    lines.append("```")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def export_csv(document: KnowledgeGraphDocument, nodes_path: Path, edges_path: Path) -> tuple[Path, Path]:
    nodes_path.parent.mkdir(parents=True, exist_ok=True)
    with nodes_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "type", "label", "summary", "importance", "confidence"])
        writer.writerows([node.id, node.type, node.label, node.summary, node.importance, node.confidence] for node in document.nodes)
    with edges_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "source", "target", "type", "label", "confidence"])
        writer.writerows([edge.id, edge.source, edge.target, edge.type, edge.label, edge.confidence] for edge in document.edges)
    return nodes_path, edges_path
