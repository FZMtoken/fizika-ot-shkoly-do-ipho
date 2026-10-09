from __future__ import annotations

import re
from datetime import date, datetime

IATA_RE = re.compile(r"^[A-Z]{3}$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}")
MAX_RANGE_DAYS = 60


def parse_iata(text: str) -> str | None:
    code = text.strip().upper()
    return code if IATA_RE.match(code) else None


def parse_date(token: str) -> date:
    if "-" in token:
        return date.fromisoformat(token)
    return datetime.strptime(token, "%d.%m.%Y").date()


def parse_date_range(text: str, today: date | None = None) -> tuple[date, date]:
    """'01.11.2026 20.11.2026', '2026-11-01 — 2026-11-20' или одна дата. ValueError при ошибке."""
    today = today or date.today()
    tokens = DATE_RE.findall(text)
    if not 1 <= len(tokens) <= 2:
        raise ValueError("Нужна одна дата или две: начало и конец периода.")
    try:
        dates = [parse_date(t) for t in tokens]
    except ValueError:
        raise ValueError("Не получилось разобрать дату.") from None
    start, end = dates[0], dates[-1]
    if end < start:
        start, end = end, start
    if end <= today:
        raise ValueError("Даты уже прошли.")
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValueError(f"Период не длиннее {MAX_RANGE_DAYS} дней.")
    return start, end


def parse_price(text: str) -> float | None:
    """'-' / 'нет' -> None; '2500' / '2 500' -> 2500.0. ValueError при ошибке."""
    t = text.strip().lower()
    if t in {"-", "нет", "no", "skip", "0"}:
        return None
    value = float(t.replace(" ", "").replace(",", "."))
    if value <= 0:
        raise ValueError
    return value
