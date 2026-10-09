from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Awaitable, Callable

from . import deals, formatting
from .config import Settings
from .db import Database
from .models import FlightOffer, Watch
from .providers import AwardProvider, FlightProvider

log = logging.getLogger(__name__)

SendFn = Callable[[int, str], Awaitable[None]]


@dataclass
class CheckResult:
    best: FlightOffer | None = None
    messages: list[str] = field(default_factory=list)


class Monitor:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        flights: FlightProvider,
        awards: AwardProvider | None,
    ):
        self.settings = settings
        self.db = db
        self.flights = flights
        self.awards = awards

    async def _cheapest(self, origin: str, destination: str, day: date, cabin: str) -> FlightOffer | None:
        return deals.cheapest(await self.flights.search(origin, destination, day, cabin))

    async def check_watch(self, w: Watch, dedupe: bool = True, today: date | None = None) -> CheckResult:
        s, demo = self.settings, self.settings.demo_mode
        today = today or date.today()
        result = CheckResult()

        async def is_new(key: str) -> bool:
            # mark_notified вызываем всегда, чтобы ручная проверка тоже гасила повторы
            fresh = await self.db.mark_notified(key)
            return fresh or not dedupe

        # 1. Прямые цены из города пользователя
        route = f"{w.origin}-{w.destination}"
        found = []
        for day in deals.sample_dates(w.date_from, w.date_to, s.max_dates_per_watch, today):
            best = await self._cheapest(w.origin, w.destination, day, w.cabin)
            if best:
                found.append(best)
        result.best = deals.cheapest(found)

        for offer in found:
            typical = await self.db.typical_price(route, w.cabin, offer.currency)
            deal = deals.evaluate_price(offer, typical, w.max_price, s.deal_threshold)
            await self.db.add_price(route, w.cabin, offer.currency, offer.price)
            key = f"price:{w.id}:{offer.departure_date}:{round(offer.price, -1)}"
            if deal and await is_new(key):
                result.messages.append(formatting.price_deal_message(deal, demo))

        # 2. Позиционные перелёты: эконом до хаба накануне + премиум из хаба
        if w.check_positioning and result.best:
            day = result.best.departure_date
            pos_day = day - timedelta(days=1)
            if pos_day <= today:
                pos_day = day
            pos_deals = []
            for hub in s.positioning_hubs:
                if hub in (w.origin, w.destination):
                    continue
                main = await self._cheapest(hub, w.destination, day, w.cabin)
                if not main or main.price >= result.best.price:
                    continue
                positioning = await self._cheapest(w.origin, hub, pos_day, "economy")
                deal = deals.evaluate_positioning(
                    hub, result.best, positioning, main, s.positioning_min_saving
                )
                if deal:
                    pos_deals.append(deal)
            pos_deals.sort(key=lambda d: d.total)
            for deal in pos_deals[:2]:
                key = f"pos:{w.id}:{deal.hub}:{day}:{round(deal.total, -1)}"
                if await is_new(key):
                    result.messages.append(formatting.positioning_message(deal, demo))

        # 3. Места за мили
        if w.check_awards and self.awards:
            start = max(w.date_from, today + timedelta(days=1))
            if start <= w.date_to:
                offers = await self.awards.search(w.origin, w.destination, start, w.date_to, w.cabin)
                max_miles = s.award_max_miles.get(w.cabin, 100_000)
                fresh = []
                for a in deals.filter_awards(offers, max_miles):
                    if await is_new(f"award:{w.id}:{a.program}:{a.day}:{a.miles}"):
                        fresh.append(a)
                if fresh:
                    result.messages.append(formatting.awards_message(w, fresh, demo))

        return result

    async def run_once(self, send: SendFn) -> None:
        await self.db.delete_expired_watches(date.today())
        for w in await self.db.list_watches():
            try:
                res = await self.check_watch(w)
            except Exception:
                log.exception("Ошибка проверки подписки #%s", w.id)
                continue
            for msg in res.messages:
                try:
                    await send(w.user_id, msg)
                except Exception:
                    log.exception("Не удалось отправить сообщение пользователю %s", w.user_id)

    async def run_forever(self, send: SendFn) -> None:
        while True:
            log.info("Проверка подписок…")
            try:
                await self.run_once(send)
            except Exception:
                log.exception("Сбой цикла мониторинга")
            await asyncio.sleep(self.settings.check_interval_min * 60)
