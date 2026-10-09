from __future__ import annotations

import logging
from datetime import date

import httpx

from ..models import AwardOffer

log = logging.getLogger(__name__)

API_URL = "https://seats.aero/partnerapi/search"
CABIN_PREFIX = {"economy": "Y", "premium": "W", "business": "J", "first": "F"}


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_availability(payload: dict, cabin: str) -> list[AwardOffer]:
    p = CABIN_PREFIX[cabin]
    offers = []
    for item in payload.get("data", []):
        if not item.get(f"{p}Available"):
            continue
        miles = _int(item.get(f"{p}MileageCost"))
        if miles <= 0:
            continue
        route = item.get("Route") or {}
        taxes_minor = item.get(f"{p}TotalTaxes")
        offers.append(
            AwardOffer(
                origin=route.get("OriginAirport", "?"),
                destination=route.get("DestinationAirport", "?"),
                day=date.fromisoformat(item["Date"][:10]),
                cabin=cabin,
                miles=miles,
                program=item.get("Source") or route.get("Source", "?"),
                airlines=item.get(f"{p}Airlines") or "",
                seats=_int(item.get(f"{p}RemainingSeats")),
                direct=bool(item.get(f"{p}Direct")),
                # seats.aero отдаёт сборы в минимальных единицах валюты (центах)
                taxes=taxes_minor / 100 if isinstance(taxes_minor, (int, float)) else None,
                taxes_currency=item.get("TaxesCurrency"),
            )
        )
    return offers


class SeatsAeroProvider:
    def __init__(self, api_key: str):
        self._client = httpx.AsyncClient(
            timeout=30, headers={"Partner-Authorization": api_key, "Accept": "application/json"}
        )

    async def search(
        self, origin: str, destination: str, date_from: date, date_to: date, cabin: str
    ) -> list[AwardOffer]:
        params = {
            "origin_airport": origin,
            "destination_airport": destination,
            "start_date": date_from.isoformat(),
            "end_date": date_to.isoformat(),
            "cabin": cabin,
            "take": 500,
        }
        try:
            resp = await self._client.get(API_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("seats.aero %s-%s: %s", origin, destination, e)
            return []
        return parse_availability(resp.json(), cabin)

    async def close(self) -> None:
        await self._client.aclose()
