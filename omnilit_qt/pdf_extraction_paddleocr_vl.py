from __future__ import annotations

import csv
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .pdf_extraction_schema import make_base_index, make_element, normalize_bbox
from .pdf_extraction_settings import redact_sensitive_text
from .parser_runtime_manager import ParserRuntimeManager


class EngineUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PaddleOCRVLConfig:
    enabled: bool
    mode: str
    server_url: str
    model: str
    pipeline_version: str
    python: str
    timeout: float

    @classmethod
    def from_env(cls) -> "PaddleOCRVLConfig":
        return cls(
            enabled=_env_bool("OMNILIT_PADDLEOCR_VL_ENABLED", True),
            mode=os.environ.get("OMNILIT_PADDLEOCR_VL_MODE", "auto").strip().lower() or "auto",
            server_url=os.environ.get("OMNILIT_PADDLEOCR_VL_URL", "http://127.0.0.1:8118/v1").strip(),
            model=os.environ.get("OMNILIT_PADDLEOCR_VL_MODEL", "PaddlePaddle/PaddleOCR-VL-1.6").strip(),
            pipeline_version=os.environ.get("OMNILIT_PADDLEOCR_VL_PIPELINE_VERSION", "v1.6").strip(),
            python=os.environ.get("OMNILIT_PADDLEOCR_VL_PYTHON", "").strip(),
            timeout=_env_float("OMNILIT_PADDLEOCR_VL_TIMEOUT", 900.0),
        )


