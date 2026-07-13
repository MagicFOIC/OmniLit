from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .knowledge_graph_core import _authors, _normalized, _split_values
from .knowledge_graph_layout import academic_layout, adjacency_index


RESEARCH_NETWORK_VERSION = 1
MAX_PEOPLE_PER_PAPER = 40
MAX_INSTITUTIONS_PER_PAPER = 24
MAX_COLLABORATION_LINKS = 600
MAX_RECOMMENDATIONS = 24


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _year(value: Any) -> int:
    text = str(value or "")
    for token in text.replace("-", " ").replace("/", " ").split():
        if token[:4].isdigit() and 1900 <= int(token[:4]) <= 2100:
            return int(token[:4])
    return 0


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("recordId") or record.get("id") or "")


def _institutions(record: dict[str, Any]) -> list[str]:
    result = []
    for key in ("institutions", "institution", "affiliations", "affiliation"):
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result.extend(_split_values(item.get("display_name") or item.get("name") or item.get("institution")))
                else:
                    result.extend(_split_values(item))
        else:
            result.extend(_split_values(value))
    unique = {}
    for label in result:
        key = _normalized(label)
        if key:
            unique.setdefault(key, str(label).strip())
    return [unique[key] for key in sorted(unique)]


def _explicit_affiliations(record: dict[str, Any]) -> list[tuple[str, str]]:
    result = set()
    for author in record.get("authors") or []:
        if not isinstance(author, dict):
            continue
        name = str(author.get("display_name") or author.get("name") or author.get("author") or "").strip()
        if not name:
            continue
        values = author.get("institutions") or author.get("affiliations") or author.get("affiliation") or []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            if isinstance(value, dict):
                label = str(value.get("display_name") or value.get("name") or value.get("institution") or "").strip()
            else:
                label = str(value or "").strip()
            if label:
                result.add((name, label))
    return sorted(result, key=lambda item: (_normalized(item[0]), _normalized(item[1])))


