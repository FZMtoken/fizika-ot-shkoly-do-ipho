from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import formatting
from .db import Database
from .models import CABIN_LABELS, JetWatch, Watch
from .monitor import Monitor
from .parsing import (
    parse_date,
    parse_date_range,
    parse_iata,
    parse_iata_list,
    parse_price,
    parse_price_currency,
)

router = Router()

HELP = (
    "<b>Ищу реально дешёвый бизнес- и первый класс</b> ✈️\n\n"
    "Что я делаю для каждой подписки:\n"
    "• слежу за ценой и пишу, когда она ниже вашего лимита или заметно ниже обычной "
    "(распродажи, ошибочные тарифы);\n"
    "• проверяю <b>позиционные перелёты</b>: иногда дешевле долететь экономом до Стамбула, "
    "Каира или Осло и лететь бизнесом оттуда;\n"
    "• ищу <b>места за мили</b>: бизнес за 50–90 тыс. миль вместо тысяч долларов;\n"
    "• ловлю <b>empty legs</b>: частный джет, летящий пустым к следующему клиенту, "
    "со скидкой 50–75%.\n\n"
    "Команды:\n"
    "/watch — новая подписка на авиабилеты\n"
    "/jet — подписка на частные джеты (empty legs)\n"
    "/list — мои подписки\n"
    "/check — проверить подписки прямо сейчас\n"
    "/search IST DXB 2026-11-15 [first] — разовый поиск\n"
    "/cancel — отменить ввод"
)


class NewJetWatch(StatesGroup):
    origins = State()
    destinations = State()
    dates = State()
    seats = State()
    max_price = State()


