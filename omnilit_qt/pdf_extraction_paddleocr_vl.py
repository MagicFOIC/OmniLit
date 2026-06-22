from __future__ import annotations

import csv
import html
import json
import os
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .pdf_cloud_client import CloudAPIClient, CloudAPIError, join_api_url
from .pdf_extraction_schema import make_base_index, make_element, normalize_bbox
from .pdf_extraction_settings import (
    PARSER_CONFIG_VERSION,
    parser_api_token,
    parser_api_url,
    parser_service_enabled,
)


class EngineUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PaddleOCRVLConfig:
    enabled: bool
    job_url: str
    model: str
    timeout: float
    api_token: str = ""
    poll_interval: float = 5.0
    config_version: str = PARSER_CONFIG_VERSION

    @classmethod
    def from_env(cls, store: Any | None = None) -> "PaddleOCRVLConfig":
        return cls(
            enabled=parser_service_enabled(store, "paddleocr_vl"),
            job_url=parser_api_url(store, "paddleocr_vl"),
            model=os.environ.get("OMNILIT_PADDLEOCR_VL_MODEL", "PaddleOCR-VL-1.6").strip() or "PaddleOCR-VL-1.6",
            timeout=_env_float("OMNILIT_PADDLEOCR_VL_TIMEOUT", 900.0),
            api_token=parser_api_token(store, "paddleocr_vl"),
            poll_interval=_env_float("OMNILIT_PADDLEOCR_VL_POLL_INTERVAL", 5.0),
        )


