"""Weather and climate from Open-Meteo.

Free and keyless, which is why the project needs no weather signup. Licence is
CC BY 4.0, non-commercial up to 10,000 calls/day, so the UI must carry attribution
and the backend must cache aggressively (see backend/cache.py).

Replaces the previous WeatherAPI integration, for two reasons: its 10-year history
endpoint is a paid feature, so the seasonal signal silently failed on a free key;
and each call fetched a single day, so building a climate normal meant eleven
sequential requests.

Here one archive request returns ten years of daily values, from which we derive
both the same-month climate normal and mean annual rainfall. Mean annual rainfall
is what the crop matcher compares against a crop's ECOCROP envelope, so this is
load-bearing data rather than decoration.

Reference: https://open-meteo.com/en/docs (WMO weather codes used for conditions)
"""

from __future__ import annotations

from calendar import month_name as MONTH_NAMES
from datetime import date, timedelta

from cache import Served, cached_call, coord_key, weather_cache
from config import HISTORY_TTL_S, LIVE_TTL_S, OPEN_METEO_ARCHIVE, OPEN_METEO_FORECAST
from sources.http import UpstreamError, get_json

SOURCE_NAME = "Open-Meteo"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

# ECMWF archive lags real time by about five days; asking for later dates returns
# nulls rather than an error, which would quietly corrupt the climate normal.
ARCHIVE_LAG_DAYS = 7
CLIMATE_YEARS = 10

# WMO 4677 interpretation codes, as used by Open-Meteo.
_WMO_CONDITIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def describe_code(code: int | None) -> str:
    if code is None:
        return "Conditions unavailable"
    return _WMO_CONDITIONS.get(int(code), "Mixed conditions")


def _mean(values: list[float]) -> float | None:
    usable = [v for v in values if v is not None]
    return round(sum(usable) / len(usable), 1) if usable else None


async def _fetch_forecast(latitude: float, longitude: float) -> dict:
    payload = await get_json(
        OPEN_METEO_FORECAST,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m,precipitation,weather_code,relative_humidity_2m",
            "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min",
            "forecast_days": 2,
            "timezone": "auto",
        },
        timeout=15.0,
        unavailable_message="Live weather is temporarily unavailable. Please try again shortly.",
    )

    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    times: list[str] = daily.get("time") or []

    rain_today = (daily.get("precipitation_probability_max") or [None])[0]
    tomorrow_rain = (daily.get("precipitation_sum") or [None, None])
    tomorrow_mm = tomorrow_rain[1] if len(tomorrow_rain) > 1 else None

    return {
        "temperature_c": current.get("temperature_2m"),
        "feels_like_note": None,
        "condition": describe_code(current.get("weather_code")),
        "wind_kmh": current.get("wind_speed_10m"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "rain_chance_pct": rain_today,
        "tomorrow_rain_mm": tomorrow_mm,
        "tomorrow_date": times[1] if len(times) > 1 else None,
        "timezone": payload.get("timezone"),
        "elevation_m": payload.get("elevation"),
    }


async def _fetch_climate(latitude: float, longitude: float) -> dict:
    """Ten years of daily values, aggregated into the signals we actually use."""
    end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    start = end.replace(year=end.year - CLIMATE_YEARS)

    payload = await get_json(
        OPEN_METEO_ARCHIVE,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "auto",
        },
        timeout=45.0,
        retries=1,
        unavailable_message=(
            "Historical climate data is temporarily unavailable. "
            "Crop suggestions need it, so they are paused for now."
        ),
    )

    daily = payload.get("daily") or {}
    days: list[str] = daily.get("time") or []
    temps: list[float | None] = daily.get("temperature_2m_mean") or []
    rain: list[float | None] = daily.get("precipitation_sum") or []

    if not days:
        raise UpstreamError(
            "Historical climate data came back empty for this location.",
            status_code=502,
        )

    month = date.today().month
    per_year_rain: dict[int, float] = {}
    per_year_days: dict[int, int] = {}
    same_month_temps: list[float] = []
    same_month_rain: dict[int, float] = {}

    for iso, temp, precip in zip(days, temps, rain):
        try:
            day = date.fromisoformat(iso)
        except ValueError:
            continue
        mm = float(precip) if precip is not None else 0.0

        per_year_rain[day.year] = per_year_rain.get(day.year, 0.0) + mm
        per_year_days[day.year] = per_year_days.get(day.year, 0) + 1

        if day.month == month:
            if temp is not None:
                same_month_temps.append(float(temp))
            same_month_rain[day.year] = same_month_rain.get(day.year, 0.0) + mm

    # Only years with near-complete coverage count, so a half-downloaded year
    # cannot report a drought that did not happen.
    complete_years = [year for year, count in per_year_days.items() if count >= 360]
    annual_totals = [per_year_rain[year] for year in sorted(complete_years)]

    if not annual_totals:
        raise UpstreamError(
            "Not enough historical data to estimate annual rainfall for this location.",
            status_code=502,
        )

    return {
        "years_span": [start.year, end.year],
        "years_used": len(annual_totals),
        "annual_rainfall_mm": round(sum(annual_totals) / len(annual_totals)),
        "same_month": month,
        # The name is derived here, from the same `month` the aggregation used,
        # rather than recomputed by the caller. Two calls to date.today() either
        # side of midnight could otherwise label July's normal "August".
        "same_month_name": MONTH_NAMES[month],
        "same_month_mean_temp_c": _mean(same_month_temps),
        "same_month_rainfall_mm": (
            round(sum(same_month_rain.values()) / len(same_month_rain))
            if same_month_rain else None
        ),
        "same_month_years": len(same_month_rain),
    }


async def get_field_climate(latitude: float, longitude: float) -> tuple[dict, bool]:
    """Live conditions plus climate normals for a coordinate.

    Returns (payload, served_from_cache). One upstream pair per coordinate per
    cache window, no matter how many components ask for it.
    """
    cache_key = coord_key(latitude, longitude)

    forecast: Served = await cached_call(
        weather_cache,
        namespace="forecast",
        key=cache_key,
        ttl=LIVE_TTL_S,
        producer=lambda: _fetch_forecast(latitude, longitude),
    )
    climate: Served = await cached_call(
        weather_cache,
        namespace="climate",
        key=cache_key,
        ttl=HISTORY_TTL_S,
        producer=lambda: _fetch_climate(latitude, longitude),
    )

    payload = {
        "current": forecast.value,
        "climate": climate.value,
        "source": {
            "name": SOURCE_NAME,
            "attribution": ATTRIBUTION,
            "licence": "CC BY 4.0 (non-commercial)",
            "cached": forecast.cached and climate.cached,
        },
    }
    return payload, (forecast.cached and climate.cached)
