"""Live conditions from MET Norway (api.met.no).

Why this exists
---------------
Open-Meteo is the project's first choice and stays first: one request covers
current conditions and the next two days, and its archive answers the climate
question too. But its free tier is metered per IP address, and a deployed
instance does not own its IP — a free Render box shares egress with other
tenants, so the quota is routinely spent by someone else's application. The
symptom is a permanent 429 from a service that works perfectly on the
developer's laptop.

MET Norway is the Norwegian Meteorological Institute's public API. It is
keyless, covers the whole planet, and is published for programmatic use by
applications rather than browsers, so it does not share Open-Meteo's problem.
Their terms ask only for an identifying User-Agent and no hammering; both are
already handled globally (config.HTTP_USER_AGENT, 30-minute cache in weather.py).

What it does not have: a probability-of-rain field. Rather than invent one, this
module returns None and the UI omits the number.

Reference: https://api.met.no/weatherapi/locationforecast/2.0/documentation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config import METNO_FORECAST
from sources.http import UpstreamError, get_json

SOURCE_NAME = "MET Norway"
ATTRIBUTION = "Weather data from MET Norway (api.met.no, CC BY 4.0)"

# Symbol codes arrive as `<weather>_<time of day>`, e.g. `lightrain_night`. The
# suffix is presentation, not weather, so it is stripped before matching. The
# order matters: `heavyrainshowersandthunder` must hit thunder before rain.
_CONDITIONS: tuple[tuple[str, str], ...] = (
    ("thunder", "Thunderstorm"),
    ("sleet", "Sleet"),
    ("snow", "Snow"),
    ("heavyrain", "Heavy rain"),
    ("lightrain", "Light rain"),
    ("drizzle", "Drizzle"),
    ("rainshowers", "Rain showers"),
    ("rain", "Rain"),
    ("fog", "Fog"),
    ("partlycloudy", "Partly cloudy"),
    ("cloudy", "Cloudy"),
    ("fair", "Mainly clear"),
    ("clearsky", "Clear sky"),
)


def describe_symbol(symbol_code: str | None) -> str:
    if not symbol_code:
        return "Conditions unavailable"
    base = str(symbol_code).split("_")[0]
    for fragment, label in _CONDITIONS:
        if fragment in base:
            return label
    return "Mixed conditions"


def _parse_time(value: str) -> datetime:
    # MET Norway always emits UTC with a trailing Z.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _precipitation_block(entry: dict) -> tuple[float | None, int]:
    """The next rainfall figure and the hours it covers.

    Takes a whole timeseries entry, which nests every forecast under `data`.
    Each entry can carry up to three overlapping forecasts (1, 6 and 12 hours
    ahead). Taking the first that exists avoids adding the same rain twice, and
    the 12-hour block is ignored for the tomorrow total because it can span two
    calendar days.
    """
    data = entry.get("data") or {}
    for key, span in (("next_1_hours", 1), ("next_6_hours", 6), ("next_12_hours", 12)):
        details = (data.get(key) or {}).get("details") or {}
        if details.get("precipitation_amount") is not None:
            return float(details["precipitation_amount"]), span
    return None, 0


async def fetch_current(latitude: float, longitude: float) -> dict:
    """Current conditions in the shape the field profile already expects."""
    payload = await get_json(
        METNO_FORECAST,
        params={"lat": latitude, "lon": longitude},
        timeout=20.0,
        retries=1,
        unavailable_message="Live weather is temporarily unavailable. Please try again shortly.",
    )

    series = (payload.get("properties") or {}).get("timeseries") or []
    if not series:
        raise UpstreamError(
            "Live weather came back empty for this location.",
            status_code=502,
        )

    first = series[0]
    details = (first.get("data") or {}).get("instant", {}).get("details") or {}
    symbol = (
        (first.get("data") or {}).get("next_1_hours", {}).get("summary") or {}
    ).get("symbol_code")

    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    tomorrow_mm = 0.0
    any_tomorrow = False
    for entry in series:
        amount, span = _precipitation_block(entry)
        if amount is None or span == 12:
            continue
        if _parse_time(entry["time"]).date() == tomorrow:
            tomorrow_mm += amount
            any_tomorrow = True

    wind_ms = details.get("wind_speed")
    # The provider speaks SI; the dashboard speaks km/h.
    wind_kmh = round(wind_ms * 3.6, 1) if wind_ms is not None else None

    coordinates = (payload.get("geometry") or {}).get("coordinates") or []
    elevation = coordinates[2] if len(coordinates) > 2 else None

    return {
        "temperature_c": details.get("air_temperature"),
        "feels_like_note": None,
        "condition": describe_symbol(symbol),
        "wind_kmh": wind_kmh,
        "humidity_pct": details.get("relative_humidity"),
        "precipitation_mm": _precipitation_block(first)[0],
        # MET Norway does not publish a probability for this product. A null is
        # the honest answer; the card shows the figure only when it exists.
        "rain_chance_pct": None,
        "tomorrow_rain_mm": round(tomorrow_mm, 1) if any_tomorrow else None,
        "tomorrow_date": tomorrow.isoformat(),
        # Timeseries timestamps are UTC, so the dates above are UTC dates.
        "timezone": "UTC",
        "elevation_m": elevation,
    }
