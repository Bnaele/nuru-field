"""Reverse geocoding from Nominatim (OpenStreetMap).

Why this replaces the hardcoded bounding boxes
----------------------------------------------
The hackathon build decided the region by testing coordinates against nine
hand-written South African rectangles. Anything outside South Africa returned
None, which silently degraded crop matching and market lookup, and the boxes
themselves were approximate — a farm on a provincial border could be attributed
to the wrong one.

Nominatim returns the actual administrative region for any coordinate on earth,
so the app is no longer structurally limited to one country. The bounding boxes
are kept only as an offline fallback in backend/geo.py.

Usage policy: at most one request per second and an identifying User-Agent, both
enforced here. Responses are cached for a month because administrative names do
not change.
"""

from __future__ import annotations

import asyncio
import time

from cache import Served, cached_call, coord_key, geo_cache
from config import GEO_TTL_S, NOMINATIM_MIN_INTERVAL_S, NOMINATIM_REVERSE
from sources.http import UpstreamError, get_json

SOURCE_NAME = "OpenStreetMap Nominatim"
ATTRIBUTION = "Place names © OpenStreetMap contributors (ODbL)"

_rate_lock = asyncio.Lock()
_last_call = 0.0


async def _throttle() -> None:
    """Serialise calls so we never exceed one request per second."""
    global _last_call
    async with _rate_lock:
        elapsed = time.monotonic() - _last_call
        if elapsed < NOMINATIM_MIN_INTERVAL_S:
            await asyncio.sleep(NOMINATIM_MIN_INTERVAL_S - elapsed)
        _last_call = time.monotonic()


async def _fetch_region(latitude: float, longitude: float) -> dict:
    await _throttle()
    payload = await get_json(
        NOMINATIM_REVERSE,
        params={
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "zoom": 10,          # administrative area, not a street address
            "addressdetails": 1,
        },
        timeout=15.0,
        retries=1,
        unavailable_message="Place lookup is temporarily unavailable.",
    )

    address = payload.get("address") or {}
    # `state` is the province in South Africa and the first-level region almost
    # everywhere else. City/town/municipality give a friendlier label than the
    # full postal address string.
    region = (
        address.get("state")
        or address.get("province")
        or address.get("region")
        or address.get("state_district")
    )
    locality = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
    )

    return {
        "region": region,
        "locality": locality,
        "country": address.get("country"),
        "country_code": (address.get("country_code") or "").upper() or None,
        "display_name": payload.get("display_name"),
        "source": {"name": SOURCE_NAME, "attribution": ATTRIBUTION},
    }


async def get_region(latitude: float, longitude: float) -> dict | None:
    """Administrative region for a coordinate, or None if lookup failed.

    Returning None rather than raising lets the caller fall back to the offline
    bounding boxes, because losing a region name should not fail the whole
    field profile.
    """
    try:
        served: Served = await cached_call(
            geo_cache,
            namespace="nominatim",
            key=coord_key(latitude, longitude),
            ttl=GEO_TTL_S,
            producer=lambda: _fetch_region(latitude, longitude),
        )
    except UpstreamError:
        return None
    return served.value
