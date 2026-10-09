from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import quote

CABINS = ("business", "first")
CABIN_LABELS = {"economy": "эконом", "business": "бизнес", "first": "первый класс"}


def google_flights_url(origin: str, destination: str, day: date, cabin: str) -> str:
    q = f"Flights from {origin} to {destination} on {day.isoformat()} {cabin} class one way"
    return "https://www.google.com/travel/flights?q=" + quote(q)


@dataclass
class FlightOffer:
    origin: str
    destination: str
    departure_date: date
    cabin: str
    price: float
    currency: str
    carrier: str
    stops: int
    duration_min: int | None = None
    source: str = "duffel"

    @property
    def book_url(self) -> str:
        return google_flights_url(self.origin, self.destination, self.departure_date, self.cabin)


@dataclass
class AwardOffer:
    origin: str
    destination: str
    day: date
    cabin: str
    miles: int
    program: str
    airlines: str
    seats: int
    direct: bool
    taxes: float | None = None
    taxes_currency: str | None = None


@dataclass
class Watch:
    id: int | None
    user_id: int
    origin: str
    destination: str
    date_from: date
    date_to: date
    cabin: str = "business"
    max_price: float | None = None
    check_positioning: bool = True
    check_awards: bool = True


@dataclass
class PriceDeal:
    offer: FlightOffer
    reason: str  # "below_max" | "below_typical"
    typical_price: float | None = None

    @property
    def discount_pct(self) -> int | None:
        if not self.typical_price:
            return None
        return round((1 - self.offer.price / self.typical_price) * 100)


@dataclass
class PositioningDeal:
    hub: str
    positioning: FlightOffer  # эконом до хаба
    main: FlightOffer  # бизнес/первый из хаба
    direct_price: float  # самый дешёвый прямой вариант из дома

    @property
    def total(self) -> float:
        return self.positioning.price + self.main.price

    @property
    def saving(self) -> float:
        return self.direct_price - self.total

    @property
    def saving_pct(self) -> int:
        return round(self.saving / self.direct_price * 100)


JET_CATEGORIES = {
    "light": "лёгкий",
    "midsize": "средний",
    "super-midsize": "средний+",
    "heavy": "большой",
    "ultra-long-range": "сверхдальний",
}


@dataclass
class EmptyLeg:
    """Перегоночный рейс частного джета (empty leg), продаётся со скидкой."""

    id: str
    origin: str
    destination: str
    date_from: date  # самая ранняя дата вылета
    date_to: date  # самая поздняя (у empty legs дата часто гибкая)
    aircraft: str
    seats: int
    operator: str
    url: str
    category: str = ""
    price: float | None = None  # None = цена по запросу
    currency: str = "USD"
    source: str = "feed"


@dataclass
class JetWatch:
    id: int | None
    user_id: int
    origins: list[str]
    destinations: list[str]  # пустой список = куда угодно
    date_from: date
    date_to: date
    max_price: float | None = None
    currency: str = "USD"  # валюта лимита
    min_seats: int = 1
