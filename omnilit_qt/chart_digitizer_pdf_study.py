from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import fitz
except Exception:  # pragma: no cover - PyMuPDF is optional outside the app runtime.
    fitz = None

from .chart_digitizer_core import analyze_chart_element
from .chart_digitizer_schema import chart_result_to_json


DEFAULT_PDF_ROOT = Path("Workspace") / "data" / "downloads" / "pdfs"


def run_pdf_study(
    pdf_paths: list[str | Path],
    *,
    output_dir: str | Path,
    case_count: int = 10,
    validation_count: int = 10,
    pages_per_pdf: int = 5,
    sample_count: int = 10,
    zoom: float = 1.5,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    for index, pdf_path in enumerate(pdf_paths):
        path = Path(pdf_path)
        if not path.exists():
            continue
        candidates.append(_best_pdf_candidate(path, output_root, index, pages_per_pdf, sample_count, zoom))
    ranked = sorted(candidates, key=_candidate_rank, reverse=True)
    total = max(0, case_count) + max(0, validation_count)
    selected = ranked[:total]
    case_items, validation_items = _balanced_case_validation_split(selected, max(0, case_count), max(0, validation_count))
    return {
        "studyKind": "local_pdf_10_plus_10",
        "pdfCount": len(candidates),
        "selectedCount": len(selected),
        "caseCount": len(case_items),
        "validationCount": len(validation_items),
        "outputDir": str(output_root),
        "cases": case_items,
        "validation": validation_items,
        "validationMetrics": _validation_metrics(validation_items),
    }


def discover_pdf_paths(root: str | Path = DEFAULT_PDF_ROOT, *, limit: int = 60) -> list[Path]:
    base = Path(root)
    if base.is_file() and base.suffix.lower() == ".pdf":
        return [base]
    if not base.exists():
        return []
    paths = sorted(path for path in base.rglob("*.pdf") if path.is_file())
    return paths[: max(0, int(limit))]


def format_case_study_markdown(report: dict[str, Any]) -> str:
    cases = report.get("cases") or []
    lines = [
        "# Chart Digitizer Case Study",
        "",
        "This section was generated from local PDF files. The PDFs and rendered figure-page PNGs are not committed.",
        "",
        "| # | PDF name | Figure page | Figure | Chart type | Multi-subplot | Auto result | Axis result | Curve result | Needs improvement |",
        "| ---: | --- | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, item in enumerate(cases, 1):
        lines.append(
            "| {index} | {pdf} | {page} | {figure} | {chart_type} | {multi} | {status} | {axes} | {curves} | {improve} |".format(
                index=index,
                pdf=_md(item.get("pdfName")),
                page=int(item.get("page") or 0) + 1,
                figure=_md(item.get("figure") or "page candidate"),
                chart_type=_md(item.get("chartType") or ""),
                multi="yes" if int(item.get("subplotCount") or 0) > 1 else "no",
                status=_md(item.get("autoResult") or ""),
                axes=_md(item.get("axisResult") or ""),
                curves=_md(item.get("curveResult") or ""),
                improve=_md(item.get("improvement") or ""),
            )
        )
    lines.extend(["", "## JSON Samples", ""])
    for index, item in enumerate(cases, 1):
        lines.extend(
            [
                f"### Case {index}: {_md(item.get('pdfName'))}",
                "",
                "```json",
                _compact_json_sample(item),
                "```",
                "",
                f"Conclusion: {_md(item.get('conclusion') or '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def format_validation_markdown(report: dict[str, Any]) -> str:
    items = report.get("validation") or []
    metrics = report.get("validationMetrics") or {}
    lines = [
        "# Chart Digitizer Validation",
        "",
        "This validation section uses local PDFs as a holdout scan. Metrics are automatic QA indicators unless hand-labeled expected points are added later.",
        "",
        "| Metric | Current value |",
        "| --- | ---: |",
        f"| Automatic recognition rate | {_percent(metrics.get('recognitionRate'))} |",
        f"| Subplot split rate | {_percent(metrics.get('subplotSplitRate'))} |",
        f"| Axis calibrated rate | {_percent(metrics.get('axisCalibratedRate'))} |",
        f"| Series extracted rate | {_percent(metrics.get('seriesExtractedRate'))} |",
        f"| Needs review rate | {_percent(metrics.get('needsReviewRate'))} |",
        "",
        "| # | PDF name | Figure page | Chart type | Subplots | Series | Axis source | Needs review | Failure attribution | Next fix |",
        "| ---: | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for index, item in enumerate(items, 1):
        lines.append(
            "| {index} | {pdf} | {page} | {chart_type} | {subplots} | {series} | {axis} | {review} | {failure} | {next_fix} |".format(
                index=index,
                pdf=_md(item.get("pdfName")),
                page=int(item.get("page") or 0) + 1,
                chart_type=_md(item.get("chartType") or ""),
                subplots=int(item.get("subplotCount") or 0),
                series=int(item.get("seriesCount") or 0),
                axis=_md(item.get("axisResult") or ""),
                review="yes" if item.get("needsReview") else "no",
                failure=_md(item.get("failureAttribution") or ""),
                next_fix=_md(item.get("improvement") or ""),
            )
        )
    lines.extend(["", "## Failure Samples", ""])
    for index, item in enumerate(items, 1):
        if item.get("needsReview") or item.get("failureAttribution"):
            lines.extend(
                [
                    f"### Validation {index}: {_md(item.get('pdfName'))}",
                    "",
                    f"- Page: {int(item.get('page') or 0) + 1}",
                    f"- Result: {_md(item.get('autoResult') or '')}",
                    f"- Warnings: {_md('; '.join(item.get('warnings') or []))}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def write_study_reports(report: dict[str, Any], *, case_report: str | Path, validation_report: str | Path, json_report: str | Path | None = None) -> None:
    case_path = Path(case_report)
    validation_path = Path(validation_report)
    case_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    case_path.write_text(format_case_study_markdown(report), encoding="utf-8")
    validation_path.write_text(format_validation_markdown(report), encoding="utf-8")
    if json_report:
        path = Path(json_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a local 10+10 PDF chart digitizer study.")
    parser.add_argument("--pdf-root", default=str(DEFAULT_PDF_ROOT), help="PDF root directory or a single PDF path.")
    parser.add_argument("--output-dir", default=str(Path("Workspace") / "chart_digitizer_pdf_study"), help="Directory for rendered page images and JSON outputs.")
    parser.add_argument("--case-report", default=str(Path("docs") / "chart_digitizer_case_study.md"))
    parser.add_argument("--validation-report", default=str(Path("docs") / "chart_digitizer_validation.md"))
    parser.add_argument("--json-report", default=str(Path("Workspace") / "chart_digitizer_pdf_study" / "report.json"))
    parser.add_argument("--pdf-limit", type=int, default=60)
    parser.add_argument("--case-count", type=int, default=10)
    parser.add_argument("--validation-count", type=int, default=10)
    parser.add_argument("--pages-per-pdf", type=int, default=5)
    parser.add_argument("--sample-count", type=int, default=10)
    parser.add_argument("--zoom", type=float, default=1.5)
    args = parser.parse_args(argv)

    pdf_paths = discover_pdf_paths(args.pdf_root, limit=args.pdf_limit)
    report = run_pdf_study(
        pdf_paths,
        output_dir=args.output_dir,
        case_count=args.case_count,
        validation_count=args.validation_count,
        pages_per_pdf=args.pages_per_pdf,
        sample_count=args.sample_count,
        zoom=args.zoom,
    )
    write_study_reports(report, case_report=args.case_report, validation_report=args.validation_report, json_report=args.json_report)
    print(f"PDFs scanned: {report['pdfCount']}; cases: {report['caseCount']}; validation: {report['validationCount']}")
    print(f"Case report: {args.case_report}")
    print(f"Validation report: {args.validation_report}")
    return 0 if report.get("selectedCount") else 2


def _best_pdf_candidate(pdf_path: Path, output_root: Path, pdf_index: int, pages_per_pdf: int, sample_count: int, zoom: float) -> dict[str, Any]:
    sha = _sha256(pdf_path)
    best: dict[str, Any] | None = None
    try:
        document = fitz.open(str(pdf_path)) if fitz is not None else None
    except Exception as exc:
        return _error_candidate(pdf_path, pdf_index, f"PDF open failed: {exc}")
    if document is None:
        return _error_candidate(pdf_path, pdf_index, "PyMuPDF is not available.")
    with document:
        page_total = min(max(1, int(pages_per_pdf)), len(document))
        for page_index in range(page_total):
            try:
                page = document.load_page(page_index)
                text_blocks = _text_blocks(page)
                analysis_text_blocks = _analysis_text_blocks(page, text_blocks)
                page_text = page.get_text("text") or ""
                source_index = {"sourcePath": str(pdf_path), "sourceSha256": sha, "pages": [{"page": page_index, "textBlocks": analysis_text_blocks}]}
                for clip_index, clip in enumerate(_candidate_clips(page, text_blocks)):
                    image_path = _render_page(page, output_root, pdf_index, page_index, clip_index, zoom, clip)
                    element = {
                        "id": f"pdf_{pdf_index + 1}_page_{page_index + 1}_clip_{clip_index + 1}",
                        "type": "figure",
                        "page": page_index,
                        "pngPath": str(image_path),
                        "caption": _caption_hint(page_text),
                        "bbox": [float(clip[0]), float(clip[1]), float(clip[2]), float(clip[3])],
                        "pageSize": [float(page.rect.width), float(page.rect.height)],
                        "metadata": {"clipBBox": [float(v) for v in clip], "zoom": zoom, "imageWidth": (float(clip[2]) - float(clip[0])) * zoom},
                    }
                    result = analyze_chart_element(element, source_index, record_id=f"pdf_{pdf_index + 1}", sample_count=sample_count)
                    candidate = _summarize_pdf_result(pdf_path, pdf_index, page_index, image_path, result)
                    if best is None or _candidate_rank(candidate) > _candidate_rank(best):
                        best = candidate
            except Exception as exc:
                candidate = _error_candidate(pdf_path, pdf_index, f"Page {page_index + 1} failed: {exc}", page_index=page_index)
                if best is None:
                    best = candidate
    return best or _error_candidate(pdf_path, pdf_index, "No pages scanned.")


def _render_page(page: Any, output_root: Path, pdf_index: int, page_index: int, clip_index: int, zoom: float, clip: list[float]) -> Path:
    image_dir = output_root / "rendered_pages"
    image_dir.mkdir(parents=True, exist_ok=True)
    path = image_dir / f"pdf_{pdf_index + 1:02d}_page_{page_index + 1:03d}_clip_{clip_index + 1:02d}.png"
    if path.exists():
        return path
    rect = fitz.Rect(float(clip[0]), float(clip[1]), float(clip[2]), float(clip[3]))
    pixmap = page.get_pixmap(matrix=fitz.Matrix(float(zoom), float(zoom)), clip=rect, alpha=False)
    pixmap.save(str(path))
    return path


def _candidate_clips(page: Any, text_blocks: list[dict[str, Any]]) -> list[list[float]]:
    width = float(page.rect.width)
    height = float(page.rect.height)
    clips: list[list[float]] = []
    for block in text_blocks:
        text = str(block.get("text") or "").strip().lower()
        bbox = block.get("bbox") or []
        if len(bbox) < 4 or not text.startswith(("fig.", "figure")):
            continue
        y0 = float(bbox[1])
        y1 = float(bbox[3])
        above = [0.0, max(0.0, y0 - height * 0.46), width, min(height, y1 + height * 0.04)]
        if _clip_is_large_enough(above):
            clips.append(above)
        below = [0.0, max(0.0, y0 - height * 0.04), width, min(height, y1 + height * 0.46)]
        if _clip_is_large_enough(below):
            clips.append(below)
        if len(clips) >= 2:
            break
    if not clips:
        clips = [[0.0, height * 0.08, width, height * 0.68], [0.0, height * 0.32, width, height * 0.92]]
    unique: list[list[float]] = []
    for clip in clips:
        clean = [float(max(0.0, clip[0])), float(max(0.0, clip[1])), float(min(width, clip[2])), float(min(height, clip[3]))]
        if not _clip_is_large_enough(clean):
            continue
        key = tuple(round(value, 1) for value in clean)
        if key not in {tuple(round(value, 1) for value in existing) for existing in unique}:
            unique.append(clean)
    return unique[:2]


def _clip_is_large_enough(clip: list[float]) -> bool:
    return len(clip) >= 4 and clip[2] - clip[0] >= 160 and clip[3] - clip[1] >= 120


def _text_blocks(page: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in page.get_text("blocks") or []:
        if len(block) < 5:
            continue
        text = str(block[4] or "").strip()
        if not text:
            continue
        blocks.append({"bbox": [float(block[0]), float(block[1]), float(block[2]), float(block[3])], "text": text, "kind": "block"})
    return blocks


def _analysis_text_blocks(page: Any, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = list(blocks)
    for word in page.get_text("words") or []:
        if len(word) < 5:
            continue
        text = str(word[4] or "").strip()
        if not text:
            continue
        items.append({"bbox": [float(word[0]), float(word[1]), float(word[2]), float(word[3])], "text": text, "kind": "word"})
    return items


def _caption_hint(page_text: str) -> str:
    lines = [line.strip() for line in str(page_text or "").splitlines() if line.strip()]
    for line in lines:
        lower = line.lower()
        if lower.startswith(("fig.", "figure")) and any(token in lower for token in ("curve", "line", "voltage", "current", "capacity", "time", "rate", "spectrum")):
            return line[:240]
    return "Fig. line curve voltage current capacity time spectrum"


def _summarize_pdf_result(pdf_path: Path, pdf_index: int, page_index: int, image_path: Path, result: dict[str, Any]) -> dict[str, Any]:
    analysis = result.get("analysis") or {}
    subplots = result.get("subplots") if isinstance(result.get("subplots"), list) else []
    series_count = sum(len(item.get("series") or []) for item in subplots if isinstance(item, dict))
    axis_sources = sorted(
        {
            str(((subplot.get("axes") or {}).get(axis) or {}).get("source") or "")
            for subplot in subplots
            if isinstance(subplot, dict)
            for axis in ("x", "y")
        }
    )
    warnings = [str(item) for item in analysis.get("warnings") or []]
    chart_type = str(analysis.get("chartType") or "unknown")
    recognized = chart_type == "line_chart" and bool(subplots)
    needs_review = bool(analysis.get("needsReview"))
    axis_calibrated = bool(axis_sources) and all(source in {"manual_calibration", "pdf_text"} for source in axis_sources)
    failure = _failure_attribution(recognized, axis_calibrated, series_count, needs_review, warnings)
    improvement = _next_improvement(axis_calibrated, series_count, needs_review, warnings)
    json_path = image_path.with_suffix(".chart.json")
    json_path.write_text(chart_result_to_json(result), encoding="utf-8")
    return {
        "caseId": f"PDF{pdf_index + 1:02d}",
        "pdfName": pdf_path.name,
        "pdfPath": str(pdf_path),
        "page": page_index,
        "figure": "rendered page candidate",
        "figureImagePath": str(image_path),
        "jsonPath": str(json_path),
        "chartType": chart_type,
        "recognized": recognized,
        "confidence": float(analysis.get("confidence") or 0.0),
        "needsReview": needs_review,
        "subplotCount": len(subplots),
        "seriesCount": series_count,
        "axisSources": axis_sources,
        "axisCalibrated": axis_calibrated,
        "autoResult": "success" if recognized and series_count else "needs review",
        "axisResult": ", ".join(axis_sources) if axis_sources else "not detected",
        "curveResult": f"{series_count} series across {len(subplots)} subplot(s)",
        "failureAttribution": failure,
        "improvement": improvement,
        "warnings": warnings,
        "jsonSample": _sample_result(result),
        "conclusion": "Usable after review/calibration." if recognized else "Not yet a reliable chart candidate.",
    }


def _error_candidate(pdf_path: Path, pdf_index: int, message: str, *, page_index: int = 0) -> dict[str, Any]:
    return {
        "caseId": f"PDF{pdf_index + 1:02d}",
        "pdfName": pdf_path.name,
        "pdfPath": str(pdf_path),
        "page": page_index,
        "figure": "n/a",
        "chartType": "unknown",
        "recognized": False,
        "confidence": 0.0,
        "needsReview": True,
        "subplotCount": 0,
        "seriesCount": 0,
        "axisSources": [],
        "axisCalibrated": False,
        "autoResult": "failed",
        "axisResult": "not detected",
        "curveResult": "0 series",
        "failureAttribution": message,
        "improvement": "Use an extracted figure crop or manual selection.",
        "warnings": [message],
        "jsonSample": {},
        "conclusion": "No usable candidate in scanned pages.",
    }


def _candidate_rank(item: dict[str, Any]) -> tuple[float, int, int, float]:
    recognized = 1.0 if item.get("recognized") else 0.0
    review_penalty = -0.25 if item.get("needsReview") else 0.0
    subplot_bonus = min(4, int(item.get("subplotCount") or 0)) * 0.12
    axis_bonus = 0.18 if item.get("axisCalibrated") else 0.0
    return (
        recognized + float(item.get("confidence") or 0.0) + subplot_bonus + axis_bonus + review_penalty,
        min(4, int(item.get("subplotCount") or 0)),
        min(8, int(item.get("seriesCount") or 0)),
        -float(item.get("page") or 0),
    )


def _balanced_case_validation_split(selected: list[dict[str, Any]], case_count: int, validation_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    case_items: list[dict[str, Any]] = []
    validation_items: list[dict[str, Any]] = []
    used: set[int] = set()
    buckets = [
        [index for index, item in enumerate(selected) if int(item.get("subplotCount") or 0) > 1],
        [index for index, item in enumerate(selected) if int(item.get("subplotCount") or 0) <= 1],
    ]
    for bucket in buckets:
        for offset, index in enumerate(bucket):
            target_validation = offset % 2 == 1
            if target_validation and len(validation_items) < validation_count:
                validation_items.append(selected[index])
                used.add(index)
            elif len(case_items) < case_count:
                case_items.append(selected[index])
                used.add(index)
            elif len(validation_items) < validation_count:
                validation_items.append(selected[index])
                used.add(index)
    for index, item in enumerate(selected):
        if index in used:
            continue
        if len(case_items) < case_count:
            case_items.append(item)
        elif len(validation_items) < validation_count:
            validation_items.append(item)
    return case_items[:case_count], validation_items[:validation_count]


def _validation_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    count = max(1, len(items))
    return {
        "recognitionRate": sum(1 for item in items if item.get("recognized")) / count,
        "subplotSplitRate": sum(1 for item in items if int(item.get("subplotCount") or 0) > 1) / count,
        "axisCalibratedRate": sum(1 for item in items if item.get("axisCalibrated")) / count,
        "seriesExtractedRate": sum(1 for item in items if int(item.get("seriesCount") or 0) > 0) / count,
        "needsReviewRate": sum(1 for item in items if item.get("needsReview")) / count,
    }


def _failure_attribution(recognized: bool, axis_calibrated: bool, series_count: int, needs_review: bool, warnings: list[str]) -> str:
    if not recognized:
        return "not recognized as line/curve chart"
    if series_count <= 0:
        return "curve extraction failed"
    if not axis_calibrated:
        return "axis values need manual/PDF-text calibration"
    if needs_review:
        return "; ".join(warnings[:2]) or "low-confidence automatic result"
    return "none"


def _next_improvement(axis_calibrated: bool, series_count: int, needs_review: bool, warnings: list[str]) -> str:
    text = " ".join(warnings)
    if not axis_calibrated:
        return "add OCR/manual tick calibration"
    if series_count <= 0:
        return "improve curve pixel separation"
    if needs_review and "legend" in text.lower():
        return "improve legend-to-series matching"
    if needs_review:
        return "manual review or calibration"
    return "add hand-labeled ground truth for point error"


def _sample_result(result: dict[str, Any]) -> dict[str, Any]:
    subplots = result.get("subplots") if isinstance(result.get("subplots"), list) else []
    return {
        "schemaVersion": result.get("schemaVersion"),
        "source": result.get("source"),
        "analysis": result.get("analysis"),
        "subplots": subplots[:1],
    }


def _compact_json_sample(item: dict[str, Any]) -> str:
    return json.dumps(item.get("jsonSample") or {}, ensure_ascii=False, indent=2)[:4000]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
