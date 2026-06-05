from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot

from .app_controller import AppController
from .i18n import LocaleController
from .paths import AppPaths
from .services import AccountStore, as_float, import_resource_module


LEVEL_ORDER: dict[str, int] = {
    "unmatched": -1,
    "keyword_only": 0,
    "loose": 1,
    "balanced": 2,
    "strict": 3,
    "very_strict": 4,
}

LEVEL_DIRS: dict[str, str] = {
    "keyword_only": "keyword_only",
    "loose": "loose",
    "balanced": "balanced",
    "strict": "strict",
    "very_strict": "very_strict",
}


class LiteratureLibraryController(QObject):
    """Expose downloaded literature metadata, previews, and organization actions."""

    changed = Signal()

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._records: list[dict[str, Any]] = []
        self._filtered: list[dict[str, Any]] = []
        self._record_by_id: dict[str, dict[str, Any]] = {}
        self._query = ""
        self._relevance_filter = "all"
        self._pdf_status_filter = "all"
        self._status = "文献库尚未刷新。" if locale.language == "zh" else "Library has not been refreshed."
        self.refresh()

    def _output_root(self) -> Path:
        raw = self.store.setting("download_form_config", "")
        try:
            config = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            config = {}
        output_root = Path(str(config.get("outputDir") or self.paths.data("Download"))).expanduser()
        if not output_root.is_absolute():
            output_root = self.paths.data(output_root)
        return output_root

    @property
    def _meta_path(self) -> Path:
        return self._output_root() / "metadata_battery.jsonl"

    @property
    def _pdf_root(self) -> Path:
        return self._output_root() / "pdfs"

    def _download_settings(self) -> dict[str, Any]:
        raw = self.store.setting("download_form_config", "")
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}

    def _current_keywords(self, fallback_records: list[dict[str, Any]]) -> list[str]:
        settings = self._download_settings()
        text = str(settings.get("keywords") or "").strip()
        keywords = [
            item.strip()
            for chunk in text.splitlines()
            for item in chunk.split(";")
            if item.strip()
        ]
        if not keywords:
            keywords = [str(record.get("keyword") or "").strip() for record in fallback_records if str(record.get("keyword") or "").strip()]
        seen: set[str] = set()
        result: list[str] = []
        for keyword in keywords:
            key = keyword.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(keyword)
        return result

    def _core_config(self, records: list[dict[str, Any]]):
        core = import_resource_module(self.paths, "Download", "literature_download_core")
        settings = self._download_settings()
        return core.CrawlConfig(
            keywords=self._current_keywords(records) or None,
            strict_keyword_match=True,
            min_keyword_match_ratio=as_float(settings.get("minKeywordMatchRatio"), 0.75),
            topic_pack=str(settings.get("topicPack") or "auto").strip() or None,
            journal_pack=str(settings.get("journalPack") or "auto").strip() or None,
            min_topic_score=0,
        )

    def _record_identity(self, core: Any, record: dict[str, Any]) -> str:
        key = core.record_key(record)
        if not key:
            key = "|".join(
                str(record.get(name) or "")
                for name in ("normalized_doi", "doi", "source_record_id", "openalex_id", "title", "publication_year")
            )
        return hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()

    def _resolve_pdf_path(self, core: Any, record: dict[str, Any]) -> Path | None:
        for path in core.resolve_record_pdf_paths(record, self._meta_path):
            if core.validate_existing_pdf(path, 8):
                return path
        return None

    def _read_metadata_records(self) -> list[dict[str, Any]]:
        path = self._meta_path
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8", errors="replace") as fin:
            for line in fin:
                text = line.strip()
                if not text:
                    continue
                try:
                    record = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
        return records

    def _enrich_record(self, core: Any, record: dict[str, Any], config: Any) -> dict[str, Any]:
        enriched = dict(record)
        keyword = str(enriched.get("keyword") or (config.effective_keywords[0] if config.effective_keywords else "")).strip()
        info = core.build_relevance_info(keyword, enriched, config)
        for key, value in info.items():
            enriched[key] = value
        record_id = self._record_identity(core, enriched)
        pdf_path = self._resolve_pdf_path(core, enriched)
        authors = enriched.get("authors") or []
        authors_text = ", ".join(str(author) for author in authors[:6]) if isinstance(authors, list) else str(authors or "")
        enriched.update(
            {
                "recordId": record_id,
                "title": str(enriched.get("title") or "Untitled"),
                "abstract": str(enriched.get("abstract") or ""),
                "authorsText": authors_text,
                "source": str(enriched.get("literature_source") or ""),
                "year": str(enriched.get("publication_year") or "") or str(enriched.get("publication_date") or "")[:4],
                "pdfStatus": str(enriched.get("download_status") or ""),
                "localPdfPath": str(pdf_path) if pdf_path else "",
                "localPdfName": pdf_path.name if pdf_path else "",
                "relevanceLabel": core.relevance_label(str(enriched.get("relevance_level") or "")),
                "matchedKeywordsText": ", ".join(str(item) for item in enriched.get("matched_keywords") or []),
                "matchedFieldsText": ", ".join(str(item) for item in enriched.get("matched_fields") or []),
                "relevanceReasonsText": "; ".join(str(item) for item in enriched.get("relevance_reasons") or []),
            }
        )
        return enriched

    def _apply_filters(self) -> None:
        query = self._query.casefold().strip()
        relevance_floor = LEVEL_ORDER.get(self._relevance_filter, -999)
        filtered: list[dict[str, Any]] = []
        for record in self._records:
            if self._relevance_filter != "all":
                if LEVEL_ORDER.get(str(record.get("relevance_level") or "unmatched"), -1) < relevance_floor:
                    continue
            if self._pdf_status_filter != "all":
                status = str(record.get("pdfStatus") or "")
                if self._pdf_status_filter == "downloaded":
                    if not record.get("localPdfPath"):
                        continue
                elif status != self._pdf_status_filter:
                    continue
            if query:
                haystack = " ".join(
                    str(record.get(name) or "")
                    for name in ("title", "abstract", "authorsText", "doi", "normalized_doi", "keyword")
                ).casefold()
                if query not in haystack:
                    continue
            filtered.append(record)
        self._filtered = filtered

    def _reload(self, rewrite_metadata: bool = False) -> None:
        core = import_resource_module(self.paths, "Download", "literature_download_core")
        raw_records = self._read_metadata_records()
        config = self._core_config(raw_records)
        enriched_records = [self._enrich_record(core, record, config) for record in raw_records]
        if rewrite_metadata and self._meta_path.exists():
            backup = self._meta_path.with_suffix(".jsonl.bak")
            if not backup.exists():
                shutil.copy2(self._meta_path, backup)
            with self._meta_path.open("w", encoding="utf-8") as fout:
                for record in enriched_records:
                    serializable = {key: value for key, value in record.items() if key not in {"recordId"}}
                    fout.write(json.dumps(serializable, ensure_ascii=False) + "\n")
        deduped: dict[str, dict[str, Any]] = {}
        for record in enriched_records:
            deduped[str(record["recordId"])] = record
        self._records = list(deduped.values())
        self._records.sort(key=lambda item: (str(item.get("year") or ""), str(item.get("title") or "")), reverse=True)
        self._record_by_id = {str(record["recordId"]): record for record in self._records}
        self._apply_filters()

    @Property("QVariantList", notify=changed)
    def records(self) -> list[dict[str, Any]]:
        return list(self._filtered)

    @Property(int, notify=changed)
    def totalCount(self) -> int:
        return len(self._records)

    @Property(int, notify=changed)
    def filteredCount(self) -> int:
        return len(self._filtered)

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Slot()
    def refresh(self) -> None:
        try:
            self._reload(False)
            self._status = f"已加载 {len(self._records)} 条文献记录。"
        except Exception as exc:
            self._status = f"文献库刷新失败：{exc}"
        self.changed.emit()

    @Slot()
    def recomputeRelevance(self) -> None:
        try:
            self._reload(True)
            self._status = f"已重算 {len(self._records)} 条文献的相关性字段。"
        except Exception as exc:
            self._status = f"相关性重算失败：{exc}"
        self.changed.emit()

    @Slot(str, str, str)
    def setFilters(self, relevance: str, pdf_status: str, query: str) -> None:
        self._relevance_filter = relevance or "all"
        self._pdf_status_filter = pdf_status or "all"
        self._query = query or ""
        self._apply_filters()
        self.changed.emit()

    @Slot(str, result=str)
    def thumbnailFor(self, record_id: str) -> str:
        record = self._record_by_id.get(str(record_id))
        if not record or not record.get("localPdfPath"):
            return ""
        pdf_path = Path(str(record["localPdfPath"]))
        if not pdf_path.exists():
            return ""
        cache_dir = self._output_root() / "library_thumbnails"
        cache_dir.mkdir(parents=True, exist_ok=True)
        thumbnail = cache_dir / f"{record_id}.png"
        if thumbnail.exists() and thumbnail.stat().st_mtime >= pdf_path.stat().st_mtime:
            return QUrl.fromLocalFile(str(thumbnail)).toString()
        try:
            import fitz

            with fitz.open(pdf_path) as document:
                if len(document) < 1:
                    return ""
                page = document.load_page(0)
                rect = page.rect
                scale = min(1.8, 960 / max(1.0, float(rect.width)))
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pixmap.save(str(thumbnail))
        except Exception:
            return ""
        return QUrl.fromLocalFile(str(thumbnail)).toString()

    @Slot(result=bool)
    def organizeByRelevance(self) -> bool:
        organized = 0
        now = datetime.now().isoformat(timespec="seconds")
        updates: dict[str, tuple[str, str]] = {}
        target_root = self._output_root() / "library"
        try:
            for record in self._records:
                level = str(record.get("relevance_level") or "")
                folder = LEVEL_DIRS.get(level)
                source_pdf = Path(str(record.get("localPdfPath") or ""))
                if not folder or not source_pdf.exists():
                    continue
                target_dir = target_root / folder
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{record['recordId']}_{source_pdf.name}"
                if not target.exists():
                    try:
                        os.link(source_pdf, target)
                    except OSError:
                        shutil.copy2(source_pdf, target)
                updates[str(record["recordId"])] = (level, str(target))
                organized += 1

            if updates:
                core = import_resource_module(self.paths, "Download", "literature_download_core")
                raw_records = self._read_metadata_records()
                with self._meta_path.open("w", encoding="utf-8") as fout:
                    for record in raw_records:
                        record_id = self._record_identity(core, record)
                        if record_id in updates:
                            level, path = updates[record_id]
                            record["organized_level"] = level
                            record["organized_path"] = path
                            record["organized_at"] = now
                        fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._reload(False)
            self._status = f"已按最高相关性等级归档 {organized} 篇 PDF。"
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"相关性归档失败：{exc}"
            self.changed.emit()
            return False
