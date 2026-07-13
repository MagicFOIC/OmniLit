from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .knowledge_graph_layout import academic_layout, adjacency_index


EVOLUTION_VERSION = 2
MAX_KEY_PATHS = 6


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _year(value: Any) -> int | None:
    import re
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    if not match:
        return None
    result = int(match.group(0))
    return result if 1900 <= result <= 2100 else None


def _record_id(graph: dict[str, Any], record: dict[str, Any] | None = None) -> str:
    record = dict(record or {})
    return str(record.get("recordId") or record.get("id") or graph.get("recordId") or graph.get("record_id") or "")


def _paper_data(graph: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = dict(record or {})
    graph_paper = dict(graph.get("paper") or {})
    paper_node = next((node for node in graph.get("nodes") or [] if isinstance(node, dict) and str(node.get("type") or "").casefold() == "paper"), {})
    details = dict(paper_node.get("details") or {})
    record_id = _record_id(graph, record)
    return {
        "recordId": record_id,
        "nodeId": str(paper_node.get("id") or f"paper:{record_id}"),
        "title": str(record.get("title") or graph_paper.get("title") or paper_node.get("label") or graph.get("title") or record_id),
        "year": _year(record.get("year") or record.get("publicationYear") or record.get("publicationDate") or graph_paper.get("year") or details.get("year")),
        "authors": record.get("authors") or record.get("authorsText") or graph_paper.get("authors") or details.get("authors") or [],
        "importance": _safe_float(paper_node.get("importance", record.get("relevance_score", 0.5)), 0.5),
        "confidence": _safe_float(paper_node.get("confidence", 1.0), 1.0),
        "evidence": [item for item in paper_node.get("evidence") or [] if isinstance(item, dict)],
        "node": paper_node,
    }


def _topic_lookup(topic_map: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    topics = {str(item.get("id") or ""): item for item in topic_map.get("topics") or [] if isinstance(item, dict)}
    assignments = {str(item.get("recordId") or ""): item for item in topic_map.get("assignments") or [] if isinstance(item, dict)}
    return topics, assignments


def _key_paths(
    papers: dict[str, dict[str, Any]], links: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    influence_edges: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    link_by_influence: dict[tuple[str, str], dict[str, Any]] = {}
    for link in links:
        if link.get("directionStatus") != "valid":
            continue
        # CITES points newer -> older. Evolution/influence moves older -> newer.
        parent = str(link.get("target") or "")
        child = str(link.get("source") or "")
        influence_edges[child].append((parent, link))
        link_by_influence[(parent, child)] = link
    by_year: dict[int, list[str]] = defaultdict(list)
    for record_id, paper in papers.items():
        if paper.get("year"):
            by_year[int(paper["year"])].append(record_id)
    ordered: list[str] = []
    for year_value in sorted(by_year):
        members = sorted(by_year[year_value])
        member_set = set(members)
        local_children: dict[str, list[str]] = defaultdict(list)
        indegree = {record_id: 0 for record_id in members}
        for child in members:
            for parent, _ in influence_edges.get(child, []):
                if parent in member_set:
                    local_children[parent].append(child)
                    indegree[child] += 1
        queue = sorted(record_id for record_id in members if indegree[record_id] == 0)
        heapq.heapify(queue)
        local_order: list[str] = []
        while queue:
            record_id = heapq.heappop(queue)
            local_order.append(record_id)
            for child in sorted(local_children.get(record_id, [])):
                indegree[child] -= 1
                if indegree[child] == 0:
                    heapq.heappush(queue, child)
        # Mutual/cyclic same-year citations cannot define a causal order. Keep
        # deterministic nodes but later ignore only the back-edges in the cycle.
        ordered_set = set(local_order)
        local_order.extend(record_id for record_id in members if record_id not in ordered_set)
        ordered.extend(local_order)
    best_score: dict[str, float] = {}
    path_length: dict[str, int] = {}
    predecessor: dict[str, str] = {}
    used_parents: set[str] = set()
    cycle_break_count = 0
    for record_id in ordered:
        base = 1.0 + papers[record_id]["keyScore"] * 0.35
        candidates = []
        for parent, _ in influence_edges.get(record_id, []):
            if parent not in best_score:
                cycle_break_count += 1
                continue
            year_span = max(0, int(papers[record_id]["year"]) - int(papers[parent]["year"]))
            candidates.append((
                best_score.get(parent, 1.0) + base + min(0.6, year_span * 0.04),
                path_length.get(parent, 1) + 1,
                parent,
            ))
        if candidates:
            score, length, parent = max(candidates, key=lambda item: (item[0], item[1], item[2]))
            best_score[record_id] = score
            path_length[record_id] = length
            predecessor[record_id] = parent
            used_parents.update(parent_id for parent_id, _ in influence_edges.get(record_id, []) if parent_id in best_score)
        else:
            best_score[record_id] = base
            path_length[record_id] = 1
    terminal_ids = [record_id for record_id in ordered if path_length[record_id] >= 2 and record_id not in used_parents]
    ranked = sorted(
        ((best_score[record_id], path_length[record_id], record_id) for record_id in terminal_ids),
        key=lambda item: (-item[0], -item[1], item[2]),
    )
    selected: list[dict[str, Any]] = []
    for score, _, endpoint in ranked:
        path = [endpoint]
        while path[-1] in predecessor:
            path.append(predecessor[path[-1]])
        path.reverse()
        path_set = set(path)
        if any(len(path_set & set(item["paperIds"])) / max(1, len(path_set | set(item["paperIds"]))) > 0.72 for item in selected):
            continue
        edges = []
        for left, right in zip(path, path[1:]):
            link = link_by_influence.get((left, right), {})
            edges.append({
                "from": left, "to": right,
                "citationSource": link.get("source", right), "citationTarget": link.get("target", left),
                "explanation": f"{papers[right]['title']} 引用了 {papers[left]['title']}，演化方向按被引论文到引用论文展示。",
            })
        years = [int(papers[item]["year"]) for item in path]
        digest = hashlib.sha1("\n".join(path).encode("utf-8")).hexdigest()[:12]
        display_path = path if len(path) <= 18 else path[:9] + path[-9:]
        selected.append({
            "id": f"citation-path:{digest}",
            "label": f"{papers[path[0]]['title']} → {papers[path[-1]]['title']}",
            "paperIds": path, "years": years, "edges": edges,
            "displayPaperIds": display_path, "displayTruncated": len(display_path) < len(path),
            "score": round(score, 4), "length": len(path), "yearSpan": max(years) - min(years),
            "explanation": "仅使用馆藏元数据中的真实有向引文；路径方向表示知识影响从被引论文传播到后续引用论文。",
        })
        if len(selected) >= MAX_KEY_PATHS:
            break
    return selected, cycle_break_count


def build_evolution(
    topic_map: dict[str, Any], graphs: list[dict[str, Any]], records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    record_values = {str(item.get("recordId") or item.get("id") or ""): dict(item) for item in records or [] if isinstance(item, dict)}
    topics, assignments = _topic_lookup(topic_map)
    paper_by_id: dict[str, dict[str, Any]] = {}
    graph_by_id: dict[str, dict[str, Any]] = {}
    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        record_id = _record_id(graph, record_values.get(_record_id(graph)))
        if not record_id:
            continue
        paper = _paper_data(graph, record_values.get(record_id))
        assignment = assignments.get(record_id, {})
        topic_id = str(assignment.get("topicId") or "")
        paper.update({
            "topicId": topic_id,
            "topicName": str((topics.get(topic_id) or {}).get("name") or "待归类"),
            "assignmentScore": _safe_float(assignment.get("score"), 0.0),
        })
        paper_by_id[record_id] = paper
        graph_by_id[record_id] = graph
    cited_by: Counter[str] = Counter()
    references: Counter[str] = Counter()
    raw_links = [item for item in topic_map.get("citationLinks") or [] if isinstance(item, dict)]
    links: list[dict[str, Any]] = []
    chronology_conflicts = 0
    missing_direction_years = 0
    for item in raw_links:
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        if source not in paper_by_id or target not in paper_by_id or source == target:
            continue
        source_year = paper_by_id[source].get("year")
        target_year = paper_by_id[target].get("year")
        if source_year is None or target_year is None:
            status = "unknown_year"
            missing_direction_years += 1
        elif int(target_year) > int(source_year):
            status = "chronology_conflict"
            chronology_conflicts += 1
        else:
            status = "valid"
        cited_by[target] += 1
        references[source] += 1
        links.append({
            "source": source, "target": target,
            "sourceYear": source_year or "", "targetYear": target_year or "",
            "sourceTopicId": paper_by_id[source].get("topicId", ""), "targetTopicId": paper_by_id[target].get("topicId", ""),
            "crossTopic": paper_by_id[source].get("topicId") != paper_by_id[target].get("topicId"),
            "directionStatus": status, "sourceKind": str(item.get("sourceKind") or "collection_metadata"),
            "explanation": "引用论文指向被引论文；时间演化视图会反向展示知识影响方向。",
        })
    max_cited = max(cited_by.values(), default=1)
    representative_ids = {
        str(item.get("recordId") or "")
        for topic in topics.values() for item in topic.get("representativePapers") or [] if isinstance(item, dict)
    }
    papers: list[dict[str, Any]] = []
    for record_id, paper in paper_by_id.items():
        citation_score = cited_by[record_id] / max(1, max_cited)
        representative_bonus = 0.18 if record_id in representative_ids else 0.0
        key_score = min(1.0, citation_score * 0.52 + paper["assignmentScore"] * 0.25 + paper["importance"] * 0.15 + representative_bonus)
        paper.update({
            "citedByCount": cited_by[record_id], "referenceCount": references[record_id],
            "keyScore": round(key_score, 4), "representative": record_id in representative_ids,
            "reasons": [
                f"馆藏内被引 {cited_by[record_id]} 次",
                f"主题匹配 {paper['assignmentScore']:.2f}",
                "主题代表论文" if record_id in representative_ids else "非主题代表论文",
            ],
        })
        papers.append({key: value for key, value in paper.items() if key not in {"node", "evidence"}})
    paper_by_id = {item["recordId"]: {**paper_by_id[item["recordId"]], **item} for item in papers}
    known_years = sorted({int(item["year"]) for item in papers if item.get("year")})
    topic_series = []
    for topic_id, topic in sorted(topics.items(), key=lambda pair: (-int(pair[1].get("size") or 0), pair[0])):
        member_ids = [record_id for record_id in topic.get("paperIds") or [] if record_id in paper_by_id and paper_by_id[record_id].get("year")]
        year_counts = Counter(int(paper_by_id[record_id]["year"]) for record_id in member_ids)
        cumulative = 0
        points = []
        for year_value in known_years:
            new_ids = sorted(record_id for record_id in member_ids if int(paper_by_id[record_id]["year"]) == year_value)
            cumulative += len(new_ids)
            representative = max(new_ids, key=lambda record_id: (paper_by_id[record_id]["keyScore"], record_id)) if new_ids else ""
            points.append({
                "year": year_value, "count": len(new_ids), "cumulative": cumulative, "paperIds": new_ids,
                "representativePaper": ({
                    "recordId": representative, "title": paper_by_id[representative]["title"],
                    "keyScore": paper_by_id[representative]["keyScore"],
                    "reason": "该主题该年度关键分最高的论文（被引、主题匹配和重要性综合）。",
                } if representative else {}),
            })
        peak = max(points, key=lambda point: (point["count"], -point["year"])) if points else {}
        first_year = min(year_counts) if year_counts else ""
        last_year = max(year_counts) if year_counts else ""
        year_span = max(1, int(last_year) - int(first_year) + 1) if first_year and last_year else 1
        growth_speed = len(member_ids) / year_span
        topic_series.append({
            "topicId": topic_id, "name": topic.get("name"), "colorIndex": topic.get("colorIndex", 0),
            "firstYear": first_year, "lastYear": last_year,
            "peakYear": peak.get("year", ""), "peakCount": peak.get("count", 0), "points": points,
            "paperCount": len(member_ids), "growthSpeed": round(growth_speed, 4),
            "growthExplanation": f"{len(member_ids)} 篇 / {year_span} 个覆盖年份 = {growth_speed:.2f} 篇/年。",
        })
    key_paths, same_year_cycle_breaks = _key_paths(paper_by_id, links)
    turning_points: list[dict[str, Any]] = []
    for series in topic_series:
        if series["firstYear"]:
            first_ids = next((point["paperIds"] for point in series["points"] if point["year"] == series["firstYear"]), [])
            turning_points.append({
                "year": series["firstYear"], "type": "topic_emergence", "score": 0.7,
                "title": f"主题出现：{series['name']}", "explanation": "该年出现当前馆藏中此主题最早的论文。",
                "paperIds": first_ids, "topicIds": [series["topicId"]],
            })
        if series["peakCount"] >= 2:
            peak_ids = next((point["paperIds"] for point in series["points"] if point["year"] == series["peakYear"]), [])
            turning_points.append({
                "year": series["peakYear"], "type": "topic_expansion", "score": min(1.0, 0.5 + series["peakCount"] * 0.08),
                "title": f"主题扩张：{series['name']}", "explanation": f"该年新增 {series['peakCount']} 篇，是此主题的馆藏峰值。",
                "paperIds": peak_ids, "topicIds": [series["topicId"]],
            })
    cross_links = [link for link in links if link["crossTopic"] and link["directionStatus"] == "valid"]
    for link in sorted(cross_links, key=lambda item: (item["sourceYear"], item["source"], item["target"]))[:12]:
        turning_points.append({
            "year": link["sourceYear"], "type": "cross_topic_bridge", "score": 0.82,
            "title": "跨主题引文桥接", "explanation": f"{paper_by_id[link['source']]['title']} 引用了另一主题的 {paper_by_id[link['target']]['title']}。",
            "paperIds": [link["target"], link["source"]],
            "topicIds": [link["targetTopicId"], link["sourceTopicId"]],
        })
    global_max_year = max(known_years) if known_years else 0
    for series in topic_series:
        if not series["lastYear"] or int(series["lastYear"]) >= global_max_year - 1:
            continue
        last_point = next((point for point in reversed(series["points"]) if point["count"]), {})
        turning_points.append({
            "year": global_max_year, "type": "topic_decline", "score": 0.72,
            "title": f"主题衰退信号：{series['name']}",
            "explanation": f"该主题最近论文停留在 {series['lastYear']} 年，而当前馆藏时间线已到 {global_max_year} 年；这是馆藏覆盖下的衰退信号，不代表领域全局结论。",
            "paperIds": list(last_point.get("paperIds") or []), "topicIds": [series["topicId"]],
        })
    split_groups: dict[tuple[str, int], dict[str, Any]] = defaultdict(lambda: {"children": set(), "papers": set()})
    merge_groups: dict[tuple[str, int], dict[str, Any]] = defaultdict(lambda: {"parents": set(), "papers": set()})
    for link in cross_links:
        year_value = int(link["sourceYear"])
        split = split_groups[(str(link["targetTopicId"]), year_value)]
        split["children"].add(str(link["sourceTopicId"])); split["papers"].update((link["target"], link["source"]))
        merge = merge_groups[(str(link["sourceTopicId"]), year_value)]
        merge["parents"].add(str(link["targetTopicId"])); merge["papers"].update((link["target"], link["source"]))
    for (parent_id, year_value), signal in sorted(split_groups.items()):
        children = sorted(item for item in signal["children"] if item)
        if parent_id and len(children) >= 2:
            turning_points.append({
                "year": year_value, "type": "topic_split_signal", "score": 0.78,
                "title": f"主题分裂信号：{(topics.get(parent_id) or {}).get('name') or parent_id}",
                "explanation": f"同年有 {len(children)} 个不同主题通过真实引文继承该主题；这是引文流分化信号，并非自动断言学科已正式分裂。",
                "paperIds": sorted(signal["papers"]), "topicIds": [parent_id, *children],
            })
    for (child_id, year_value), signal in sorted(merge_groups.items()):
        parents = sorted(item for item in signal["parents"] if item)
        if child_id and len(parents) >= 2:
            turning_points.append({
                "year": year_value, "type": "topic_merge_signal", "score": 0.8,
                "title": f"主题合并信号：{(topics.get(child_id) or {}).get('name') or child_id}",
                "explanation": f"该主题在同年通过真实引文汇聚了 {len(parents)} 个不同主题；这是知识汇流信号，并非自动断言主题已完全合并。",
                "paperIds": sorted(signal["papers"]), "topicIds": [*parents, child_id],
            })
    turning_points.sort(key=lambda item: (int(item["year"]), -_safe_float(item.get("score"), 0.0), item["title"]))
    events = []
    cumulative_by_topic: Counter[str] = Counter()
    for year_value in known_years:
        year_papers = sorted((paper for paper in papers if paper.get("year") == year_value), key=lambda paper: (-paper["keyScore"], paper["recordId"]))
        topic_counts: Counter[str] = Counter(str(paper.get("topicId") or "") for paper in year_papers)
        topic_events = []
        for topic_id, count in sorted(topic_counts.items(), key=lambda pair: (-pair[1], pair[0])):
            cumulative_by_topic[topic_id] += count
            topic_events.append({
                "topicId": topic_id, "name": str((topics.get(topic_id) or {}).get("name") or "待归类"),
                "newCount": count, "cumulative": cumulative_by_topic[topic_id],
                "paperIds": [paper["recordId"] for paper in year_papers if str(paper.get("topicId") or "") == topic_id],
                "representativePaper": max(
                    (paper for paper in year_papers if str(paper.get("topicId") or "") == topic_id),
                    key=lambda paper: (paper["keyScore"], paper["recordId"]), default={},
                ),
            })
        events.append({
            "year": year_value, "papers": year_papers, "topics": topic_events,
            "citations": [link for link in links if link.get("sourceYear") == year_value],
            "turningPoints": [item for item in turning_points if item.get("year") == year_value],
        })
    cache_payload = json.dumps({
        "version": EVOLUTION_VERSION, "topicMap": topic_map.get("cacheKey"),
        "papers": [(item["recordId"], item.get("year"), item.get("topicId")) for item in sorted(papers, key=lambda paper: paper["recordId"])],
        "citations": [(item["source"], item["target"]) for item in links],
    }, ensure_ascii=False, sort_keys=True)
    topic_speed_comparisons = []
    for index, left in enumerate(topic_series):
        for right in topic_series[index + 1:]:
            difference = _safe_float(left.get("growthSpeed")) - _safe_float(right.get("growthSpeed"))
            faster = left if difference >= 0 else right
            topic_speed_comparisons.append({
                "leftTopicId": left["topicId"], "rightTopicId": right["topicId"],
                "leftSpeed": left["growthSpeed"], "rightSpeed": right["growthSpeed"],
                "fasterTopicId": faster["topicId"], "difference": round(abs(difference), 4),
                "explanation": f"{left['name']} {left['growthSpeed']:.2f} 篇/年；{right['name']} {right['growthSpeed']:.2f} 篇/年。按馆藏覆盖年份内的平均新增速度比较。",
            })
    return {
        "version": EVOLUTION_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cacheKey": hashlib.sha256(cache_payload.encode("utf-8")).hexdigest(),
        "papers": sorted(papers, key=lambda paper: (paper.get("year") or 9999, -paper["keyScore"], paper["recordId"])),
        "events": events, "topicSeries": topic_series, "citationLinks": links,
        "keyPaths": key_paths, "turningPoints": turning_points,
        "topicSpeedComparisons": topic_speed_comparisons,
        "yearRange": {
            "minimum": min(known_years) if known_years else "", "maximum": max(known_years) if known_years else "",
            "years": known_years, "knownYearCount": sum(bool(item.get("year")) for item in papers),
            "missingYearCount": sum(not item.get("year") for item in papers),
        },
        "diagnostics": {
            "paperCount": len(papers), "citationCount": len(links),
            "validCitationCount": sum(item["directionStatus"] == "valid" for item in links),
            "chronologyConflictCount": chronology_conflicts,
            "unknownCitationYearCount": missing_direction_years,
            "sameYearCycleBreakCount": same_year_cycle_breaks,
            "splitSignalCount": sum(item["type"] == "topic_split_signal" for item in turning_points),
            "mergeSignalCount": sum(item["type"] == "topic_merge_signal" for item in turning_points),
            "declineSignalCount": sum(item["type"] == "topic_decline" for item in turning_points),
            "keyPathCount": len(key_paths), "method": "directed_collection_citation_dag_v1",
        },
    }


def build_evolution_graph(
    evolution: dict[str, Any], topic_map: dict[str, Any], graphs: list[dict[str, Any]],
    records: list[dict[str, Any]] | None, start_year: int, end_year: int,
) -> dict[str, Any]:
    start = int(start_year)
    end = int(end_year)
    if start > end:
        start, end = end, start
    included_papers = [paper for paper in evolution.get("papers") or [] if paper.get("year") and start <= int(paper["year"]) <= end]
    if not included_papers:
        return {}
    included_ids = {str(item["recordId"]) for item in included_papers}
    graph_by_id = {_record_id(graph): graph for graph in graphs if isinstance(graph, dict)}
    nodes: list[dict[str, Any]] = []
    paper_node_ids: dict[str, str] = {}
    for paper in included_papers:
        record_id = str(paper["recordId"])
        original = next((node for node in graph_by_id.get(record_id, {}).get("nodes") or [] if isinstance(node, dict) and str(node.get("type") or "").casefold() == "paper"), {})
        node = dict(original or {})
        node_id = str(node.get("id") or f"paper:{record_id}")
        paper_node_ids[record_id] = node_id
        node.update({
            "id": node_id, "type": "paper", "label": paper.get("title") or record_id,
            "importance": max(_safe_float(node.get("importance"), 0.5), _safe_float(paper.get("keyScore"), 0.0)),
            "confidence": _safe_float(node.get("confidence"), 1.0),
            "details": {**dict(node.get("details") or {}), "recordId": record_id, "year": paper.get("year"), "topicId": paper.get("topicId"), "keyScore": paper.get("keyScore")},
        })
        nodes.append(node)
    topics = {str(item.get("id") or ""): item for item in topic_map.get("topics") or [] if isinstance(item, dict)}
    topic_ids = sorted({str(paper.get("topicId") or "") for paper in included_papers if paper.get("topicId")})
    topic_node_ids = {}
    for topic_id in topic_ids:
        topic = topics.get(topic_id, {})
        node_id = f"evolution-topic:{hashlib.sha1(topic_id.encode('utf-8')).hexdigest()[:12]}"
        topic_node_ids[topic_id] = node_id
        nodes.append({
            "id": node_id, "type": "topic", "label": topic.get("name") or "待归类主题",
            "summary": f"{start}–{end} 时间窗口中的主题聚合节点。", "importance": 0.92,
            "confidence": max(0.4, _safe_float(topic.get("cohesion"), 0.5)), "tags": ["topic", "evolution"],
            "evidence": [], "details": {"topicId": topic_id, "timeStart": start, "timeEnd": end},
        })
    edges: list[dict[str, Any]] = []
    for paper in included_papers:
        topic_id = str(paper.get("topicId") or "")
        if topic_id not in topic_node_ids:
            continue
        edges.append({
            "id": f"evolution-edge:{len(edges) + 1}", "source": paper_node_ids[str(paper["recordId"])], "target": topic_node_ids[topic_id],
            "type": "HAS_TOPIC", "label": "研究主题", "confidence": _safe_float(paper.get("assignmentScore"), 0.0),
            "evidence": [], "direction_reason": "主题聚类归属",
        })
    for link in evolution.get("citationLinks") or []:
        source = str(link.get("source") or "")
        target = str(link.get("target") or "")
        if source not in included_ids or target not in included_ids:
            continue
        edges.append({
            "id": f"evolution-edge:{len(edges) + 1}", "source": paper_node_ids[source], "target": paper_node_ids[target],
            "type": "CITES", "label": "馆藏内引文", "confidence": 1.0,
            "evidence": [], "details": {"directionStatus": link.get("directionStatus"), "crossTopic": link.get("crossTopic")},
            "direction_reason": "馆藏元数据中的原始引用论文到被引论文方向",
        })
    layout = academic_layout(nodes, comparison=True)
    key = f"evolution_{start}_{end}_{hashlib.sha1(str(evolution.get('cacheKey') or '').encode('utf-8')).hexdigest()[:10]}"
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = {
        "comparison": True, "evolution_graph": True, "time_start": start, "time_end": end,
        "comparison_record_ids": sorted(included_ids), "builder_version": EVOLUTION_VERSION,
        "source": {"pdfPath": "", "extractionEngine": "evolution", "sourceSha256": evolution.get("cacheKey", "")},
        "summary": {"keywords": [topics[item].get("name") for item in topic_ids if item in topics], "contentSummary": "按年份与真实馆藏引文构建的时间窗口图谱", "abstract": ""},
        "layout": layout, "adjacency": adjacency_index(edges),
        "quality_summary": {
            "node_count": len(nodes), "edge_count": len(edges),
            "known_year_count": len(included_papers), "citation_count": sum(edge["type"] == "CITES" for edge in edges),
        },
    }
    return {
        "version": 1, "schema_version": 1, "recordId": key, "record_id": key,
        "title": f"研究演化 {start}–{end}", "paper": {"title": f"研究演化 {start}–{end}", "authors": [], "year": "", "source": "evolution", "pdf_path": ""},
        "generatedAt": generated, "generated_at": generated, "source_fingerprint": str(evolution.get("cacheKey") or ""),
        "nodes": nodes, "edges": edges, "metadata": metadata,
        "layout": layout, "adjacency": metadata["adjacency"], "quality_summary": metadata["quality_summary"],
    }
