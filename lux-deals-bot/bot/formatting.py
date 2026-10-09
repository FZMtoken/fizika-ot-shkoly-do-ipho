from __future__ import annotations

from html import escape

from .models import CABIN_LABELS, AwardOffer, FlightOffer, PositioningDeal, PriceDeal, Watch


def money(amount: float, currency: str) -> str:
    return f"{amount:,.0f} {currency}".replace(",", " ")


def _duration(minutes: int | None) -> str:
    if not minutes:
        return ""
    return f", {minutes // 60} ч {minutes % 60:02d} мин"


def _stops(n: int) -> str:
    return "прямой" if n == 0 else f"пересадок: {n}"


def offer_line(o: FlightOffer) -> str:
    return (
        f"{o.origin} → {o.destination}, {o.departure_date:%d.%m.%Y}, "
        f"{CABIN_LABELS.get(o.cabin, o.cabin)}\n"
        f"✈️ {escape(o.carrier)} ({_stops(o.stops)}{_duration(o.duration_min)})\n"
        f"💰 <b>{money(o.price, o.currency)}</b>"
    )


def watch_line(w: Watch) -> str:
    limit = f", до {money(w.max_price, 'USD')}" if w.max_price else ""
    return (
        f"#{w.id} {w.origin} → {w.destination}, {w.date_from:%d.%m}–{w.date_to:%d.%m.%Y}, "
        f"{CABIN_LABELS[w.cabin]}{limit}"
    )


def price_deal_message(d: PriceDeal, demo: bool = False) -> str:
    if d.reason == "below_typical":
        head = f"🔥 <b>Цена на {d.discount_pct}% ниже обычной</b>"
        tail = f"\nОбычно: {money(d.typical_price, d.offer.currency)}"
    else:
        head = "✅ <b>Цена ниже вашего лимита</b>"
        tail = ""
    return (
        f"{head}{_demo(demo)}\n\n{offer_line(d.offer)}{tail}\n\n"
        f'<a href="{d.offer.book_url}">Проверить и купить</a>'
    )


def positioning_message(d: PositioningDeal, demo: bool = False) -> str:
    p, m = d.positioning, d.main
    return (
        f"🧭 <b>Позиционный перелёт: экономия {d.saving_pct}%</b>{_demo(demo)}\n\n"
        f"Из {p.origin} напрямую в {m.destination}: {money(d.direct_price, m.currency)}\n"
        f"Через {d.hub}: <b>{money(d.total, m.currency)}</b> "
        f"(вы экономите {money(d.saving, m.currency)})\n\n"
        f"1️⃣ Эконом {p.origin} → {d.hub}, {p.departure_date:%d.%m}: {money(p.price, p.currency)} "
        f'— <a href="{p.book_url}">билет</a>\n'
        f"2️⃣ {CABIN_LABELS[m.cabin].capitalize()} {d.hub} → {m.destination}, "
        f"{m.departure_date:%d.%m}: {money(m.price, m.currency)}, {escape(m.carrier)} "
        f'— <a href="{m.book_url}">билет</a>\n\n'
        "⚠️ Это два отдельных билета: если первый рейс задержат, вторая авиакомпания "
        "не обязана вас ждать. Прилетайте в хаб заранее (лучше накануне)."
    )


def awards_message(watch: Watch, awards: list[AwardOffer], demo: bool = False) -> str:
    lines = [
        f"🎟 <b>Места за мили: {watch.origin} → {watch.destination}, "
        f"{CABIN_LABELS[watch.cabin]}</b>{_demo(demo)}\n"
    ]
    for a in awards:
        taxes = f" + {money(a.taxes, a.taxes_currency or '')}" if a.taxes else ""
        direct = "прямой" if a.direct else "с пересадкой"
        lines.append(
            f"• {a.day:%d.%m}: <b>{a.miles:,} миль</b>".replace(",", " ")
            + f"{taxes} — {escape(a.program)}, {escape(a.airlines)}, {direct}, мест: {a.seats}"
        )
    lines.append(
        "\nБронируйте на сайте программы лояльности. Мили часто можно получить, "
        "переведя баллы банковских карт (Amex, Chase, Citi и т.п.)."
    )
    return "\n".join(lines)


def _demo(demo: bool) -> str:
    return "\n<i>(демо-режим, цены вымышленные)</i>" if demo else ""
