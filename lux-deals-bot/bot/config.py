from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Города, откуда бизнес-класс часто продаётся заметно дешевле
# (региональные тарифы, распродажи Qatar/Emirates/Turkish и т.п.).
DEFAULT_POSITIONING_HUBS = ["IST", "CAI", "CMB", "OSL", "ARN", "AMS", "MAD", "DOH"]


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


@dataclass
class Settings:
    telegram_token: str = ""
    duffel_token: str = ""
    seats_aero_key: str = ""
    db_path: str = "data/bot.db"
    check_interval_min: int = 180
    max_dates_per_watch: int = 4
    deal_threshold: float = 0.7
    positioning_min_saving: float = 0.15
    positioning_hubs: list[str] = field(default_factory=lambda: list(DEFAULT_POSITIONING_HUBS))
    empty_legs_feed: str = ""
    award_max_miles: dict[str, int] = field(
        default_factory=lambda: {"business": 90_000, "first": 130_000}
    )

    @property
    def demo_mode(self) -> bool:
        return not self.duffel_token

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        hubs_raw = os.getenv("POSITIONING_HUBS", "").strip()
        hubs = [h.strip().upper() for h in hubs_raw.split(",") if h.strip()]
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            duffel_token=os.getenv("DUFFEL_TOKEN", "").strip(),
            seats_aero_key=os.getenv("SEATS_AERO_KEY", "").strip(),
            db_path=os.getenv("DB_PATH", "data/bot.db").strip(),
            check_interval_min=_int("CHECK_INTERVAL_MIN", 180),
            max_dates_per_watch=_int("MAX_DATES_PER_WATCH", 4),
            deal_threshold=_float("DEAL_THRESHOLD", 0.7),
            positioning_min_saving=_float("POSITIONING_MIN_SAVING", 0.15),
            positioning_hubs=hubs or list(DEFAULT_POSITIONING_HUBS),
            empty_legs_feed=os.getenv("EMPTY_LEGS_FEED", "").strip(),
            award_max_miles={
                "business": _int("AWARD_MAX_MILES_BUSINESS", 90_000),
                "first": _int("AWARD_MAX_MILES_FIRST", 130_000),
            },
        )
