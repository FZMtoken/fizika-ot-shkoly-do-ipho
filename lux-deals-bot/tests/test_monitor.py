import asyncio
from datetime import date

from bot.config import Settings
from bot.db import Database
from bot.models import FlightOffer, Watch
from bot.monitor import Monitor
from bot.providers.demo import DemoAwardProvider, DemoFlightProvider

TODAY = date(2026, 10, 9)
DAY = date(2026, 12, 1)


class FakeFlights:
    """Из MOW бизнес дорогой, из IST дешёвый, эконом MOW→IST копеечный."""

    async def search(self, origin, destination, day, cabin):
        prices = {("MOW", "BKK", "business"): 5000, ("IST", "BKK", "business"): 2500,
                  ("MOW", "IST", "economy"): 200}
        price = prices.get((origin, destination, cabin))
        if price is None:
            return []
        return [FlightOffer(origin, destination, day, cabin, price, "USD", "X", 0)]

    async def close(self):
        pass


def run(coro):
    return asyncio.run(coro)


async def _make(flights, awards=None):
    db = Database(":memory:")
    await db.connect()
    s = Settings(duffel_token="x", positioning_hubs=["IST", "CAI"])
    return db, Monitor(s, db, flights, awards)


def test_positioning_and_limit_and_dedupe():
    async def scenario():
        db, m = await _make(FakeFlights())
        w = Watch(None, 1, "MOW", "BKK", DAY, DAY, max_price=6000)
        await db.add_watch(w)
        res = await m.check_watch(w, today=TODAY)
        assert res.best.price == 5000
        assert len(res.messages) == 2
        assert "ниже вашего лимита" in res.messages[0]
        assert "Позиционный перелёт" in res.messages[1] and "IST" in res.messages[1]
        # повторная проверка не шлёт то же самое
        again = await m.check_watch(w, today=TODAY)
        assert again.messages == []
        # ручная проверка (/check) показывает всё
        manual = await m.check_watch(w, dedupe=False, today=TODAY)
        assert len(manual.messages) == 2
        await db.close()

    run(scenario())


def test_demo_providers_end_to_end():
    async def scenario():
        db, m = await _make(DemoFlightProvider(), DemoAwardProvider())
        w = Watch(None, 1, "LON", "NYC", date(2026, 11, 1), date(2026, 11, 30))
        await db.add_watch(w)
        res = await m.check_watch(w, today=TODAY)
        assert res.best is not None and res.best.currency == "USD"
        assert await db.list_watches(1)
        assert await db.delete_watch(w.id, 2) is False
        assert await db.delete_watch(w.id, 1) is True
        await db.close()

    run(scenario())


def test_typical_price_needs_history():
    async def scenario():
        db, _ = await _make(FakeFlights())
        for p in [100, 200, 300, 400]:
            await db.add_price("A-B", "business", "USD", p)
        assert await db.typical_price("A-B", "business", "USD") is None
        await db.add_price("A-B", "business", "USD", 500)
        assert await db.typical_price("A-B", "business", "USD") == 300
        await db.close()

    run(scenario())
