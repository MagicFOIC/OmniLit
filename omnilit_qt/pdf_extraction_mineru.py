from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parser_runtime_manager import ParserRuntimeManager
from .pdf_cloud_client import CloudAPIClient, CloudAPIError, join_api_url, safe_extract_zip
from .pdf_extraction_schema import make_base_index, make_element, normalize_bbox
from .pdf_extraction_settings import (
    PARSER_CONFIG_VERSION,
    parser_api_token,
    parser_api_url,
    parser_service_enabled,
    redact_sensitive_text,
)
from .pdf_extraction_table_utils import html_table_to_rows, markdown_table_to_rows, table_to_rows


class EngineUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MinerUConfig:
    enabled: bool
    mode: str
    command: str
    python: str
    api_url: str
    timeout: float
    backend: str
    api_token: str = ""
    poll_interval: float = 2.0
    config_version: str = PARSER_CONFIG_VERSION

    @classmethod
    def from_env(cls, store: Any | None = None) -> "MinerUConfig":
        return cls(
            enabled=parser_service_enabled(store, "mineru"),
            mode=os.environ.get("OMNILIT_MINERU_MODE", "api").strip().lower() or "api",
            command=os.environ.get("OMNILIT_MINERU_COMMAND", "mineru").strip() or "mineru",
            python=os.environ.get("OMNILIT_MINERU_PYTHON", "").strip(),
            api_url=parser_api_url(store, "mineru"),
            timeout=_env_float("OMNILIT_MINERU_TIMEOUT", 900.0),
            backend=os.environ.get("OMNILIT_MINERU_BACKEND", "pipeline").strip() or "pipeline",
            api_token=parser_api_token(store, "mineru"),
            poll_interval=_env_float("OMNILIT_MINERU_POLL_INTERVAL", 2.0),
        )


