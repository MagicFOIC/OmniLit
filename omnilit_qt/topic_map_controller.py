from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot

from .background_tasks import ManagedWorker, shutdown_workers
from .knowledge_graph_builder import build_knowledge_graph
from .knowledge_graph_evolution import build_evolution, build_evolution_graph
from .knowledge_graph_network_analysis import build_network_analysis, build_network_analysis_graph
from .knowledge_graph_research_network import build_research_network, build_research_network_graph
from .knowledge_graph_topics import build_topic_graph, build_topic_map


def _safe_radius(value: Any, count: int, original_size: int, maximum: int) -> float:
    try:
        base = float(value)
    except (TypeError, ValueError):
        base = 0.10
    if not math.isfinite(base):
        base = 0.10
    window_share = math.sqrt(max(0.0, count / max(1, original_size)))
    relative_scale = 0.72 + 0.28 * math.sqrt(max(0.0, count / max(1, maximum)))
    return min(base, base * window_share * relative_scale)


class TopicMapController(QObject):
    changed = Signal()
    topicMapReady = Signal(str)
    _taskFinished = Signal(str, object, str, bool)

    def __init__(self, shell, paths, store, locale) -> None:
        super().__init__()
        self.paths = paths
        self._loading = False
        self._status = ""
        self._state = "idle"
        self._current_key = ""
        self._topic_map: dict[str, Any] = {}
        self._selected_topic: dict[str, Any] = {}
        self._evolution: dict[str, Any] = {}
        self._network_analysis: dict[str, Any] = {}
        self._research_network: dict[str, Any] = {}
        self._evolution_start = 0
        self._evolution_end = 0
        self._evolution_playback_year = 0
        self._selected_evolution_path: dict[str, Any] = {}
        self._source_graphs: list[dict[str, Any]] = []
        self._source_records: list[dict[str, Any]] = []
        self._worker: ManagedWorker | None = None
        self._stop = threading.Event()
        self._taskFinished.connect(self._on_task_finished)

    @staticmethod
    def _safe_id(value: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "record")).strip("._")[:72] or "record"
        return f"{clean}_{hashlib.sha1(str(value).encode('utf-8')).hexdigest()[:8]}"

    @staticmethod
    def _collection_key(records: list[dict[str, Any]]) -> str:
        record_ids = sorted(str(item.get("recordId") or item.get("id") or "") for item in records)
        return hashlib.sha1("\n".join(record_ids).encode("utf-8")).hexdigest()[:16]

    def _content_path(self, *parts: str) -> Path:
        if hasattr(self.paths, "content"):
            return self.paths.content(*parts)
        return self.paths.data(*parts)

    def _runtime_path(self, *parts: str) -> Path:
        if hasattr(self.paths, "runtime"):
            return self.paths.runtime(*parts)
        return self.paths.data(*parts)

    def _graph_path(self, record_id: str) -> Path:
        return self._content_path("literature", "graphs", self._safe_id(record_id), "knowledge_graph.json")

    def _index_path(self, record_id: str) -> Path:
        return self._content_path("literature", "extractions", self._safe_id(record_id), "extraction_index.json")

    def _topic_map_path(self, key: str) -> Path:
        return self._content_path("literature", "graphs", "topic_maps", key, "topic_map.json")

    def _evolution_path(self, key: str) -> Path:
        return self._content_path("literature", "graphs", "topic_maps", key, "evolution.json")

    def _network_analysis_path(self, key: str) -> Path:
        return self._content_path("literature", "graphs", "topic_maps", key, "network_analysis.json")

    def _research_network_path(self, key: str) -> Path:
        return self._content_path("literature", "graphs", "topic_maps", key, "research_network.json")

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(str, notify=changed)
    def currentKey(self) -> str:
        return self._current_key

    @Property("QVariantMap", notify=changed)
    def topicMap(self) -> dict[str, Any]:
        return dict(self._topic_map)

    @Property("QVariantList", notify=changed)
    def topics(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._topic_map.get("topics") or [] if isinstance(item, dict)]

    @Property("QVariantMap", notify=changed)
    def selectedTopic(self) -> dict[str, Any]:
        return dict(self._selected_topic)

    @Property("QVariantMap", notify=changed)
    def evolution(self) -> dict[str, Any]:
        return dict(self._evolution)

    @Property("QVariantMap", notify=changed)
    def networkAnalysis(self) -> dict[str, Any]:
        return dict(self._network_analysis)

    @Property("QVariantMap", notify=changed)
    def researchNetwork(self) -> dict[str, Any]:
        return dict(self._research_network)

    @Property("QVariantList", notify=changed)
    def evolutionYears(self) -> list[int]:
        return [int(item) for item in (self._evolution.get("yearRange") or {}).get("years") or []]

    @Property("QVariantMap", notify=changed)
    def evolutionRange(self) -> dict[str, Any]:
        return {
            "start": self._evolution_start, "end": self._evolution_end,
            "playbackYear": self._evolution_playback_year,
            "minimum": (self._evolution.get("yearRange") or {}).get("minimum", ""),
            "maximum": (self._evolution.get("yearRange") or {}).get("maximum", ""),
        }

    @Property("QVariantList", notify=changed)
    def visibleEvolutionEvents(self) -> list[dict[str, Any]]:
        effective_end = min(self._evolution_end, self._evolution_playback_year) if self._evolution_playback_year else self._evolution_end
        return [
            dict(item) for item in self._evolution.get("events") or []
            if self._evolution_start <= int(item.get("year") or 0) <= effective_end
        ]

    @Property("QVariantList", notify=changed)
    def windowTopicStats(self) -> list[dict[str, Any]]:
        effective_end = min(self._evolution_end, self._evolution_playback_year) if self._evolution_playback_year else self._evolution_end
        result = []
        for series in self._evolution.get("topicSeries") or []:
            points = [item for item in series.get("points") or [] if self._evolution_start <= int(item.get("year") or 0) <= effective_end]
            count = sum(int(item.get("count") or 0) for item in points)
            if count:
                result.append({
                    "topicId": series.get("topicId"), "name": series.get("name"),
                    "colorIndex": series.get("colorIndex", 0), "count": count,
                    "paperIds": [paper_id for point in points for paper_id in point.get("paperIds") or []],
                })
        result.sort(key=lambda item: (-int(item["count"]), str(item.get("name") or "")))
        return result

    @Property("QVariantList", notify=changed)
    def windowTopics(self) -> list[dict[str, Any]]:
        stats = self.windowTopicStats
        total = sum(int(item.get("count") or 0) for item in stats)
        maximum = max((int(item.get("count") or 0) for item in stats), default=1)
        topics = {str(item.get("id") or ""): item for item in self._topic_map.get("topics") or [] if isinstance(item, dict)}
        result = []
        for item in stats:
            topic = dict(topics.get(str(item.get("topicId") or "")) or {})
            if not topic:
                continue
            count = int(item.get("count") or 0)
            original_size = max(1, int(topic.get("size") or 1))
            topic.update({
                "size": count, "share": round(count / max(1, total), 4),
                "paperIds": list(item.get("paperIds") or []),
                "radius": round(max(0.052, _safe_radius(topic.get("radius"), count, original_size, maximum)), 6),
                "windowFiltered": True,
            })
            result.append(topic)
        return result

    @Property("QVariantMap", notify=changed)
    def selectedEvolutionPath(self) -> dict[str, Any]:
        return dict(self._selected_evolution_path)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @Slot("QVariantList", result=bool)
    def generateForRecords(self, records: list) -> bool:
        return self._generate(records, force=False)

    @Slot("QVariantList", result=bool)
    def regenerateForRecords(self, records: list) -> bool:
        return self._generate(records, force=True)

    def _generate(self, records: list, *, force: bool) -> bool:
        payloads = [dict(item) for item in records or [] if isinstance(item, dict) and str(item.get("recordId") or item.get("id") or "")]
        if not payloads:
            self._state = "empty"
            self._status = "当前筛选结果中没有可分析的论文。"
            self._topic_map = {}
            self._selected_topic = {}
            self.changed.emit()
            return False
        if self._loading:
            self._status = "领域主题分析任务正在运行。"
            self.changed.emit()
            return False
        key = self._collection_key(payloads)
        path = self._topic_map_path(key)
        self._loading = True
        self._state = "loading"
        self._current_key = key
        self._status = f"正在分析 {len(payloads)} 篇论文的主题结构..."
        self._stop.clear()
        self.changed.emit()

        def run() -> None:
            try:
                graphs: list[dict[str, Any]] = []
                for record in payloads:
                    if self._stop.is_set():
                        message = "领域主题分析已取消。"
                        task.update_state("cancelled", detail=message)
                        self._taskFinished.emit(key, {}, message, False)
                        return
                    record_id = str(record.get("recordId") or record.get("id") or "")
                    graph = self._read(self._graph_path(record_id))
                    if not graph:
                        graph = build_knowledge_graph(record, self._read(self._index_path(record_id)) or None)
                        try:
                            self._write(self._graph_path(record_id), graph)
                        except OSError:
                            # The in-memory graph remains valid for analysis; a
                            # read-only cache location must not discard results.
                            pass
                    graphs.append(graph)
                generated = build_topic_map(graphs, payloads, f"当前筛选结果（{len(payloads)} 篇）")
                cached = {} if force else self._read(path)
                topic_map = cached if cached and cached.get("cacheKey") == generated.get("cacheKey") else generated
                if topic_map is generated:
                    self._write(path, topic_map)
                generated_evolution = build_evolution(topic_map, graphs, payloads)
                evolution_path = self._evolution_path(key)
                cached_evolution = {} if force else self._read(evolution_path)
                evolution = cached_evolution if cached_evolution and cached_evolution.get("cacheKey") == generated_evolution.get("cacheKey") else generated_evolution
                if evolution is generated_evolution:
                    self._write(evolution_path, evolution)
                generated_analysis = build_network_analysis(topic_map, evolution, graphs, payloads)
                analysis_path = self._network_analysis_path(key)
                cached_analysis = {} if force else self._read(analysis_path)
                network_analysis = cached_analysis if cached_analysis and cached_analysis.get("cacheKey") == generated_analysis.get("cacheKey") else generated_analysis
                if network_analysis is generated_analysis:
                    self._write(analysis_path, network_analysis)
                generated_research = build_research_network(topic_map, evolution, network_analysis, payloads)
                research_path = self._research_network_path(key)
                cached_research = {} if force else self._read(research_path)
                research_network = cached_research if cached_research and cached_research.get("cacheKey") == generated_research.get("cacheKey") else generated_research
                if research_network is generated_research:
                    self._write(research_path, research_network)
                state = "empty" if not topic_map.get("topics") else "ready"
                message = "没有足够语义信息形成主题。" if state == "empty" else f"已识别 {len(topic_map.get('topics') or [])} 个主题，覆盖 {topic_map.get('analyzedPaperCount', 0)} 篇论文。"
                result = {
                    "topicMap": topic_map, "evolution": evolution, "networkAnalysis": network_analysis,
                    "researchNetwork": research_network,
                    "graphs": graphs, "records": payloads, "state": state,
                }
                task.update_state("completed", detail=message)
                self._taskFinished.emit(key, result, message, True)
            except Exception as exc:
                message = f"领域主题分析失败：{exc}"
                task.update_state("failed", detail=message)
                self._taskFinished.emit(key, {}, message, False)

        task = ManagedWorker(
            name="TopicMapBuild", target=run,
            state_path=self._runtime_path("task_state", f"topic_map_{key}.json"),
            cancel_event=self._stop,
            metadata={"record_ids": [str(item.get("recordId") or item.get("id") or "") for item in payloads]},
        )
        self._worker = task
        task.start()
        return True

    def _on_task_finished(self, key: str, payload: object, message: str, success: bool) -> None:
        self._loading = False
        self._status = str(message or "")
        if success and isinstance(payload, dict):
            self._topic_map = dict(payload.get("topicMap") or {})
            self._evolution = dict(payload.get("evolution") or {})
            self._network_analysis = dict(payload.get("networkAnalysis") or {})
            self._research_network = dict(payload.get("researchNetwork") or {})
            self._source_graphs = [dict(item) for item in payload.get("graphs") or [] if isinstance(item, dict)]
            self._source_records = [dict(item) for item in payload.get("records") or [] if isinstance(item, dict)]
            self._state = str(payload.get("state") or ("ready" if self._topic_map.get("topics") else "empty"))
            topics = self._topic_map.get("topics") or []
            self._selected_topic = dict(topics[0]) if topics else {}
            years = self.evolutionYears
            self._evolution_start = years[0] if years else 0
            self._evolution_end = years[-1] if years else 0
            self._evolution_playback_year = self._evolution_end
            paths = self._evolution.get("keyPaths") or []
            self._selected_evolution_path = dict(paths[0]) if paths else {}
            self.topicMapReady.emit(key)
        else:
            self._state = "idle" if self._stop.is_set() else "error"
        self.changed.emit()

    @Slot(str, result=bool)
    def selectTopic(self, topic_id: str) -> bool:
        topic = next((item for item in self._topic_map.get("topics") or [] if str(item.get("id") or "") == str(topic_id or "")), None)
        self._selected_topic = dict(topic or {})
        if topic is None:
            self._status = "未找到所选主题。"
        self.changed.emit()
        return topic is not None

    @Slot(str, result="QVariantMap")
    @Slot(str, "QVariantList", result="QVariantMap")
    def topicGraph(self, topic_id: str, paper_ids: list | None = None) -> dict[str, Any]:
        selected_ids = [str(item) for item in paper_ids or []] if paper_ids is not None else None
        graph = build_topic_graph(self._topic_map, topic_id, self._source_graphs, self._source_records, selected_ids)
        if not graph:
            self._status = "无法生成所选主题的局部图谱。"
            self.changed.emit()
        return graph

    @Slot(int, int, result=bool)
    def setEvolutionRange(self, start_year: int, end_year: int) -> bool:
        years = self.evolutionYears
        if not years:
            self._status = "当前集合没有可用年份。"
            self.changed.emit()
            return False
        start = max(years[0], min(years[-1], int(start_year)))
        end = max(years[0], min(years[-1], int(end_year)))
        if start > end:
            start, end = end, start
        self._evolution_start = start
        self._evolution_end = end
        self._evolution_playback_year = end
        self._status = f"时间范围已设置为 {start}–{end}。"
        self.changed.emit()
        return True

    @Slot(result=bool)
    def resetEvolutionRange(self) -> bool:
        years = self.evolutionYears
        if not years:
            return False
        return self.setEvolutionRange(years[0], years[-1])

    @Slot(result=bool)
    def startEvolutionPlayback(self) -> bool:
        if not self.evolutionYears or not self._evolution_start:
            return False
        self._evolution_playback_year = self._evolution_start
        self._status = f"演化播放从 {self._evolution_start} 年开始。"
        self.changed.emit()
        return True

    @Slot(result=bool)
    def advanceEvolutionPlayback(self) -> bool:
        candidates = [year for year in self.evolutionYears if self._evolution_start <= year <= self._evolution_end and year > self._evolution_playback_year]
        if not candidates:
            return False
        self._evolution_playback_year = candidates[0]
        self._status = f"演化播放：{self._evolution_playback_year} 年。"
        self.changed.emit()
        return True

    @Slot(int, result=bool)
    def setEvolutionPlaybackYear(self, year: int) -> bool:
        candidates = [value for value in self.evolutionYears if self._evolution_start <= value <= self._evolution_end]
        if not candidates:
            return False
        selected = min(candidates, key=lambda value: (abs(value - int(year)), value))
        self._evolution_playback_year = selected
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def selectEvolutionPath(self, path_id: str) -> bool:
        path = next((item for item in self._evolution.get("keyPaths") or [] if str(item.get("id") or "") == str(path_id or "")), None)
        self._selected_evolution_path = dict(path or {})
        self.changed.emit()
        return path is not None

    @Slot(result="QVariantMap")
    @Slot(int, int, result="QVariantMap")
    def evolutionGraph(self, start_year: int = 0, end_year: int = 0) -> dict[str, Any]:
        start = int(start_year or self._evolution_start)
        end = int(end_year or min(self._evolution_end, self._evolution_playback_year or self._evolution_end))
        graph = build_evolution_graph(self._evolution, self._topic_map, self._source_graphs, self._source_records, start, end)
        if not graph:
            self._status = "当前时间窗口没有可生成图谱的论文。"
            self.changed.emit()
        return graph

    @Slot(str, result="QVariantMap")
    def networkAnalysisGraph(self, mode: str) -> dict[str, Any]:
        graph = build_network_analysis_graph(self._network_analysis, mode)
        if not graph:
            self._status = "当前结构分析没有可生成图谱的论文或关系。"
            self.changed.emit()
        return graph

    @Slot(str, result="QVariantMap")
    def researchNetworkGraph(self, mode: str) -> dict[str, Any]:
        graph = build_research_network_graph(self._research_network, mode)
        if not graph:
            self._status = "当前集合缺少可生成合作网络的作者或机构元数据。"
            self.changed.emit()
        return graph

    @Slot(result=bool)
    def clear(self) -> bool:
        if self._loading:
            return False
        self._topic_map = {}
        self._selected_topic = {}
        self._evolution = {}
        self._network_analysis = {}
        self._research_network = {}
        self._evolution_start = 0
        self._evolution_end = 0
        self._evolution_playback_year = 0
        self._selected_evolution_path = {}
        self._source_graphs = []
        self._source_records = []
        self._state = "idle"
        self._status = ""
        self.changed.emit()
        return True

    @Slot(result=bool)
    def cancel(self) -> bool:
        if not self._loading:
            return False
        self._stop.set()
        self._status = "正在取消领域主题分析..."
        self.changed.emit()
        return True

    @Slot(result=bool)
    def shutdown(self, timeout: float = 15.0) -> bool:
        self._stop.set()
        return shutdown_workers([self._worker], timeout=timeout)
