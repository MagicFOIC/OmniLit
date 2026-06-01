from __future__ import annotations

from datetime import date, timedelta


def parse_iso_date(value: str) -> date:
    """解析 ISO 日期。参数：YYYY-MM-DD 文本。返回值：日期对象。"""
    return date.fromisoformat(value.strip())


def month_grid(year: int, month: int) -> list[date]:
    """生成日期选择器的 42 格月份视图。参数：年份和月份。返回值：包含相邻月份日期的列表。"""
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    return [start + timedelta(days=offset) for offset in range(42)]


def shift_month(value: date, offset: int) -> date:
    """按月移动日期并限制月底边界。参数：原日期和月份偏移。返回值：调整后的日期。"""
    index = value.year * 12 + value.month - 1 + offset
    year, month_index = divmod(index, 12)
    month = month_index + 1
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))
