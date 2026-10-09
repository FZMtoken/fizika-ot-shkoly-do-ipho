from datetime import date

import pytest

from bot import deals
from bot.models import AwardOffer, FlightOffer
from bot.parsing import parse_date_range, parse_iata, parse_price
from bot.providers.duffel import parse_iso_duration, parse_offers
from bot.providers.seats_aero import parse_availability

TODAY = date(2026, 10, 9)


def offer(price, origin="MOW", dest="DXB", cabin="business", currency="USD", day=date(2026, 12, 1)):
    return FlightOffer(origin, dest, day, cabin, price, currency, "X", 0)


def test_sample_dates_spreads_and_skips_past():
    got = deals.sample_dates(date(2026, 10, 1), date(2026, 10, 30), 4, TODAY)
    assert got[0] == date(2026, 10, 10)
    assert got[-1] == date(2026, 10, 30)
    assert len(got) == 4
    assert deals.sample_dates(date(2026, 10, 1), date(2026, 10, 5), 4, TODAY) == []
    assert len(deals.sample_dates(date(2026, 11, 1), date(2026, 11, 2), 4, TODAY)) == 2


def test_evaluate_price():
    assert deals.evaluate_price(offer(2000), 3000, None, 0.7).reason == "below_typical"
    assert deals.evaluate_price(offer(2500), 3000, None, 0.7) is None
    assert deals.evaluate_price(offer(2500), None, 2600, 0.7).reason == "below_max"
    # лимит в USD не сравниваем с ценой в EUR
    assert deals.evaluate_price(offer(2500, currency="EUR"), None, 2600, 0.7) is None
    d = deals.evaluate_price(offer(1500), 3000, None, 0.7)
    assert d.discount_pct == 50


def test_evaluate_positioning():
    direct = offer(4000)
    pos = offer(150, dest="IST", cabin="economy")
    main = offer(2500, origin="IST")
    d = deals.evaluate_positioning("IST", direct, pos, main, 0.15)
    assert d.total == 2650 and d.saving == 1350 and d.saving_pct == 34
    assert deals.evaluate_positioning("IST", offer(2800), pos, main, 0.15) is None
    assert deals.evaluate_positioning("IST", direct, None, main, 0.15) is None


def test_filter_awards():
    mk = lambda miles, seats=2, direct=False: AwardOffer(
        "A", "B", date(2026, 12, 1), "business", miles, "p", "x", seats, direct
    )
    got = deals.filter_awards([mk(120_000), mk(70_000), mk(60_000, seats=0), mk(70_000, direct=True)], 90_000)
    assert [(a.miles, a.direct) for a in got] == [(70_000, True), (70_000, False)]


def test_parsing():
    assert parse_iata(" ist ") == "IST"
    assert parse_iata("ISTA") is None
    assert parse_date_range("01.12.2026 20.12.2026", TODAY) == (date(2026, 12, 1), date(2026, 12, 20))
    assert parse_date_range("2026-12-05", TODAY) == (date(2026, 12, 5), date(2026, 12, 5))
    with pytest.raises(ValueError):
        parse_date_range("01.01.2026", TODAY)
    with pytest.raises(ValueError):
        parse_date_range("01.11.2026 31.03.2027", TODAY)
    assert parse_price("-") is None
    assert parse_price("2 500") == 2500
    with pytest.raises(ValueError):
        parse_price("abc")


def test_duffel_parsing():
    assert parse_iso_duration("PT13H25M") == 805
    assert parse_iso_duration("P1DT2H") == 1560
    payload = {"data": {"offers": [{
        "total_amount": "2450.10", "total_currency": "USD", "owner": {"name": "Qatar Airways"},
        "slices": [{
            "origin": {"iata_code": "IST"}, "destination": {"iata_code": "BKK"}, "duration": "PT14H",
            "segments": [
                {"marketing_carrier": {"name": "Qatar Airways"}},
                {"marketing_carrier": {"name": "Qatar Airways"}},
            ],
        }],
    }]}}
    [o] = parse_offers(payload, "business", date(2026, 12, 1))
    assert (o.origin, o.destination, o.price, o.stops, o.carrier, o.duration_min) == (
        "IST", "BKK", 2450.10, 1, "Qatar Airways", 840
    )


def test_seats_aero_parsing():
    payload = {"data": [
        {"Date": "2026-12-01", "Source": "aeroplan",
         "Route": {"OriginAirport": "IST", "DestinationAirport": "BKK"},
         "JAvailable": True, "JMileageCost": "70000", "JRemainingSeats": 2, "JAirlines": "TK",
         "JDirect": True, "JTotalTaxes": 12345, "TaxesCurrency": "CAD"},
        {"Date": "2026-12-02", "Source": "aeroplan", "Route": {}, "JAvailable": False},
    ]}
    [a] = parse_availability(payload, "business")
    assert (a.miles, a.program, a.seats, a.direct, a.taxes) == (70000, "aeroplan", 2, True, 123.45)
