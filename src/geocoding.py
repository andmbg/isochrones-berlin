import requests

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_HEADERS = {"User-Agent": "isochrones-app/1.0"}


def reverse_geocode(lat: float, lng: float) -> str:
    """Return a human-readable address for the given coordinates.

    Format: '{postcode} {city}, {road}'
    Falls back to display_name if individual fields are missing.
    """
    r = requests.get(
        _NOMINATIM_URL,
        params={"lat": lat, "lon": lng, "format": "json"},
        headers=_HEADERS,
        timeout=5,
    )
    r.raise_for_status()
    data = r.json()

    if "error" in data:
        return data["display_name"]

    addr = data["address"]
    postcode = addr.get("postcode", "")
    city = addr.get("city") or addr.get("town") or addr.get("village", "")
    road = addr.get("road", "")

    if postcode and city and road:
        return f"{postcode} {city}, {road}"
    return data.get("display_name", f"{lat:.5f}, {lng:.5f}")
