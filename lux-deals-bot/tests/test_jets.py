import asyncio
import json
from datetime import date

import pytest

from bot import deals
from bot.config import Settings
from bot.db import Database
from bot.models import EmptyLeg, JetWatch
from bot.monitor import Monitor
from bot.parsing import parse_iata_list, parse_price_currency
from bot.providers.empty_legs import DemoEmptyLegProvider, JsonFeedEmptyLegProvider, parse_feed

TODAY = date(2026, 10, 9)


def leg(id, o="LBG", d="NCE", start=date(2026, 11, 3), end=None, price=5000.0, cur="EUR", seats=8):
    return EmptyLeg(id, o, d, start, end or start, "Citation XLS", seats, "Op", "https://x", "midsize",
                    price, cur)


def watch(**kw):
    base = dict(id=1, user_id=1, origins=["LBG", "FAB"], destinations=[],
                date_from=date(2026, 11, 1), date_to=date(2026, 11, 10))
    base.update(kw)
    return JetWatch(**base)


def test_match_empty_legs():
    legs = [
        leg("ok"),
        leg("wrong-origin", o="VKO"),
        leg("too-late", start=date(2026, 11, 20)),
        # гибкое окно 28.10–02.11 пересекается с периодом
        leg("flex", start=date(2026, 10, 28), end=date(2026, 11, 2)),
        leg("few-seats", seats=2),
        leg("on-request", price=None),
    ]
    got = [l.id for l in deals.match_empty_legs(legs, watch(min_seats=4), TODAY)]
    assert got == ["flex", "ok", "on-request"]

    # фильтр по назначению
    assert deals.match_empty_legs(legs, watch(destinations=["GVA"]), TODAY) == []

    # лимит: цена по запросу и чужая валюта отсекаются
    limited = watch(max_price=6000, currency="EUR")
    assert [l.id for l in deals.match_empty_legs([leg("a"), leg("b", price=None),
            leg("c", cur="USD"), leg("d", price=7000)], limited, TODAY)] == ["a"]

    # прошедшие рейсы не показываем
    assert deals.match_empty_legs([leg("past", start=date(2026, 10, 1))],
                                  watch(date_from=date(2026, 9, 1)), TODAY) == []


def test_parse_feed_and_file_provider(tmp_path):
    payload = {"legs": [
        {"id": 1, "origin": "lbg", "destination": "nce", "date_from": "2026-11-03",
         "aircraft": "Phenom 300", "seats": 7, "price": 3900, "currency": "EUR",
         "operator": "Op", "url": "https://x"},
        {"id": 2, "origin": "LBG"},  # битая запись пропускается
    ]}
    [l] = parse_feed(payload)
    assert (l.origin, l.destination, l.date_to, l.price) == ("LBG", "NCE", date(2026, 11, 3), 3900.0)

    f = tmp_path / "legs.json"
    f.write_text(json.dumps(payload))
    legs = asyncio.run(JsonFeedEmptyLegProvider(str(f)).fetch())
    assert len(legs) == 1
    assert asyncio.run(JsonFeedEmptyLegProvider(str(tmp_path / "nope.json")).fetch()) == []


def test_parsing_helpers():
    assert parse_iata_list("ltn, fab  LTN") == ["LTN", "FAB"]
    assert parse_iata_list("LTN XX") is None
    assert parse_price_currency("8 000 eur") == (8000.0, "EUR")
    assert parse_price_currency("10000") == (10000.0, "USD")
    assert parse_price_currency("-") == (None, "USD")
    with pytest.raises(ValueError):
        parse_price_currency("100 XYZ")


def test_monitor_jets_dedupe_and_demo():
    class Feed:
        is_demo = False

        async def fetch(self):
            return [leg("a"), leg("b", price=None)]

        async def close(self):
            pass

    async def scenario():
        db = Database(":memory:")
        await db.connect()
        m = Monitor(Settings(duffel_token="x"), db, None, None, Feed())
        w = watch(id=None)
        await db.add_jet_watch(w)
        [stored] = await db.list_jet_watches(1)
        assert stored.origins == ["LBG", "FAB"] and stored.destinations == []

        msgs = await m.check_jet_watch(stored, today=TODAY)
        assert len(msgs) == 1 and "LBG → NCE" in msgs[0] and "цена по запросу" in msgs[0]
        assert await m.check_jet_watch(stored, today=TODAY) == []
        assert len(await m.check_jet_watch(stored, dedupe=False, today=TODAY)) == 1

        assert await db.delete_expired_watches(date(2026, 12, 1)) == 1
        assert await db.list_jet_watches() == []

        demo_legs = await DemoEmptyLegProvider().fetch(TODAY)
        assert demo_legs and all(l.origin != l.destination for l in demo_legs)
        await db.close()

    asyncio.run(scenario())


def test_jet_message_is_capped():
    class Feed:
        is_demo = False

        async def fetch(self):
            return [leg(str(i)) for i in range(10)]

        async def close(self):
            pass

    async def scenario():
        db = Database(":memory:")
        await db.connect()
        m = Monitor(Settings(duffel_token="x"), db, None, None, Feed())
        w = watch(id=None)
        await db.add_jet_watch(w)
        [first] = await m.check_jet_watch(w, today=TODAY)
        assert first.count("LBG → NCE") == 6 and "ещё 4" in first
        [second] = await m.check_jet_watch(w, today=TODAY)
        assert second.count("LBG → NCE") == 4
        await db.close()

    asyncio.run(scenario())
