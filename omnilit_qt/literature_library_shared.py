from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LIBRARY_CACHE_VERSION = 2
LEVEL_ORDER = {"unmatched": -1, "weak": 1, "medium": 2, "strong": 3, "keyword_only": 0, "loose": 1, "balanced": 2, "strict": 3, "very_strict": 4}
SORT_MODES = {"relevance_desc", "relevance_asc", "year_desc", "year_asc", "downloaded_first", "title_asc"}
DEFAULT_FAVORITE_PROJECTS = [
    {"id": "to_read", "name": "待读精读", "built_in": True}, {"id": "core", "name": "核心文献", "built_in": True},
    {"id": "review", "name": "综述与背景", "built_in": True}, {"id": "method", "name": "方法/模型", "built_in": True},
    {"id": "data", "name": "数据集/实验", "built_in": True}, {"id": "writing", "name": "写作引用", "built_in": True},
    {"id": "read_archive", "name": "已读归档", "built_in": True},
]


class LibraryStateConflict(RuntimeError):
    pass


class LibraryStateStore:
    """Versioned cross-process store for collections and the compare workspace."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    @staticmethod
    def default_state() -> dict[str, Any]:
        return {"schema_version": 2, "revision": 0, "updated_at": "", "sync_state": "local_only", "projects": [dict(project) for project in DEFAULT_FAVORITE_PROJECTS], "favorites": {}, "compare": {"active": []}}

    @contextmanager
    def _lock(self, timeout: float = 2.0):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                try:
                    if time.time() - self.lock_path.stat().st_mtime > 30:
                        self.lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("library state is busy")
                time.sleep(0.02)
        try:
            yield
        finally:
            os.close(descriptor)
            self.lock_path.unlink(missing_ok=True)

    def _load_unlocked(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("library state must be an object")
        except FileNotFoundError:
            return self.default_state()
        except (OSError, ValueError, json.JSONDecodeError):
            backup = self.path.with_suffix(self.path.suffix + ".bak")
            if backup.exists():
                backup = self.path.with_suffix(self.path.suffix + f".{int(time.time())}.bak")
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                pass
            state = self.default_state()
            self._save_unlocked(state)
            return state
        return self._normalized_state(state)

    def load(self) -> dict[str, Any]:
        with self._lock():
            state = self._load_unlocked()
            if not self.path.exists():
                self._save_unlocked(state)
            return state

    def _save_unlocked(self, state: dict[str, Any]) -> None:
        normalized = self._normalized_state(state)
        tmp_path = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def save(self, state: dict[str, Any]) -> None:
        with self._lock():
            current = self._load_unlocked()
            candidate = self._normalized_state(dict(state))
            candidate_revision = int(candidate.get("revision") or 0)
            current_revision = int(current.get("revision") or 0)
            if candidate_revision < current_revision or (
                candidate_revision == current_revision and candidate != current
            ):
                raise LibraryStateConflict("library state revision is stale")
            self._save_unlocked(candidate)

    def mutate(self, action: str, *, expected_revision: int | None = None, collection_id: str = "", name: str = "", record_id: str = "") -> tuple[dict[str, Any], bool]:
        with self._lock():
            state = self._load_unlocked()
            revision = int(state.get("revision") or 0)
            if expected_revision is not None and expected_revision != revision:
                raise LibraryStateConflict(f"expected revision {expected_revision}, current revision {revision}")
            changed = self._apply_mutation(state, action, collection_id=collection_id, name=name, record_id=record_id)
            if changed:
                state["revision"] = revision + 1
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                state["sync_state"] = "local_only"
                self._save_unlocked(state)
            return self._normalized_state(state), changed

    @staticmethod
    def _project_id(name: str, existing: set[str]) -> str:
        base = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", name.strip()).strip("_")[:64] or "collection"
        candidate, index = base, 2
        while candidate in existing:
            candidate, index = f"{base}_{index}", index + 1
        return candidate

    def _apply_mutation(self, state: dict[str, Any], action: str, *, collection_id: str, name: str, record_id: str) -> bool:
        projects = state["projects"]
        favorites = state["favorites"]
        compare = state["compare"]["active"]
        project = next((item for item in projects if item["id"] == collection_id), None)
        if action == "create_collection":
            clean = name.strip()[:120]
            if not clean: raise ValueError("collection name is required")
            projects.append({"id": self._project_id(clean, {item["id"] for item in projects}), "name": clean, "built_in": False})
            return True
        if action == "rename_collection":
            if not project: raise KeyError("collection not found")
            clean = name.strip()[:120]
            if not clean: raise ValueError("collection name is required")
            if project["name"] == clean: return False
            project["name"] = clean
            return True
        if action == "delete_collection":
            if not project: raise KeyError("collection not found")
            if project["built_in"]: raise ValueError("built-in collection cannot be deleted")
            state["projects"] = [item for item in projects if item["id"] != collection_id]
            for key in list(favorites):
                favorites[key] = [value for value in favorites[key] if value != collection_id]
                if not favorites[key]: favorites.pop(key)
            return True
        if action == "toggle_collection_record":
            if not project: raise KeyError("collection not found")
            if not record_id: raise ValueError("recordId is required")
            values = list(favorites.get(record_id, []))
            values = [value for value in values if value != collection_id] if collection_id in values else [*values, collection_id]
            if values: favorites[record_id] = values
            else: favorites.pop(record_id, None)
            return True
        if action == "toggle_compare_record":
            if not record_id: raise ValueError("recordId is required")
            if record_id in compare: compare.remove(record_id)
            elif len(compare) < 4: compare.append(record_id)
            else: raise ValueError("compare workspace accepts at most four records")
            return True
        if action == "remove_compare_record":
            if record_id not in compare: return False
            compare.remove(record_id)
            return True
        if action == "clear_compare":
            if not compare: return False
            compare.clear()
            return True
        raise ValueError("unsupported library mutation")

    @classmethod
    def _normalized_state(cls, state: dict[str, Any]) -> dict[str, Any]:
        normalized = cls.default_state()
        try:
            normalized["revision"] = max(0, int(state.get("revision") or 0))
        except (TypeError, ValueError):
            normalized["revision"] = 0
        normalized["updated_at"] = str(state.get("updated_at") or "")
        normalized["sync_state"] = str(state.get("sync_state") or "local_only") if str(state.get("sync_state") or "local_only") in {"local_only", "pending_sync", "synced", "conflict", "deleting"} else "local_only"
        projects = state.get("projects") if isinstance(state.get("projects"), list) else []
        seen = set()
        normalized["projects"] = []
        for project in [*DEFAULT_FAVORITE_PROJECTS, *projects]:
            if not isinstance(project, dict): continue
            project_id, name = str(project.get("id") or "").strip()[:64], str(project.get("name") or "").strip()[:120]
            if not project_id or not name or project_id in seen: continue
            seen.add(project_id)
            normalized["projects"].append({"id": project_id, "name": name, "built_in": bool(project.get("built_in"))})
        valid = {project["id"] for project in normalized["projects"]}
        favorites = state.get("favorites") if isinstance(state.get("favorites"), dict) else {}
        normalized["favorites"] = {str(record_id)[:256]: list(dict.fromkeys(str(value) for value in values if str(value) in valid)) for record_id, values in favorites.items() if isinstance(values, list)}
        normalized["favorites"] = {key: values for key, values in normalized["favorites"].items() if values}
        compare = state.get("compare") if isinstance(state.get("compare"), dict) else {}
        active = compare.get("active") if isinstance(compare.get("active"), list) else []
        normalized["compare"] = {"active": list(dict.fromkeys(str(value)[:256] for value in active if str(value)))[:4]}
        return normalized


def read_library_cache(data_root: Path) -> tuple[bool, list[dict[str, Any]]]:
    path = Path(data_root).resolve() / "cache" / "downloads" / "library_cache.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False, []
    records = payload.get("records") if isinstance(payload, dict) and payload.get("version") == LIBRARY_CACHE_VERSION else None
    return (True, [dict(record) for record in records if isinstance(record, dict)]) if isinstance(records, list) else (False, [])


def record_search_text(record: dict[str, Any]) -> str:
    fields = ("title", "abstract", "contentSummary", "keywordsText", "authorsText", "doi", "normalized_doi", "keyword", "journalTitle", "journalName", "journalTypeLabel")
    return " ".join(str(record.get(name) or "") for name in fields).casefold()


def year_value(record: dict[str, Any]) -> int:
    for value in (record.get("year"), record.get("publication_year"), record.get("publicationDate"), record.get("publication_date")):
        match = re.search(r"(?:19|20)\d{2}", str(value or ""))
        if match:
            return int(match.group(0))
    return 0


def relevance_rank(record: dict[str, Any]) -> int:
    return LEVEL_ORDER.get(str(record.get("relevance_level") or "unmatched"), -1)


def relevance_score(record: dict[str, Any]) -> float:
    try:
        return float(record.get("relevance_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def sort_library_records(records: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    mode = mode if mode in SORT_MODES else "relevance_desc"
    if mode == "relevance_asc":
        return sorted(records, key=lambda item: (relevance_rank(item), relevance_score(item), year_value(item), str(item.get("title") or "").casefold()))
    if mode == "year_desc":
        return sorted(records, key=lambda item: (year_value(item), relevance_rank(item), relevance_score(item), str(item.get("title") or "").casefold()), reverse=True)
    if mode == "year_asc":
        return sorted(records, key=lambda item: (year_value(item) or 9999, str(item.get("title") or "").casefold()))
    if mode == "downloaded_first":
        return sorted(records, key=lambda item: (bool(item.get("localPdfPath")), relevance_rank(item), relevance_score(item), year_value(item)), reverse=True)
    if mode == "title_asc":
        return sorted(records, key=lambda item: str(item.get("title") or "").casefold())
    return sorted(records, key=lambda item: (relevance_rank(item), relevance_score(item), year_value(item), str(item.get("title") or "").casefold()), reverse=True)


def filter_library_records(records: list[dict[str, Any]], *, query: str = "", relevance: str = "all", pdf_status: str = "all", journal_type: str = "all", keyword_groups: set[str] | None = None, sort: str = "relevance_desc", collection_id: str = "all", favorites: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    needle = str(query or "").casefold().strip()[:500]
    floor = LEVEL_ORDER.get(relevance, -999)
    groups = keyword_groups or set()
    result = []
    for record in records:
        if relevance != "all" and relevance_rank(record) < floor:
            continue
        status = str(record.get("pdfStatus") or "")
        if pdf_status != "all" and ((pdf_status == "downloaded" and not record.get("localPdfPath")) or (pdf_status != "downloaded" and status != pdf_status)):
            continue
        if journal_type != "all" and str(record.get("journalType") or "unknown") != journal_type:
            continue
        if groups and not groups.intersection(str(value) for value in record.get("keywordGroupKeys") or []):
            continue
        if collection_id not in {"", "all"} and collection_id not in (favorites or {}).get(str(record.get("recordId") or ""), []):
            continue
        if needle and needle not in str(record.get("_librarySearchText") or record_search_text(record)):
            continue
        result.append(record)
    return sort_library_records(result, sort)


def safe_record_folder(record_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record_id or "record")).strip("._")[:72] or "record"
    return f"{value}_{hashlib.sha1(str(record_id).encode('utf-8')).hexdigest()[:8]}"


def has_extraction(data_root: Path, record_id: str) -> bool:
    path = Path(data_root) / "data" / "literature" / "extractions" / safe_record_folder(record_id) / "extraction_index.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    try:
        page_count = int(payload.get("pageCount") or 0)
    except (TypeError, ValueError):
        return False
    return page_count > 0 and isinstance(payload.get("pages"), list) and bool(payload["pages"])


def project_library_summary(record: dict[str, Any], data_root: Path) -> dict[str, Any]:
    record_id = str(record.get("recordId") or "")
    return {"recordId": record_id, "title": str(record.get("title") or ""), "authorsText": str(record.get("authorsText") or ""), "source": str(record.get("source") or ""), "year": str(record.get("year") or ""), "publicationDate": str(record.get("publicationDate") or ""), "journalTitle": str(record.get("journalTitle") or record.get("journalName") or ""), "journalType": str(record.get("journalType") or "unknown"), "journalTypeLabel": str(record.get("journalTypeLabel") or "未识别"), "impactFactorText": str(record.get("impactFactorText") or "未知"), "keywordsText": str(record.get("keywordsText") or ""), "summaryText": str(record.get("summaryText") or record.get("contentSummary") or ""), "topicTagsText": str(record.get("topicTagsText") or ""), "pdfStatus": str(record.get("pdfStatus") or ""), "relevanceLabel": str(record.get("relevanceLabel") or ""), "relevanceScore": relevance_score(record), "matchedKeywordsText": str(record.get("matchedKeywordsText") or ""), "keywordGroupKeys": [str(value) for value in record.get("keywordGroupKeys") or []], "downloaded": bool(record.get("localPdfPath")), "hasExtraction": has_extraction(data_root, record_id)}


def project_library_detail(record: dict[str, Any], data_root: Path, protocol_version: str = "1.0") -> dict[str, Any]:
    summary = project_library_summary(record, data_root)
    return {"protocolVersion": protocol_version, **summary, "abstract": str(record.get("abstract") or ""), "doi": str(record.get("doi") or record.get("normalized_doi") or ""), "impactFactorSource": str(record.get("impactFactorSource") or ""), "impactFactorMetric": str(record.get("impactFactorMetric") or ""), "impactFactorYear": str(record.get("impactFactorYear") or ""), "impactFactorQuartile": str(record.get("impactFactorQuartile") or ""), "matchedFieldsText": str(record.get("matchedFieldsText") or ""), "relevanceReasonsText": str(record.get("relevanceReasonsText") or "")}


def library_facets(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    def counts(values): return dict(sorted(Counter(str(value) for value in values if str(value)).items()))
    return {"relevance": counts(record.get("relevance_level") or "unmatched" for record in records), "pdfStatus": counts("downloaded" if record.get("localPdfPath") else record.get("pdfStatus") or "unknown" for record in records), "journalType": counts(record.get("journalType") or "unknown" for record in records), "keywordGroups": counts(group for record in records for group in (record.get("keywordGroupKeys") or []))}


def project_library_state(state: dict[str, Any], protocol_version: str = "1.0") -> dict[str, Any]:
    favorites = state.get("favorites") if isinstance(state.get("favorites"), dict) else {}
    counts = Counter(collection_id for values in favorites.values() if isinstance(values, list) for collection_id in values)
    return {
        "protocolVersion": protocol_version,
        "revision": int(state.get("revision") or 0),
        "updatedAt": str(state.get("updated_at") or ""),
        "syncState": str(state.get("sync_state") or "local_only"),
        "collections": [{"id": str(item.get("id") or ""), "name": str(item.get("name") or ""), "builtIn": bool(item.get("built_in")), "recordCount": counts[str(item.get("id") or "")]} for item in state.get("projects") or [] if isinstance(item, dict)],
        "favorites": {str(record_id): [str(value) for value in values] for record_id, values in favorites.items() if isinstance(values, list)},
        "workspace": {"compareRecordIds": [str(value) for value in (state.get("compare") or {}).get("active", [])]},
    }
