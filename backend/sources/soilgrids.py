"""Soil properties by coordinate, from ISRIC SoilGrids.

Free, keyless REST API at 250 m resolution. This replaces the pH placeholder the
hackathon build admitted it had ("a pH placeholder" per the old README): the app
now reads real clay, sand, silt, pH, organic carbon and nitrogen for the field.

Important behaviour discovered while integrating this: SoilGrids returns HTTP 200
with null values for pixels it has no prediction for, typically built-up areas. A
user who geolocates from their house can therefore get an empty result that looks
like a bug. We surface that as an explicit `available: false` with guidance to
move the pin onto the field, rather than silently dropping soil from the
recommendation or inventing a midpoint.

Reference: https://rest.isric.org/soilgrids/v2.0/docs
"""

from __future__ import annotations

from cache import Served, cached_call, coord_key, soil_cache
from config import SOIL_TTL_S, SOILGRIDS_ENDPOINT
from sources.http import get_json

SOURCE_NAME = "ISRIC SoilGrids 2.0"
ATTRIBUTION = "Soil data: ISRIC SoilGrids 2.0 (CC BY 4.0)"

# SoilGrids reports each depth band separately. 0-30 cm matches a typical rooting
# and sampling depth for field crops and is what a grower would call "topsoil".
DEPTHS = ["0-5cm", "5-15cm", "15-30cm"]
PROPERTIES = ["clay", "sand", "silt", "phh2o", "soc", "nitrogen"]

# Values are scaled integers. clay/sand/silt and soc carry a d_factor of 10;
# phh2o is pH x 10.
_DIVISORS = {"clay": 10.0, "sand": 10.0, "silt": 10.0, "phh2o": 10.0, "soc": 10.0, "nitrogen": 100.0}


def classify_texture(sand: float | None, silt: float | None, clay: float | None) -> str | None:
    """Approximate USDA texture class from sand/silt/clay percentages.

    Deliberately approximate: SoilGrids predictions already carry uncertainty, so
    naming a band is more honest than implying laboratory precision.
    """
    if sand is None or silt is None or clay is None:
        return None

    if clay >= 40:
        if silt >= 40:
            return "silty clay"
        if sand >= 45:
            return "sandy clay"
        return "clay"
    if clay >= 27:
        if sand >= 45:
            return "sandy clay loam"
        if silt >= 40:
            return "silty clay loam"
        return "clay loam"
    if clay >= 20:
        if sand >= 52:
            return "sandy loam"
        if silt >= 50:
            return "silt loam"
        return "loam"
    if silt >= 80:
        return "silt"
    if sand >= 85:
        return "sand"
    if sand >= 70:
        return "loamy sand"
    if silt >= 50 and clay < 12:
        return "silt loam"
    return "sandy loam"


def _depth_mean(layer: dict, divisor: float) -> float | None:
    """Mean of the reported depths, ignoring nulls."""
    values: list[float] = []
    for depth in layer.get("depths") or []:
        mean = (depth.get("values") or {}).get("mean")
        if mean is None:
            continue
        values.append(float(mean) / divisor)
    if not values:
        return None
    return round(sum(values) / len(values), 1)


async def _fetch_soil(latitude: float, longitude: float) -> dict:
    params: list[tuple[str, str]] = [
        ("lon", str(longitude)),
        ("lat", str(latitude)),
        ("value", "mean"),
    ]
    params += [("property", prop) for prop in PROPERTIES]
    params += [("depth", depth) for depth in DEPTHS]

    payload = await get_json(
        SOILGRIDS_ENDPOINT,
        params=params,
        timeout=30.0,
        retries=1,
        unavailable_message="Soil data is temporarily unavailable for this location.",
    )

    layers = (payload.get("properties") or {}).get("layers") or []
    measured: dict[str, float | None] = {prop: None for prop in PROPERTIES}
    for layer in layers:
        name = layer.get("name")
        if name in measured:
            measured[name] = _depth_mean(layer, _DIVISORS.get(name, 1.0))

    if all(value is None for value in measured.values()):
        return {
            "available": False,
            "reason": (
                "No soil prediction exists for this exact point. This usually means the pin "
                "is on buildings or water rather than open ground — drop it on the field itself."
            ),
            "depths_cm": [0, 30],
            "source": {"name": SOURCE_NAME, "attribution": ATTRIBUTION},
        }

    texture = classify_texture(measured["sand"], measured["silt"], measured["clay"])

    return {
        "available": True,
        "texture_class": texture,
        "clay_pct": measured["clay"],
        "sand_pct": measured["sand"],
        "silt_pct": measured["silt"],
        "ph": measured["phh2o"],
        "organic_carbon_g_per_kg": measured["soc"],
        "nitrogen_g_per_kg": measured["nitrogen"],
        "depths_cm": [0, 30],
        "resolution_m": 250,
        "note": (
            "Modelled estimate at 250 m resolution, not a laboratory test. "
            "Use it to shortlist crops, then confirm with a soil test before fertiliser decisions."
        ),
        "source": {"name": SOURCE_NAME, "attribution": ATTRIBUTION},
    }


async def get_soil_profile(latitude: float, longitude: float) -> tuple[dict, bool]:
    """Soil for a coordinate, cached for a month (it is a static raster)."""
    served: Served = await cached_call(
        soil_cache,
        namespace="soilgrids",
        key=coord_key(latitude, longitude),
        ttl=SOIL_TTL_S,
        producer=lambda: _fetch_soil(latitude, longitude),
    )
    return served.value, served.cached
