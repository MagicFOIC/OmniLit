from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot

from .app_controller import AppController
from .background_tasks import ManagedWorker, shutdown_workers
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

KEYWORD_GROUP_ALIASES: dict[str, str] = {
    "li s battery": "lithium sulfur battery",
    "li battery": "lithium sulfur battery",
    "lithium s battery": "lithium sulfur battery",
    "li-s battery": "lithium sulfur battery",
    "li sulfur battery": "lithium sulfur battery",
    "lithium sulfur batteries": "lithium sulfur battery",
    "lithium-sulfur batteries": "lithium sulfur battery",
    "polysulfides": "polysulfide",
    "separators": "separator",
}

BROAD_KEYWORD_GROUPS = {"article", "study", "result", "method", "battery"}


class LiteratureLibraryController(QObject):
    """Expose downloaded literature metadata, previews, and organization actions."""

    changed = Signal()
    thumbnailReady = Signal(str, str)
    previewReady = Signal(str, str)
    _taskFinished = Signal(str, object, str, bool)

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._records: list[dict[str, Any]] = []
        self._filtered: list[dict[str, Any]] = []
        self._record_by_id: dict[str, dict[str, Any]] = {}
        self._query = ""
        self._relevance_filter = "all"
        self._pdf_status_filter = "all"
        self._keyword_group_filter: set[str] = set()
        self._keyword_group_options: list[dict[str, Any]] = []
        self._status = "文献库尚未加载。" if locale.language == "zh" else "Library has not been loaded."
        self._loading = False
        self._busy_action = ""
        self._progress_text = ""
        self._last_loaded_at = ""
        self._has_loaded = False
        self._worker: ManagedWorker | None = None
        self._thumbnail_workers: dict[str, ManagedWorker] = {}
        self._thumbnail_urls: dict[str, str] = {}
        self._preview_workers: dict[str, ManagedWorker] = {}
        self._preview_urls: dict[str, str] = {}
        self._cleanup_candidates: list[dict[str, Any]] = []
        self._cleanup_summary: dict[str, Any] = self._empty_cleanup_summary()
        self._cleanup_pending = False
        self._stop = threading.Event()
        self._taskFinished.connect(self._on_task_finished)
        self.thumbnailReady.connect(self._on_thumbnail_ready)
        self.previewReady.connect(self._on_preview_ready)

    @staticmethod
    def _empty_cleanup_summary() -> dict[str, Any]:
        return {
            "count": 0,
            "totalBytes": 0,
            "totalSizeText": "0 B",
            "metadataCount": 0,
            "orphanCount": 0,
            "libraryCount": 0,
            "thumbnailCount": 0,
            "reasonCounts": {},
        }

    def _output_root_from_settings(self, settings: dict[str, Any]) -> Path:
        output_root = Path(str(settings.get("outputDir") or self.paths.data("Download"))).expanduser()
        if not output_root.is_absolute():
            output_root = self.paths.data(output_root)
        return output_root

    def _output_root(self) -> Path:
        return self._output_root_from_settings(self._download_settings())

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

    def _current_keywords(self, settings: dict[str, Any], fallback_records: list[dict[str, Any]]) -> list[str]:
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

    def _core_config(self, records: list[dict[str, Any]], settings: dict[str, Any]):
        core = import_resource_module(self.paths, "Download", "literature_download_core")
        return core.CrawlConfig(
            keywords=self._current_keywords(settings, records) or None,
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

    @staticmethod
    def _resolve_pdf_path(core: Any, record: dict[str, Any], meta_path: Path, *, validate: bool = False) -> Path | None:
        for path in core.resolve_record_pdf_paths(record, meta_path):
            if validate:
                if core.validate_existing_pdf(path, 8):
                    return path
                continue
            try:
                if path.exists() and path.is_file() and path.stat().st_size > 0:
                    return path
            except OSError:
                continue
        return None

    @staticmethod
    def _read_metadata_records(meta_path: Path) -> list[dict[str, Any]]:
        if not meta_path.exists():
            return []
        records: list[dict[str, Any]] = []
        with meta_path.open("r", encoding="utf-8", errors="replace") as fin:
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

    @staticmethod
    def _file_size(path: Path) -> int:
        try:
            return int(path.stat().st_size) if path.exists() else 0
        except OSError:
            return 0

    @staticmethod
    def _format_bytes(size: int) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        value = float(max(0, size))
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{int(size)} B"

    @staticmethod
    def _path_key(path: Path) -> str:
        try:
            return str(path.resolve()).casefold()
        except OSError:
            return str(path.absolute()).casefold()

    @staticmethod
    def _relative_pdf_text(output_root: Path, pdf_path: Path) -> str:
        try:
            return pdf_path.resolve().relative_to(output_root.resolve()).as_posix()
        except (OSError, ValueError):
            return str(pdf_path)

    @staticmethod
    def _manual_pdf_title(pdf_path: Path) -> str:
        title = ""
        try:
            import fitz

            with fitz.open(pdf_path) as document:
                metadata = document.metadata or {}
                title = str(metadata.get("title") or "").strip()
        except Exception:
            title = ""
        if title and title.casefold() not in {"untitled", "none"}:
            return re.sub(r"\s+", " ", title).strip()
        stem = re.sub(r"[_\-]+", " ", pdf_path.stem).strip()
        return re.sub(r"\s+", " ", stem).strip() or pdf_path.name

    def _manual_pdf_records(
        self,
        *,
        output_root: Path,
        referenced_pdf_keys: set[str],
    ) -> list[dict[str, Any]]:
        pdf_root = output_root / "pdfs"
        if not pdf_root.exists():
            return []

        records: list[dict[str, Any]] = []
        for pdf_path in sorted(pdf_root.rglob("*.pdf"), key=lambda item: self._path_key(item)):
            pdf_key = self._path_key(pdf_path)
            if pdf_key in referenced_pdf_keys:
                continue
            try:
                if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
                    continue
            except OSError:
                continue
            relative_path = self._relative_pdf_text(output_root, pdf_path)
            records.append(
                {
                    "literature_source": "local_pdf",
                    "source_record_id": f"local_pdf:{relative_path}",
                    "title": self._manual_pdf_title(pdf_path),
                    "download_status": "downloaded",
                    "local_pdf_path": relative_path,
                    "manual_pdf": True,
                    "_synthetic_local_pdf_record": True,
                }
            )
        return records

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            return False

    @staticmethod
    def _list_values(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = re.split(r"[,;|]", str(value))
        return [str(item).strip() for item in values if str(item).strip()]

    @staticmethod
    def _format_metric_value(value: Any) -> str:
        try:
            return f"{float(value):.1f}"
        except (TypeError, ValueError):
            return ""

    @classmethod
    def _impact_factor_text(cls, record: dict[str, Any]) -> str:
        value = record.get("impact_factor")
        if value is None or str(value).strip() == "":
            value = record.get("journal_impact_value")
        formatted = cls._format_metric_value(value)
        if not formatted:
            return "未知"
        source = str(record.get("impact_factor_source") or record.get("journal_metric_source") or "").casefold()
        metric = str(record.get("impact_factor_metric") or record.get("journal_impact_metric") or "").casefold()
        if source == "openalex" or metric == "openalex_2yr_mean_citedness":
            return f"IF≈{formatted}"
        if source == "jcr":
            return f"JIF {formatted}"
        if source == "sjr":
            return f"SJR {formatted}"
        return f"IF {formatted}"

    @staticmethod
    def _normalize_keyword_group_key(key: str) -> str:
        text = re.sub(r"\s+", " ", str(key or "").casefold().replace("-", " ")).strip()
        return KEYWORD_GROUP_ALIASES.get(text, text)

    @classmethod
    def _keyword_group_key(cls, core: Any, value: Any) -> str:
        raw_key = core.keyword_group_key(value)
        return cls._normalize_keyword_group_key(raw_key)

    @staticmethod
    def _is_broad_keyword_group(key: str) -> bool:
        return key in BROAD_KEYWORD_GROUPS

    def _enrich_record(self, core: Any, record: dict[str, Any], config: Any, meta_path: Path) -> dict[str, Any]:
        enriched = dict(record)
        keyword = str(enriched.get("keyword") or (config.effective_keywords[0] if config.effective_keywords else "")).strip()
        info = core.build_relevance_info(keyword, enriched, config)
        for key, value in info.items():
            enriched[key] = value
        record_id = self._record_identity(core, enriched)
        pdf_path = self._resolve_pdf_path(core, enriched, meta_path, validate=False)
        if "impact_factor_unknown" not in enriched and "impact_factor" not in enriched:
            core.enrich_record_with_journal_metrics(enriched)
        abstract = str(enriched.get("abstract") or enriched.get("extracted_abstract") or "")
        extracted_abstract = str(enriched.get("extracted_abstract") or "")
        explicit_keywords = list(enriched.get("extracted_keywords") or [])
        if (not abstract or not explicit_keywords) and pdf_path:
            pdf_text = core.extract_pdf_text(pdf_path)
            if not abstract:
                extracted_abstract = core.extract_abstract_from_text(pdf_text)
                abstract = extracted_abstract
            if not explicit_keywords:
                explicit_keywords = core.extract_keywords_from_text(pdf_text)
        extracted_keywords = core.generate_extracted_keywords(
            keyword,
            str(enriched.get("title") or ""),
            abstract,
            explicit_keywords,
            list(enriched.get("matched_keywords") or []),
        )
        keyword_groups = self._keyword_groups_for_record(core, enriched, keyword, extracted_keywords)
        authors = enriched.get("authors") or []
        authors_text = ", ".join(str(author) for author in authors[:6]) if isinstance(authors, list) else str(authors or "")
        impact_factor_text = self._impact_factor_text(enriched)
        publication_date = str(enriched.get("publication_date") or "")
        journal_issns = self._list_values(enriched.get("journal_issns") or enriched.get("journal_issn") or enriched.get("issn"))
        journal_issns_text = ", ".join(journal_issns)
        summary_text = str(enriched.get("summary_text") or enriched.get("content_summary") or core.summarize_content(abstract, str(enriched.get("title") or "")))
        topic_tags = self._list_values(enriched.get("topic_tags") or enriched.get("keyword_groups"))
        if not topic_tags:
            topic_tags = [str(group.get("label") or "") for group in keyword_groups if str(group.get("label") or "")]
        topic_tags_text = ", ".join(topic_tags)
        enriched.update(
            {
                "recordId": record_id,
                "title": str(enriched.get("title") or "Untitled"),
                "abstract": abstract,
                "extracted_abstract": extracted_abstract,
                "extracted_keywords": extracted_keywords,
                "keywordsText": ", ".join(extracted_keywords),
                "keywordGroups": keyword_groups,
                "keywordGroupKeys": [group["key"] for group in keyword_groups],
                "contentSummary": summary_text,
                "summaryText": summary_text,
                "topicTagsText": topic_tags_text,
                "authorsText": authors_text,
                "source": str(enriched.get("literature_source") or ""),
                "year": str(enriched.get("publication_year") or "") or str(enriched.get("publication_date") or "")[:4],
                "publicationDate": publication_date,
                "journalTitle": str(enriched.get("journal_title") or ""),
                "impactFactorText": impact_factor_text,
                "impactFactorSource": str(enriched.get("impact_factor_source") or enriched.get("journal_metric_source") or ""),
                "impactFactorMetric": str(enriched.get("impact_factor_metric") or enriched.get("journal_impact_metric") or ""),
                "impactFactorYear": str(enriched.get("impact_factor_year") or enriched.get("journal_impact_year") or ""),
                "impactFactorQuartile": str(enriched.get("impact_factor_quartile") or ""),
                "journalIssnL": str(enriched.get("journal_issn_l") or ""),
                "journalIssnsText": journal_issns_text,
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

    @staticmethod
    def _keyword_groups_for_record(core: Any, record: dict[str, Any], keyword: str, extracted_keywords: list[str]) -> list[dict[str, Any]]:
        values: list[Any] = [
            *extracted_keywords,
            *LiteratureLibraryController._list_values(record.get("keyword_groups")),
            *LiteratureLibraryController._list_values(record.get("topic_tags")),
            *LiteratureLibraryController._list_values(record.get("matched_keywords")),
            keyword,
        ]
        explicit_key = LiteratureLibraryController._keyword_group_key(core, keyword)
        groups: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in values:
            key = LiteratureLibraryController._keyword_group_key(core, value)
            if not key or key in seen:
                continue
            seen.add(key)
            groups.append({"key": key, "label": core.keyword_group_label(value), "explicit": key == explicit_key})
        return groups

    @staticmethod
    def _build_keyword_group_options(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        label_counts: dict[str, dict[str, int]] = {}
        counts: dict[str, int] = {}
        explicit_keys: set[str] = set()
        for record in records:
            keys_seen: set[str] = set()
            for group in record.get("keywordGroups") or []:
                key = LiteratureLibraryController._normalize_keyword_group_key(str(group.get("key") or ""))
                if not key or key in keys_seen:
                    continue
                keys_seen.add(key)
                label = str(group.get("label") or key).strip() or key
                label_counts.setdefault(key, {})
                label_counts[key][label] = label_counts[key].get(label, 0) + 1
                counts[key] = counts.get(key, 0) + 1
                if bool(group.get("explicit")):
                    explicit_keys.add(key)

        labels: dict[str, str] = {}
        for key, options in label_counts.items():
            labels[key] = sorted(options, key=lambda label: (-options[label], -len(label), label.casefold()))[0]

        filtered_keys = [
            key
            for key in counts
            if len(key) >= 3 and (key in explicit_keys or not LiteratureLibraryController._is_broad_keyword_group(key))
        ]
        filtered_keys.sort(key=lambda key: (-counts[key], labels.get(key, key).casefold()))
        return [{"key": key, "label": labels.get(key, key), "count": counts[key]} for key in filtered_keys[:30]]

    def _load_records(self, *, rewrite_metadata: bool, settings: dict[str, Any], output_root: Path) -> list[dict[str, Any]]:
        core = import_resource_module(self.paths, "Download", "literature_download_core")
        meta_path = output_root / "metadata_battery.jsonl"
        raw_records = self._read_metadata_records(meta_path)
        referenced_pdf_keys: set[str] = set()
        for record in raw_records:
            for pdf_path in core.resolve_record_pdf_paths(record, meta_path):
                referenced_pdf_keys.add(self._path_key(pdf_path))
        manual_pdf_records = self._manual_pdf_records(output_root=output_root, referenced_pdf_keys=referenced_pdf_keys)
        all_records = [*raw_records, *manual_pdf_records]
        config = self._core_config(all_records, settings)
        enriched_records = [self._enrich_record(core, record, config, meta_path) for record in all_records]
        if rewrite_metadata and meta_path.exists():
            backup = meta_path.with_suffix(".jsonl.bak")
            if not backup.exists():
                shutil.copy2(meta_path, backup)
            with meta_path.open("w", encoding="utf-8") as fout:
                for record in enriched_records:
                    if record.get("_synthetic_local_pdf_record"):
                        continue
                    serializable = {key: value for key, value in record.items() if key not in {"recordId"}}
                    fout.write(json.dumps(serializable, ensure_ascii=False) + "\n")

        deduped: dict[str, dict[str, Any]] = {}
        for record in enriched_records:
            deduped[str(record["recordId"])] = record
        records = list(deduped.values())
        records.sort(key=lambda item: (str(item.get("year") or ""), str(item.get("title") or "")), reverse=True)
        return records

    def _cleanup_candidate(
        self,
        *,
        path: Path,
        reason: str,
        reason_text: str,
        kind: str,
        record_id: str = "",
        title: str = "",
    ) -> dict[str, Any]:
        size = self._file_size(path)
        return {
            "path": str(path),
            "name": path.name,
            "size": size,
            "sizeText": self._format_bytes(size),
            "reason": reason,
            "reasonText": reason_text,
            "kind": kind,
            "recordId": record_id,
            "title": title,
        }

    def _cleanup_summary_from_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        reason_counts: dict[str, int] = {}
        total = 0
        metadata_count = 0
        orphan_count = 0
        library_count = 0
        thumbnail_count = 0
        for candidate in candidates:
            total += int(candidate.get("size") or 0)
            reason = str(candidate.get("reason") or "unknown")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            kind = str(candidate.get("kind") or "")
            if kind == "metadata_pdf":
                metadata_count += 1
            elif kind == "orphan_pdf":
                orphan_count += 1
            elif kind == "library_pdf":
                library_count += 1
            elif kind == "thumbnail":
                thumbnail_count += 1
        return {
            "count": len(candidates),
            "totalBytes": total,
            "totalSizeText": self._format_bytes(total),
            "metadataCount": metadata_count,
            "orphanCount": orphan_count,
            "libraryCount": library_count,
            "thumbnailCount": thumbnail_count,
            "reasonCounts": reason_counts,
        }

    def _cleanup_preview_task(self) -> tuple[object, str]:
        settings = self._download_settings()
        output_root = self._output_root_from_settings(settings)
        meta_path = output_root / "metadata_battery.jsonl"
        pdf_root = output_root / "pdfs"
        library_root = output_root / "library"
        thumbnail_root = output_root / "library_thumbnails"
        preview_root = output_root / "library_previews"
        core = import_resource_module(self.paths, "Download", "literature_download_core")
        raw_records = self._read_metadata_records(meta_path)
        config = self._core_config(raw_records, settings)

        referenced_pdf_keys: set[str] = set()
        valid_record_ids: set[str] = set()
        invalid_record_ids: set[str] = set()
        candidates: list[dict[str, Any]] = []
        seen_candidate_paths: set[str] = set()

        def add_candidate(candidate: dict[str, Any]) -> None:
            key = self._path_key(Path(str(candidate.get("path") or "")))
            if key in seen_candidate_paths:
                return
            seen_candidate_paths.add(key)
            candidates.append(candidate)

        for raw in raw_records:
            enriched = self._enrich_record(core, raw, config, meta_path)
            record_id = str(enriched.get("recordId") or "")
            title = str(enriched.get("title") or "Untitled")
            resolved_paths = core.resolve_record_pdf_paths(raw, meta_path)
            for path in resolved_paths:
                referenced_pdf_keys.add(self._path_key(path))
            pdf_path = self._resolve_pdf_path(core, raw, meta_path, validate=False)
            relevant = str(enriched.get("relevance_level") or "unmatched") != "unmatched"
            if relevant:
                valid_record_ids.add(record_id)
                continue
            invalid_record_ids.add(record_id)
            if pdf_path and self._is_within(pdf_path, output_root):
                add_candidate(
                    self._cleanup_candidate(
                        path=pdf_path,
                        reason="metadata_unmatched",
                        reason_text="metadata 记录不再命中当前关键词规则",
                        kind="metadata_pdf",
                        record_id=record_id,
                        title=title,
                    )
                )
            thumbnail = thumbnail_root / f"{record_id}.png"
            if thumbnail.exists():
                add_candidate(
                    self._cleanup_candidate(
                        path=thumbnail,
                        reason="thumbnail_for_deleted_record",
                        reason_text="对应文献 PDF 将被清理的缩略图缓存",
                        kind="thumbnail",
                        record_id=record_id,
                        title=title,
                    )
                )
            preview = preview_root / f"{record_id}.png"
            if preview.exists():
                add_candidate(
                    self._cleanup_candidate(
                        path=preview,
                        reason="preview_for_deleted_record",
                        reason_text="对应文献 PDF 将被清理的高清预览缓存",
                        kind="thumbnail",
                        record_id=record_id,
                        title=title,
                    )
                )

        for manual_record in self._manual_pdf_records(output_root=output_root, referenced_pdf_keys=referenced_pdf_keys):
            for path in core.resolve_record_pdf_paths(manual_record, meta_path):
                referenced_pdf_keys.add(self._path_key(path))

        if pdf_root.exists():
            for path in pdf_root.rglob("*.pdf"):
                if self._path_key(path) not in referenced_pdf_keys:
                    add_candidate(
                        self._cleanup_candidate(
                            path=path,
                            reason="orphan_pdf",
                            reason_text="Download/pdfs 中无法关联到 metadata 的孤儿 PDF",
                            kind="orphan_pdf",
                        )
                    )

        known_record_ids = valid_record_ids | invalid_record_ids
        if library_root.exists():
            for path in library_root.rglob("*.pdf"):
                stem = path.name.split("_", 1)[0]
                if stem in invalid_record_ids:
                    reason = "library_for_deleted_record"
                    reason_text = "对应文献不再命中当前关键词规则的归档副本"
                elif stem not in known_record_ids:
                    reason = "orphan_library_pdf"
                    reason_text = "归档目录中无法关联到 metadata 的孤儿 PDF"
                else:
                    continue
                add_candidate(
                    self._cleanup_candidate(
                        path=path,
                        reason=reason,
                        reason_text=reason_text,
                        kind="library_pdf",
                        record_id=stem if stem in known_record_ids else "",
                    )
                )

        summary = self._cleanup_summary_from_candidates(candidates)
        message = (
            f"发现 {summary['count']} 个可清理文件，预计释放 {summary['totalSizeText']}。"
            if summary["count"]
            else "没有需要清理的旧 PDF。"
        )
        return {"candidates": candidates, "summary": summary}, message

    def _cleanup_delete_task(self, candidates: list[dict[str, Any]]) -> tuple[object, str]:
        settings = self._download_settings()
        output_root = self._output_root_from_settings(settings)
        meta_path = output_root / "metadata_battery.jsonl"
        now = datetime.now().isoformat(timespec="seconds")
        deleted_paths: set[str] = set()
        deleted_record_reasons: dict[str, str] = {}
        deleted = 0
        freed = 0

        for candidate in candidates:
            path_text = str(candidate.get("path") or "")
            if not path_text:
                continue
            path = Path(path_text)
            if not self._is_within(path, output_root):
                continue
            size = self._file_size(path)
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    deleted += 1
                    freed += size
                    deleted_paths.add(self._path_key(path))
            except OSError:
                continue
            if candidate.get("kind") == "metadata_pdf":
                record_id = str(candidate.get("recordId") or "")
                if record_id:
                    deleted_record_reasons[record_id] = str(candidate.get("reasonText") or candidate.get("reason") or "cleanup")

        if deleted_record_reasons and meta_path.exists():
            core = import_resource_module(self.paths, "Download", "literature_download_core")
            raw_records = self._read_metadata_records(meta_path)
            with meta_path.open("w", encoding="utf-8") as fout:
                for record in raw_records:
                    record_id = self._record_identity(core, record)
                    if record_id in deleted_record_reasons:
                        record["download_status"] = "deleted_by_cleanup"
                        record["local_pdf_path"] = None
                        record["cleanup_deleted_at"] = now
                        record["cleanup_reason"] = deleted_record_reasons[record_id]
                        record.pop("organized_path", None)
                        record.pop("organized_level", None)
                        record.pop("organized_at", None)
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")

        refreshed = self._load_records(rewrite_metadata=False, settings=settings, output_root=output_root)
        summary = {
            "deletedCount": deleted,
            "freedBytes": freed,
            "freedSizeText": self._format_bytes(freed),
            "deletedPaths": list(deleted_paths),
        }
        return {"records": refreshed, "summary": summary}, f"已直接删除 {deleted} 个旧文件，释放 {self._format_bytes(freed)}。"

    @staticmethod
    def _render_pdf_first_page(pdf_path: Path, image_path: Path, max_width: int) -> str:
        try:
            image_path.parent.mkdir(parents=True, exist_ok=True)
            import fitz

            with fitz.open(pdf_path) as document:
                if len(document) < 1:
                    return ""
                page = document.load_page(0)
                rect = page.rect
                scale = min(3.5, max_width / max(1.0, float(rect.width)))
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pixmap.save(str(image_path))
                return QUrl.fromLocalFile(str(image_path)).toString()
        except Exception:
            return ""

    def _cached_page_image_url(
        self,
        *,
        record_id: str,
        cache_folder: str,
        max_width: int,
        workers: dict[str, ManagedWorker],
        urls: dict[str, str],
        ready_signal: Signal,
        state_prefix: str,
    ) -> str:
        key = str(record_id)
        if key in urls:
            return urls[key]
        record = self._record_by_id.get(key)
        if not record or not record.get("localPdfPath"):
            return ""
        if key in workers and workers[key].is_alive():
            return ""

        pdf_path = Path(str(record["localPdfPath"]))
        if not pdf_path.exists():
            return ""
        cache_dir = self._output_root() / cache_folder
        image_path = cache_dir / f"{key}.png"
        if image_path.exists() and image_path.stat().st_mtime >= pdf_path.stat().st_mtime:
            url = QUrl.fromLocalFile(str(image_path)).toString()
            urls[key] = url
            return url

        def run() -> None:
            url = self._render_pdf_first_page(pdf_path, image_path, max_width)
            ready_signal.emit(key, url)

        task = ManagedWorker(
            name=state_prefix,
            target=run,
            state_path=self.paths.data("task_state", f"{state_prefix.lower()}_{key}.json"),
            metadata={"record_id": key},
        )
        workers[key] = task
        task.start()
        return ""

    def _cached_page_image_state(
        self,
        *,
        record_id: str,
        workers: dict[str, ManagedWorker],
        urls: dict[str, str],
    ) -> str:
        key = str(record_id)
        if key in urls:
            return "ready" if urls[key] else "failed"
        record = self._record_by_id.get(key)
        if not record or not record.get("localPdfPath"):
            return "missing_pdf"
        worker = workers.get(key)
        if worker is not None:
            return "generating" if worker.is_alive() else "failed"
        pdf_path = Path(str(record["localPdfPath"]))
        if not pdf_path.exists():
            return "missing_pdf"
        return "idle"

    def _apply_loaded_records(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self._record_by_id = {str(record["recordId"]): record for record in self._records}
        self._keyword_group_options = self._build_keyword_group_options(self._records)
        valid_keys = {str(option.get("key") or "") for option in self._keyword_group_options}
        self._keyword_group_filter = {key for key in self._keyword_group_filter if key in valid_keys}
        self._apply_filters()

    @staticmethod
    def _list_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "recordId": record.get("recordId", ""),
            "title": record.get("title", ""),
            "authorsText": record.get("authorsText", ""),
            "source": record.get("source", ""),
            "year": record.get("year", ""),
            "publicationDate": record.get("publicationDate", ""),
            "journalTitle": record.get("journalTitle", ""),
            "impactFactorText": record.get("impactFactorText", "未知"),
            "impactFactorSource": record.get("impactFactorSource", ""),
            "impactFactorMetric": record.get("impactFactorMetric", ""),
            "impactFactorYear": record.get("impactFactorYear", ""),
            "impactFactorQuartile": record.get("impactFactorQuartile", ""),
            "journalIssnL": record.get("journalIssnL", ""),
            "journalIssnsText": record.get("journalIssnsText", ""),
            "keywordsText": record.get("keywordsText", ""),
            "contentSummary": record.get("contentSummary", ""),
            "summaryText": record.get("summaryText") or record.get("contentSummary", ""),
            "topicTagsText": record.get("topicTagsText", ""),
            "pdfStatus": record.get("pdfStatus", ""),
            "localPdfPath": record.get("localPdfPath", ""),
            "localPdfName": record.get("localPdfName", ""),
            "relevanceLabel": record.get("relevanceLabel", ""),
            "relevance_level": record.get("relevance_level", ""),
            "relevance_score": record.get("relevance_score", 0),
            "matchedKeywordsText": record.get("matchedKeywordsText", ""),
            "matchedFieldsText": record.get("matchedFieldsText", ""),
            "keywordGroupKeys": record.get("keywordGroupKeys", []),
        }

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
            if self._keyword_group_filter:
                record_groups = {str(key) for key in record.get("keywordGroupKeys") or []}
                if not record_groups.intersection(self._keyword_group_filter):
                    continue
            if query:
                haystack = " ".join(
                    str(record.get(name) or "")
                    for name in (
                        "title",
                        "abstract",
                        "contentSummary",
                        "keywordsText",
                        "authorsText",
                        "doi",
                        "normalized_doi",
                        "keyword",
                        "journalTitle",
                    )
                ).casefold()
                if query not in haystack:
                    continue
            filtered.append(record)
        self._filtered = filtered

    def _start_worker(
        self,
        *,
        action: str,
        name: str,
        state_file: str,
        start_message: str,
        target: Callable[[ManagedWorker], tuple[object, str]],
    ) -> bool:
        if self._loading:
            self._status = "文献库正在处理任务，请稍候。" if self.locale.language == "zh" else "The library is busy."
            self.changed.emit()
            return False

        self._loading = True
        self._busy_action = action
        self._progress_text = start_message
        self._status = start_message
        self._stop.clear()
        self.changed.emit()

        def run() -> None:
            try:
                payload, message = target(task)
                task.update_state("completed", detail=message)
                self._taskFinished.emit(action, payload, message, True)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                task.update_state("failed", detail=message)
                self._taskFinished.emit(action, {}, message, False)

        task = ManagedWorker(
            name=name,
            target=run,
            state_path=self.paths.data("task_state", state_file),
            cancel_event=self._stop,
            metadata={"action": action},
        )
        self._worker = task
        task.start()
        return True

    def _load_task(self, rewrite_metadata: bool) -> tuple[object, str]:
        settings = self._download_settings()
        output_root = self._output_root_from_settings(settings)
        records = self._load_records(rewrite_metadata=rewrite_metadata, settings=settings, output_root=output_root)
        return {"records": records}, f"已加载 {len(records)} 条文献记录。"

    def _organize_task(self, records: list[dict[str, Any]]) -> tuple[object, str]:
        settings = self._download_settings()
        output_root = self._output_root_from_settings(settings)
        meta_path = output_root / "metadata_battery.jsonl"
        target_root = output_root / "library"
        organized = 0
        now = datetime.now().isoformat(timespec="seconds")
        updates: dict[str, tuple[str, str]] = {}

        for record in records:
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

        if updates and meta_path.exists():
            core = import_resource_module(self.paths, "Download", "literature_download_core")
            raw_records = self._read_metadata_records(meta_path)
            with meta_path.open("w", encoding="utf-8") as fout:
                for record in raw_records:
                    record_id = self._record_identity(core, record)
                    if record_id in updates:
                        level, path = updates[record_id]
                        record["organized_level"] = level
                        record["organized_path"] = path
                        record["organized_at"] = now
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")

        refreshed = self._load_records(rewrite_metadata=False, settings=settings, output_root=output_root)
        return {"records": refreshed, "organized": organized}, f"已按最高相关性等级归档 {organized} 篇 PDF。"

    @Property("QVariantList", notify=changed)
    def records(self) -> list[dict[str, Any]]:
        return [self._list_record(record) for record in self._filtered]

    @Property("QVariantList", notify=changed)
    def keywordGroupOptions(self) -> list[dict[str, Any]]:
        return list(self._keyword_group_options)

    @Property(int, notify=changed)
    def totalCount(self) -> int:
        return len(self._records)

    @Property(int, notify=changed)
    def filteredCount(self) -> int:
        return len(self._filtered)

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def busyAction(self) -> str:
        return self._busy_action

    @Property(str, notify=changed)
    def progressText(self) -> str:
        return self._progress_text

    @Property(str, notify=changed)
    def lastLoadedAt(self) -> str:
        return self._last_loaded_at

    @Property(bool, notify=changed)
    def hasLoaded(self) -> bool:
        return self._has_loaded

    @Property("QVariantList", notify=changed)
    def cleanupCandidates(self) -> list[dict[str, Any]]:
        return list(self._cleanup_candidates)

    @Property("QVariantMap", notify=changed)
    def cleanupSummary(self) -> dict[str, Any]:
        return dict(self._cleanup_summary)

    @Property(bool, notify=changed)
    def cleanupPending(self) -> bool:
        return self._cleanup_pending

    @Slot(result=bool)
    def refresh(self) -> bool:
        message = "正在后台加载文献库..." if self.locale.language == "zh" else "Loading literature library in the background..."
        return self._start_worker(
            action="refresh",
            name="LiteratureLibraryRefresh",
            state_file="literature_library_refresh.json",
            start_message=message,
            target=lambda _task: self._load_task(False),
        )

    @Slot(result=bool)
    def recomputeRelevance(self) -> bool:
        message = "正在后台重算相关性字段..." if self.locale.language == "zh" else "Recomputing relevance fields in the background..."
        return self._start_worker(
            action="recompute",
            name="LiteratureLibraryRecompute",
            state_file="literature_library_recompute.json",
            start_message=message,
            target=lambda _task: self._load_task(True),
        )

    @Slot(result=bool)
    def previewCleanup(self) -> bool:
        message = "正在后台扫描可清理的旧 PDF..." if self.locale.language == "zh" else "Scanning cleanup candidates in the background..."
        return self._start_worker(
            action="preview_cleanup",
            name="LiteratureLibraryCleanupPreview",
            state_file="literature_library_cleanup_preview.json",
            start_message=message,
            target=lambda _task: self._cleanup_preview_task(),
        )

    @Slot(result=bool)
    def confirmCleanup(self) -> bool:
        if not self._cleanup_pending or not self._cleanup_candidates:
            self._status = "没有待确认清理的旧 PDF。" if self.locale.language == "zh" else "There are no cleanup candidates to confirm."
            self.changed.emit()
            return False
        candidates = [dict(candidate) for candidate in self._cleanup_candidates]
        message = "正在直接删除已确认的旧 PDF..." if self.locale.language == "zh" else "Deleting confirmed old PDFs in the background..."
        return self._start_worker(
            action="confirm_cleanup",
            name="LiteratureLibraryCleanupDelete",
            state_file="literature_library_cleanup_delete.json",
            start_message=message,
            target=lambda _task: self._cleanup_delete_task(candidates),
        )

    @Slot(str, str, str)
    @Slot(str, str, str, "QVariantList")
    def setFilters(self, relevance: str, pdf_status: str, query: str, keyword_groups: list[Any] | None = None) -> None:
        self._relevance_filter = relevance or "all"
        self._pdf_status_filter = pdf_status or "all"
        self._query = query or ""
        self._keyword_group_filter = {str(item) for item in (keyword_groups or []) if str(item)}
        self._apply_filters()
        self.changed.emit()

    @Slot(str, result=str)
    def thumbnailFor(self, record_id: str) -> str:
        return self._cached_page_image_url(
            record_id=str(record_id),
            cache_folder="library_thumbnails",
            max_width=960,
            workers=self._thumbnail_workers,
            urls=self._thumbnail_urls,
            ready_signal=self.thumbnailReady,
            state_prefix="LiteratureThumbnail",
        )

    @Slot(str, result=str)
    def thumbnailStateFor(self, record_id: str) -> str:
        return self._cached_page_image_state(
            record_id=str(record_id),
            workers=self._thumbnail_workers,
            urls=self._thumbnail_urls,
        )

    @Slot(str, result=str)
    def previewFor(self, record_id: str) -> str:
        return self._cached_page_image_url(
            record_id=str(record_id),
            cache_folder="library_previews",
            max_width=2200,
            workers=self._preview_workers,
            urls=self._preview_urls,
            ready_signal=self.previewReady,
            state_prefix="LiteraturePreview",
        )

    @Slot(str, result=str)
    def previewStateFor(self, record_id: str) -> str:
        return self._cached_page_image_state(
            record_id=str(record_id),
            workers=self._preview_workers,
            urls=self._preview_urls,
        )

    @Slot(str, result="QVariantMap")
    def detailsFor(self, record_id: str) -> dict[str, Any]:
        record = self._record_by_id.get(str(record_id))
        if not record:
            return {}
        return {
            "recordId": record.get("recordId", ""),
            "title": record.get("title", ""),
            "abstract": record.get("abstract", ""),
            "authorsText": record.get("authorsText", ""),
            "doi": record.get("doi") or record.get("normalized_doi") or "",
            "source": record.get("source", ""),
            "year": record.get("year", ""),
            "publicationDate": record.get("publicationDate", ""),
            "journalTitle": record.get("journalTitle", ""),
            "impactFactorText": record.get("impactFactorText", "未知"),
            "impactFactorSource": record.get("impactFactorSource", ""),
            "impactFactorMetric": record.get("impactFactorMetric", ""),
            "impactFactorYear": record.get("impactFactorYear", ""),
            "impactFactorQuartile": record.get("impactFactorQuartile", ""),
            "journalIssnL": record.get("journalIssnL", ""),
            "journalIssnsText": record.get("journalIssnsText", ""),
            "keywordsText": record.get("keywordsText", ""),
            "contentSummary": record.get("contentSummary", ""),
            "summaryText": record.get("summaryText") or record.get("contentSummary", ""),
            "topicTagsText": record.get("topicTagsText", ""),
            "pdfStatus": record.get("pdfStatus", ""),
            "localPdfPath": record.get("localPdfPath", ""),
            "relevanceLabel": record.get("relevanceLabel", ""),
            "relevance_score": record.get("relevance_score", 0),
            "matchedKeywordsText": record.get("matchedKeywordsText", ""),
            "matchedFieldsText": record.get("matchedFieldsText", ""),
            "relevanceReasonsText": record.get("relevanceReasonsText", ""),
        }

    @Slot(result=bool)
    def organizeByRelevance(self) -> bool:
        records = [dict(record) for record in self._records]
        message = "正在后台按相关性归档..." if self.locale.language == "zh" else "Organizing PDFs by relevance in the background..."
        return self._start_worker(
            action="organize",
            name="LiteratureLibraryOrganize",
            state_file="literature_library_organize.json",
            start_message=message,
            target=lambda _task: self._organize_task(records),
        )

    @Slot(str, str)
    def _on_thumbnail_ready(self, record_id: str, url: str) -> None:
        self._thumbnail_urls[str(record_id)] = str(url or "")
        self._thumbnail_workers.pop(str(record_id), None)
        self.changed.emit()

    @Slot(str, str)
    def _on_preview_ready(self, record_id: str, url: str) -> None:
        self._preview_urls[str(record_id)] = str(url or "")
        self._preview_workers.pop(str(record_id), None)
        self.changed.emit()

    def _on_task_finished(self, action: str, payload: object, message: str, ok: bool) -> None:
        self._loading = False
        self._busy_action = ""
        self._progress_text = ""
        if ok and isinstance(payload, dict):
            if action == "preview_cleanup":
                candidates = payload.get("candidates")
                summary = payload.get("summary")
                self._cleanup_candidates = list(candidates) if isinstance(candidates, list) else []
                self._cleanup_summary = dict(summary) if isinstance(summary, dict) else self._empty_cleanup_summary()
                self._cleanup_pending = bool(self._cleanup_candidates)
                self._status = message
                self.changed.emit()
                return

            records = payload.get("records")
            if isinstance(records, list):
                self._apply_loaded_records(records)
                self._has_loaded = True
                self._last_loaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if action == "confirm_cleanup":
                self._cleanup_candidates = []
                self._cleanup_summary = self._empty_cleanup_summary()
                self._cleanup_pending = False
            self._status = message
        else:
            if self.locale.language == "zh":
                labels = {
                    "refresh": "刷新",
                    "recompute": "重算相关性",
                    "organize": "相关性归档",
                    "preview_cleanup": "清理扫描",
                    "confirm_cleanup": "旧 PDF 清理",
                }
                self._status = f"{labels.get(action, '任务')}失败：{message}"
            else:
                self._status = f"{action or 'Task'} failed: {message}"
        self.changed.emit()

    def shutdown(self, timeout: float = 15.0) -> bool:
        return shutdown_workers([self._worker, *self._thumbnail_workers.values(), *self._preview_workers.values()], timeout)