class PaddleOCRVLExtractionEngine:
    name = "paddleocr_vl"

    def __init__(self, config: PaddleOCRVLConfig | None = None, store: Any | None = None) -> None:
        self.config = config or PaddleOCRVLConfig.from_env(store)

    def is_available(self) -> bool:
        return bool(self.availability().get("available"))

    def availability(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"available": False, "status": "off", "message": "PaddleOCR-VL 高精度引擎已禁用。"}
        configured = bool(self.config.api_token and self.config.job_url)
        return {
            "available": configured,
            "status": "ready" if configured else "not_configured",
            "message": "PaddleOCR-VL cloud API is configured." if configured else "Configure the PaddleOCR-VL API token in system settings.",
        }

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = dict(options or {})
        if not self.is_available():
            raise EngineUnavailable(str(self.availability().get("message") or "PaddleOCR-VL API is not configured."))
        return self._analyze_api(pdf_path, output_dir, options)

    def _analyze_api(self, pdf_path: Path, output_dir: Path, options: dict[str, Any]) -> dict[str, Any]:
        if not self.config.api_token or not self.config.job_url:
            raise EngineUnavailable("Configure the PaddleOCR-VL API token in system settings.")
        source = Path(pdf_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"PDF file does not exist: {source}")
        engine_dir = Path(output_dir) / self.name
        engine_dir.mkdir(parents=True, exist_ok=True)
        callback = options.get("progress_callback")
        cancel_event = options.get("cancel_event")
        client = CloudAPIClient(
            self.name,
            timeout=self.config.timeout,
            cancel_event=cancel_event if hasattr(cancel_event, "is_set") else None,
            progress=callback if callable(callback) else None,
        )
        headers = {"Authorization": f"bearer {self.config.api_token}"}
        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }
        client.notify(28, "正在上传 PDF 到 PaddleOCR-VL...")
        with source.open("rb") as handle:
            response = client.request_json(
                "POST",
                self.config.job_url,
                headers=headers,
                data={"model": self.config.model, "optionalPayload": json.dumps(optional_payload)},
                files={"file": (source.name, handle, "application/pdf")},
                expected=(200,),
                request_timeout=self.config.timeout,
            )
        job_id = str(_paddle_response_data(response).get("jobId") or "").strip()
        if not job_id:
            raise CloudAPIError("PaddleOCR-VL did not return a job ID.", code="INVALID_RESPONSE")

        status_url = join_api_url(self.config.job_url, job_id)
        deadline = time.monotonic() + self.config.timeout
        jsonl_url = ""
        while time.monotonic() < deadline:
            status_payload = client.request_json("GET", status_url, headers=headers, expected=(200,))
            status_data = _paddle_response_data(status_payload)
            state = str(status_data.get("state") or "").strip().lower()
            if state in {"pending", "running"}:
                progress = status_data.get("extractProgress") if isinstance(status_data.get("extractProgress"), dict) else {}
                total = _safe_int(progress.get("totalPages"))
                extracted = _safe_int(progress.get("extractedPages"))
                percent = 45 if not total else min(75, 35 + int(40 * extracted / max(1, total)))
                client.notify(percent, f"PaddleOCR-VL 正在解析页面：{extracted}/{total}" if total else "PaddleOCR-VL 正在解析文档...")
                client.wait(self.config.poll_interval)
                continue
            if state == "failed":
                raise CloudAPIError(str(status_data.get("errorMsg") or "PaddleOCR-VL parsing failed."), code="TASK_FAILED")
            if state == "done":
                result_url = status_data.get("resultUrl") if isinstance(status_data.get("resultUrl"), dict) else {}
                jsonl_url = str(result_url.get("jsonUrl") or "").strip()
                break
            raise CloudAPIError(f"PaddleOCR-VL returned an unknown job state: {state or 'missing'}", code="INVALID_RESPONSE")
        if not jsonl_url:
            raise CloudAPIError("PaddleOCR-VL parsing timed out or completed without a JSONL URL.", code="TIMEOUT")

        client.notify(78, "正在下载 PaddleOCR-VL 解析结果...")
        jsonl_path = client.download(jsonl_url, engine_dir / "paddleocr_vl_result.jsonl")
        result = _parse_paddle_jsonl(jsonl_path)
        client.notify(78, "正在整理 PaddleOCR-VL 图、表格和公式...")
        (engine_dir / "paddleocr_vl_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_images = _download_api_images(client, result, engine_dir)
        markdown_text = _collect_api_markdown(result)
        markdown_path = engine_dir / "paddleocr_vl.md"
        markdown_path.write_text(markdown_text, encoding="utf-8")
        index = self._to_index(source, Path(output_dir), engine_dir, result, markdown_path, markdown_text)
        figures = [element for element in index.get("elements", []) if element.get("type") == "figure"]
        for element, image_path in zip(figures, saved_images):
            element["pngPath"] = str(image_path)
        index["parserConfigVersion"] = self.config.config_version
        index["providerMode"] = "cloud-api"
        client.notify(100, "PaddleOCR-VL 云解析完成。")
        return index

    def _to_index(
        self,
        pdf_path: Path,
        output_dir: Path,
        engine_dir: Path,
        result: dict[str, Any],
        markdown_path: Path,
        markdown_text: str,
    ) -> dict[str, Any]:
        pages = _extract_pdf_pages(pdf_path)
        page_count = max(len(pages), _page_count_from_result(result))
        index = make_base_index(pdf_path, output_dir, self.name, page_count=page_count)
        index["engineChain"] = [self.name]
        index["pages"] = pages or [{"page": page, "width": 0.0, "height": 0.0, "rect": [0.0, 0.0, 0.0, 0.0]} for page in range(page_count)]
        index["markdownPath"] = str(markdown_path) if markdown_path.exists() else ""
        index["rawOutputs"][self.name] = str(engine_dir)

        text_blocks_by_page = {int(page.get("page") or 0): page.get("textBlocks") or [] for page in index["pages"]}
        elements: list[dict[str, Any]] = []
        table_counter = 0
        figure_counter = 0
        formula_counter = 0
        for raw_block in _iter_blocks(result):
            label = _block_label(raw_block)
            element_type = _element_type_from_label(label)
            page = _block_page(raw_block)
            if element_type is None:
                _append_text_block(index["pages"], raw_block, page)
                continue

            page_size = _page_size(index["pages"], page)
            bbox = _block_bbox(raw_block)
            text = _block_text(raw_block)
            if not bbox:
                bbox = _fuzzy_match_bbox(text, text_blocks_by_page.get(page, []))
            has_bbox = bool(bbox)
            confidence = 0.88 if has_bbox else 0.65
            needs_review = not has_bbox

            rows = _table_rows(raw_block)
            csv_path = ""
            json_path = ""
            if element_type == "table":
                table_counter += 1
                element_id = f"p{page + 1}_paddleocr_vl_table_{table_counter}"
                if rows:
                    csv_path, json_path = _write_table_outputs(engine_dir, element_id, rows)
            elif element_type == "formula":
                formula_counter += 1
                element_id = f"p{page + 1}_paddleocr_vl_formula_{formula_counter}"
            else:
                figure_counter += 1
                element_id = f"p{page + 1}_paddleocr_vl_figure_{figure_counter}"

            markdown = str(raw_block.get("markdown") or raw_block.get("md") or "")
            latex = markdown if element_type == "formula" else str(raw_block.get("latex") or "")
            if element_type == "formula" and not latex:
                latex = text

            elements.append(
                make_element(
                    element_id,
                    element_type,
                    page,
                    bbox if has_bbox else [],
                    page_size,
                    engine=self.name,
                    confidence=confidence,
                    needs_review=needs_review,
                    text=text,
                    table=rows,
                    csv_path=csv_path,
                    json_path=json_path,
                    markdown=markdown,
                    html=str(raw_block.get("html") or ""),
                    latex=latex,
                    caption=str(raw_block.get("caption") or ""),
                    raw=raw_block,
                    source_element_id=str(raw_block.get("id") or raw_block.get("block_id") or ""),
                    structure_type=label,
                )
            )

        index["elements"] = elements
        index["raw"] = {"paddleocr_vl": result}
        if markdown_text and not index["markdownPath"]:
            index["raw"]["markdown"] = markdown_text
        return index


def markdown_table_to_rows(markdown_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in str(markdown_text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        if any(cells):
            rows.append(cells)
    return rows


def html_table_to_rows(html_text: str) -> list[list[str]]:
    parser = _HTMLTableParser()
    parser.feed(str(html_text or ""))
    return parser.rows


class _HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._current_row = []
        elif tag.lower() in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"td", "th"} and self._current_row is not None and self._current_cell is not None:
            self._current_row.append(html.unescape("".join(self._current_cell)).strip())
            self._current_cell = None
        elif lowered == "tr" and self._current_row is not None:
            if any(self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None


def _paddle_response_data(payload: dict[str, Any]) -> dict[str, Any]:
    code = payload.get("code", payload.get("errorCode"))
    if code not in (None, 0, "0", 200, "200"):
        raise CloudAPIError(str(payload.get("errorMsg") or payload.get("message") or "PaddleOCR API failed."), code="API_FAILED")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CloudAPIError("PaddleOCR returned an invalid data object.", code="INVALID_RESPONSE")
    return data


def _parse_paddle_jsonl(path: Path) -> dict[str, Any]:
    layout_results: list[Any] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CloudAPIError(f"PaddleOCR returned invalid JSONL on line {line_number}.", code="INVALID_RESPONSE") from exc
        if not isinstance(payload, dict):
            raise CloudAPIError(f"PaddleOCR returned an invalid JSONL value on line {line_number}.", code="INVALID_RESPONSE")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise CloudAPIError(f"PaddleOCR JSONL line {line_number} has no result object.", code="INVALID_RESPONSE")
        pages = result.get("layoutParsingResults")
        if isinstance(pages, list):
            layout_results.extend(pages)
        else:
            layout_results.append(result)
    if not layout_results:
        raise CloudAPIError("PaddleOCR returned an empty JSONL result.", code="INVALID_RESPONSE")
    return {"layoutParsingResults": layout_results}


def _collect_api_markdown(value: Any) -> str:
    if isinstance(value, dict) and isinstance(value.get("layoutParsingResults"), list):
        page_parts: list[str] = []
        for page in value["layoutParsingResults"]:
            if not isinstance(page, dict):
                continue
            markdown = page.get("markdown")
            text = str(markdown.get("text") or "").strip() if isinstance(markdown, dict) else str(markdown or "").strip()
            if text:
                page_parts.append(text)
        if page_parts:
            return "\n\n".join(page_parts)

    parts: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            markdown = item.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                parts.append(markdown.strip())
            elif isinstance(markdown, dict):
                text = str(markdown.get("text") or "").strip()
                if text:
                    parts.append(text)
            for key, child in item.items():
                if key != "markdown":
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return "\n\n".join(parts)


def _download_api_images(client: CloudAPIClient, value: Any, engine_dir: Path) -> list[Path]:
    figure_assets: list[Path] = []
    seen_targets: set[Path] = set()

    def download_mapping(mapping: dict[str, Any], *, preserve_path: bool) -> None:
        for name, remote_url in mapping.items():
            if not isinstance(remote_url, str) or not remote_url.startswith(("https://", "http://")):
                continue
            target = _paddle_image_target(engine_dir, str(name), remote_url, preserve_path, len(seen_targets) + 1)
            if target in seen_targets:
                continue
            client.download(remote_url, target)
            seen_targets.add(target)
            if preserve_path:
                figure_assets.append(target)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            markdown = item.get("markdown")
            if isinstance(markdown, dict) and isinstance(markdown.get("images"), dict):
                download_mapping(markdown["images"], preserve_path=True)
            output_images = item.get("outputImages")
            if isinstance(output_images, dict):
                download_mapping(output_images, preserve_path=False)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return figure_assets


def _paddle_image_target(engine_dir: Path, name: str, remote_url: str, preserve_path: bool, number: int) -> Path:
    raw_name = str(name or "").replace("\\", "/").strip("/")
    relative = Path(raw_name) if raw_name else Path(f"image_{number}.jpg")
    if relative.is_absolute() or ".." in relative.parts:
        raise CloudAPIError("PaddleOCR returned an unsafe image path.", code="UNSAFE_ASSET_PATH")
    if not relative.suffix:
        url_suffix = Path(urlsplit(remote_url).path).suffix
        relative = relative.with_suffix(url_suffix if url_suffix else ".jpg")
    if preserve_path:
        target = engine_dir / relative
    else:
        target = engine_dir / "images" / f"{relative.stem}_{number}{relative.suffix}"
    root = engine_dir.resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CloudAPIError("PaddleOCR returned an unsafe image path.", code="UNSAFE_ASSET_PATH") from exc
    return resolved


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:
    try:
        import fitz
    except Exception:
        return []
    pages: list[dict[str, Any]] = []
    try:
        with fitz.open(pdf_path) as document:
            for page_index in range(len(document)):
                page = document.load_page(page_index)
                rect = page.rect
                text_blocks = []
                for raw in page.get_text("blocks") or []:
                    if len(raw) >= 5 and str(raw[4] or "").strip():
                        text_blocks.append(
                            {
                                "bbox": [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])],
                                "text": str(raw[4] or "").strip(),
                            }
                        )
                pages.append(
                    {
                        "page": page_index,
                        "width": float(rect.width),
                        "height": float(rect.height),
                        "rect": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)],
                        "textBlocks": text_blocks,
                    }
                )
    except Exception:
        return []
    return pages


