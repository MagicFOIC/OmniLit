from __future__ import annotations

import json
import math
import tempfile
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
except Exception:  # pragma: no cover - PySide6 is optional in headless test environments.
    QColor = None
    QImage = None
    QPainter = None
    QPen = None

from .chart_digitizer_core import analyze_chart_element


@dataclass(frozen=True)
class SyntheticChartCase:
    case_id: str
    pdf_name: str
    figure: str
    chart_kind: str
    expected_subplots: int
    expected_series: int
    sample_count: int = 10
    use_calibration: bool = True
    use_pdf_text_ticks: bool = False
    needs_review_expected: bool = False


@dataclass(frozen=True)
class ValidationCaseSpec:
    case_id: str
    pdf_name: str
    figure: str
    chart_kind: str
    expected_subplots: int
    expected_series: int
    sample_count: int = 10
    needs_review_expected: bool = False
    expected_points: tuple[dict[str, Any], ...] = ()


SYNTHETIC_VALIDATION_CASES: tuple[SyntheticChartCase, ...] = (
    SyntheticChartCase("V1", "synthetic_single_line.pdf", "Fig. 1", "single line", 1, 1),
    SyntheticChartCase("V2", "synthetic_multi_line.pdf", "Fig. 1", "multi-line", 1, 2),
    SyntheticChartCase("V3", "synthetic_curve.pdf", "Fig. 1", "curve", 1, 1),
    SyntheticChartCase("V4", "synthetic_marker_line.pdf", "Fig. 1", "marker line", 1, 1),
    SyntheticChartCase("V5", "synthetic_subplots.pdf", "Fig. 2", "multi-subplot", 2, 1, use_calibration=False),
    SyntheticChartCase("V6", "synthetic_color_curve.pdf", "Fig. 1", "color curve", 1, 1),
    SyntheticChartCase("V7", "synthetic_gray_curve.pdf", "Fig. 1", "gray curve", 1, 1),
    SyntheticChartCase("V8", "synthetic_grid_line.pdf", "Fig. 1", "grid line", 1, 1),
    SyntheticChartCase("V9", "synthetic_complex_legend.pdf", "Fig. 1", "complex legend", 1, 1, use_pdf_text_ticks=True),
    SyntheticChartCase("V10", "synthetic_hard_ticks.pdf", "Fig. 1", "OCR-hard ticks", 1, 1, use_calibration=False, needs_review_expected=True),
)


def run_manifest_validation(manifest_path: str | Path) -> dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser()
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "validationKind": "manifest",
            "manifestPath": str(manifest_file),
            "caseCount": 0,
            "skipped": True,
            "skipReason": f"Failed to read manifest: {exc}",
            "cases": [],
            "metrics": {},
        }
    raw_cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(raw_cases, list):
        return {
            "validationKind": "manifest",
            "manifestPath": str(manifest_file),
            "caseCount": 0,
            "skipped": True,
            "skipReason": "Manifest must contain a cases list.",
            "cases": [],
            "metrics": {},
        }
    base_dir = manifest_file.parent
    cases: list[dict[str, Any]] = []
    for index, entry in enumerate(raw_cases):
        if not isinstance(entry, dict):
            continue
        cases.append(_run_manifest_case(entry, base_dir, index, manifest))
    return {
        "validationKind": "manifest",
        "manifestPath": str(manifest_file),
        "caseCount": len(cases),
        "skipped": False,
        "cases": cases,
        "metrics": _aggregate_metrics(cases),
    }


def run_synthetic_validation(output_dir: str | Path | None = None) -> dict[str, Any]:
    if QImage is None:
        return {
            "validationKind": "synthetic",
            "caseCount": 0,
            "skipped": True,
            "skipReason": "PySide6 is not available.",
            "cases": [],
            "metrics": {},
        }
    root = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="omnilit_chart_validation_"))
    root.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    for case in SYNTHETIC_VALIDATION_CASES:
        image_path = root / f"{case.case_id.lower()}_{case.chart_kind.replace(' ', '_')}.png"
        element, index, calibration = _build_case_input(case, image_path)
        result = analyze_chart_element(element, index, record_id=case.case_id, sample_count=case.sample_count, calibration=calibration)
        cases.append(_summarize_case(case, result))
    return {
        "validationKind": "synthetic",
        "caseCount": len(cases),
        "skipped": False,
        "cases": cases,
        "metrics": _aggregate_metrics(cases),
    }


