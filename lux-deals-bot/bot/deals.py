"""Логика поиска выгодных предложений. Без I/O — легко тестировать."""

from __future__ import annotations

from datetime import date, timedelta

from .models import AwardOffer, EmptyLeg, FlightOffer, JetWatch, PositioningDeal, PriceDeal


def sample_dates(date_from: date, date_to: date, max_n: int, today: date | None = None) -> list[date]:
    """Равномерно выбирает до max_n дат из диапазона, пропуская прошедшие."""
    today = today or date.today()
    start = max(date_from, today + timedelta(days=1))
    if start > date_to or max_n <= 0:
        return []
    span = (date_to - start).days
    if span + 1 <= max_n:
        return [start + timedelta(days=i) for i in range(span + 1)]
    if max_n == 1:
        return [start]
    step = span / (max_n - 1)
    return sorted({start + timedelta(days=round(i * step)) for i in range(max_n)})


def cheapest(offers: list[FlightOffer]) -> FlightOffer | None:
    return min(offers, key=lambda o: o.price, default=None)


def evaluate_price(
    offer: FlightOffer,
    typical_price: float | None,
    max_price: float | None,
    threshold: float,
    max_price_currency: str = "USD",
) -> PriceDeal | None:
    """Сделка, если цена ниже лимита пользователя или заметно ниже обычной для маршрута."""
    if typical_price and offer.price <= typical_price * threshold:
        return PriceDeal(offer, "below_typical", typical_price)
    if max_price is not None and offer.currency == max_price_currency and offer.price <= max_price:
        return PriceDeal(offer, "below_max", typical_price)
    return None


def evaluate_positioning(
    hub: str,
    direct: FlightOffer | None,
    positioning: FlightOffer | None,
    main: FlightOffer | None,
    min_saving: float,
) -> PositioningDeal | None:
    """Выгоден ли эконом до хаба + премиум-класс из хаба по сравнению с вылетом из дома."""
    if not (direct and positioning and main):
        return None
    if not (direct.currency == positioning.currency == main.currency):
        return None
    deal = PositioningDeal(hub=hub, positioning=positioning, main=main, direct_price=direct.price)
    if deal.saving >= direct.price * min_saving:
        return deal
    return None


def filter_awards(offers: list[AwardOffer], max_miles: int, limit: int = 5) -> list[AwardOffer]:
    good = [o for o in offers if o.miles <= max_miles and o.seats > 0]
    good.sort(key=lambda o: (o.miles, not o.direct, o.day))
    return good[:limit]


def match_empty_legs(
    legs: list[EmptyLeg], w: JetWatch, today: date | None = None
) -> list[EmptyLeg]:
    """Рейсы из нужных аэропортов в нужные даты, подходящие по местам и цене."""
    today = today or date.today()
    out = []
    for leg in legs:
        if leg.origin not in w.origins:
            continue
        if w.destinations and leg.destination not in w.destinations:
            continue
        # окно вылета пересекается с периодом пользователя и ещё не прошло
        if leg.date_to < max(w.date_from, today) or leg.date_from > w.date_to:
            continue
        if leg.seats < w.min_seats:
            continue
        if w.max_price is not None:
            # «цена по запросу» и цены в другой валюте не можем сравнить с лимитом — пропускаем
            if leg.price is None or leg.currency != w.currency or leg.price > w.max_price:
                continue
        out.append(leg)
    out.sort(key=lambda l: (l.date_from, l.price if l.price is not None else float("inf")))
    return out
