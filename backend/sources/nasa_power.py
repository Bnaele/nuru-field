"""Climate normals from NASA POWER.

Why this exists
---------------
The dashboard needs long-term rainfall and temperature, not just today's
weather: the crop matcher compares a field's annual rainfall against each
species' ECOCROP envelope, so this is load-bearing data. Open-Meteo's archive
supplies it on a developer machine, but its free tier is metered per IP and a
deployed instance shares its address with other tenants, which is what turns
the seasonal card into a 429 on Render.

NASA POWER is the same agency data behind the satellite record, served for
agricultural modelling. It is keyless, and its climatology endpoint answers the
whole question in one request instead of the ten years of daily values that
Open-Meteo requires. The numbers agree: for Johannesburg this reports 642 mm of
rain a year against Open-Meteo's 644.

One difference the UI has to carry: POWER publishes millimetres per day, so the
month and year totals below are that rate multiplied out by the length of the
period. The API returns -999 for a cell it cannot fill, and that is discarded
rather than charted as a drought.

Reference: https://power.larc.nasa.gov/docs/services/api/temporal/climatology/
"""

from __future__ import annotations

from calendar import month_name as MONTH_NAMES
from calendar import monthrange
from datetime import date

from config import NASA_POWER_CLIMATOLOGY
from sources.http import UpstreamError, get_json

SOURCE_NAME = "NASA POWER"
ATTRIBUTION = "Climate normals by NASA POWER (MERRA-2, CC BY 4.0)"

_MONTH_KEYS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# POWER publishes millimetres per day and temperatures in Celsius. Month totals
# multiply the rate by the length of a standard (non-leap) month.
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# POWER's documented fill value for "no data here".
_FILL = -999.0

NOTE = (
    "Long-term monthly averages from the NASA POWER reanalysis. This is a "
    "climate normal, not a drought or flood record."
)


def _value(series: dict, key: str) -> float | None:
    raw = series.get(key)
    if raw is None:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return None if number <= _FILL else number


async def fetch_climate(latitude: float, longitude: float) -> dict:
    """Same-month and annual normals, in the shape the field profile expects."""
    payload = await get_json(
        NASA_POWER_CLIMATOLOGY,
        params={
            # T2M_MIN is the coldest value in the record, not a mean of the daily
            # minimum: for Johannesburg it reports -4 °C for July, against an
            # average July night near 4 °C. It is kept under a name that says
            # exactly that, so nothing downstream can mistake it for a normal.
            "parameters": "T2M,T2M_MIN,PRECTOTCORR",
            "community": "AG",
            "latitude": latitude,
            "longitude": longitude,
            "format": "JSON",
        },
        timeout=45.0,
        retries=1,
        unavailable_message=(
            "Historical climate data is temporarily unavailable. "
            "Crop suggestions need it, so they are paused for now."
        ),
    )

    parameters = (payload.get("properties") or {}).get("parameter") or {}
    temperature = parameters.get("T2M") or {}
    record_low = parameters.get("T2M_MIN") or {}
    rainfall = parameters.get("PRECTOTCORR") or {}

    month = date.today().month
    month_key = _MONTH_KEYS[month - 1]

    month_temp = _value(temperature, month_key)
    # mm/day -> mm for the month, using its real length.
    month_rain_per_day = _value(rainfall, month_key)
    month_rain_mm = (
        round(month_rain_per_day * monthrange(date.today().year, month)[1])
        if month_rain_per_day is not None
        else None
    )

    annual_per_day = _value(rainfall, "ANN")
    annual_mm = round(annual_per_day * 365) if annual_per_day is not None else None

    if annual_mm is None:
        raise UpstreamError(
            "Not enough historical data to estimate annual rainfall for this location.",
            status_code=502,
        )

    monthly_normals: list[dict] = []
    for index, key in enumerate(_MONTH_KEYS):
        temp = _value(temperature, key)
        per_day = _value(rainfall, key)
        lowest = _value(record_low, key)
        if temp is None and per_day is None:
            continue
        monthly_normals.append(
            {
                "month": index + 1,
                "name": MONTH_NAMES[index + 1],
                "mean_temp_c": round(temp, 1) if temp is not None else None,
                # POWER cannot supply a mean of the daily minimum in this
                # endpoint, so it is left null rather than filled with the
                # record low wearing the wrong label.
                "mean_min_temp_c": None,
                "rainfall_mm": (
                    round(per_day * _DAYS_IN_MONTH[index]) if per_day is not None else None
                ),
                "record_low_temp_c": round(lowest, 1) if lowest is not None else None,
            }
        )

    return {
        # POWER computes its climatology over the whole reanalysis record rather
        # than a requested window, so there is no start/end year to report.
        "years_span": None,
        "years_used": None,
        "annual_rainfall_mm": annual_mm,
        "monthly_normals": monthly_normals,
        "same_month": month,
        "same_month_name": MONTH_NAMES[month],
        "same_month_mean_temp_c": (
            round(month_temp, 1) if month_temp is not None else None
        ),
        "same_month_rainfall_mm": month_rain_mm,
        "same_month_years": None,
        "note": NOTE,
    }
