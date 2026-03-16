from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

_BASE_URL = "https://v6.bvg.transport.rest"
_BERLIN = ZoneInfo("Europe/Berlin")


def _next_tuesday_8am() -> str:
    """Return next Tuesday 08:00 Europe/Berlin as ISO 8601 string."""
    now = datetime.now(_BERLIN)
    days_ahead = (1 - now.weekday()) % 7  # Tuesday = weekday 1
    if days_ahead == 0 and now.hour >= 8:
        days_ahead = 7
    target = (now + timedelta(days=days_ahead)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    return target.isoformat()


def nearest_stop(lat: float, lng: float) -> dict:
    """Return the nearest public transit stop to the given coordinates.

    Returns a dict with: id, name, lat, lng.
    """
    r = requests.get(
        f"{_BASE_URL}/locations/nearby",
        params={"latitude": lat, "longitude": lng, "results": 1, "stops": "true", "poi": "false"},
        timeout=10,
    )
    r.raise_for_status()
    stop = r.json()[0]
    return {
        "id": stop["id"],
        "name": stop["name"],
        "lat": stop["location"]["latitude"],
        "lng": stop["location"]["longitude"],
    }


def fetch_reachable_stops(lat: float, lng: float, address: str, max_duration: int) -> list[dict]:
    """Fetch reachable stops from the API (no caching).

    Searches for next Tuesday at 08:00 Europe/Berlin.
    Each stop dict contains: id, name, lat, lng, duration (minutes).
    """
    r = requests.get(
        f"{_BASE_URL}/stops/reachable-from",
        params={
            "latitude": lat,
            "longitude": lng,
            "address": address,
            "maxDuration": max_duration,
            "when": _next_tuesday_8am(),
        },
        timeout=15,
    )
    r.raise_for_status()

    best: dict[str, dict] = {}
    for timeslice in r.json().get("reachable", []):
        duration = timeslice["duration"]
        for station in timeslice["stations"]:
            sid = station["id"]
            if sid not in best or duration < best[sid]["duration"]:
                loc = station["location"]
                best[sid] = {
                    "id": sid,
                    "name": station["name"],
                    "lat": loc["latitude"],
                    "lng": loc["longitude"],
                    "duration": duration,
                }
    return list(best.values())
