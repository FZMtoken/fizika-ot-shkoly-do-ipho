from __future__ import annotations

from ..config import Settings
from .base import AwardProvider, FlightProvider
from .demo import DemoAwardProvider, DemoFlightProvider
from .duffel import DuffelProvider
from .seats_aero import SeatsAeroProvider


def build_providers(settings: Settings) -> tuple[FlightProvider, AwardProvider | None]:
    if settings.demo_mode:
        return DemoFlightProvider(), DemoAwardProvider()
    flights = DuffelProvider(settings.duffel_token)
    awards = SeatsAeroProvider(settings.seats_aero_key) if settings.seats_aero_key else None
    return flights, awards


__all__ = ["AwardProvider", "FlightProvider", "build_providers"]
