"""Field weather, with a second provider behind the first.

The dashboard asks one question — "what is it like on this field, this month" —
and there are three ways to answer it. This module owns that policy so the
endpoints do not have to: Open-Meteo first, because a single request covers both
current conditions and ten years of history; then MET Norway for live
conditions and NASA POWER for the climate normals if Open-Meteo refuses.

The refusal is the reason this file exists. Open-Meteo's free tier is metered
per IP address, and a deployed instance shares egress with its neighbours, so
the quota is routinely exhausted by another application. Locally every request
succeeds, which makes the failure look like a bug in this code. Falling back
keeps the app honest: the card still shows real measurements, labelled with
whichever institute actually supplied them.

Caching happens once, around the whole fallback chain, so a fallback result is
remembered exactly as long as a primary one would be.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from cache import Served, cached_call, coord_key, weather_cache
from config import HISTORY_TTL_S, LIVE_TTL_S
from sources import metno, nasa_power, open_meteo
from sources.http import UpstreamError

log = logging.getLogger(__name__)

LICENCE = "CC BY 4.0"


async def _with_fallback(
    primary: Callable[[], Awaitable[dict]],
    backup: Callable[[], Awaitable[dict]],
    primary_name: str,
    backup_name: str,
) -> dict:
    """Run `primary`, and on any upstream failure run `backup` instead.

    Returns {payload, provider}. The primary's error is re-raised only when the
    backup fails too — otherwise a recoverable throttle on one provider would
    take down a dashboard the second provider could have filled.
    """
    try:
        return {"payload": await primary(), "provider": primary_name}
    except UpstreamError as error:
        log.warning("%s failed (%s); trying %s", primary_name, error.message, backup_name)
        try:
            return {"payload": await backup(), "provider": backup_name}
        except UpstreamError:
            # Both are down. Report the first, because it is the one whose
            # absence the UI text was written around.
            raise error


async def get_field_climate(latitude: float, longitude: float) -> tuple[dict, bool]:
    """Live conditions plus climate normals for a coordinate.

    Returns (payload, served_entirely_from_cache). One upstream pair per
    coordinate per cache window, no matter how many components ask for it.
    """
    key = coord_key(latitude, longitude)

    forecast: Served = await cached_call(
        weather_cache,
        namespace="forecast",
        key=key,
        ttl=LIVE_TTL_S,
        producer=lambda: _with_fallback(
            lambda: open_meteo.fetch_forecast(latitude, longitude),
            lambda: metno.fetch_current(latitude, longitude),
            open_meteo.SOURCE_NAME,
            metno.SOURCE_NAME,
        ),
    )
    climate: Served = await cached_call(
        weather_cache,
        namespace="climate",
        key=key,
        ttl=HISTORY_TTL_S,
        producer=lambda: _with_fallback(
            lambda: open_meteo.fetch_climate(latitude, longitude),
            lambda: nasa_power.fetch_climate(latitude, longitude),
            open_meteo.SOURCE_NAME,
            nasa_power.SOURCE_NAME,
        ),
    )

    current_block: dict[str, Any] = forecast.value
    climate_block: dict[str, Any] = climate.value
    providers = {current_block["provider"], climate_block["provider"]}

    payload = {
        "current": current_block["payload"],
        "climate": climate_block["payload"],
        "source": {
            "name": current_block["provider"],
            "climate_name": climate_block["provider"],
            "attribution": " · ".join(
                _attribution_for(name) for name in sorted(providers)
            ),
            "licence": LICENCE,
            "fallback": bool(providers - {open_meteo.SOURCE_NAME}),
            "cached": forecast.cached and climate.cached,
        },
    }
    return payload, (forecast.cached and climate.cached)


def _attribution_for(name: str) -> str:
    if name == metno.SOURCE_NAME:
        return metno.ATTRIBUTION
    if name == nasa_power.SOURCE_NAME:
        return nasa_power.ATTRIBUTION
    return open_meteo.ATTRIBUTION
