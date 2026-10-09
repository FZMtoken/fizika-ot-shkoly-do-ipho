from __future__ import annotations

import logging
import re
from datetime import date

import httpx

from ..models import FlightOffer

log = logging.getLogger(__name__)

API_URL = "https://api.duffel.com/air/offer_requests"


def parse_iso_duration(value: str | None) -> int | None:
    """'PT13H25M' / 'P1DT2H' -> минуты."""
    if not value:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", value)
    if not m:
        return None
    d, h, mins = (int(x) if x else 0 for x in m.groups())
    return d * 1440 + h * 60 + mins


def parse_offers(payload: dict, cabin: str, day: date) -> list[FlightOffer]:
    offers = []
    for raw in payload.get("data", {}).get("offers", []):
        slices = raw.get("slices") or []
        if not slices:
            continue
        sl = slices[0]
        segments = sl.get("segments") or []
        if not segments:
            continue
        carriers = {s.get("marketing_carrier", {}).get("name") or "" for s in segments}
        offers.append(
            FlightOffer(
                origin=sl["origin"]["iata_code"],
                destination=sl["destination"]["iata_code"],
                departure_date=day,
                cabin=cabin,
                price=float(raw["total_amount"]),
                currency=raw["total_currency"],
                carrier=", ".join(sorted(c for c in carriers if c))
                or raw.get("owner", {}).get("name", "?"),
                stops=len(segments) - 1,
                duration_min=parse_iso_duration(sl.get("duration")),
                source="duffel",
            )
        )
    return offers


class DuffelProvider:
    def __init__(self, token: str, max_connections: int = 1):
        self.max_connections = max_connections
        self._client = httpx.AsyncClient(
            timeout=60,
            headers={
                "Authorization": f"Bearer {token}",
                "Duffel-Version": "v2",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def search(self, origin: str, destination: str, day: date, cabin: str) -> list[FlightOffer]:
        body = {
            "data": {
                "slices": [
                    {"origin": origin, "destination": destination, "departure_date": day.isoformat()}
                ],
                "passengers": [{"type": "adult"}],
                "cabin_class": cabin,
                "max_connections": self.max_connections,
            }
        }
        try:
            resp = await self._client.post(
                API_URL, params={"return_offers": "true", "supplier_timeout": 20000}, json=body
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("Duffel %s-%s %s: %s", origin, destination, day, e)
            return []
        return parse_offers(resp.json(), cabin, day)

    async def close(self) -> None:
        await self._client.aclose()