class PaddleOCRVLExtractionEngine:
    name = "paddleocr_vl"

    def __init__(self, config: PaddleOCRVLConfig | None = None, runtime_manager: ParserRuntimeManager | None = None) -> None:
        self.config = config or PaddleOCRVLConfig.from_env()
        self.runtime_manager = runtime_manager or ParserRuntimeManager()
        self._runtime_info: dict[str, Any] = {}

    def is_available(self) -> bool:
        return bool(self.availability().get("available"))

    def availability(self) -> dict[str, Any]:
        if not self.config.enabled or self.config.mode == "off":
            return {"available": False, "installable": False, "status": "off", "message": "PaddleOCR-VL 高精度引擎已禁用。"}
        if self.config.mode not in {"auto", "service", "subprocess", "cli"}:
            return {"available": False, "installable": False, "status": "invalid", "message": f"不支持的 PaddleOCR-VL 模式：{self.config.mode}"}
        info = self.runtime_manager.check_paddleocr_vl_available()
        if self.config.python and Path(self.config.python).exists():
            info = {"available": True, "installable": False, "status": "managed", "python": self.config.python, "serviceUrl": self.config.server_url, "command": "", "message": "PaddleOCR-VL 独立运行环境可用。"}
        elif self.config.mode == "service" and info.get("status") != "service":
            info = {"available": False, "installable": False, "status": "not_initialized", "message": "PaddleOCR-VL 服务未启动，已尝试使用 MinerU fallback。"}
        elif self.config.mode == "subprocess" and not self.config.python:
            info = {"available": False, "installable": False, "status": "not_initialized", "message": "PaddleOCR-VL 本地运行环境未初始化，已尝试使用 MinerU fallback。"}
        self._runtime_info = dict(info)
        return dict(info)

    def bootstrap_paddleocr_vl_service(self) -> dict[str, Any]:
        info = self.runtime_manager.check_paddleocr_vl_available()
        if info.get("available"):
            return info
        return {
            "available": False,
            "installable": bool(info.get("installable")),
            "message": "PaddleOCR-VL 依赖和模型较大，请先启动本地服务、配置独立环境，或使用 Docker 部署服务后重试。",
            "status": info.get("status") or "not_initialized",
        }

    def is_locally_runnable(self) -> bool:
        info = self.availability()
        return bool(info.get("python") or info.get("command"))

    def _effective_mode(self) -> str:
        if self.config.mode != "auto":
            return self.config.mode
        status = str(self._runtime_info.get("status") or "")
        if status == "service":
            return "service"
        if status == "cli":
            return "cli"
        return "subprocess"

    def _effective_python(self) -> str:
        return self.config.python or str(self._runtime_info.get("python") or "")

    def _effective_command(self) -> str:
        return str(self._runtime_info.get("command") or "")

    def _effective_server_url(self) -> str:
        return str(self._runtime_info.get("serviceUrl") or self.config.server_url or "")

    def _raise_not_initialized(self) -> None:
        raise EngineUnavailable("PaddleOCR-VL 高精度引擎尚未初始化，已尝试使用 MinerU fallback。")

    def _can_run_worker(self) -> bool:
        return bool(self._effective_python())

    def _can_run_cli(self) -> bool:
        return bool(self._effective_command())

    def _ensure_ready_for_analyze(self) -> None:
        info = self.availability()
        if not info.get("available"):
            self._raise_not_initialized()
        if not self._can_run_worker() and not self._can_run_cli():
            self._raise_not_initialized()

    def _run_cli(self, pdf_path: Path, engine_dir: Path) -> None:
        command = self._effective_command()
        if not command:
            self._raise_not_initialized()
        cmd = [command, "doc_parser", "-i", str(pdf_path), "-o", str(engine_dir)]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.timeout, check=False)
        except Exception as exc:
            raise EngineUnavailable(f"无法启动 PaddleOCR-VL CLI：{exc}") from exc
        if completed.returncode != 0:
            detail = redact_sensitive_text((completed.stderr or completed.stdout or "").strip())
            raise EngineUnavailable(f"PaddleOCR-VL CLI 解析失败：{detail}")

    def _result_ready(self, engine_dir: Path) -> bool:
        return (engine_dir / "paddleocr_vl_result.json").exists()

    def _load_result(self, engine_dir: Path) -> dict[str, Any]:
        result_path = engine_dir / "paddleocr_vl_result.json"
        if result_path.exists():
            value = json.loads(result_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        matches = sorted(engine_dir.rglob("*.json"))
        if matches:
            value = json.loads(matches[0].read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"blocks": value}
        return {}

    def _write_merged_markdown(self, engine_dir: Path) -> Path:
        markdown_path = engine_dir / "paddleocr_vl.md"
        if markdown_path.exists():
            return markdown_path
        parts = [path.read_text(encoding="utf-8", errors="ignore") for path in sorted(engine_dir.rglob("*.md"))]
        markdown_path.write_text("\n\n".join(parts), encoding="utf-8")
        return markdown_path

    def _maybe_write_normalized_result(self, engine_dir: Path, result: dict[str, Any]) -> None:
        target = engine_dir / "paddleocr_vl_result.json"
        if not target.exists():
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def _is_service_only(self) -> bool:
        return self._effective_mode() == "service" and not self._can_run_worker()

    def _service_only_unimplemented(self) -> None:
        raise EngineUnavailable("PaddleOCR-VL 服务已发现，但当前需要独立 Python worker 或 paddleocr CLI 来归一化结果，已尝试使用 MinerU fallback。")

    def _mode_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.mode == "off":
            return False
        return True

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = dict(options or {})
        if not self._mode_available():
            self._raise_not_initialized()
        self._ensure_ready_for_analyze()

        source = Path(pdf_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"PDF file does not exist: {source}")

        engine_dir = Path(output_dir) / self.name
        engine_dir.mkdir(parents=True, exist_ok=True)
        if self._is_service_only():
            self._service_only_unimplemented()
        if self._can_run_worker():
            self._run_worker(source, engine_dir, options)
        elif self._can_run_cli():
            self._run_cli(source, engine_dir)

        if not self._result_ready(engine_dir) and not list(engine_dir.rglob("*.json")):
            raise EngineUnavailable("PaddleOCR-VL 没有生成可读取的 JSON 结果，已尝试使用 MinerU fallback。")
        result = self._load_result(engine_dir)
        self._maybe_write_normalized_result(engine_dir, result)
        markdown_path = self._write_merged_markdown(engine_dir)
        markdown_text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        return self._to_index(source, Path(output_dir), engine_dir, result, markdown_path, markdown_text)

    def _run_worker(self, pdf_path: Path, engine_dir: Path, options: dict[str, Any]) -> None:
        cmd = [
            self._effective_python(),
            "-m",
            "omnilit_qt.tools.paddleocr_vl_worker",
            "--input",
            str(pdf_path),
            "--output",
            str(engine_dir),
            "--model",
            str(options.get("model") or self.config.model),
            "--pipeline-version",
            str(options.get("pipeline_version") or self.config.pipeline_version),
            "--engine",
            str(options.get("paddleocr_vl_engine") or ("server" if self._effective_mode() == "service" else "paddle")),
        ]
        server_url = str(options.get("server_url") or self._effective_server_url()).strip()
        if self._effective_mode() == "service" and server_url:
            cmd.extend(["--server-url", server_url])
        if bool(options.get("merge_tables", True)):
            cmd.append("--merge-tables")
        if bool(options.get("relevel_titles", True)):
            cmd.append("--relevel-titles")

        env = os.environ.copy()
        repo_root = str(Path(__file__).resolve().parents[1])
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = repo_root if not existing_pythonpath else repo_root + os.pathsep + existing_pythonpath

        try:
            completed = subprocess.run(
                cmd,
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineUnavailable(f"PaddleOCR-VL timed out after {self.config.timeout:g}s") from exc
        except OSError as exc:
            raise EngineUnavailable(f"Unable to start PaddleOCR-VL worker: {exc}") from exc

        if completed.returncode != 0:
            detail = redact_sensitive_text((completed.stderr or completed.stdout or "").strip())
            raise EngineUnavailable(f"PaddleOCR-VL worker failed with exit code {completed.returncode}: {detail}")

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


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    return 0


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
        for key in ("blocks", "layout", "elements", "items", "results", "pages"):
            child = value.get(key)
            if isinstance(child, list):
                for item in child:
                    blocks.extend(_iter_blocks(item, current_page))
        for key in ("json", "raw"):
            child = value.get(key)
            if isinstance(child, (dict, list)):
                blocks.extend(_iter_blocks(child, current_page))
    elif isinstance(value, list):
        for item in value:
            blocks.extend(_iter_blocks(item, inherited_page))
    return blocks


def _block_label(block: dict[str, Any]) -> str:
    for key in ("block_label", "label", "type", "category", "structureType"):
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
    for key in ("bbox", "box", "coordinate", "coordinates", "position"):
        bbox = normalize_bbox(block.get(key))
        if len(bbox) == 4 and any(bbox):
            return bbox
    return []


def _block_text(block: dict[str, Any]) -> str:
    for key in ("text", "content", "caption", "markdown", "latex"):
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
