from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from .knowledge_graph_layout import academic_layout, adjacency_index
from .knowledge_graph_topics import extract_feature_documents


NETWORK_ANALYSIS_VERSION = 1
MAX_TERMS_PER_PAPER = 12
MAX_KEYWORD_NODES = 120
MAX_KEYWORD_LINKS = 480
MAX_REFERENCE_FANOUT = 80
MAX_BETWEENNESS_SOURCES = 48


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _pair_counts(groups: dict[str, set[str]], cap: int) -> tuple[Counter[tuple[str, str]], int]:
    result: Counter[tuple[str, str]] = Counter()
    truncated = 0
    for group_id in sorted(groups):
        values = sorted(groups[group_id])
        if len(values) > cap:
            truncated += len(values) - cap
            values = values[:cap]
        for index, left in enumerate(values):
            for right in values[index + 1:]:
                result[(left, right)] += 1
    return result, truncated


def _structural_links(
    citations: list[dict[str, Any]], valid_ids: set[str], mode: str,
) -> tuple[list[dict[str, Any]], int]:
    references: dict[str, set[str]] = defaultdict(set)
    citers: dict[str, set[str]] = defaultdict(set)
    for item in citations:
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        if source in valid_ids and target in valid_ids and source != target:
            references[source].add(target)
            citers[target].add(source)
    # Pair papers by the opposite incidence list: coupling pairs citing papers
    # under each shared reference; co-citation pairs referenced papers under
    # each shared citer.
    groups = citers if mode == "coupling" else references
    pair_counts, truncated = _pair_counts(groups, MAX_REFERENCE_FANOUT)
    memberships = references if mode == "coupling" else citers
    evidence_kind = "sharedReferences" if mode == "coupling" else "sharedCiters"
    links = []
    for (left, right), shared in pair_counts.items():
        union = len(memberships.get(left, set()) | memberships.get(right, set()))
        score = shared / max(1, union)
        evidence = sorted(memberships.get(left, set()) & memberships.get(right, set()))[:12]
        label = "共同引用" if mode == "coupling" else "共同被引用"
        links.append({
            "source": left, "target": right, evidence_kind: shared,
            "score": round(score, 4), "evidencePaperIds": evidence,
            "explanation": f"两篇论文有 {shared} 篇{label}证据；Jaccard 归一化强度为 {score:.2f}。",
        })
    links.sort(key=lambda item: (-int(item[evidence_kind]), -item["score"], item["source"], item["target"]))
    return links, truncated


