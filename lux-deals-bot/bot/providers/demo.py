"""Детерминированные вымышленные цены, чтобы бот работал без API-ключей."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from ..models import AwardOffer, FlightOffer

CARRIERS = ["Qatar Airways", "Emirates", "Turkish Airlines", "Lufthansa", "Etihad", "Singapore Airlines"]
PROGRAMS = ["aeroplan", "flyingblue", "alaska", "virginatlantic", "qantas"]


def _rnd(*parts) -> float:
    """Псевдослучайное число в [0, 1), стабильное для одинаковых аргументов."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _base_price(origin: str, destination: str, cabin: str) -> float:
    base = {"economy": 450, "business": 3200, "first": 7000}[cabin]
    return base * (0.7 + _rnd(origin, destination, cabin))


class DemoFlightProvider:
    async def search(self, origin: str, destination: str, day: date, cabin: str) -> list[FlightOffer]:
        base = _base_price(origin, destination, cabin)
        offers = []
        for i in range(3):
            r = _rnd(origin, destination, day, cabin, i)
            price = base * (0.85 + 0.4 * r)
            # иногда «ошибочный тариф» / распродажа
            if i == 0 and _rnd("deal", origin, destination, day, cabin) < 0.15:
                price = base * 0.45
            offers.append(
                FlightOffer(
                    origin=origin,
                    destination=destination,
                    departure_date=day,
                    cabin=cabin,
                    price=round(price, 2),
                    currency="USD",
                    carrier=CARRIERS[int(r * len(CARRIERS))],
                    stops=int(r * 2),
                    duration_min=int(300 + r * 600),
                    source="demo",
                )
            )
        return offers

    async def close(self) -> None:
        pass


class DemoAwardProvider:
    async def search(
        self, origin: str, destination: str, date_from: date, date_to: date, cabin: str
    ) -> list[AwardOffer]:
        offers = []
        day = date_from
        while day <= date_to:
            r = _rnd("award", origin, destination, day, cabin)
            if r < 0.2:
                base = 60_000 if cabin == "business" else 90_000
                offers.append(
                    AwardOffer(
                        origin=origin,
                        destination=destination,
                        day=day,
                        cabin=cabin,
                        miles=int(base * (0.8 + r * 3) // 500 * 500),
                        program=PROGRAMS[int(r * 5 * len(PROGRAMS)) % len(PROGRAMS)],
                        airlines=CARRIERS[int(r * 100) % len(CARRIERS)],
                        seats=1 + int(r * 20) % 4,
                        direct=r < 0.1,
                        taxes=round(50 + r * 400, 2),
                        taxes_currency="USD",
                    )
                )
            day += timedelta(days=1)
        return offers

    async def close(self) -> None:
        pass