class NewWatch(StatesGroup):
    origin = State()
    destination = State()
    dates = State()
    cabin = State()
    max_price = State()


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message, monitor: Monitor) -> None:
    text = HELP
    if monitor.settings.demo_mode:
        text += "\n\n<i>Бот работает в демо-режиме: цены вымышленные.</i>"
    await message.answer(text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


# --- /watch ---
@router.message(Command("watch"))
async def watch_start(message: Message, state: FSMContext) -> None:
    await state.set_state(NewWatch.origin)
    await message.answer("Откуда летим? Код аэропорта или города IATA, например <code>MOW</code>, <code>LON</code>, <code>IST</code>.")


@router.message(NewWatch.origin, F.text)
async def watch_origin(message: Message, state: FSMContext) -> None:
    code = parse_iata(message.text)
    if not code:
        await message.answer("Нужен трёхбуквенный код IATA, например <code>IST</code>.")
        return
    await state.update_data(origin=code)
    await state.set_state(NewWatch.destination)
    await message.answer("Куда? Например <code>DXB</code>, <code>BKK</code>, <code>NYC</code>.")


@router.message(NewWatch.destination, F.text)
async def watch_destination(message: Message, state: FSMContext) -> None:
    code = parse_iata(message.text)
    if not code:
        await message.answer("Нужен трёхбуквенный код IATA, например <code>DXB</code>.")
        return
    if code == (await state.get_data())["origin"]:
        await message.answer("Пункт назначения совпадает с вылетом. Введите другой код.")
        return
    await state.update_data(destination=code)
    await state.set_state(NewWatch.dates)
    await message.answer(
        "Когда? Одна дата или период до 60 дней:\n<code>01.12.2026 20.12.2026</code>"
    )


@router.message(NewWatch.dates, F.text)
async def watch_dates(message: Message, state: FSMContext) -> None:
    try:
        start, end = parse_date_range(message.text)
    except ValueError as e:
        await message.answer(f"{e} Пример: <code>01.12.2026 20.12.2026</code>")
        return
    await state.update_data(date_from=start.isoformat(), date_to=end.isoformat())
    await state.set_state(NewWatch.cabin)
    kb = InlineKeyboardBuilder()
    kb.button(text="Бизнес", callback_data="cabin:business")
    kb.button(text="Первый класс", callback_data="cabin:first")
    await message.answer("Класс обслуживания?", reply_markup=kb.as_markup())


@router.callback_query(NewWatch.cabin, F.data.startswith("cabin:"))
async def watch_cabin(call: CallbackQuery, state: FSMContext) -> None:
    cabin = call.data.split(":", 1)[1]
    await state.update_data(cabin=cabin)
    await state.set_state(NewWatch.max_price)
    await call.message.edit_text(f"Класс: {CABIN_LABELS[cabin]}")
    await call.message.answer(
        "Максимальная цена в USD за одного взрослого в одну сторону? "
        "Например <code>2500</code>. Или <code>-</code>, если без лимита: "
        "тогда сообщу только о ценах заметно ниже обычных."
    )
    await call.answer()


@router.message(NewWatch.max_price, F.text)
async def watch_max_price(message: Message, state: FSMContext, db: Database) -> None:
    try:
        max_price = parse_price(message.text)
    except ValueError:
        await message.answer("Введите число, например <code>2500</code>, или <code>-</code>.")
        return
    data = await state.get_data()
    await state.clear()
    w = Watch(
        id=None,
        user_id=message.chat.id,
        origin=data["origin"],
        destination=data["destination"],
        date_from=parse_date(data["date_from"]),
        date_to=parse_date(data["date_to"]),
        cabin=data["cabin"],
        max_price=max_price,
    )
    await db.add_watch(w)
    await message.answer(
        f"Готово! Подписка {formatting.watch_line(w)}\n\n"
        "Буду проверять регулярно. /check — проверить прямо сейчас."
    )


# --- /list ---
@router.message(Command("list"))
async def cmd_list(message: Message, db: Database) -> None:
    watches = await db.list_watches(message.chat.id)
    jets = await db.list_jet_watches(message.chat.id)
    if not watches and not jets:
        await message.answer("Подписок пока нет. Создайте: /watch или /jet")
        return
    kb = InlineKeyboardBuilder()
    for w in watches:
        kb.button(text=f"🗑 #{w.id} {w.origin}→{w.destination}", callback_data=f"del:{w.id}")
    for j in jets:
        kb.button(text=f"🗑 🛩 #{j.id} {','.join(j.origins)}", callback_data=f"deljet:{j.id}")
    kb.adjust(1)
    text = "\n".join(
        [formatting.watch_line(w) for w in watches] + [formatting.jet_watch_line(j) for j in jets]
    )
    await message.answer(f"<b>Ваши подписки:</b>\n{text}", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(call: CallbackQuery, db: Database) -> None:
    watch_id = int(call.data.split(":", 1)[1])
    ok = await db.delete_watch(watch_id, call.message.chat.id)
    await call.answer("Удалено" if ok else "Не найдено")
    if ok:
        await call.message.answer(f"Подписка #{watch_id} удалена.")


@router.callback_query(F.data.startswith("deljet:"))
async def cb_delete_jet(call: CallbackQuery, db: Database) -> None:
    watch_id = int(call.data.split(":", 1)[1])
    ok = await db.delete_jet_watch(watch_id, call.message.chat.id)
    await call.answer("Удалено" if ok else "Не найдено")
    if ok:
        await call.message.answer(f"Подписка на джеты #{watch_id} удалена.")


# --- /check ---
@router.message(Command("check"))
async def cmd_check(message: Message, db: Database, monitor: Monitor) -> None:
    watches = await db.list_watches(message.chat.id)
    jets = await db.list_jet_watches(message.chat.id)
    if not watches and not jets:
        await message.answer("Подписок пока нет. Создайте: /watch или /jet")
        return
    await message.answer("Проверяю, это может занять минуту… ⏳")
    if jets:
        legs = await monitor.empty_legs.fetch() if monitor.empty_legs else []
        for j in jets:
            msgs = await monitor.check_jet_watch(j, legs, dedupe=False)
            if not msgs:
                await message.answer(f"{formatting.jet_watch_line(j)}\n→ подходящих рейсов пока нет")
            for msg in msgs:
                await message.answer(msg)
    for w in watches:
        res = await monitor.check_watch(w, dedupe=False)
        best = (
            f"лучшая цена {formatting.money(res.best.price, res.best.currency)} "
            f"({res.best.departure_date:%d.%m}, {res.best.carrier})"
            if res.best
            else "предложений не найдено"
        )
        await message.answer(f"{formatting.watch_line(w)}\n→ {best}")
        for msg in res.messages:
            await message.answer(msg)


# --- /search ---
@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject, monitor: Monitor) -> None:
    usage = "Формат: <code>/search IST DXB 2026-11-15</code> (можно добавить <code>first</code>)"
    args = (command.args or "").split()
    if len(args) not in (3, 4):
        await message.answer(usage)
        return
    origin, destination = parse_iata(args[0]), parse_iata(args[1])
    cabin = args[3].lower() if len(args) == 4 else "business"
    try:
        day = parse_date(args[2])
    except ValueError:
        day = None
    if not (origin and destination and day and cabin in ("business", "first")):
        await message.answer(usage)
        return
    offers = sorted(
        await monitor.flights.search(origin, destination, day, cabin), key=lambda o: o.price
    )[:3]
    if not offers:
        await message.answer("Ничего не нашёл на эту дату.")
        return
    demo = "\n<i>(демо-режим, цены вымышленные)</i>" if monitor.settings.demo_mode else ""
    parts = [f'{formatting.offer_line(o)}\n<a href="{o.book_url}">Купить</a>' for o in offers]
    await message.answer("\n\n".join(parts) + demo)


# --- /jet ---
@router.message(Command("jet"))
async def jet_start(message: Message, state: FSMContext) -> None:
    await state.set_state(NewJetWatch.origins)
    await message.answer(
        "🛩 <b>Частные джеты: empty legs</b>\n\n"
        "Из каких аэропортов готовы вылететь? Перечислите коды IATA, включая аэропорты "
        "деловой авиации. Например: <code>LTN FAB LBG</code> (Лондон, Париж) или "
        "<code>VKO DME</code>."
    )


@router.message(NewJetWatch.origins, F.text)
async def jet_origins(message: Message, state: FSMContext) -> None:
    codes = parse_iata_list(message.text)
    if not codes:
        await message.answer("Нужны коды IATA через пробел (до 10), например <code>LTN FAB</code>.")
        return
    await state.update_data(origins=codes)
    await state.set_state(NewJetWatch.destinations)
    await message.answer(
        "Куда? Коды через пробел, например <code>NCE GVA IBZ</code>, "
        "или <code>*</code> — куда угодно."
    )


@router.message(NewJetWatch.destinations, F.text)
async def jet_destinations(message: Message, state: FSMContext) -> None:
    text = message.text.strip().lower()
    if text in {"*", "любой", "куда угодно", "any"}:
        codes: list[str] = []
    else:
        codes = parse_iata_list(message.text)
        if not codes:
            await message.answer("Нужны коды IATA через пробел или <code>*</code>.")
            return
    await state.update_data(destinations=codes)
    await state.set_state(NewJetWatch.dates)
    await message.answer("Когда? Период до 60 дней: <code>01.12.2026 20.12.2026</code>")


@router.message(NewJetWatch.dates, F.text)
async def jet_dates(message: Message, state: FSMContext) -> None:
    try:
        start, end = parse_date_range(message.text)
    except ValueError as e:
        await message.answer(f"{e} Пример: <code>01.12.2026 20.12.2026</code>")
        return
    await state.update_data(date_from=start.isoformat(), date_to=end.isoformat())
    await state.set_state(NewJetWatch.seats)
    await message.answer("Сколько вас человек?")


@router.message(NewJetWatch.seats, F.text)
async def jet_seats(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit() or not 1 <= int(text) <= 19:
        await message.answer("Введите число от 1 до 19.")
        return
    await state.update_data(min_seats=int(text))
    await state.set_state(NewJetWatch.max_price)
    await message.answer(
        "Максимальная цена <b>за весь самолёт</b>? Например <code>8000 EUR</code> или "
        "<code>10000</code> (USD). <code>-</code> — без лимита, присылать всё, включая "
        "«цену по запросу»."
    )


@router.message(NewJetWatch.max_price, F.text)
async def jet_max_price(message: Message, state: FSMContext, db: Database) -> None:
    try:
        max_price, currency = parse_price_currency(message.text)
    except ValueError:
        await message.answer(
            "Введите сумму, например <code>8000 EUR</code>, или <code>-</code>. "
            "Валюты: USD, EUR, GBP, CHF, AED."
        )
        return
    data = await state.get_data()
    await state.clear()
    w = JetWatch(
        id=None,
        user_id=message.chat.id,
        origins=data["origins"],
        destinations=data["destinations"],
        date_from=parse_date(data["date_from"]),
        date_to=parse_date(data["date_to"]),
        max_price=max_price,
        currency=currency,
        min_seats=data["min_seats"],
    )
    await db.add_jet_watch(w)
    await message.answer(
        f"Готово! {formatting.jet_watch_line(w)}\n\n"
        "Empty legs появляются за несколько дней до вылета и разбираются быстро, "
        "поэтому пришлю сразу, как найду. /check — проверить сейчас."
    )
