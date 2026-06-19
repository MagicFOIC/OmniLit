from __future__ import annotations

import csv
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


def markdown_table_to_rows(markdown_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw_line in str(markdown_text or "").splitlines():
        line = raw_line.strip()
        if not line or "|" not in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        rows.append(cells)
    return [row for row in rows if any(cell for cell in row)]


def html_table_to_rows(html: str) -> list[list[str]]:
    parser = _TableParser()
    try:
        parser.feed(str(html or ""))
        parser.close()
    except Exception:
        return []
    return [[str(cell or "").strip() for cell in row] for row in parser.rows if any(str(cell or "").strip() for cell in row)]


def table_to_rows(value: Any, markdown: str = "", html: str = "") -> list[list[str]]:
    if isinstance(value, list):
        if value and all(isinstance(row, list) for row in value):
            return [[str(cell or "").strip() for cell in row] for row in value if any(str(cell or "").strip() for cell in row)]
        if value and all(isinstance(row, dict) for row in value):
            keys: list[str] = []
            for row in value:
                for key in row:
                    if key not in keys:
                        keys.append(str(key))
            rows = [keys] if keys else []
            rows.extend([[str(row.get(key, "") or "").strip() for key in keys] for row in value])
            return [row for row in rows if any(row)]
    if isinstance(value, dict):
        for key in ("rows", "table", "cells", "table_body", "body"):
            rows = table_to_rows(value.get(key))
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
    return []


def non_empty_cell_ratio(rows: list[list[Any]]) -> float:
    total = 0
    filled = 0
    for row in rows or []:
        for cell in row or []:
            total += 1
            if str(cell or "").strip():
                filled += 1
    return filled / total if total else 0.0


def table_shape(rows: list[list[Any]]) -> tuple[int, int]:
    return len(rows or []), max((len(row or []) for row in rows or []), default=0)


def write_rows_csv(path: Path, rows: list[list[Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows([[str(cell or "") for cell in row] for row in rows])
    return path


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None
        self._in_cell = False
        self._rowspan = 1
        self._colspan = 1
        self._pending_spans: dict[int, tuple[int, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "tr":
            self._row = []
            for column, (remaining, value) in sorted(self._pending_spans.items()):
                self._set_cell(column, value)
                if remaining <= 1:
                    del self._pending_spans[column]
                else:
                    self._pending_spans[column] = (remaining - 1, value)
        elif lowered in {"td", "th"}:
            self._cell_parts = []
            self._in_cell = True
            attributes = {str(key).lower(): value for key, value in attrs}
            self._rowspan = _positive_span(attributes.get("rowspan"))
            self._colspan = _positive_span(attributes.get("colspan"))
        elif lowered == "br" and self._in_cell and self._cell_parts is not None:
            self._cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_cell and self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            value = re.sub(r"\s+", " ", "".join(self._cell_parts)).strip()
            column = self._next_open_column()
            for offset in range(self._colspan):
                target = column + offset
                self._set_cell(target, value if offset == 0 else "")
                if self._rowspan > 1:
                    self._pending_spans[target] = (self._rowspan - 1, value if offset == 0 else "")
            self._cell_parts = None
            self._in_cell = False
        elif lowered == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def _next_open_column(self) -> int:
        if self._row is None:
            return 0
        for column, value in enumerate(self._row):
            if value is None:
                return column
        return len(self._row)

    def _set_cell(self, column: int, value: str) -> None:
        if self._row is None:
            return
        while len(self._row) <= column:
            self._row.append(None)  # type: ignore[arg-type]
        self._row[column] = value


def _positive_span(value: str | None) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1
