"""Источники empty legs.

Открытого API у рынка нет: профессиональная база Avinode доступна только брокерам и
операторам. Поэтому бот читает простой JSON-фид (по URL или из файла), который может
отдавать партнёр-брокер, собственный парсер или админка. Формат:

{"legs": [{
    "id": "abc123",
    "origin": "LBG", "destination": "NCE",
    "date_from": "2026-11-03", "date_to": "2026-11-05",   # date_to необязателен
    "aircraft": "Citation XLS", "category": "midsize",       # category необязательна
    "seats": 8,
    "price": 4900, "currency": "EUR",                        # price можно не указывать
    "operator": "Example Jets", "url": "https://..."
}]}
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import httpx

from ..models import EmptyLeg
from .demo import _rnd

log = logging.getLogger(__name__)


def parse_feed(payload: dict) -> list[EmptyLeg]:
    legs = []
    for raw in payload.get("legs", []):
        try:
            start = date.fromisoformat(raw["date_from"])
            price = raw.get("price")
            legs.append(
                EmptyLeg(
                    id=str(raw["id"]),
                    origin=raw["origin"].upper(),
                    destination=raw["destination"].upper(),
                    date_from=start,
                    date_to=date.fromisoformat(raw["date_to"]) if raw.get("date_to") else start,
                    aircraft=raw.get("aircraft", "?"),
                    seats=int(raw.get("seats", 0)),
                    operator=raw.get("operator", "?"),
                    url=raw.get("url", ""),
                    category=raw.get("category", ""),
                    price=float(price) if price not in (None, "") else None,
                    currency=raw.get("currency", "USD"),
                    source="feed",
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Пропускаю некорректный empty leg %r: %s", raw.get("id"), e)
    return legs


class JsonFeedEmptyLegProvider:
    is_demo = False

    def __init__(self, source: str):
        self.source = source
        self._client = httpx.AsyncClient(timeout=30) if source.startswith("http") else None

    async def fetch(self) -> list[EmptyLeg]:
        try:
            if self._client:
                resp = await self._client.get(self.source)
                resp.raise_for_status()
                payload = resp.json()
            else:
                payload = json.loads(Path(self.source).read_text(encoding="utf-8"))
        except (httpx.HTTPError, OSError, ValueError) as e:
            log.warning("Фид empty legs недоступен (%s): %s", self.source, e)
            return []
        return parse_feed(payload)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()


# Популярные аэропорты деловой авиации
DEMO_AIRPORTS = ["LTN", "FAB", "LBG", "NCE", "GVA", "ZRH", "LIN", "IBZ", "PMI", "OLB",
                 "DXB", "DWC", "VKO", "TEB", "VNY", "OPF", "MLE", "CPT"]
DEMO_AIRCRAFT = [
    ("Citation CJ3", "light", 7, 2500),
    ("Phenom 300", "light", 8, 3000),
    ("Citation XLS+", "midsize", 9, 4500),
    ("Challenger 350", "super-midsize", 9, 6500),
    ("Falcon 7X", "heavy", 13, 12000),
    ("Global 6000", "ultra-long-range", 14, 18000),
]
DEMO_OPERATORS = ["Demo Air Charter", "Sample Jets", "Example Aviation"]


class DemoEmptyLegProvider:
    is_demo = True

    async def fetch(self, today: date | None = None) -> list[EmptyLeg]:
        today = today or date.today()
        legs = []
        for i in range(120):
            r = _rnd("leg", today, i)
            o = DEMO_AIRPORTS[int(r * len(DEMO_AIRPORTS))]
            d = DEMO_AIRPORTS[int(_rnd("dest", today, i) * len(DEMO_AIRPORTS))]
            if o == d:
                continue
            aircraft, cat, seats, base = DEMO_AIRCRAFT[int(_rnd("ac", i) * len(DEMO_AIRCRAFT))]
            start = today + timedelta(days=1 + int(_rnd("day", today, i) * 30))
            p = _rnd("price", today, i)
            legs.append(
                EmptyLeg(
                    id=f"demo-{today}-{i}",
                    origin=o,
                    destination=d,
                    date_from=start,
                    date_to=start + timedelta(days=int(r * 3)),
                    aircraft=aircraft,
                    seats=seats,
                    operator=DEMO_OPERATORS[i % len(DEMO_OPERATORS)],
                    url="https://example.com/empty-leg",
                    category=cat,
                    price=None if p < 0.2 else round(base * (0.6 + p), -2),
                    currency="EUR",
                    source="demo",
                )
            )
        return legs

    async def close(self) -> None:
        pass