def format_synthetic_validation_markdown(report: dict[str, Any]) -> str:
    if report.get("skipped"):
        return f"Synthetic validation skipped: {report.get('skipReason') or 'unknown'}"
    metrics = report.get("metrics") or {}
    lines = [
        "## Synthetic Baseline",
        "",
        "| Metric | Current value |",
        "| --- | ---: |",
        f"| Automatic chart recognition success rate | {_percent(metrics.get('chartRecognitionSuccessRate'))} |",
        f"| Subplot splitting accuracy | {_percent(metrics.get('subplotSplittingAccuracy'))} |",
        f"| Axis calibration accuracy | {_percent(metrics.get('axisCalibrationAccuracy'))} |",
        f"| Series separation accuracy | {_percent(metrics.get('seriesSeparationAccuracy'))} |",
        f"| Mean missing point rate | {_percent(metrics.get('meanMissingPointRate'))} |",
        f"| Mean point RMSE | {_number(metrics.get('meanPointRmse'))} |",
        "",
        "| Case | Expected type | Result | Subplots | Series | Needs review | Notes |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in report.get("cases") or []:
        lines.append(
            "| {caseId} | {chartKind} | {status} | {subplotCount}/{expectedSubplots} | "
            "{maxSeriesCount}/{expectedSeries} | {needsReview} | {notes} |".format(
                caseId=item.get("caseId", ""),
                chartKind=item.get("chartKind", ""),
                status=item.get("status", ""),
                subplotCount=item.get("subplotCount", 0),
                expectedSubplots=item.get("expectedSubplots", 0),
                maxSeriesCount=item.get("maxSeriesCount", 0),
                expectedSeries=item.get("expectedSeries", 0),
                needsReview="yes" if item.get("needsReview") else "no",
                notes="; ".join(item.get("warnings") or [])[:120],
            )
        )
    return "\n".join(lines)


def format_manifest_validation_markdown(report: dict[str, Any]) -> str:
    if report.get("skipped"):
        return f"Manifest validation skipped: {report.get('skipReason') or 'unknown'}"
    metrics = report.get("metrics") or {}
    lines = [
        "## Local Manifest Validation",
        "",
        f"Manifest: `{report.get('manifestPath') or ''}`",
        "",
        "| Metric | Current value |",
        "| --- | ---: |",
        f"| Automatic chart recognition success rate | {_percent(metrics.get('chartRecognitionSuccessRate'))} |",
        f"| Subplot splitting accuracy | {_percent(metrics.get('subplotSplittingAccuracy'))} |",
        f"| Axis calibration accuracy | {_percent(metrics.get('axisCalibrationAccuracy'))} |",
        f"| Series separation accuracy | {_percent(metrics.get('seriesSeparationAccuracy'))} |",
        f"| Mean missing point rate | {_percent(metrics.get('meanMissingPointRate'))} |",
        f"| Mean point RMSE | {_number(metrics.get('meanPointRmse'))} |",
        "",
        "| Case | PDF | Figure | Expected type | Result | Subplots | Series | Needs review | Notes |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in report.get("cases") or []:
        lines.append(
            "| {caseId} | {pdfName} | {figure} | {chartKind} | {status} | {subplotCount}/{expectedSubplots} | "
            "{maxSeriesCount}/{expectedSeries} | {needsReview} | {notes} |".format(
                caseId=item.get("caseId", ""),
                pdfName=item.get("pdfName", ""),
                figure=item.get("figure", ""),
                chartKind=item.get("chartKind", ""),
                status=item.get("status", ""),
                subplotCount=item.get("subplotCount", 0),
                expectedSubplots=item.get("expectedSubplots", 0),
                maxSeriesCount=item.get("maxSeriesCount", 0),
                expectedSeries=item.get("expectedSeries", 0),
                needsReview="yes" if item.get("needsReview") else "no",
                notes="; ".join(item.get("warnings") or [])[:120],
            )
        )
    return "\n".join(lines)


def run_validation_report(
    *,
    manifest_path: str | Path | None = None,
    synthetic: bool = False,
    synthetic_output_dir: str | Path | None = None,
    markdown_path: str | Path | None = None,
    json_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run a chart validation set and optionally write Markdown/JSON reports."""
    if manifest_path:
        report = run_manifest_validation(manifest_path)
        markdown = format_manifest_validation_markdown(report)
    else:
        report = run_synthetic_validation(synthetic_output_dir if synthetic or synthetic_output_dir else None)
        markdown = format_synthetic_validation_markdown(report)
    report = dict(report)
    report["markdown"] = markdown
    if markdown_path:
        path = Path(markdown_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown + "\n", encoding="utf-8")
        report["markdownPath"] = str(path)
    if json_path:
        path = Path(json_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        json_payload = {key: value for key, value in report.items() if key != "markdown"}
        path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["jsonPath"] = str(path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run OmniLit chart digitizer validation reports.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--manifest", help="Path to a local real-PDF validation manifest.")
    source.add_argument("--synthetic", action="store_true", help="Run the built-in synthetic 10-case baseline.")
    parser.add_argument("--synthetic-output-dir", help="Directory for generated synthetic chart images.")
    parser.add_argument("--out", help="Write the Markdown report to this path.")
    parser.add_argument("--json-out", help="Write the raw validation report JSON to this path.")
    parser.add_argument("--quiet", action="store_true", help="Do not print Markdown to stdout.")
    args = parser.parse_args(argv)

    report = run_validation_report(
        manifest_path=args.manifest,
        synthetic=args.synthetic or not args.manifest,
        synthetic_output_dir=args.synthetic_output_dir,
        markdown_path=args.out,
        json_path=args.json_out,
    )
    if not args.quiet:
        print(report.get("markdown") or "")
    return 0 if not report.get("skipped") else 2


def _run_manifest_case(entry: dict[str, Any], base_dir: Path, index: int, manifest: dict[str, Any]) -> dict[str, Any]:
    case_id = str(entry.get("caseId") or entry.get("id") or f"M{index + 1}")
    image_path = _manifest_path(entry.get("figureImagePath") or entry.get("pngPath"), base_dir)
    spec = ValidationCaseSpec(
        case_id=case_id,
        pdf_name=str(entry.get("pdfName") or entry.get("pdfPath") or manifest.get("pdfName") or manifest.get("pdfPath") or ""),
        figure=str(entry.get("figure") or entry.get("figureLabel") or f"Fig. {index + 1}"),
        chart_kind=str(entry.get("chartKind") or entry.get("expectedType") or "line chart"),
        expected_subplots=max(0, _int_value(entry.get("expectedSubplots"), 1)),
        expected_series=max(0, _int_value(entry.get("expectedSeries"), 1)),
        sample_count=max(2, _int_value(entry.get("sampleCount"), 10)),
        needs_review_expected=bool(entry.get("needsReviewExpected") or entry.get("expectedNeedsReview")),
        expected_points=tuple(item for item in (entry.get("expectedPoints") or []) if isinstance(item, dict)),
    )
    if image_path is None or not image_path.exists():
        return _missing_manifest_case(spec, f"Missing figure image: {entry.get('figureImagePath') or entry.get('pngPath') or ''}")
    element = {
        "id": str(entry.get("elementId") or f"figure_{case_id}"),
        "type": "figure",
        "page": _int_value(entry.get("page"), 0),
        "pngPath": str(image_path),
        "caption": str(entry.get("caption") or f"{spec.figure} {spec.chart_kind}"),
        "bbox": entry.get("bbox") or [],
        "pageSize": entry.get("pageSize") or [],
        "metadata": entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
    }
    index_payload = entry.get("index") if isinstance(entry.get("index"), dict) else {}
    index_payload = {
        **index_payload,
        "sourcePath": str(entry.get("pdfPath") or manifest.get("pdfPath") or spec.pdf_name),
        "sourceSha256": str(entry.get("sourceSha256") or manifest.get("sourceSha256") or ""),
    }
    if "pages" not in index_payload and isinstance(entry.get("textBlocks"), list):
        index_payload["pages"] = [{"page": element["page"], "textBlocks": entry.get("textBlocks")}]
    calibration = entry.get("calibration") if isinstance(entry.get("calibration"), dict) else {}
    result = analyze_chart_element(element, index_payload, record_id=case_id, sample_count=spec.sample_count, calibration=calibration)
    return _summarize_case(spec, result)


def _missing_manifest_case(spec: ValidationCaseSpec, warning: str) -> dict[str, Any]:
    return {
        "caseId": spec.case_id,
        "pdfName": spec.pdf_name,
        "figure": spec.figure,
        "chartKind": spec.chart_kind,
        "status": "missing",
        "recognized": False,
        "expectedSubplots": spec.expected_subplots,
        "subplotCount": 0,
        "subplotCorrect": False,
        "expectedSeries": spec.expected_series,
        "maxSeriesCount": 0,
        "seriesCorrect": False,
        "axisCalibrated": False,
        "legendMatched": False,
        "needsReview": True,
        "missingPointRate": 1.0,
        "warnings": [warning],
        "jsonSample": {},
    }


def _build_case_input(case: SyntheticChartCase, image_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if case.case_id == "V5":
        _write_subplot_image(image_path)
    else:
        _write_standard_image(image_path, case)
    element: dict[str, Any] = {
        "id": f"figure_{case.case_id.lower()}",
        "type": "figure",
        "page": 0,
        "pngPath": str(image_path),
        "caption": f"{case.figure} {case.chart_kind} curve over time",
        "metadata": {"clipBBox": [0, 0, 260, 180], "zoom": 1.0, "imageWidth": 260},
    }
    index: dict[str, Any] = {"sourcePath": case.pdf_name, "sourceSha256": f"sha-{case.case_id}", "pages": []}
    if case.use_pdf_text_ticks:
        index["pages"] = [
            {
                "page": 0,
                "textBlocks": [
                    {"bbox": [35, 160, 45, 170], "text": "0"},
                    {"bbox": [210, 160, 230, 170], "text": "100"},
                    {"bbox": [12, 145, 28, 155], "text": "0"},
                    {"bbox": [12, 15, 28, 25], "text": "1"},
                    {"bbox": [224, 42, 255, 54], "text": "Red curve"},
                ],
            }
        ]
    calibration = _default_calibration() if case.use_calibration else {}
    return element, index, calibration


def _summarize_case(case: SyntheticChartCase | ValidationCaseSpec, result: dict[str, Any]) -> dict[str, Any]:
    subplots = result.get("subplots") if isinstance(result.get("subplots"), list) else []
    series_counts = [len(item.get("series") or []) for item in subplots if isinstance(item, dict)]
    max_series = max(series_counts or [0])
    missing_points = 0
    total_points = 0
    axis_sources: list[str] = []
    legend_matched = False
    extracted_series: list[dict[str, Any]] = []
    for subplot in subplots:
        axes = subplot.get("axes") or {}
        axis_sources.extend(str((axes.get(axis) or {}).get("source") or "") for axis in ("x", "y"))
        for series in subplot.get("series") or []:
            extracted_series.append(series)
            legend_matched = legend_matched or series.get("nameSource") == "pdf_text_legend"
            for point in series.get("points") or []:
                total_points += 1
                if point.get("missing"):
                    missing_points += 1
    point_error = _point_error_summary(tuple(getattr(case, "expected_points", ())), extracted_series)
    subplot_ok = len(subplots) == case.expected_subplots
    series_ok = max_series >= case.expected_series
    axis_ok = bool(axis_sources) and all(source in {"manual_calibration", "pdf_text"} for source in axis_sources)
    recognized = (result.get("analysis") or {}).get("chartType") == "line_chart" and bool(subplots)
    needs_review = bool((result.get("analysis") or {}).get("needsReview"))
    status = "pass" if recognized and subplot_ok and series_ok and (axis_ok or case.needs_review_expected) else "review"
    warnings = list((result.get("analysis") or {}).get("warnings") or [])
    return {
        "caseId": case.case_id,
        "pdfName": case.pdf_name,
        "figure": case.figure,
        "chartKind": case.chart_kind,
        "status": status,
        "recognized": bool(recognized),
        "expectedSubplots": case.expected_subplots,
        "subplotCount": len(subplots),
        "subplotCorrect": subplot_ok,
        "expectedSeries": case.expected_series,
        "maxSeriesCount": max_series,
        "seriesCorrect": series_ok,
        "axisCalibrated": axis_ok,
        "legendMatched": legend_matched,
        "needsReview": needs_review,
        "missingPointRate": missing_points / max(1, total_points),
        "pointError": point_error,
        "pointMae": point_error.get("mae"),
        "pointRmse": point_error.get("rmse"),
        "warnings": warnings,
        "jsonSample": {"schemaVersion": result.get("schemaVersion"), "analysis": result.get("analysis"), "subplots": subplots[:1]},
    }


def _aggregate_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    count = max(1, len(cases))
    point_errors = [float(item["pointRmse"]) for item in cases if item.get("pointRmse") is not None]
    return {
        "chartRecognitionSuccessRate": sum(1 for item in cases if item.get("recognized")) / count,
        "subplotSplittingAccuracy": sum(1 for item in cases if item.get("subplotCorrect")) / count,
        "axisCalibrationAccuracy": sum(1 for item in cases if item.get("axisCalibrated")) / count,
        "seriesSeparationAccuracy": sum(1 for item in cases if item.get("seriesCorrect")) / count,
        "meanMissingPointRate": sum(float(item.get("missingPointRate") or 0.0) for item in cases) / count,
        "meanPointRmse": sum(point_errors) / len(point_errors) if point_errors else None,
        "pointErrorCaseCount": len(point_errors),
        "needsReviewCount": sum(1 for item in cases if item.get("needsReview")),
        "legendMatchedCount": sum(1 for item in cases if item.get("legendMatched")),
    }


def _point_error_summary(expected_points: tuple[dict[str, Any], ...], extracted_series: list[dict[str, Any]]) -> dict[str, Any]:
    if not expected_points:
        return {"count": 0, "mae": None, "rmse": None, "coverage": 0.0}
    errors: list[float] = []
    matched = 0
    for expected in expected_points:
        actual = _match_actual_point(expected, extracted_series)
        if actual is None:
            continue
        try:
            expected_x = float(expected.get("x"))
            expected_y = float(expected.get("y"))
            actual_x = float(actual.get("x"))
            actual_y = float(actual.get("y"))
        except (TypeError, ValueError):
            continue
        errors.append(math.hypot(actual_x - expected_x, actual_y - expected_y))
        matched += 1
    if not errors:
        return {"count": 0, "mae": None, "rmse": None, "coverage": 0.0}
    return {
        "count": matched,
        "mae": sum(errors) / len(errors),
        "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "coverage": matched / max(1, len(expected_points)),
    }


def _match_actual_point(expected: dict[str, Any], extracted_series: list[dict[str, Any]]) -> dict[str, Any] | None:
    series = _select_expected_series(expected, extracted_series)
    if not series:
        return None
    points = [point for point in (series.get("points") or []) if isinstance(point, dict) and not point.get("missing")]
    if not points:
        return None
    if "index" in expected:
        try:
            expected_index = int(expected.get("index"))
        except (TypeError, ValueError):
            expected_index = -1
        for point in points:
            if int(point.get("index") or -1) == expected_index:
                return point
    if "x" in expected:
        try:
            expected_x = float(expected.get("x"))
        except (TypeError, ValueError):
            expected_x = 0.0
        return min(points, key=lambda point: abs(float(point.get("x") or 0.0) - expected_x))
    return points[0]


def _select_expected_series(expected: dict[str, Any], extracted_series: list[dict[str, Any]]) -> dict[str, Any] | None:
    series_id = str(expected.get("seriesId") or "")
    series_name = str(expected.get("series") or expected.get("seriesName") or "")
    if series_id:
        for series in extracted_series:
            if str(series.get("seriesId") or "") == series_id:
                return series
    if series_name:
        for series in extracted_series:
            if str(series.get("name") or "") == series_name:
                return series
    try:
        series_index = int(expected.get("seriesIndex"))
    except (TypeError, ValueError):
        series_index = 0
    if 0 <= series_index < len(extracted_series):
        return extracted_series[series_index]
    return extracted_series[0] if extracted_series else None


def _write_standard_image(path: Path, case: SyntheticChartCase) -> None:
    image = QImage(260, 180, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    _draw_axes(painter)
    if case.case_id == "V2":
        _draw_polyline(painter, "#d62728", [(40, 140), (220, 42)])
        _draw_polyline(painter, "#1f77b4", [(40, 58), (220, 120)])
    elif case.case_id == "V3":
        points = [(40 + x, int(95 - math.sin(x / 22.0) * 42)) for x in range(0, 181, 8)]
        _draw_polyline(painter, "#2ca02c", points)
    elif case.case_id == "V4":
        points = [(40, 136), (85, 102), (130, 88), (175, 60), (220, 42)]
        _draw_polyline(painter, "#9467bd", points)
        painter.setPen(QPen(QColor("#9467bd"), 5))
        for x, y in points:
            painter.drawPoint(x, y)
    elif case.case_id == "V7":
        _draw_polyline(painter, "#777777", [(40, 135), (120, 76), (220, 44)])
    elif case.case_id == "V8":
        _draw_grid(painter, "#b9b9b9", vertical=True)
        _draw_polyline(painter, "#d62728", [(40, 140), (220, 42)])
    elif case.case_id == "V9":
        _draw_polyline(painter, "#d62728", [(40, 140), (220, 42)])
        _draw_polyline(painter, "#d62728", [(205, 48), (221, 48)], width=3)
    else:
        color = "#ff7f0e" if case.case_id == "V6" else "#d62728"
        _draw_polyline(painter, color, [(40, 140), (220, 40)])
    painter.end()
    image.save(str(path))


def _write_subplot_image(path: Path) -> None:
    image = QImage(560, 180, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    for offset, color in ((0, "#d62728"), (280, "#1f77b4")):
        painter.setPen(QPen(QColor("#111111"), 2))
        painter.drawLine(offset + 40, 150, offset + 250, 150)
        painter.drawLine(offset + 40, 20, offset + 40, 150)
        _draw_polyline(painter, color, [(offset + 40, 135), (offset + 250, 45)])
    painter.end()
    image.save(str(path))


def _draw_axes(painter: Any) -> None:
    painter.setPen(QPen(QColor("#111111"), 2))
    painter.drawLine(40, 150, 230, 150)
    painter.drawLine(40, 20, 40, 150)
    _draw_grid(painter, "#e5e7eb", vertical=False)


def _draw_grid(painter: Any, color: str, *, vertical: bool) -> None:
    painter.setPen(QPen(QColor(color), 1))
    for y in (52, 85, 118):
        painter.drawLine(41, y, 230, y)
    if vertical:
        for x in (85, 130, 175):
            painter.drawLine(x, 20, x, 149)


def _draw_polyline(painter: Any, color: str, points: list[tuple[int, int]], width: int = 3) -> None:
    painter.setPen(QPen(QColor(color), width))
    for start, end in zip(points, points[1:]):
        painter.drawLine(start[0], start[1], end[0], end[1])


def _default_calibration() -> dict[str, Any]:
    return {
        "plotAreaPx": [40, 20, 220, 150],
        "xAxis": {"calibration": [{"pixel": [40, 150], "value": 0}, {"pixel": [220, 150], "value": 100}]},
        "yAxis": {"calibration": [{"pixel": [40, 150], "value": 0}, {"pixel": [40, 20], "value": 1}]},
    }


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _number(value: Any) -> str:
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return "n/a"


def _manifest_path(value: Any, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else base_dir / path


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


if __name__ == "__main__":  # pragma: no cover - covered through main(argv) in tests.
    raise SystemExit(main())
