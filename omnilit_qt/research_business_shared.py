from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .literature_library_shared import project_library_detail, project_library_state, year_value
from .shared_protocol import PROTOCOL_VERSION


COMPARE_LIMIT = 4
SETTINGS_FIELDS = {
    "themeMode", "density", "reduceMotion", "highContrast", "startPage", "defaultLibrarySort",
    "aiEvidenceLimit", "aiEndpoint", "aiModel", "allowRemoteResearchContent",
}
DEFAULT_BUSINESS_SETTINGS: dict[str, Any] = {
    "revision": 0,
    "themeMode": "system",
    "density": "comfortable",
    "reduceMotion": False,
    "highContrast": False,
    "startPage": "graph",
    "defaultLibrarySort": "relevance_desc",
    "aiEvidenceLimit": 4,
    "aiEndpoint": "",
    "aiModel": "",
    "allowRemoteResearchContent": False,
    "updatedAt": "",
}


class BusinessSettingsConflict(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _workspace_record(record: dict[str, Any], data_root: Path, collection_ids: list[str]) -> dict[str, Any]:
    detail = project_library_detail(record, data_root, PROTOCOL_VERSION)
    return {
        "recordId": detail["recordId"],
        "title": detail["title"],
        "authorsText": detail["authorsText"],
        "year": detail["year"],
        "journalTitle": detail["journalTitle"],
        "source": detail["source"],
        "abstract": detail["abstract"] or detail["summaryText"],
        "keywordsText": detail["keywordsText"],
        "pdfStatus": detail["pdfStatus"],
        "downloaded": detail["downloaded"],
        "hasExtraction": detail["hasExtraction"],
        "collectionIds": collection_ids[:100],
    }


def project_research_workspace(data_root: Path, cache_available: bool, records: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    projected_state = project_library_state(state, PROTOCOL_VERSION)
    selected_ids = projected_state["workspace"]["compareRecordIds"][:COMPARE_LIMIT]
    if not cache_available:
        return {"protocolVersion": PROTOCOL_VERSION, "status": "unavailable", "records": [], "compareLimit": COMPARE_LIMIT, "message": "Desktop literature cache is unavailable."}
    by_id = {str(record.get("recordId") or ""): record for record in records}
    selected = [
        _workspace_record(by_id[record_id], data_root, list(projected_state["favorites"].get(record_id, [])))
        for record_id in selected_ids if record_id in by_id
    ]
    missing = len(selected_ids) - len(selected)
    if not selected:
        message = "Add up to four papers from the library to start a comparison."
        if missing:
            message = "The selected comparison papers are no longer present in the local library cache."
        return {"protocolVersion": PROTOCOL_VERSION, "status": "empty", "records": [], "compareLimit": COMPARE_LIMIT, "message": message}
    message = f"{missing} selected paper(s) are unavailable." if missing else ""
    return {"protocolVersion": PROTOCOL_VERSION, "status": "ready", "records": selected, "compareLimit": COMPARE_LIMIT, "message": message}


def _buckets(values: list[str], *, limit: int = 0, descending_key: bool = False) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value)
    if descending_key:
        items = sorted(counts.items(), key=lambda item: item[0], reverse=True)
    else:
        items = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    if limit:
        items = items[:limit]
    return [{"key": key, "label": key, "count": count} for key, count in items]


def project_research_statistics(cache_available: bool, records: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    projected_state = project_library_state(state, PROTOCOL_VERSION)
    if not cache_available:
        return {
            "protocolVersion": PROTOCOL_VERSION, "status": "unavailable", "totalRecords": 0,
            "downloadedRecords": 0, "extractedRecords": 0, "compareRecords": len(projected_state["workspace"]["compareRecordIds"]),
            "yearBuckets": [], "sourceBuckets": [], "pdfStatusBuckets": [], "topKeywords": [], "collectionBuckets": [],
            "message": "Desktop literature cache is unavailable.",
        }
    downloaded = sum(1 for record in records if record.get("localPdfPath"))
    extracted = sum(1 for record in records if record.get("hasExtraction") or record.get("extractionStatus") in {"ready", "completed"})
    years = [str(year_value(record)) for record in records if year_value(record)]
    sources = [str(record.get("source") or "unknown") for record in records]
    pdf_statuses = ["downloaded" if record.get("localPdfPath") else str(record.get("pdfStatus") or "unknown") for record in records]
    keywords: list[str] = []
    for record in records:
        raw = str(record.get("keywordsText") or record.get("keyword") or "")
        keywords.extend(value.strip()[:160] for value in re.split(r"[;,，；|]", raw) if value.strip())
    collection_buckets = [
        {"key": collection["id"], "label": collection["name"], "count": collection["recordCount"]}
        for collection in projected_state["collections"]
    ]
    status = "ready" if records else "empty"
    return {
        "protocolVersion": PROTOCOL_VERSION, "status": status, "totalRecords": len(records),
        "downloadedRecords": downloaded, "extractedRecords": extracted,
        "compareRecords": len(projected_state["workspace"]["compareRecordIds"]),
        "yearBuckets": _buckets(years, descending_key=True), "sourceBuckets": _buckets(sources, limit=12),
        "pdfStatusBuckets": _buckets(pdf_statuses), "topKeywords": _buckets(keywords, limit=12),
        "collectionBuckets": collection_buckets, "message": "" if records else "No literature records are available for analysis.",
    }


class BusinessSettingsStore:
    """Cross-process-safe non-secret settings shared by browser and Qt-hosted React pages."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()

    @contextmanager
    def _lock(self, timeout: float = 3.0) -> Iterator[None]:
        with self._thread_lock:
            descriptor = None
            deadline = time.monotonic() + timeout
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
                        raise TimeoutError("business settings are busy")
                    time.sleep(0.02)
            try:
                yield
            finally:
                os.close(descriptor)
                self.lock_path.unlink(missing_ok=True)

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(DEFAULT_BUSINESS_SETTINGS)
        result.update({key: payload[key] for key in SETTINGS_FIELDS if key in payload})
        result["revision"] = max(0, int(payload.get("revision") or 0))
        result["updatedAt"] = str(payload.get("updatedAt") or "")[:40]
        return result

    def _load_unlocked(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("business settings must be an object")
            return self._normalize(payload)
        except FileNotFoundError:
            return dict(DEFAULT_BUSINESS_SETTINGS)
        except (OSError, ValueError, json.JSONDecodeError):
            backup = self.path.with_suffix(self.path.suffix + f".{int(time.time())}.bak")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return dict(DEFAULT_BUSINESS_SETTINGS)

    def _save_unlocked(self, payload: dict[str, Any]) -> None:
        temporary = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _project(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            **payload,
            "aiCredentialConfigured": bool(os.getenv("OMNILIT_AI_API_KEY", "").strip()),
        }

    def load(self) -> dict[str, Any]:
        with self._lock():
            payload = self._load_unlocked()
            if not self.path.exists():
                self._save_unlocked(payload)
            return self._project(payload)

    def update(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock():
            current = self._load_unlocked()
            expected = int(request.get("expectedRevision") or 0)
            if expected != int(current["revision"]):
                raise BusinessSettingsConflict(f"expected revision {expected}, current revision {current['revision']}")
            candidate = self._normalize({**current, **{key: request[key] for key in SETTINGS_FIELDS}})
            endpoint = str(candidate["aiEndpoint"] or "").strip()
            if endpoint:
                parsed = urlsplit(endpoint)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("AI endpoint must be an HTTPS URL without embedded credentials")
            candidate["aiEndpoint"] = endpoint.rstrip("/")
            candidate["aiModel"] = str(candidate["aiModel"] or "").strip()[:160]
            candidate["revision"] = int(current["revision"]) + 1
            candidate["updatedAt"] = _now()
            self._save_unlocked(candidate)
            return self._project(candidate)


def _sentence(text: str, maximum: int = 900) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= maximum:
        return clean
    clipped = clean[:maximum]
    boundary = max(clipped.rfind("。"), clipped.rfind("."), clipped.rfind(";"))
    return (clipped[:boundary + 1] if boundary > maximum // 2 else clipped.rstrip()) + "…"


def _evidence_sections(records: list[dict[str, Any]], focus: str, question: str) -> list[dict[str, Any]]:
    ids = [record["recordId"] for record in records]
    scope = "；".join(f"{record['title']}（{record['year'] or '年份未知'}）" for record in records)
    sections = [{"heading": "研究范围", "body": f"比较文献：{scope}" + (f"\n研究问题：{question}" if question else ""), "evidenceRecordIds": ids}]
    heading = {"overview": "证据概览", "methods": "方法线索", "findings": "主要发现线索", "gaps": "证据缺口"}[focus]
    for record in records:
        abstract = _sentence(record["abstract"], 1800)
        keywords = _sentence(record["keywordsText"], 500)
        if focus == "methods":
            body = f"关键词：{keywords or '未提供'}\n摘要中的方法证据：{abstract or '摘要不可用，无法提取方法线索。'}"
        elif focus == "gaps":
            missing = [name for name, value in (("摘要", abstract), ("关键词", keywords), ("年份", record["year"])) if not value]
            body = "；".join([f"当前元数据缺失：{'、'.join(missing) or '无'}", "需要阅读全文验证样本、方法和结论边界。"])
        else:
            body = abstract or "摘要不可用；仅能确认题名、作者与来源，不能推断研究结论。"
        sections.append({"heading": f"{heading} · {record['title']}", "body": body, "evidenceRecordIds": [record["recordId"]]})
    return sections


def _remote_completion(settings: dict[str, Any], prompt: str) -> str:
    api_key = os.getenv("OMNILIT_AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI credential is not configured")
    endpoint, model = str(settings["aiEndpoint"]), str(settings["aiModel"])
    if not settings["allowRemoteResearchContent"] or not endpoint or not model:
        raise RuntimeError("Remote research-content processing is not fully configured")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "Synthesize only the supplied evidence. Identify uncertainty and never invent citations."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1400,
    }, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=body, method="POST", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urlopen(request, timeout=120) as response:
        length = int(response.headers.get("Content-Length") or 0)
        if length > 2 * 1024 * 1024:
            raise RuntimeError("AI response is too large")
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise RuntimeError("AI response is too large")
    payload = json.loads(raw)
    content = str((((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
    if not content:
        raise RuntimeError("AI response did not contain content")
    return content[:12000]


def build_research_brief(
    workspace: dict[str, Any], request: dict[str, Any], context: Any, settings: dict[str, Any],
    completion: Callable[[dict[str, Any], str], str] = _remote_completion,
) -> dict[str, Any]:
    requested_ids = [str(value) for value in request["recordIds"]]
    by_id = {record["recordId"]: record for record in workspace["records"]}
    records = [by_id[record_id] for record_id in requested_ids if record_id in by_id]
    if len(records) != len(requested_ids):
        raise ValueError("One or more requested records are unavailable in the comparison workspace")
    context.report(1, 3, "steps", "Preparing bounded research evidence")
    mode = str(request["mode"])
    focus, question = str(request["focus"]), str(request.get("question") or "").strip()
    evidence_sections = _evidence_sections(records, focus, question)
    context.check_cancelled()
    if mode == "model":
        prompt = "\n\n".join(f"[{section['heading']}]\n{section['body']}" for section in evidence_sections)
        context.report(2, 3, "steps", "Requesting configured model synthesis")
        content = completion(settings, prompt)
        sections = [{"heading": "模型综合", "body": content, "evidenceRecordIds": requested_ids}]
        warnings = ["研究内容已发送到用户明确配置的远程 HTTPS 模型端点。请回到原文核验所有结论。"]
    else:
        context.report(2, 3, "steps", "Composing local evidence brief")
        sections = evidence_sections
        warnings = ["本结果由本地确定性证据编排生成，未调用生成式模型，也不代表对全文结论的验证。"]
    context.report(3, 3, "steps", "Research brief ready")
    return {
        "protocolVersion": PROTOCOL_VERSION, "mode": mode, "generatedAt": _now(),
        "title": question[:240] or {"overview": "研究证据概览", "methods": "研究方法比较", "findings": "主要发现比较", "gaps": "研究证据缺口"}[focus],
        "sections": sections, "warnings": warnings,
    }