def _keyword_network(
    documents: list[dict[str, Any]], assignments: dict[str, str], topic_layout: dict[str, tuple[float, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[int, int]], int]:
    document_frequency: Counter[str] = Counter()
    labels: dict[str, str] = {}
    sources: dict[str, set[str]] = defaultdict(set)
    topics: dict[str, set[str]] = defaultdict(set)
    years: dict[str, Counter[int]] = defaultdict(Counter)
    pairs: Counter[tuple[str, str]] = Counter()
    paper_ids: dict[str, list[str]] = defaultdict(list)
    truncated = 0
    for document in documents:
        features = [item for item in document.get("features") or [] if isinstance(item, dict)]
        terms = []
        for feature in features[:MAX_TERMS_PER_PAPER]:
            term = str(feature.get("term") or "")
            if term and term not in terms:
                terms.append(term)
                labels.setdefault(term, str(feature.get("label") or term))
                sources[term].update(str(item) for item in feature.get("sources") or [])
        truncated += max(0, len(features) - MAX_TERMS_PER_PAPER)
        year = int(document.get("year")) if str(document.get("year") or "").isdigit() else 0
        record_id = str(document.get("recordId") or "")
        topic_id = assignments.get(record_id, "")
        for term in terms:
            document_frequency[term] += 1
            paper_ids[term].append(record_id)
            if topic_id:
                topics[term].add(topic_id)
            if year:
                years[term][year] += 1
        for index, left in enumerate(sorted(terms)):
            for right in sorted(terms)[index + 1:]:
                pairs[(left, right)] += 1
    selected_terms = [term for term, _ in sorted(document_frequency.items(), key=lambda item: (-item[1], item[0]))[:MAX_KEYWORD_NODES]]
    selected = set(selected_terms)
    link_values = []
    weighted_degree: Counter[str] = Counter()
    total_documents = max(1, len(documents))
    for (left, right), count in pairs.items():
        if left not in selected or right not in selected:
            continue
        union = document_frequency[left] + document_frequency[right] - count
        jaccard = count / max(1, union)
        pmi = math.log2((count * total_documents) / max(1, document_frequency[left] * document_frequency[right]))
        link_values.append({
            "source": left, "target": right, "cooccurrence": count,
            "score": round(jaccard, 4), "pmi": round(pmi, 4),
            "explanation": f"共同出现在 {count} 篇论文中；Jaccard={jaccard:.2f}，PMI={pmi:.2f}。",
        })
        weighted_degree[left] += count
        weighted_degree[right] += count
    link_values.sort(key=lambda item: (-item["cooccurrence"], -item["score"], item["source"], item["target"]))
    link_values = link_values[:MAX_KEYWORD_LINKS]
    maximum_degree = max(weighted_degree.values(), default=1)
    nodes = []
    golden = math.pi * (3 - math.sqrt(5))
    for index, term in enumerate(selected_terms):
        angle = index * golden
        topic_points = [topic_layout[topic_id] for topic_id in sorted(topics[term]) if topic_id in topic_layout]
        if topic_points:
            center_x = sum(point[0] for point in topic_points) / len(topic_points)
            center_y = sum(point[1] for point in topic_points) / len(topic_points)
            jitter = 0.025 + 0.09 * math.sqrt((index + 1) / max(1, len(selected_terms)))
            x = min(0.94, max(0.06, center_x + math.cos(angle) * jitter))
            y = min(0.94, max(0.06, center_y + math.sin(angle) * jitter * 0.75))
        else:
            radius = 0.08 + 0.39 * math.sqrt((index + 1) / max(1, len(selected_terms)))
            x = 0.5 + math.cos(angle) * radius
            y = 0.5 + math.sin(angle) * radius * 0.78
        density = weighted_degree[term] / maximum_degree
        nodes.append({
            "id": term, "term": term, "label": labels.get(term, term),
            "paperCount": document_frequency[term], "weightedDegree": weighted_degree[term],
            "density": round(density, 4), "x": round(x, 6), "y": round(y, 6),
            "topicIds": sorted(topics[term]), "sources": sorted(sources[term]),
            "paperIds": paper_ids[term][:40],
            "explanation": f"覆盖 {document_frequency[term]} 篇论文，共现加权度 {weighted_degree[term]}；密度按当前网络最大值归一化。",
        })
    yearly = {term: dict(sorted(values.items())) for term, values in years.items()}
    return nodes, link_values, yearly, truncated


def _approx_betweenness(adjacency: dict[str, set[str]]) -> tuple[dict[str, float], int]:
    ids = sorted(adjacency)
    if not ids:
        return {}, 0
    source_count = min(MAX_BETWEENNESS_SOURCES, len(ids))
    sources = [ids[min(len(ids) - 1, index * len(ids) // source_count)] for index in range(source_count)]
    centrality: Counter[str] = Counter()
    for source in sources:
        predecessors: dict[str, list[str]] = defaultdict(list)
        paths: Counter[str] = Counter({source: 1})
        distance = {source: 0}
        queue = deque([source])
        stack = []
        while queue:
            node = queue.popleft(); stack.append(node)
            for neighbor in adjacency.get(node, set()):
                if neighbor not in distance:
                    distance[neighbor] = distance[node] + 1; queue.append(neighbor)
                if distance[neighbor] == distance[node] + 1:
                    paths[neighbor] += paths[node]; predecessors[neighbor].append(node)
        dependency: Counter[str] = Counter()
        while stack:
            node = stack.pop()
            for predecessor in predecessors[node]:
                dependency[predecessor] += (paths[predecessor] / max(1, paths[node])) * (1 + dependency[node])
            if node != source:
                centrality[node] += dependency[node]
    maximum = max(centrality.values(), default=1.0)
    return {node: float(value / maximum) for node, value in centrality.items()}, source_count


def _paper_metrics(
    papers: list[dict[str, Any]], citations: list[dict[str, Any]], assignments: dict[str, str],
    coupling: list[dict[str, Any]], cocitation: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    paper_by_id = {str(item.get("recordId") or ""): item for item in papers}
    adjacency: dict[str, set[str]] = {record_id: set() for record_id in paper_by_id}
    incoming: Counter[str] = Counter(); outgoing: Counter[str] = Counter(); cross_topic: Counter[str] = Counter()
    for link in citations:
        source = str(link.get("source") or ""); target = str(link.get("target") or "")
        if source in adjacency and target in adjacency:
            adjacency[source].add(target); adjacency[target].add(source)
            outgoing[source] += 1; incoming[target] += 1
            if assignments.get(source) and assignments.get(source) != assignments.get(target):
                cross_topic[source] += 1; cross_topic[target] += 1
    structural: Counter[str] = Counter()
    for link in coupling + cocitation:
        structural[str(link.get("source") or "")] += 1
        structural[str(link.get("target") or "")] += 1
    between, sampled = _approx_betweenness(adjacency)
    max_in = max(1, max(incoming.values(), default=0))
    max_degree = max(1, max((len(value) for value in adjacency.values()), default=0))
    metrics = []
    for record_id in sorted(paper_by_id):
        degree = len(adjacency[record_id])
        bridge = 0.62 * between.get(record_id, 0.0) + 0.38 * cross_topic[record_id] / max(1, degree)
        core = 0.55 * incoming[record_id] / max_in + 0.30 * degree / max_degree + 0.15 * min(1.0, structural[record_id] / 5)
        reasons = []
        if incoming[record_id]: reasons.append(f"被馆藏内 {incoming[record_id]} 篇论文引用")
        if cross_topic[record_id]: reasons.append(f"连接 {cross_topic[record_id]} 条跨主题引文")
        if structural[record_id]: reasons.append(f"参与 {structural[record_id]} 条共被引/耦合关系")
        if not reasons: reasons.append("当前馆藏没有检测到可追溯结构关系")
        metrics.append({
            "recordId": record_id, "title": paper_by_id[record_id].get("title") or record_id,
            "year": paper_by_id[record_id].get("year") or "", "topicId": assignments.get(record_id, ""),
            "citationIn": incoming[record_id], "citationOut": outgoing[record_id], "degree": degree,
            "crossTopicLinks": cross_topic[record_id], "structuralLinks": structural[record_id],
            "coreScore": round(core, 4), "bridgeScore": round(bridge, 4),
            "reasons": reasons,
            "explanation": "核心度综合馆藏内被引、连接度和结构关系；桥接度综合抽样介数与跨主题引文占比。",
        })
    return metrics, sampled


def _bursts(yearly: dict[str, dict[int, int]], nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    node_by_term = {str(item["term"]): item for item in nodes}
    result = []
    for term, values in yearly.items():
        total = sum(values.values())
        known = sorted(values)
        if total < 3 or len(known) < 2:
            continue
        end = known[-1]; recent_years = range(end - 2, end + 1); previous_years = range(end - 5, end - 2)
        recent = sum(values.get(year, 0) for year in recent_years)
        previous = sum(values.get(year, 0) for year in previous_years)
        recent_rate = (recent + 1) / 4; previous_rate = (previous + 1) / 4
        growth = recent_rate / previous_rate
        score = math.log2(growth) * math.log1p(recent)
        if score <= 0.35 or recent < 2:
            continue
        node = node_by_term.get(term, {})
        result.append({
            "term": term, "label": node.get("label") or term,
            "startYear": end - 2, "endYear": end, "recentCount": recent, "previousCount": previous,
            "growthRate": round(growth, 3), "burstScore": round(score, 4),
            "paperIds": node.get("paperIds") or [], "topicIds": node.get("topicIds") or [],
            "explanation": f"最近 3 年出现 {recent} 次，前一 3 年 {previous} 次；平滑增长倍数 {growth:.2f}。",
        })
    result.sort(key=lambda item: (-item["burstScore"], -item["recentCount"], item["term"]))
    return result[:40]


def build_network_analysis(
    topic_map: dict[str, Any], evolution: dict[str, Any], graphs: list[dict[str, Any]],
    records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = extract_feature_documents(graphs, records)
    valid_ids = {str(item.get("recordId") or "") for item in documents}
    assignments = {str(item.get("recordId") or ""): str(item.get("topicId") or "") for item in topic_map.get("assignments") or []}
    citations = [dict(item) for item in topic_map.get("citationLinks") or [] if isinstance(item, dict)]
    cocitation, cocitation_truncated = _structural_links(citations, valid_ids, "cocitation")
    coupling, coupling_truncated = _structural_links(citations, valid_ids, "coupling")
    topic_layout = {
        str(item.get("id") or ""): (_safe_float(item.get("x"), 0.5), _safe_float(item.get("y"), 0.5))
        for item in topic_map.get("topics") or [] if isinstance(item, dict)
    }
    keyword_nodes, keyword_links, yearly, keyword_truncated = _keyword_network(documents, assignments, topic_layout)
    papers = [dict(item) for item in evolution.get("papers") or [] if isinstance(item, dict)]
    if not papers:
        papers = [{"recordId": item["recordId"], "title": item["title"], "year": item.get("year", "")} for item in documents]
    metrics, sampled_sources = _paper_metrics(papers, citations, assignments, coupling, cocitation)
    core = sorted(metrics, key=lambda item: (-item["coreScore"], item["recordId"]))[:20]
    bridges = [item for item in sorted(metrics, key=lambda item: (-item["bridgeScore"], item["recordId"])) if item["bridgeScore"] > 0][:20]
    bursts = _bursts(yearly, keyword_nodes)
    topic_trends = [{
        "topicId": item.get("id"), "name": item.get("name"), "size": item.get("size", 0),
        "yearStart": item.get("yearStart", ""), "yearEnd": item.get("yearEnd", ""),
        **dict(item.get("growth") or {}),
        "explanation": (
            f"最近窗口 {int((item.get('growth') or {}).get('recentCount') or 0)} 篇，"
            f"前一窗口 {int((item.get('growth') or {}).get('previousCount') or 0)} 篇；"
            "同时展示绝对规模，避免把小样本高增长误读为主流主题。"
        ),
    } for item in topic_map.get("topics") or [] if isinstance(item, dict)]
    topic_trends.sort(key=lambda item: (-_safe_float(item.get("rate")), -int(item.get("size") or 0), str(item.get("name") or "")))
    known_years = sum(bool(item.get("year")) for item in documents)
    referenced_sources = len({str(item.get("source") or "") for item in citations})
    warnings = []
    if not citations: warnings.append("当前馆藏没有可追溯的论文间引文，共被引和文献耦合为空。")
    if known_years < len(documents): warnings.append(f"{len(documents) - known_years} 篇论文缺少年份，不参与突现趋势。")
    if cocitation_truncated or coupling_truncated: warnings.append("超高扇出引文已按稳定顺序截断，以控制二次复杂度。")
    cache_payload = json.dumps({
        "version": NETWORK_ANALYSIS_VERSION, "topic": topic_map.get("cacheKey"), "evolution": evolution.get("cacheKey"),
        "documents": [(item["recordId"], item.get("year"), [feature["term"] for feature in item.get("features") or []]) for item in documents],
        "citations": [(item.get("source"), item.get("target")) for item in citations],
    }, ensure_ascii=False, sort_keys=True)
    return {
        "version": NETWORK_ANALYSIS_VERSION, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cacheKey": hashlib.sha256(cache_payload.encode("utf-8")).hexdigest(),
        "coverage": {
            "paperCount": len(documents), "citationLinkCount": len(citations), "referenceSourceCount": referenced_sources,
            "referenceCoverage": round(referenced_sources / max(1, len(documents)), 4),
            "semanticFeaturePaperCount": sum(bool(item.get("features")) for item in documents),
            "yearCoverage": round(known_years / max(1, len(documents)), 4), "warnings": warnings,
        },
        "coCitation": {"links": cocitation, "method": "馆藏内两篇被引论文共享的施引论文；分数为 Jaccard。"},
        "coupling": {"links": coupling, "method": "馆藏内两篇施引论文共享的参考论文；分数为 Jaccard。"},
        "keywordNetwork": {"nodes": keyword_nodes, "links": keyword_links, "method": "每篇论文最多取 12 个有来源的语义特征，边表示同篇共现。"},
        "paperMetrics": metrics, "corePapers": core, "bridgePapers": bridges,
        "bursts": bursts, "topicTrends": topic_trends,
        "methods": {
            "core": "馆藏内被引 55% + 无向连接度 30% + 共被引/耦合参与度 15%。",
            "bridge": f"最多 {MAX_BETWEENNESS_SOURCES} 个确定性抽样源的近似介数 62% + 跨主题引文占比 38%。",
            "burst": "最近 3 年与前一 3 年的加一平滑频率比，并按近期规模加权。",
            "trend": "沿用主题地图的相邻时间窗口增长率，并与主题绝对规模并列展示。",
        },
        "diagnostics": {
            "coCitationTruncatedMembers": cocitation_truncated, "couplingTruncatedMembers": coupling_truncated,
            "keywordFeaturesTruncated": keyword_truncated, "betweennessSampledSources": sampled_sources,
            "maxKeywordNodes": MAX_KEYWORD_NODES, "maxKeywordLinks": MAX_KEYWORD_LINKS,
        },
    }


def build_network_analysis_graph(analysis: dict[str, Any], mode: str = "core") -> dict[str, Any]:
    mode_value = str(mode or "core")
    metrics = {str(item.get("recordId") or ""): item for item in analysis.get("paperMetrics") or [] if isinstance(item, dict)}
    if mode_value == "cocitation":
        links = list((analysis.get("coCitation") or {}).get("links") or [])[:160]; edge_type = "CO_CITED"
    elif mode_value == "coupling":
        links = list((analysis.get("coupling") or {}).get("links") or [])[:160]; edge_type = "BIBLIOGRAPHIC_COUPLING"
    else:
        selected = analysis.get("bridgePapers") if mode_value == "bridge" else analysis.get("corePapers")
        selected_ids = {str(item.get("recordId") or "") for item in (selected or [])[:30]}
        all_links = list((analysis.get("coCitation") or {}).get("links") or []) + list((analysis.get("coupling") or {}).get("links") or [])
        links = [item for item in all_links if str(item.get("source") or "") in selected_ids or str(item.get("target") or "") in selected_ids][:160]
        edge_type = "STRUCTURAL_SIMILARITY"
    ids = {str(item.get(key) or "") for item in links for key in ("source", "target")}
    if not ids:
        ranked = analysis.get("bridgePapers") if mode_value == "bridge" else analysis.get("corePapers")
        ids = {str(item.get("recordId") or "") for item in (ranked or [])[:30]}
    nodes = [{
        "id": f"paper:{record_id}", "type": "paper", "label": metrics.get(record_id, {}).get("title") or record_id,
        "importance": max(_safe_float(metrics.get(record_id, {}).get("coreScore")), _safe_float(metrics.get(record_id, {}).get("bridgeScore"))),
        "confidence": 1.0, "details": dict(metrics.get(record_id) or {}), "evidence": [],
    } for record_id in sorted(ids) if record_id in metrics]
    node_ids = {str(node["details"].get("recordId") or ""): node["id"] for node in nodes}
    edges = [{
        "id": f"analysis-edge:{index + 1}", "source": node_ids[str(link["source"])], "target": node_ids[str(link["target"])],
        "type": edge_type, "label": edge_type.replace("_", " ").title(), "confidence": _safe_float(link.get("score"), 0.5),
        "details": dict(link), "evidence": [], "direction_reason": "对称结构分析关系，无引文方向。",
    } for index, link in enumerate(links) if str(link.get("source") or "") in node_ids and str(link.get("target") or "") in node_ids]
    if not nodes:
        return {}
    layout = academic_layout(nodes, comparison=True)
    key = f"network_analysis_{mode_value}_{str(analysis.get('cacheKey') or '')[:12]}"
    metadata = {
        "comparison": True, "network_analysis_graph": True, "analysis_mode": mode_value,
        "comparison_record_ids": sorted(node_ids), "source": {"extractionEngine": "network-analysis"},
        "summary": {"keywords": [], "contentSummary": "可解释的馆藏结构分析局部图谱。", "abstract": ""},
        "layout": layout, "adjacency": adjacency_index(edges),
        "quality_summary": {"node_count": len(nodes), "edge_count": len(edges)},
    }
    return {
        "version": 1, "schema_version": 1, "recordId": key, "record_id": key,
        "title": f"结构分析 · {mode_value}", "paper": {"title": f"结构分析 · {mode_value}", "authors": [], "year": "", "source": "network-analysis", "pdf_path": ""},
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source_fingerprint": str(analysis.get("cacheKey") or ""),
        "nodes": nodes, "edges": edges, "metadata": metadata, "layout": layout,
        "adjacency": metadata["adjacency"], "quality_summary": metadata["quality_summary"],
    }
