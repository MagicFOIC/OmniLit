from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parser_runtime_manager import ParserRuntimeManager
from .pdf_extraction_schema import make_base_index, make_element, normalize_bbox
from .pdf_extraction_settings import redact_sensitive_text
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

    @classmethod
    def from_env(cls) -> "MinerUConfig":
        return cls(
            enabled=_env_bool("OMNILIT_MINERU_ENABLED", True),
            mode=os.environ.get("OMNILIT_MINERU_MODE", "auto").strip().lower() or "auto",
            command=os.environ.get("OMNILIT_MINERU_COMMAND", "mineru").strip() or "mineru",
            python=os.environ.get("OMNILIT_MINERU_PYTHON", "").strip(),
            api_url=os.environ.get("OMNILIT_MINERU_API_URL", "http://127.0.0.1:8000").strip(),
            timeout=_env_float("OMNILIT_MINERU_TIMEOUT", 900.0),
            backend=os.environ.get("OMNILIT_MINERU_BACKEND", "pipeline").strip() or "pipeline",
        )


class MinerUExtractionEngine:
    name = "mineru"

    def __init__(self, config: MinerUConfig | None = None, runtime_manager: ParserRuntimeManager | None = None) -> None:
        self.config = config or MinerUConfig.from_env()
        self.runtime_manager = runtime_manager or ParserRuntimeManager()
        self._runtime_info: dict[str, Any] = {}

    def is_available(self) -> bool:
        return bool(self.availability().get("available"))

    def availability(self) -> dict[str, Any]:
        if not self.config.enabled or self.config.mode == "off":
            return {"available": False, "installable": False, "status": "off", "message": "MinerU deep parser is disabled."}
        if self.config.mode == "api":
            return {"available": False, "installable": False, "status": "reserved", "message": "MinerU API mode is reserved; CLI is used for now."}
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
        self._run_cli(source, engine_dir, raw_dir, options, runtime_info)
        return self._to_index(source, Path(output_dir), engine_dir, raw_dir)

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
            raise EngineUnavailable(f"MinerU timed out after {self.config.timeout:g}s") from exc
        except OSError as exc:
            raise EngineUnavailable(f"Unable to start MinerU: {exc}") from exc
        _append_log(log_path, f"$ {' '.join(cmd)}\nSTDOUT\n{redact_sensitive_text(completed.stdout)}\nSTDERR\n{redact_sensitive_text(completed.stderr)}\n")
        if completed.returncode != 0:
            detail = redact_sensitive_text((completed.stderr or completed.stdout or "").strip())
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

        json_payloads = _load_json_files(raw_dir)
        elements = parse_mineru_json_files(discovered["json_files"], pages, engine_dir)
        counters = {"table": 0, "formula": 0, "figure": 0}
        if not elements:
            for block in _iter_layout_blocks(json_payloads):
                element_type = _element_type(block)
                if element_type not in counters:
                    continue
                page = max(0, int(block.get("page") or block.get("page_idx") or block.get("page_no") or 0))
                page_size = _page_size(pages, page)
                bbox, flags = normalize_mineru_bbox(block.get("bbox") or block.get("box") or block.get("poly"), block.get("mineruPageSize") or block.get("page_size") or block.get("pageSize"), page_size)
                needs_review = not bbox or bool(flags)
                confidence = {"table": 0.82, "formula": 0.84, "figure": 0.78}[element_type] - (0.15 if not bbox else 0.0)
                counters[element_type] += 1
                element_id = f"p{page + 1}_mineru_{element_type}_{counters[element_type]}"
                text = str(block.get("text") or block.get("latex") or block.get("caption") or block.get("markdown") or block.get("content") or "")
                html_value = str(block.get("html") or "")
                markdown_value = str(block.get("markdown") or "")
                table_rows: list[list[str]] = []
                csv_path = ""
                json_path = ""
                if element_type == "table":
                    table_rows = table_to_rows_from_mineru(block, markdown_value, html_value)
                    csv_path = str(_write_csv(engine_dir, element_id, table_rows)) if table_rows else ""
                    json_path = str(_write_json(engine_dir, element_id, block))
                png_path = _resolve_image_path(raw_dir, block) if element_type == "figure" else ""
                latex = _clean_latex(str(block.get("latex") or text)) if element_type == "formula" else ""
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
    return {
        "json_files": json_files,
        "markdown_files": markdown_files,
        "html_files": html_files,
        "image_files": image_files,
        "layout_pdf": layout_pdf,
    }


def parse_mineru_json_files(files: list[Path], pymupdf_pages: list[dict[str, Any]], output_dir: Path | None = None) -> list[dict[str, Any]]:
    payloads = []
    for path in files:
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    counters = {"table": 0, "formula": 0, "figure": 0}
    elements: list[dict[str, Any]] = []
    table_dir = Path(output_dir or Path.cwd())
    for block in _iter_layout_blocks(payloads):
            element_type = _element_type(block)
            if element_type not in counters:
                continue
            page = max(0, int(block.get("page") or block.get("page_idx") or block.get("page_no") or 0))
            page_size = _page_size(pymupdf_pages, page)
            bbox, flags = normalize_mineru_bbox(block.get("bbox") or block.get("box") or block.get("poly") or block.get("polygon"), block.get("mineruPageSize") or block.get("page_size") or block.get("pageSize"), page_size)
            needs_review = not bbox or bool(flags)
            confidence = {"table": 0.82, "formula": 0.84, "figure": 0.78}[element_type] - (0.15 if needs_review else 0.0)
            counters[element_type] += 1
            element_id = f"p{page + 1}_mineru_{element_type}_{counters[element_type]}"
            text = str(block.get("text") or block.get("latex") or block.get("caption") or block.get("markdown") or block.get("content") or "")
            html_value = str(block.get("html") or "")
            markdown_value = str(block.get("markdown") or "")
            table_rows: list[list[str]] = []
            csv_path = ""
            json_path = ""
            if element_type == "table":
                table_rows = table_to_rows_from_mineru(block, markdown_value, html_value)
                csv_path = str(_write_csv(table_dir, element_id, table_rows)) if table_rows else ""
                json_path = str(_write_json(table_dir, element_id, block))
            latex = _clean_latex(str(block.get("latex") or text)) if element_type == "formula" else ""
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
                    png_path=str(block.get("image_path") or block.get("img_path") or block.get("path") or "") if element_type == "figure" else "",
                    latex=latex,
                    html=html_value,
                    markdown=markdown_value,
                    caption=str(block.get("caption") or ""),
                    raw=block,
                    structure_type=str(block.get("type") or block.get("block_type") or ""),
                    quality_flags=flags,
                )
            )
    return elements


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
            local_page = value.get("page", value.get("page_idx", value.get("page_no", page)))
            try:
                local_page = int(local_page or 0)
            except Exception:
                local_page = page or 0
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
    if label in {"table", "table_body", "table_caption"}:
        return "table"
    if label in {"image", "figure", "fig", "chart"}:
        return "figure"
    if label in {"interline_equation", "inline_equation", "equation", "formula"}:
        return "formula"
    return ""


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
        rows = table_to_rows(raw.get(key))
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


def _resolve_image_path(raw_dir: Path, block: dict[str, Any]) -> str:
    value = str(block.get("image_path") or block.get("img_path") or block.get("path") or "").strip()
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = raw_dir / value
    return str(path) if path.exists() else ""


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


def _command_exists(command: str) -> bool:
    if not command:
        return False
    path = Path(command)
    if path.parent != Path("."):
        return path.exists()
    return shutil.which(command) is not None