class MinerUExtractionEngine:
    name = "mineru"

    def __init__(self, config: MinerUConfig | None = None, runtime_manager: ParserRuntimeManager | None = None, store: Any | None = None) -> None:
        self.config = config or MinerUConfig.from_env(store)
        self.runtime_manager = runtime_manager or ParserRuntimeManager()
        self._runtime_info: dict[str, Any] = {}
        self._runtime_warnings: list[dict[str, str]] = []

    def is_available(self) -> bool:
        return bool(self.availability().get("available"))

    def availability(self) -> dict[str, Any]:
        if not self.config.enabled or self.config.mode == "off":
            return {"available": False, "installable": False, "status": "off", "message": "MinerU deep parser is disabled."}
        if self.config.mode == "api":
            configured = bool(self.config.api_token and self.config.api_url)
            return {
                "available": configured,
                "installable": False,
                "status": "ready" if configured else "not_configured",
                "message": "MinerU cloud API is configured." if configured else "Configure the MinerU API token in system settings.",
            }
        if self.config.mode not in {"auto", "cli"}:
            return {"available": False, "installable": False, "status": "invalid", "message": f"Unsupported MinerU mode: {self.config.mode}"}
        if self.config.python:
            exists = Path(self.config.python).exists()
            info = {
                "available": exists,
                "installable": False,
                "status": "ready" if exists else "missing",
                "python": self.config.python if exists else "",
                "command": "",
                "message": "MinerU configured Python is available." if exists else "MinerU configured Python does not exist.",
            }
        elif self.config.mode == "cli":
            available = _command_exists(self.config.command)
            info = {
                "available": available,
                "installable": False,
                "status": "ready" if available else "missing",
                "python": "",
                "command": self.config.command if available else "",
                "message": "MinerU CLI is available." if available else "mineru command not found.",
            }
        else:
            info = self.runtime_manager.check_mineru_available()
        self._runtime_info = dict(info)
        return dict(info)

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = dict(options or {})
        runtime_info = self.availability()
        if self.config.mode == "api":
            if not runtime_info.get("available"):
                raise EngineUnavailable(str(runtime_info.get("message") or "MinerU API is not configured."))
            return self._analyze_api(pdf_path, output_dir, options)
        if not runtime_info.get("available") and runtime_info.get("installable") and self.config.mode == "auto":
            callback = options.get("runtime_progress_callback")
            runtime_info = self.runtime_manager.ensure_mineru_runtime(callback if callable(callback) else None)
        if not runtime_info.get("available"):
            raise EngineUnavailable(str(runtime_info.get("message") or "MinerU automatic initialization failed; fell back to PyMuPDF."))

        source = Path(pdf_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"PDF file does not exist: {source}")

        engine_dir = Path(output_dir) / self.name
        raw_dir = engine_dir / "mineru_raw"
        engine_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        self._runtime_warnings = []
        self._run_cli(source, engine_dir, raw_dir, options, runtime_info)
        index = self._to_index(source, Path(output_dir), engine_dir, raw_dir)
        index.setdefault("engineErrors", []).extend(self._runtime_warnings)
        return index

    def _analyze_api(self, pdf_path: Path, output_dir: Path, options: dict[str, Any]) -> dict[str, Any]:
        source = Path(pdf_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"PDF file does not exist: {source}")
        engine_dir = Path(output_dir) / self.name
        raw_dir = engine_dir / "mineru_raw"
        engine_dir.mkdir(parents=True, exist_ok=True)
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        callback = options.get("runtime_progress_callback")
        cancel_event = options.get("cancel_event")
        client = CloudAPIClient(
            self.name,
            timeout=self.config.timeout,
            cancel_event=cancel_event if hasattr(cancel_event, "is_set") else None,
            progress=callback if callable(callback) else None,
        )
        headers = {"Authorization": f"Bearer {self.config.api_token}", "Content-Type": "application/json"}
        data_id = uuid.uuid4().hex
        client.notify(8, "正在向 MinerU 申请 PDF 上传地址...")
        create_payload = {
            "files": [{"name": source.name, "data_id": data_id}],
            "model_version": self.config.backend,
            "enable_formula": True,
            "enable_table": True,
        }
        created = client.request_json(
            "POST",
            join_api_url(self.config.api_url, "file-urls/batch"),
            headers=headers,
            json=create_payload,
            expected=(200,),
        )
        data = _mineru_response_data(created)
        batch_id = str(data.get("batch_id") or data.get("batchId") or "").strip()
        upload_urls = data.get("file_urls") or data.get("fileUrls") or []
        upload_url = str(upload_urls[0] if isinstance(upload_urls, list) and upload_urls else "").strip()
        if not batch_id or not upload_url:
            raise CloudAPIError("MinerU did not return a batch ID and upload URL.", code="INVALID_RESPONSE")

        client.notify(20, "正在上传 PDF 到 MinerU...")
        with source.open("rb") as handle:
            client.request(
                "PUT",
                upload_url,
                data=handle,
                expected=(200, 201, 204),
                request_timeout=self.config.timeout,
            )

        status_url = join_api_url(self.config.api_url, f"extract-results/batch/{batch_id}")
        deadline = time.monotonic() + self.config.timeout
        result: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            client.notify(45, "MinerU 正在识别图、表格和公式...")
            status_payload = client.request_json("GET", status_url, headers=headers, expected=(200,))
            status_data = _mineru_response_data(status_payload)
            candidates = status_data.get("extract_result") or status_data.get("extract_results") or status_data.get("results") or []
            if isinstance(candidates, dict):
                candidates = [candidates]
            for candidate in candidates if isinstance(candidates, list) else []:
                if not isinstance(candidate, dict):
                    continue
                candidate_status = str(candidate.get("state") or candidate.get("status") or "").lower()
                if candidate_status in {"failed", "error"}:
                    raise CloudAPIError(str(candidate.get("err_msg") or candidate.get("message") or "MinerU parsing failed."), code="TASK_FAILED")
                if candidate_status in {"done", "completed", "success"}:
                    result = candidate
                    break
            if result is not None:
                break
            client.wait(self.config.poll_interval)
        if result is None:
            raise CloudAPIError("MinerU parsing timed out.", code="TIMEOUT")

        archive_url = str(result.get("full_zip_url") or result.get("fullZipUrl") or result.get("zip_url") or "").strip()
        if not archive_url:
            raise CloudAPIError("MinerU completed without a result archive.", code="INVALID_RESPONSE")
        client.notify(78, "正在下载 MinerU 解析结果...")
        archive = client.download(archive_url, engine_dir / "mineru_result.zip")
        safe_extract_zip(archive, raw_dir)
        client.notify(90, "正在整理 MinerU 图、表格和公式...")
        index = self._to_index(source, Path(output_dir), engine_dir, raw_dir)
        index["parserConfigVersion"] = self.config.config_version
        index["providerMode"] = "cloud-api"
        client.notify(100, "MinerU 云解析完成。")
        return index

    def _run_cli(self, pdf_path: Path, engine_dir: Path, raw_dir: Path, options: dict[str, Any], runtime_info: dict[str, Any]) -> None:
        backend = str(options.get("mineru_backend") or self.config.backend or "pipeline")
        log_path = Path(options.get("record_dir") or engine_dir.parent) / "logs" / "mineru_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        python = self.config.python or str(runtime_info.get("python") or "")
        command = str(runtime_info.get("command") or self.config.command or "mineru")
        if python:
            cmd = [
                python,
                "-m",
                "omnilit_qt.tools.mineru_worker",
                "--input",
                str(pdf_path),
                "--output",
                str(engine_dir),
                "--backend",
                backend,
                "--command",
                command,
            ]
        else:
            cmd = [command, "-p", str(pdf_path), "-o", str(raw_dir)]
            if backend:
                cmd.extend(["-b", backend])
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            _append_log(log_path, f"MinerU timed out after {self.config.timeout:g}s\n")
            if _has_usable_mineru_outputs(raw_dir):
                self._runtime_warnings.append(
                    {
                        "engine": self.name,
                        "level": "warning",
                        "code": "TIMEOUT_WITH_OUTPUT",
                        "message": f"MinerU timed out after {self.config.timeout:g}s, but parseable output was recovered.",
                        "type": "EngineWarning",
                    }
                )
                return
            raise EngineUnavailable(f"MinerU timed out after {self.config.timeout:g}s") from exc
        except OSError as exc:
            raise EngineUnavailable(f"Unable to start MinerU: {exc}") from exc
        _append_log(log_path, f"$ {' '.join(cmd)}\nSTDOUT\n{redact_sensitive_text(completed.stdout)}\nSTDERR\n{redact_sensitive_text(completed.stderr)}\n")
        if completed.returncode != 0:
            detail = redact_sensitive_text((completed.stderr or completed.stdout or "").strip())
            if _has_usable_mineru_outputs(raw_dir):
                self._runtime_warnings.append(
                    {
                        "engine": self.name,
                        "level": "warning",
                        "code": "NONZERO_WITH_OUTPUT",
                        "message": f"MinerU exited with code {completed.returncode}, but parseable output was recovered: {detail}",
                        "type": "EngineWarning",
                    }
                )
                return
            raise EngineUnavailable(f"MinerU failed with exit code {completed.returncode}: {detail}")

    def _to_index(self, pdf_path: Path, output_dir: Path, engine_dir: Path, raw_dir: Path) -> dict[str, Any]:
        pages = _extract_pdf_pages(pdf_path)
        index = make_base_index(pdf_path, output_dir, self.name, page_count=len(pages))
        index["pages"] = pages
        index["rawOutputs"]["mineru"] = str(engine_dir)

        discovered = discover_mineru_outputs(raw_dir)
        markdown_files = discovered["markdown_files"]
        markdown_path = engine_dir / "mineru.md"
        markdown_text = "\n\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in markdown_files)
        markdown_path.write_text(markdown_text, encoding="utf-8")
        index["markdownPath"] = str(markdown_path) if markdown_text or markdown_files else ""

        selected_json_files = select_mineru_json_files(discovered["json_files"])
        json_payloads = _load_json_files(raw_dir)
        elements = parse_mineru_json_files(selected_json_files, pages, engine_dir, raw_dir)
        counters = {"table": 0, "formula": 0, "figure": 0}
        if not elements:
            for block in _iter_layout_blocks(json_payloads):
                element_type = _element_type(block)
                if element_type not in counters:
                    continue
                page = _block_page_index(block, len(pages))
                page_size = _page_size(pages, page)
                bbox, flags = normalize_mineru_bbox(block.get("bbox") or block.get("box") or block.get("poly"), block.get("mineruPageSize") or block.get("page_size") or block.get("pageSize"), page_size)
                needs_review = not bbox or bool(flags)
                confidence = {"table": 0.82, "formula": 0.84, "figure": 0.78}[element_type] - (0.15 if not bbox else 0.0)
                counters[element_type] += 1
                element_id = f"p{page + 1}_mineru_{element_type}_{counters[element_type]}"
                text = _first_text(block, ("text", "latex", "caption", "markdown", "content"))
                html_value = _first_text(block, ("html", "table_html"))
                markdown_value = _first_text(block, ("markdown", "md"))
                table_rows: list[list[str]] = []
                csv_path = ""
                json_path = ""
                if element_type == "table":
                    table_rows = table_to_rows_from_mineru(block, markdown_value, html_value)
                    csv_path = str(_write_csv(engine_dir, element_id, table_rows)) if table_rows else ""
                    json_path = str(_write_json(engine_dir, element_id, block))
                png_path = _resolve_image_path(raw_dir, block) if element_type == "figure" else ""
                latex = _clean_latex(_first_text(block, ("latex", "latex_text", "text", "content"))) if element_type == "formula" else ""
                elements.append(
                    make_element(
                        element_id,
                        element_type,
                        page,
                        bbox,
                        page_size,
                        engine=self.name,
                        confidence=confidence,
                        needs_review=needs_review,
                        text=latex or text,
                        table=table_rows,
                        csv_path=csv_path,
                        json_path=json_path,
                        png_path=png_path,
                        latex=latex,
                        html=html_value,
                        markdown=markdown_value,
                        caption=str(block.get("caption") or ""),
                        raw=block,
                        structure_type=str(block.get("type") or block.get("block_type") or ""),
                        quality_flags=flags,
                    )
                )
        index["elements"] = elements
        for element in index["elements"]:
            if str(element.get("type") or "") == "figure" and element.get("pngPath"):
                path = Path(str(element.get("pngPath") or ""))
                if not path.is_absolute():
                    path = raw_dir / path
                element["pngPath"] = str(path) if path.exists() else str(element.get("pngPath") or "")
        index["raw"] = {"mineru": json_payloads}
        index["debugFiles"]["mineruLayoutPdf"] = str(discovered["layout_pdf"] or "")
        manifest = {
            "markdown_files": [str(path) for path in markdown_files],
            "json_files": [str(path) for path in discovered["json_files"]],
            "image_files": [str(path) for path in discovered["image_files"]],
            "html_files": [str(path) for path in discovered["html_files"]],
            "layout_pdf": str(discovered["layout_pdf"] or ""),
            "selected_json_files": [str(path) for path in selected_json_files],
        }
        (engine_dir / "mineru_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return index


def discover_mineru_outputs(raw_dir: Path) -> dict[str, Any]:
    raw = Path(raw_dir)
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    json_files = sorted(raw.rglob("*.json"))
    markdown_files = sorted(raw.rglob("*.md"))
    html_files = sorted(raw.rglob("*.html"))
    image_files = sorted(path for path in raw.rglob("*") if path.suffix.lower() in image_exts)
    layout_pdf = next((path for path in sorted(raw.rglob("layout.pdf")) if path.exists()), None)
    if layout_pdf is None:
        layout_pdf = next((path for path in sorted(raw.rglob("*layout*.pdf")) if path.exists()), None)
    return {
        "json_files": json_files,
        "markdown_files": markdown_files,
        "html_files": html_files,
        "image_files": image_files,
        "layout_pdf": layout_pdf,
    }


def select_mineru_json_files(files: list[Path]) -> list[Path]:
    ordered = sorted(Path(path) for path in files)
    content_lists = [path for path in ordered if path.name.endswith("_content_list.json")]
    if content_lists:
        return content_lists[:1]
    middle_files = [path for path in ordered if path.name.endswith("_middle.json")]
    if middle_files:
        return middle_files[:1]
    return ordered


def parse_mineru_json_files(files: list[Path], pymupdf_pages: list[dict[str, Any]], output_dir: Path | None = None, raw_dir: Path | None = None) -> list[dict[str, Any]]:
    counters = {"table": 0, "formula": 0, "figure": 0}
    elements: list[dict[str, Any]] = []
    table_dir = Path(output_dir or Path.cwd())
    selected_files = select_mineru_json_files(files)
    for path in selected_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source_format = "content_list" if path.name.endswith("_content_list.json") else "middle" if path.name.endswith("_middle.json") else "generic"
        for block in _iter_layout_blocks([payload]):
            element_type = _element_type(block)
            if element_type not in counters:
                continue
            page = _block_page_index(block, len(pymupdf_pages))
            page_size = _page_size(pymupdf_pages, page)
            source_page_size = [1000.0, 1000.0] if source_format == "content_list" else block.get("mineruPageSize") or block.get("page_size") or block.get("pageSize")
            bbox, flags = normalize_mineru_bbox(block.get("bbox") or block.get("box") or block.get("poly") or block.get("polygon"), source_page_size, page_size)
            needs_review = not bbox or bool(flags)
            confidence = {"table": 0.82, "formula": 0.84, "figure": 0.78}[element_type] - (0.15 if needs_review else 0.0)
            counters[element_type] += 1
            element_id = f"p{page + 1}_mineru_{element_type}_{counters[element_type]}"
            text = _first_text(block, ("text", "latex", "caption", "markdown", "content"))
            html_value = _first_text(block, ("html", "table_html", "table_body"))
            markdown_value = _first_text(block, ("markdown", "md"))
            table_rows: list[list[str]] = []
            csv_path = ""
            json_path = ""
            if element_type == "table":
                table_rows = table_to_rows_from_mineru(block, markdown_value, html_value)
                csv_path = str(_write_csv(table_dir, element_id, table_rows)) if table_rows else ""
                json_path = str(_write_json(table_dir, element_id, block))
            latex = _clean_latex(_first_text(block, ("latex", "latex_text", "text", "content"))) if element_type == "formula" else ""
            elements.append(
                make_element(
                    element_id,
                    element_type,
                    page,
                    bbox,
                    page_size,
                    engine="mineru",
                    confidence=confidence,
                    needs_review=needs_review,
                    text=latex or text,
                    table=table_rows,
                    csv_path=csv_path,
                    json_path=json_path,
                    png_path=_resolve_image_path(_raw_dir_for_parse(selected_files, raw_dir), block) if element_type in {"figure", "table"} else "",
                    latex=latex,
                    html=html_value,
                    markdown=markdown_value,
                    caption=_caption_text(block),
                    raw=block,
                    structure_type=str(block.get("type") or block.get("block_type") or ""),
                    quality_flags=flags,
                    metadata={
                        "tableSourceFormat": source_format,
                        "tableEvidenceScore": 0.92 if element_type == "table" and table_rows else 0.0,
                    },
                )
            )
    return _dedupe_mineru_elements(elements)


def _load_json_files(raw_dir: Path) -> list[Any]:
    payloads: list[Any] = []
    for path in sorted(raw_dir.rglob("*.json")):
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return payloads


def _iter_layout_blocks(payloads: list[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    def visit(value: Any, page: int | None = None, page_width: float = 0.0, page_height: float = 0.0) -> None:
        if isinstance(value, dict):
            local_page = _page_index_from_mapping(value, page)
            width = float(value.get("page_width") or value.get("width") or page_width or 0.0)
            height = float(value.get("page_height") or value.get("height") or page_height or 0.0)
            if any(key in value for key in ("type", "block_type", "category", "bbox", "latex", "html", "image_path")):
                item = dict(value)
                item.setdefault("page", local_page)
                if width and height:
                    item.setdefault("mineruPageSize", [width, height])
                blocks.append(item)
            for key in ("pages", "blocks", "layout", "spans", "items", "children"):
                child = value.get(key)
                if child is not None:
                    visit(child, local_page, width, height)
        elif isinstance(value, list):
            for item in value:
                visit(item, page, page_width, page_height)

    visit(payloads)
    return blocks


def _element_type(block: dict[str, Any]) -> str:
    label = str(block.get("type") or block.get("block_type") or block.get("category") or "").strip().lower()
    if label in {"table", "table_body"}:
        return "table"
    if label in {"image", "image_body", "figure", "figure_body", "fig", "chart", "pic", "picture"}:
        return "figure"
    if label in {"interline_equation", "inline_equation", "equation", "formula", "isolate_formula", "isolated_formula", "display_formula"}:
        return "formula"
    return ""


def _block_page_index(block: dict[str, Any], page_count: int = 0) -> int:
    page = _page_index_from_mapping(block, None)
    if page_count > 0:
        return max(0, min(page, page_count - 1))
    return max(0, page)


def _page_index_from_mapping(value: dict[str, Any], inherited: int | None = None) -> int:
    for key in ("page_idx", "page_index"):
        if key in value:
            return _safe_int(value.get(key), inherited or 0)
    for key in ("page_no", "page_num", "page_number", "pageNumber", "pageNum"):
        if key in value:
            return max(0, _safe_int(value.get(key), 1) - 1)
    if "page" in value:
        return max(0, _safe_int(value.get("page"), inherited or 0))
    return max(0, inherited or 0)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _scaled_bbox(block: dict[str, Any], page_size: list[float]) -> list[float]:
    bbox = normalize_bbox(block.get("bbox") or block.get("box") or block.get("poly"))
    if not bbox or bbox == [0.0, 0.0, 0.0, 0.0]:
        return []
    mineru_size = block.get("mineruPageSize") or block.get("page_size") or block.get("pageSize")
    if isinstance(mineru_size, (list, tuple)) and len(mineru_size) >= 2 and float(mineru_size[0] or 0) and float(mineru_size[1] or 0):
        sx = float(page_size[0]) / float(mineru_size[0])
        sy = float(page_size[1]) / float(mineru_size[1])
        return [bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy]
    return bbox


def normalize_mineru_bbox(raw_bbox: Any, mineru_page_size: Any, pymupdf_page_size: list[float]) -> tuple[list[float], list[str]]:
    flags: list[str] = []
    bbox = _bbox_from_mineru_value(raw_bbox)
    if not bbox:
        return [], ["missing_bbox"]
    page_width = float(pymupdf_page_size[0] if len(pymupdf_page_size) > 0 else 0.0)
    page_height = float(pymupdf_page_size[1] if len(pymupdf_page_size) > 1 else 0.0)
    if page_width <= 0 or page_height <= 0:
        return bbox, []

    if all(0.0 <= value <= 1.0 for value in bbox):
        bbox = [bbox[0] * page_width, bbox[1] * page_height, bbox[2] * page_width, bbox[3] * page_height]
    else:
        mineru_size = mineru_page_size
        if isinstance(mineru_size, dict):
            mineru_size = [mineru_size.get("width") or mineru_size.get("w"), mineru_size.get("height") or mineru_size.get("h")]
        if isinstance(mineru_size, (list, tuple)) and len(mineru_size) >= 2:
            try:
                mineru_width = float(mineru_size[0] or 0)
                mineru_height = float(mineru_size[1] or 0)
            except (TypeError, ValueError):
                mineru_width = mineru_height = 0.0
            if mineru_width and mineru_height and (abs(mineru_width - page_width) > 1 or abs(mineru_height - page_height) > 1):
                bbox = [bbox[0] * page_width / mineru_width, bbox[1] * page_height / mineru_height, bbox[2] * page_width / mineru_width, bbox[3] * page_height / mineru_height]

    if bbox[0] < -page_width * 0.2 or bbox[1] < -page_height * 0.2 or bbox[2] > page_width * 1.2 or bbox[3] > page_height * 1.2:
        flags.append("bbox_out_of_page")
    clipped = [max(0.0, min(page_width, bbox[0])), max(0.0, min(page_height, bbox[1])), max(0.0, min(page_width, bbox[2])), max(0.0, min(page_height, bbox[3]))]
    if clipped != bbox:
        flags.append("bbox_clipped")
    if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        return [], list(dict.fromkeys(flags + ["invalid_bbox"]))
    return clipped, list(dict.fromkeys(flags))


def table_to_rows_from_mineru(raw: dict[str, Any], markdown: str = "", html: str = "") -> list[list[str]]:
    for key in ("table", "rows", "table_body", "body", "cells"):
        value = raw.get(key)
        if isinstance(value, str) and "<table" in value.lower():
            rows = html_table_to_rows(value)
        else:
            rows = table_to_rows(value)
        if rows:
            return rows
    if html:
        rows = html_table_to_rows(html)
        if rows:
            return rows
    if markdown:
        rows = markdown_table_to_rows(markdown)
        if rows:
            return rows
    for key in ("text", "content"):
        value = str(raw.get(key) or "")
        rows = markdown_table_to_rows(value)
        if rows:
            return rows
    return []


def _bbox_from_mineru_value(value: Any) -> list[float]:
    if isinstance(value, dict):
        if all(key in value for key in ("x0", "y0", "x1", "y1")):
            return normalize_bbox(value)
        if "points" in value:
            return _bbox_from_mineru_value(value.get("points"))
    if isinstance(value, (list, tuple)):
        if len(value) >= 4 and all(isinstance(item, (int, float, str)) for item in value[:4]):
            return normalize_bbox(value)
        points: list[tuple[float, float]] = []
        for point in value:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                try:
                    points.append((float(point[0]), float(point[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(point, dict) and ("x" in point and "y" in point):
                try:
                    points.append((float(point["x"]), float(point["y"])))
                except (TypeError, ValueError):
                    continue
        if points:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            return [min(xs), min(ys), max(xs), max(ys)]
    return []


def _clean_latex(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^\${1,2}", "", text)
    text = re.sub(r"\${1,2}$", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _first_text(block: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = block.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            text = " ".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _caption_text(block: dict[str, Any]) -> str:
    return _first_text(block, ("caption", "table_caption", "image_caption", "figure_caption"))


def _dedupe_mineru_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for element in elements:
        bbox = normalize_bbox(element.get("bbox"))
        if bbox and bbox != [0.0, 0.0, 0.0, 0.0]:
            location = tuple(round(value, 1) for value in bbox)
        else:
            location = (str(element.get("text") or element.get("caption") or "")[:80],)
        key = (int(element.get("page") or 0), str(element.get("type") or ""), location)
        current = selected.get(key)
        if current is None or _mineru_element_quality(element) > _mineru_element_quality(current):
            selected[key] = element
    counters: dict[tuple[int, str], int] = {}
    result = []
    for element in sorted(selected.values(), key=lambda item: (int(item.get("page") or 0), float((item.get("bbox") or [0, 0])[1] or 0), str(item.get("type") or ""))):
        bucket = (int(element.get("page") or 0), str(element.get("type") or ""))
        counters[bucket] = counters.get(bucket, 0) + 1
        element["id"] = f"p{bucket[0] + 1}_mineru_{bucket[1]}_{counters[bucket]}"
        result.append(element)
    return result


def _mineru_element_quality(element: dict[str, Any]) -> tuple[int, int, int]:
    rows = element.get("table") or []
    return len(rows), len(str(element.get("html") or "")), len(str(element.get("text") or element.get("caption") or ""))


def _page_size(pages: list[dict[str, Any]], page: int) -> list[float]:
    if 0 <= page < len(pages):
        return [float(pages[page].get("width") or 0.0), float(pages[page].get("height") or 0.0)]
    return [0.0, 0.0]


def _extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:
    try:
        import fitz
    except Exception:
        return []
    pages: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            rect = page.rect
            pages.append({"page": page_index, "width": float(rect.width), "height": float(rect.height), "rect": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]})
    return pages


def _raw_dir_for_parse(files: list[Path], raw_dir: Path | None) -> Path:
    if raw_dir is not None:
        return Path(raw_dir)
    if files:
        return files[0].parent
    return Path.cwd()


def _resolve_image_path(raw_dir: Path, block: dict[str, Any]) -> str:
    for value in _image_path_candidates(block):
        path = Path(value)
        if not path.is_absolute():
            path = raw_dir / value
        if path.exists():
            return str(path)
    return ""


def _image_path_candidates(block: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("image_path", "img_path", "path", "file", "filename"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    for key in ("image", "img", "figure"):
        value = block.get(key)
        if isinstance(value, dict):
            candidates.extend(_image_path_candidates(value))
        elif isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    return list(dict.fromkeys(candidates))


def _write_csv(engine_dir: Path, element_id: str, rows: list[list[str]]) -> Path:
    path = engine_dir / f"{element_id}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)
    return path


def _write_json(engine_dir: Path, element_id: str, value: Any) -> Path:
    path = engine_dir / f"{element_id}.json"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def _has_usable_mineru_outputs(raw_dir: Path) -> bool:
    discovered = discover_mineru_outputs(raw_dir)
    for path in select_mineru_json_files(discovered["json_files"]):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload:
            return True
    return any(path.stat().st_size > 0 for path in discovered["markdown_files"] if path.exists())


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "auto"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _mineru_response_data(payload: dict[str, Any]) -> dict[str, Any]:
    code = payload.get("code")
    if code not in (None, 0, "0", 200, "200"):
        raise CloudAPIError(str(payload.get("msg") or payload.get("message") or "MinerU API rejected the request."), code="API_REJECTED")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise CloudAPIError("MinerU returned an invalid response.", code="INVALID_RESPONSE")
    return data


def _command_exists(command: str) -> bool:
    if not command:
        return False
    path = Path(command)
    if path.parent != Path("."):
        return path.exists()
    return shutil.which(command) is not None
