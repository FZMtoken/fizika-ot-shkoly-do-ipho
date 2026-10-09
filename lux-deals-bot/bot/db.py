from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from .models import JetWatch, Watch

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    cabin TEXT NOT NULL,
    max_price REAL,
    check_positioning INTEGER NOT NULL DEFAULT 1,
    check_awards INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    route TEXT NOT NULL,
    cabin TEXT NOT NULL,
    currency TEXT NOT NULL,
    price REAL NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history ON price_history(route, cabin, currency);
CREATE TABLE IF NOT EXISTS jet_watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    origins TEXT NOT NULL,
    destinations TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    max_price REAL,
    currency TEXT NOT NULL DEFAULT 'USD',
    min_seats INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notified (
    key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_watch(row) -> Watch:
    return Watch(
        id=row[0],
        user_id=row[1],
        origin=row[2],
        destination=row[3],
        date_from=date.fromisoformat(row[4]),
        date_to=date.fromisoformat(row[5]),
        cabin=row[6],
        max_price=row[7],
        check_positioning=bool(row[8]),
        check_awards=bool(row[9]),
    )


_WATCH_COLS = (
    "id, user_id, origin, destination, date_from, date_to, cabin, max_price, "
    "check_positioning, check_awards"
)


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() не вызван"
        return self._conn

    # --- подписки ---
    async def add_watch(self, w: Watch) -> int:
        cur = await self.conn.execute(
            "INSERT INTO watches (user_id, origin, destination, date_from, date_to, cabin, "
            "max_price, check_positioning, check_awards, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                w.user_id, w.origin, w.destination, w.date_from.isoformat(), w.date_to.isoformat(),
                w.cabin, w.max_price, int(w.check_positioning), int(w.check_awards), _now(),
            ),
        )
        await self.conn.commit()
        w.id = cur.lastrowid
        return w.id

    async def list_watches(self, user_id: int | None = None) -> list[Watch]:
        if user_id is None:
            sql, args = f"SELECT {_WATCH_COLS} FROM watches ORDER BY id", ()
        else:
            sql, args = f"SELECT {_WATCH_COLS} FROM watches WHERE user_id=? ORDER BY id", (user_id,)
        async with self.conn.execute(sql, args) as cur:
            return [_row_to_watch(r) for r in await cur.fetchall()]

    async def delete_watch(self, watch_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM watches WHERE id=? AND user_id=?", (watch_id, user_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def delete_expired_watches(self, today: date) -> int:
        n = 0
        for table in ("watches", "jet_watches"):
            cur = await self.conn.execute(
                f"DELETE FROM {table} WHERE date_to < ?", (today.isoformat(),)
            )
            n += cur.rowcount
        await self.conn.commit()
        return n

    # --- подписки на джеты ---
    async def add_jet_watch(self, w: JetWatch) -> int:
        cur = await self.conn.execute(
            "INSERT INTO jet_watches (user_id, origins, destinations, date_from, date_to, "
            "max_price, currency, min_seats, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                w.user_id, ",".join(w.origins), ",".join(w.destinations), w.date_from.isoformat(),
                w.date_to.isoformat(), w.max_price, w.currency, w.min_seats, _now(),
            ),
        )
        await self.conn.commit()
        w.id = cur.lastrowid
        return w.id

    async def list_jet_watches(self, user_id: int | None = None) -> list[JetWatch]:
        sql = (
            "SELECT id, user_id, origins, destinations, date_from, date_to, max_price, currency, "
            "min_seats "
            "FROM jet_watches"
        )
        args: tuple = ()
        if user_id is not None:
            sql, args = sql + " WHERE user_id=?", (user_id,)
        async with self.conn.execute(sql + " ORDER BY id", args) as cur:
            rows = await cur.fetchall()
        return [
            JetWatch(
                id=r[0], user_id=r[1],
                origins=[c for c in r[2].split(",") if c],
                destinations=[c for c in r[3].split(",") if c],
                date_from=date.fromisoformat(r[4]), date_to=date.fromisoformat(r[5]),
                max_price=r[6], currency=r[7], min_seats=r[8],
            )
            for r in rows
        ]

    async def delete_jet_watch(self, watch_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM jet_watches WHERE id=? AND user_id=?", (watch_id, user_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # --- история цен ---
    async def add_price(self, route: str, cabin: str, currency: str, price: float) -> None:
        await self.conn.execute(
            "INSERT INTO price_history VALUES (?,?,?,?,?)", (route, cabin, currency, price, _now())
        )
        await self.conn.commit()

    async def typical_price(
        self, route: str, cabin: str, currency: str, days: int = 60, min_samples: int = 5
    ) -> float | None:
        """Медиана цен за последние `days` дней; None, если данных мало."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with self.conn.execute(
            "SELECT price FROM price_history WHERE route=? AND cabin=? AND currency=? "
            "AND observed_at >= ?",
            (route, cabin, currency, since),
        ) as cur:
            prices = [r[0] for r in await cur.fetchall()]
        if len(prices) < min_samples:
            return None
        return statistics.median(prices)

    # --- антиспам уведомлений ---
    async def mark_notified(self, key: str) -> bool:
        """True, если ключ новый (уведомление ещё не отправлялось)."""
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO notified (key, created_at) VALUES (?, ?)", (key, _now())
        )
        await self.conn.commit()
        return cur.rowcount > 0
