from __future__ import annotations

from datetime import date
from typing import Protocol

from ..models import AwardOffer, FlightOffer


class FlightProvider(Protocol):
    async def search(
        self, origin: str, destination: str, day: date, cabin: str
    ) -> list[FlightOffer]: ...

    async def close(self) -> None: ...


class AwardProvider(Protocol):
    async def search(
        self, origin: str, destination: str, date_from: date, date_to: date, cabin: str
    ) -> list[AwardOffer]: ...

    async def close(self) -> None: ...