def _page_count_from_result(result: dict[str, Any]) -> int:
    pages = result.get("pages")
    if isinstance(pages, list):
        return len(pages)
    layout_results = result.get("layoutParsingResults")
    if isinstance(layout_results, list):
        return len(layout_results)
    return 0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iter_blocks(value: Any, inherited_page: int | None = None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(value, dict):
        current_page = inherited_page
        for key in ("page", "page_index", "page_idx"):
            if key in value:
                try:
                    current_page = max(0, int(value[key]))
                except (TypeError, ValueError):
                    pass
        for key in ("page_no", "pageNumber", "page_num"):
            if key in value:
                try:
                    current_page = max(0, int(value[key]) - 1)
                except (TypeError, ValueError):
                    pass
        if _block_label(value):
            item = dict(value)
            if current_page is not None and not any(page_key in item for page_key in ("page", "page_index", "page_idx", "page_no", "pageNumber", "page_num")):
                item["page"] = current_page
            blocks.append(item)
        for key in ("blocks", "layout", "elements", "items", "results", "pages", "layoutParsingResults", "prunedResult", "layoutDetections", "parsing_res_list", "layout_det_res"):
            child = value.get(key)
            if isinstance(child, list):
                for index, item in enumerate(child):
                    page = index if key == "layoutParsingResults" and current_page is None else current_page
                    blocks.extend(_iter_blocks(item, page))
            elif isinstance(child, dict):
                blocks.extend(_iter_blocks(child, current_page))
        for key in ("json", "raw"):
            child = value.get(key)
            if isinstance(child, (dict, list)):
                blocks.extend(_iter_blocks(child, current_page))
    elif isinstance(value, list):
        for item in value:
            blocks.extend(_iter_blocks(item, inherited_page))
    return blocks


def _block_label(block: dict[str, Any]) -> str:
    for key in ("block_label", "label", "type", "category", "structureType", "layout_type"):
        value = str(block.get(key) or "").strip().lower()
        if value:
            return value
    return ""


def _element_type_from_label(label: str) -> str | None:
    normalized = label.strip().lower()
    if normalized in {"table"}:
        return "table"
    if normalized in {"formula", "equation"}:
        return "formula"
    if normalized in {"image", "figure", "chart"}:
        return "figure"
    return None


def _block_page(block: dict[str, Any]) -> int:
    for key in ("page", "page_index", "page_idx"):
        if key in block:
            try:
                return max(0, int(block[key]))
            except (TypeError, ValueError):
                return 0
    for key in ("page_no", "pageNumber", "page_num"):
        if key in block:
            try:
                return max(0, int(block[key]) - 1)
            except (TypeError, ValueError):
                return 0
    return 0


def _block_bbox(block: dict[str, Any]) -> list[float]:
    for key in ("bbox", "block_bbox", "box", "coordinate", "coordinates", "position"):
        bbox = normalize_bbox(block.get(key))
        if len(bbox) == 4 and any(bbox):
            return bbox
    return []


def _block_text(block: dict[str, Any]) -> str:
    for key in ("text", "block_content", "content", "caption", "markdown", "latex"):
        value = str(block.get(key) or "").strip()
        if value:
            return value
    rows = _table_rows(block)
    if rows:
        return "\n".join("\t".join(row) for row in rows)
    return ""


def _table_rows(block: dict[str, Any]) -> list[list[str]]:
    table = block.get("table") or block.get("table_data") or block.get("cells")
    if isinstance(table, list):
        if all(isinstance(row, list) for row in table):
            return [[str(cell or "").strip() for cell in row] for row in table if any(str(cell or "").strip() for cell in row)]
        if all(isinstance(row, dict) for row in table):
            return [[str(value or "").strip() for value in row.values()] for row in table]
    markdown_rows = markdown_table_to_rows(str(block.get("markdown") or block.get("md") or ""))
    if markdown_rows:
        return markdown_rows
    return html_table_to_rows(str(block.get("html") or ""))


def _write_table_outputs(engine_dir: Path, element_id: str, rows: list[list[str]]) -> tuple[str, str]:
    table_dir = engine_dir / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    csv_path = table_dir / f"{element_id}.csv"
    json_path = table_dir / f"{element_id}.json"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump({"rows": rows}, handle, ensure_ascii=False, indent=2)
    return str(csv_path), str(json_path)


def _page_size(pages: list[dict[str, Any]], page: int) -> list[float]:
    for item in pages:
        if int(item.get("page") or 0) == page:
            return [float(item.get("width") or 0.0), float(item.get("height") or 0.0)]
    return [0.0, 0.0]


def _append_text_block(pages: list[dict[str, Any]], raw_block: dict[str, Any], page: int) -> None:
    text = _block_text(raw_block)
    if not text:
        return
    bbox = _block_bbox(raw_block)
    for item in pages:
        if int(item.get("page") or 0) == page:
            item.setdefault("textBlocks", []).append({"bbox": bbox, "text": text, "engine": "paddleocr_vl", "raw": raw_block})
            return


def _fuzzy_match_bbox(text: str, text_blocks: list[dict[str, Any]]) -> list[float]:
    needle = _compact_text(text)
    if len(needle) < 8:
        return []
    best_score = 0.0
    best_bbox: list[float] = []
    for block in text_blocks:
        haystack = _compact_text(str(block.get("text") or ""))
        if not haystack:
            continue
        if needle in haystack or haystack in needle:
            score = min(len(needle), len(haystack)) / max(len(needle), len(haystack))
        else:
            overlap = len(set(needle.split()) & set(haystack.split()))
            score = overlap / max(1, len(set(needle.split())))
        if score > best_score:
            best_score = score
            best_bbox = normalize_bbox(block.get("bbox"))
    return best_bbox if best_score >= 0.72 and len(best_bbox) == 4 else []


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())
