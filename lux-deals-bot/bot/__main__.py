from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import Settings
from .db import Database
from .handlers import router
from .monitor import Monitor
from .providers import build_empty_legs_provider, build_providers


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    if not settings.telegram_token:
        sys.exit("Не задан TELEGRAM_BOT_TOKEN (см. .env.example)")
    if settings.demo_mode:
        logging.warning("DUFFEL_TOKEN не задан: работаю в демо-режиме на вымышленных ценах")

    db = Database(settings.db_path)
    await db.connect()
    flights, awards = build_providers(settings)
    empty_legs = build_empty_legs_provider(settings)
    monitor = Monitor(settings, db, flights, awards, empty_legs)

    bot = Bot(
        settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = Dispatcher()
    dp["db"] = db
    dp["monitor"] = monitor
    dp.include_router(router)

    async def send(chat_id: int, text: str) -> None:
        await bot.send_message(chat_id, text)

    task = asyncio.create_task(monitor.run_forever(send))
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await flights.close()
        if awards:
            await awards.close()
        await empty_legs.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