def _pair_links(groups: dict[str, list[str]], kind: str, labels: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    counts: Counter[tuple[str, str]] = Counter()
    evidence: dict[tuple[str, str], list[str]] = defaultdict(list)
    truncated = 0
    cap = MAX_PEOPLE_PER_PAPER if kind == "author" else MAX_INSTITUTIONS_PER_PAPER
    for paper_id in sorted(groups):
        values = sorted(set(groups[paper_id]))
        if len(values) > cap:
            truncated += len(values) - cap
            values = values[:cap]
        for index, left in enumerate(values):
            for right in values[index + 1:]:
                pair = (left, right)
                counts[pair] += 1
                if len(evidence[pair]) < 12:
                    evidence[pair].append(paper_id)
    links = [{
        "source": left, "target": right, "paperCount": count, "paperIds": evidence[(left, right)],
        "sourceLabel": labels.get(left, left), "targetLabel": labels.get(right, right),
        "explanation": f"{labels.get(left, left)} 与 {labels.get(right, right)} 共同参与 {count} 篇馆藏论文。",
    } for (left, right), count in counts.items()]
    links.sort(key=lambda item: (-item["paperCount"], item["sourceLabel"], item["targetLabel"]))
    return links[:MAX_COLLABORATION_LINKS], truncated


def _entity_metrics(
    kind: str, paper_groups: dict[str, list[str]], labels: dict[str, str], links: list[dict[str, Any]],
    topic_by_paper: dict[str, str], citations_in: Counter[str], paper_year: dict[str, int],
) -> list[dict[str, Any]]:
    papers_by_entity: dict[str, set[str]] = defaultdict(set)
    for paper_id, entities in paper_groups.items():
        for entity in entities:
            papers_by_entity[entity].add(paper_id)
    collaborators: dict[str, set[str]] = defaultdict(set)
    collaboration_weight: Counter[str] = Counter()
    for link in links:
        left = str(link["source"]); right = str(link["target"]); weight = int(link["paperCount"])
        collaborators[left].add(right); collaborators[right].add(left)
        collaboration_weight[left] += weight; collaboration_weight[right] += weight
    max_papers = max((len(value) for value in papers_by_entity.values()), default=1)
    max_citations = max((sum(citations_in[paper_id] for paper_id in values) for values in papers_by_entity.values()), default=1)
    max_collaborators = max((len(value) for value in collaborators.values()), default=1)
    result = []
    for entity_id in sorted(papers_by_entity):
        paper_ids = sorted(papers_by_entity[entity_id])
        topics = sorted({topic_by_paper.get(paper_id, "") for paper_id in paper_ids if topic_by_paper.get(paper_id)})
        cited_by = sum(citations_in[paper_id] for paper_id in paper_ids)
        collaborator_count = len(collaborators[entity_id])
        topic_diversity = min(1.0, max(0, len(topics) - 1) / 3)
        importance = (
            0.36 * len(paper_ids) / max(1, max_papers)
            + 0.30 * cited_by / max(1, max_citations)
            + 0.20 * collaborator_count / max(1, max_collaborators)
            + 0.14 * topic_diversity
        )
        bridge = 0.58 * topic_diversity + 0.42 * collaborator_count / max(1, max_collaborators)
        years = sorted({paper_year.get(paper_id, 0) for paper_id in paper_ids if paper_year.get(paper_id, 0)})
        reasons = [f"参与当前馆藏 {len(paper_ids)} 篇论文"]
        if cited_by:
            reasons.append(f"这些论文累计获得 {cited_by} 次馆藏内引用")
        if collaborator_count:
            reasons.append(f"连接 {collaborator_count} 个合作{('作者' if kind == 'author' else '机构')}")
        if len(topics) > 1:
            reasons.append(f"覆盖 {len(topics)} 个研究主题")
        result.append({
            "id": entity_id, "type": kind, "label": labels.get(entity_id, entity_id),
            "paperCount": len(paper_ids), "paperIds": paper_ids, "citationIn": cited_by,
            "collaboratorCount": collaborator_count, "collaborationWeight": collaboration_weight[entity_id],
            "topicCount": len(topics), "topicIds": topics, "yearStart": years[0] if years else "", "yearEnd": years[-1] if years else "",
            "importanceScore": round(importance, 4), "bridgeScore": round(bridge, 4), "reasons": reasons,
            "explanation": "重要性综合产出规模 36%、馆藏内被引 30%、合作广度 20% 和主题跨度 14%；桥接度强调主题跨度与合作广度。",
        })
    result.sort(key=lambda item: (-item["importanceScore"], -item["paperCount"], item["label"]))
    golden = math.pi * (3 - math.sqrt(5))
    for index, item in enumerate(result):
        radius = 0.08 + 0.40 * math.sqrt((index + 1) / max(1, len(result)))
        angle = index * golden
        item["x"] = round(0.5 + math.cos(angle) * radius, 6)
        item["y"] = round(0.5 + math.sin(angle) * radius * 0.78, 6)
    return result


def _recommendations(
    topic_map: dict[str, Any], evolution: dict[str, Any], network_analysis: dict[str, Any], records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    assignments = {str(item.get("recordId") or ""): str(item.get("topicId") or "") for item in topic_map.get("assignments") or []}
    topics = {str(item.get("id") or ""): item for item in topic_map.get("topics") or [] if isinstance(item, dict)}
    metrics = {str(item.get("recordId") or ""): item for item in network_analysis.get("paperMetrics") or [] if isinstance(item, dict)}
    evolution_papers = {str(item.get("recordId") or ""): item for item in evolution.get("papers") or [] if isinstance(item, dict)}
    citation_pairs = {(str(item.get("source") or ""), str(item.get("target") or "")) for item in topic_map.get("citationLinks") or [] if isinstance(item, dict)}
    max_year = max((_year(item.get("year") or item.get("publicationDate")) for item in records), default=0)
    archived = set(); queued = set(); favored = set(); compared = set()
    for record in records:
        record_id = _record_id(record)
        projects = {str(item) for item in record.get("favoriteProjectIds") or []}
        if "read_archive" in projects: archived.add(record_id)
        if "to_read" in projects: queued.add(record_id)
        if projects - {"read_archive"}: favored.add(record_id)
        if record.get("inCompare"): compared.add(record_id)
    candidates = []
    for record in records:
        record_id = _record_id(record)
        if not record_id or record_id in archived:
            continue
        metric = metrics.get(record_id, {})
        evolved = evolution_papers.get(record_id, {})
        topic_id = assignments.get(record_id, "")
        topic = topics.get(topic_id, {})
        growth = topic.get("growth") or {}
        year = _year(record.get("year") or record.get("publicationYear") or record.get("publicationDate") or evolved.get("year"))
        core = _safe_float(metric.get("coreScore"))
        bridge = _safe_float(metric.get("bridgeScore"))
        key_score = _safe_float(evolved.get("keyScore"))
        growing = 1.0 if str(growth.get("trend") or "") == "growing" else 0.0
        recent = 1.0 if max_year and year >= max_year - 2 else 0.0
        context = 1.0 if record_id in favored or record_id in compared else 0.0
        available = 1.0 if record.get("localPdfPath") else 0.0
        score = 0.30 * core + 0.20 * bridge + 0.20 * key_score + 0.10 * growing + 0.06 * recent + 0.08 * context + 0.04 * available + (0.02 if record_id in queued else 0.0)
        citation_in = int(metric.get("citationIn") or evolved.get("citationIn") or 0)
        if core >= max(0.28, bridge * 1.25) or citation_in >= 2:
            stage = "foundation"
        elif bridge >= 0.12 or int(metric.get("crossTopicLinks") or 0) > 0:
            stage = "bridge"
        else:
            stage = "frontier"
        reasons = []
        if core > 0: reasons.append(f"核心度 {core:.2f}，馆藏内被引 {citation_in} 次")
        if bridge > 0: reasons.append(f"桥接度 {bridge:.2f}，连接 {int(metric.get('crossTopicLinks') or 0)} 条跨主题关系")
        if key_score > 0: reasons.append(f"演化关键性 {key_score:.2f}")
        if growing: reasons.append("所属主题最近窗口正在增长")
        if recent: reasons.append("属于当前集合的近期研究")
        if record_id in queued: reasons.append("已在“待读精读”中")
        if record_id in compared: reasons.append("已加入当前对比上下文")
        if not reasons: reasons.append("当前集合证据有限，按主题覆盖与年份补充推荐")
        candidates.append({
            "recordId": record_id, "title": record.get("title") or evolved.get("title") or record_id,
            "year": year or "", "topicId": topic_id, "topicName": topic.get("name") or "待归类主题",
            "stage": stage, "score": round(score, 4), "coreScore": round(core, 4), "bridgeScore": round(bridge, 4),
            "keyScore": round(key_score, 4), "citationIn": citation_in, "downloaded": bool(record.get("localPdfPath")),
            "queued": record_id in queued, "reasons": reasons,
            "explanation": "推荐分综合核心度 30%、桥接度 20%、演化关键性 20%、主题增长 10%、近期性 6%、用户上下文 8%、本地可读性 4% 和待读状态 2%。",
        })
    candidates.sort(key=lambda item: (-item["score"], item["year"] or 9999, item["recordId"]))
    recommendations = candidates[:MAX_RECOMMENDATIONS]
    selected = []
    limits = {"foundation": 3, "bridge": 3, "frontier": 4}
    for stage in ("foundation", "bridge", "frontier"):
        stage_items = [item for item in recommendations if item["stage"] == stage]
        if stage == "foundation":
            stage_items.sort(key=lambda item: (item["year"] or 9999, -item["score"], item["recordId"]))
        for item in stage_items[:limits[stage]]:
            if item["recordId"] not in {value["recordId"] for value in selected}:
                selected.append(item)
    if len(selected) < 5:
        for item in recommendations:
            if item["recordId"] not in {value["recordId"] for value in selected}:
                selected.append(item)
            if len(selected) >= 8:
                break
    steps = []
    for index, item in enumerate(selected[:10]):
        transition = {"type": "start", "explanation": "先阅读领域基础或最高证据论文。"}
        if index:
            previous = selected[index - 1]
            if (item["recordId"], previous["recordId"]) in citation_pairs:
                transition = {"type": "cites_previous", "explanation": "该论文真实引用上一步论文，可沿方法继承继续阅读。"}
            elif (previous["recordId"], item["recordId"]) in citation_pairs:
                transition = {"type": "cited_by_previous", "explanation": "上一步论文真实引用该论文；回读它可补充前置基础。"}
            elif item["topicId"] and item["topicId"] == previous["topicId"]:
                transition = {"type": "shared_topic", "explanation": "两篇论文属于同一聚类；这是主题相关过渡，不代表存在引用。"}
            else:
                transition = {"type": "cross_topic", "explanation": "转向跨主题桥梁或前沿方向；该过渡不表示两篇论文存在直接引用。"}
        steps.append({**item, "step": index + 1, "transition": transition})
    paths = [{
        "id": "recommended:balanced", "name": "基础 → 桥梁 → 前沿",
        "paperIds": [item["recordId"] for item in steps], "steps": steps,
        "explanation": "先建立领域基础，再阅读跨主题桥梁，最后进入增长主题与近期研究；只有真实馆藏引文才标为引用过渡。",
    }] if steps else []
    return recommendations, paths, {
        "archivedExcluded": len(archived), "queuedCount": len(queued), "favoriteContextCount": len(favored),
        "compareContextCount": len(compared), "candidateCount": len(candidates),
    }


def build_research_network(
    topic_map: dict[str, Any], evolution: dict[str, Any], network_analysis: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    values = [dict(item) for item in records if isinstance(item, dict) and _record_id(item)]
    values.sort(key=_record_id)
    topic_by_paper = {str(item.get("recordId") or ""): str(item.get("topicId") or "") for item in topic_map.get("assignments") or []}
    citations_in: Counter[str] = Counter(str(item.get("target") or "") for item in topic_map.get("citationLinks") or [] if isinstance(item, dict))
    author_groups: dict[str, list[str]] = {}
    institution_groups: dict[str, list[str]] = {}
    author_labels: dict[str, str] = {}
    institution_labels: dict[str, str] = {}
    paper_year = {}
    explicit_affiliations = []
    author_papers = 0; institution_papers = 0
    for record in values:
        paper_id = _record_id(record); paper_year[paper_id] = _year(record.get("year") or record.get("publicationDate"))
        author_ids = []
        for label in _authors(record):
            entity_id = _normalized(label)
            if entity_id:
                author_labels.setdefault(entity_id, str(label).strip()); author_ids.append(entity_id)
        author_groups[paper_id] = sorted(set(author_ids))
        author_papers += bool(author_ids)
        institution_ids = []
        for label in _institutions(record):
            entity_id = _normalized(label)
            if entity_id:
                institution_labels.setdefault(entity_id, str(label).strip()); institution_ids.append(entity_id)
        institution_groups[paper_id] = sorted(set(institution_ids))
        institution_papers += bool(institution_ids)
        for author, institution in _explicit_affiliations(record):
            author_id = _normalized(author); institution_id = _normalized(institution)
            if author_id and institution_id:
                author_labels.setdefault(author_id, author); institution_labels.setdefault(institution_id, institution)
                explicit_affiliations.append({"authorId": author_id, "institutionId": institution_id, "paperId": paper_id, "sourceKind": "explicit_author_affiliation"})
    author_links, author_truncated = _pair_links(author_groups, "author", author_labels)
    institution_links, institution_truncated = _pair_links(institution_groups, "institution", institution_labels)
    authors = _entity_metrics("author", author_groups, author_labels, author_links, topic_by_paper, citations_in, paper_year)
    institutions = _entity_metrics("institution", institution_groups, institution_labels, institution_links, topic_by_paper, citations_in, paper_year)
    recommendations, reading_paths, recommendation_context = _recommendations(topic_map, evolution, network_analysis, values)
    signature = {
        "version": RESEARCH_NETWORK_VERSION, "topic": topic_map.get("cacheKey"), "evolution": evolution.get("cacheKey"),
        "network": network_analysis.get("cacheKey"),
        "records": [(_record_id(item), _authors(item), _institutions(item), item.get("favoriteProjectIds"), item.get("inCompare")) for item in values],
    }
    warnings = []
    if author_papers < len(values): warnings.append(f"{len(values) - author_papers} 篇论文缺少作者元数据。")
    if institution_papers < len(values): warnings.append(f"{len(values) - institution_papers} 篇论文缺少机构元数据。")
    if not explicit_affiliations: warnings.append("没有作者级 affiliation；不推断具体作者所属机构。")
    return {
        "version": RESEARCH_NETWORK_VERSION, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cacheKey": hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        "coverage": {
            "paperCount": len(values), "authorPaperCount": author_papers, "institutionPaperCount": institution_papers,
            "authorCoverage": round(author_papers / max(1, len(values)), 4), "institutionCoverage": round(institution_papers / max(1, len(values)), 4),
            "explicitAffiliationCount": len(explicit_affiliations), "warnings": warnings,
        },
        "authors": authors, "institutions": institutions,
        "authorLinks": author_links, "institutionLinks": institution_links, "affiliations": explicit_affiliations,
        "recommendations": recommendations, "readingPaths": reading_paths, "recommendationContext": recommendation_context,
        "methods": {
            "importance": "产出规模 36% + 馆藏内被引 30% + 合作广度 20% + 主题跨度 14%。",
            "bridge": "主题跨度 58% + 合作广度 42%。",
            "recommendation": "核心、桥接、演化、主题增长、近期性、用户收藏/对比上下文和本地可读性加权；已读归档默认排除。",
        },
        "diagnostics": {
            "authorLinkTruncatedMembers": author_truncated, "institutionLinkTruncatedMembers": institution_truncated,
            "maxCollaborationLinks": MAX_COLLABORATION_LINKS, "recommendationLimit": MAX_RECOMMENDATIONS,
        },
    }


def build_research_network_graph(analysis: dict[str, Any], mode: str) -> dict[str, Any]:
    requested = str(mode or "").casefold()
    if requested.startswith("read"):
        path = next(iter(analysis.get("readingPaths") or []), {})
        steps = list(path.get("steps") or [])
        if not steps:
            return {}
        nodes = [{
            "id": f"paper:{item['recordId']}", "type": "paper", "label": item.get("title") or item["recordId"],
            "importance": _safe_float(item.get("score")), "confidence": 1.0,
            "details": {**dict(item), "recordId": item["recordId"]}, "evidence": [],
        } for item in steps]
        edges = []
        for index, item in enumerate(steps[1:]):
            previous = steps[index]
            transition = dict(item.get("transition") or {})
            transition_type = str(transition.get("type") or "cross_topic")
            confidence = 1.0 if transition_type in {"cites_previous", "cited_by_previous"} else (0.62 if transition_type == "shared_topic" else 0.38)
            edges.append({
                "id": f"reading-step:{index + 1}", "source": f"paper:{previous['recordId']}", "target": f"paper:{item['recordId']}",
                "type": "READING_NEXT", "label": "下一步阅读", "confidence": confidence,
                "details": {"transitionType": transition_type, "step": index + 2}, "evidence": [],
                "direction_reason": str(transition.get("explanation") or "推荐阅读顺序。"),
            })
        layout = academic_layout(nodes, comparison=True)
        key = f"research_reading_{str(analysis.get('cacheKey') or '')[:12]}"
        metadata = {
            "comparison": True, "research_network_graph": True, "research_network_mode": "reading",
            "comparison_record_ids": [str(item["recordId"]) for item in steps],
            "source": {"extractionEngine": "reading-recommendation", "sourceSha256": analysis.get("cacheKey", "")},
            "summary": {"keywords": [], "contentSummary": str(path.get("explanation") or "可解释推荐阅读路径。"), "abstract": ""},
            "layout": layout, "adjacency": adjacency_index(edges),
            "quality_summary": {"node_count": len(nodes), "edge_count": len(edges)},
        }
        return {
            "version": 1, "schema_version": 1, "recordId": key, "record_id": key,
            "title": "推荐阅读路径", "paper": {"title": "推荐阅读路径", "authors": [], "year": "", "source": "recommendation", "pdf_path": ""},
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source_fingerprint": str(analysis.get("cacheKey") or ""),
            "nodes": nodes, "edges": edges, "metadata": metadata, "layout": layout,
            "adjacency": metadata["adjacency"], "quality_summary": metadata["quality_summary"],
        }
    mode_value = "institutions" if requested.startswith("institution") else "authors"
    kind = "institution" if mode_value == "institutions" else "author"
    entities = list(analysis.get("institutions") if kind == "institution" else analysis.get("authors") or [])[:80]
    links = list(analysis.get("institutionLinks") if kind == "institution" else analysis.get("authorLinks") or [])
    included = {str(item.get("id") or "") for item in entities}
    nodes = [{
        "id": f"{kind}:{item['id']}", "type": kind, "label": item.get("label") or item["id"],
        "importance": _safe_float(item.get("importanceScore")), "confidence": 1.0, "details": dict(item), "evidence": [],
    } for item in entities]
    edges = [{
        "id": f"collaboration:{kind}:{index + 1}", "source": f"{kind}:{item['source']}", "target": f"{kind}:{item['target']}",
        "type": "COAUTHOR_WITH" if kind == "author" else "COLLABORATES_WITH", "label": "共同署名" if kind == "author" else "共同参与论文",
        "confidence": min(1.0, 0.45 + 0.12 * int(item.get("paperCount") or 0)), "details": dict(item), "evidence": [],
        "direction_reason": "对称合作关系，不表示方向。",
    } for index, item in enumerate(links) if str(item.get("source") or "") in included and str(item.get("target") or "") in included][:MAX_COLLABORATION_LINKS]
    if not nodes:
        return {}
    layout = academic_layout(nodes, comparison=True)
    key = f"research_{mode_value}_{str(analysis.get('cacheKey') or '')[:12]}"
    metadata = {
        "comparison": True, "research_network_graph": True, "research_network_mode": mode_value,
        "comparison_record_ids": sorted({paper_id for item in entities for paper_id in item.get("paperIds") or []}),
        "source": {"extractionEngine": "research-network", "sourceSha256": analysis.get("cacheKey", "")},
        "summary": {"keywords": [], "contentSummary": "基于馆藏真实署名与机构元数据构建的合作网络。", "abstract": ""},
        "layout": layout, "adjacency": adjacency_index(edges),
        "quality_summary": {"node_count": len(nodes), "edge_count": len(edges)},
    }
    return {
        "version": 1, "schema_version": 1, "recordId": key, "record_id": key,
        "title": "作者合作网络" if kind == "author" else "机构合作网络",
        "paper": {"title": "作者合作网络" if kind == "author" else "机构合作网络", "authors": [], "year": "", "source": "research-network", "pdf_path": ""},
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source_fingerprint": str(analysis.get("cacheKey") or ""),
        "nodes": nodes, "edges": edges, "metadata": metadata, "layout": layout,
        "adjacency": metadata["adjacency"], "quality_summary": metadata["quality_summary"],
    }
