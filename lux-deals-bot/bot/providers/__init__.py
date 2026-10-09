from __future__ import annotations

from ..config import Settings
from .base import AwardProvider, EmptyLegProvider, FlightProvider
from .demo import DemoAwardProvider, DemoFlightProvider
from .duffel import DuffelProvider
from .empty_legs import DemoEmptyLegProvider, JsonFeedEmptyLegProvider
from .seats_aero import SeatsAeroProvider


def build_providers(settings: Settings) -> tuple[FlightProvider, AwardProvider | None]:
    if settings.demo_mode:
        return DemoFlightProvider(), DemoAwardProvider()
    flights = DuffelProvider(settings.duffel_token)
    awards = SeatsAeroProvider(settings.seats_aero_key) if settings.seats_aero_key else None
    return flights, awards


def build_empty_legs_provider(settings: Settings) -> EmptyLegProvider:
    """Без фида — демо-данные, чтобы раздел джетов можно было попробовать сразу."""
    if settings.empty_legs_feed:
        return JsonFeedEmptyLegProvider(settings.empty_legs_feed)
    return DemoEmptyLegProvider()


__all__ = [
    "AwardProvider", "EmptyLegProvider", "FlightProvider",
    "build_empty_legs_provider", "build_providers",
]
