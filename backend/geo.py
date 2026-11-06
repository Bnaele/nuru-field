"""Where is this field? Region resolution with an offline fallback.

Two layers, in order:

1. **Nominatim** (see `sources/nominatim.py`) — the real administrative region
   for any coordinate on earth. This is the answer whenever the network cooperates.
2. **South African bounding boxes** — kept only as a fallback for when Nominatim
   is rate-limited or unreachable, so a transient geocoder failure does not blank
   out the region name on the dashboard.

The boxes are deliberately demoted from primary to fallback. In the hackathon
build they *were* the whole lookup, which meant anything outside South Africa
returned `None` and quietly degraded both crop matching and market lookup. They
also overlap at provincial borders, so a farm near a boundary could be attributed
to the wrong province. Treat a `bounding_box` result as approximate, and say so
in the payload rather than letting the UI present it as authoritative.
"""

from __future__ import annotations

from sources.nominatim import get_region

# (name, min_lat, max_lat, min_lon, max_lon)
SA_PROVINCE_BOXES: list[tuple[str, float, float, float, float]] = [
    ("Western Cape", -35.0, -30.0, 17.5, 24.5),
    ("Northern Cape", -31.5, -25.5, 17.5, 25.5),
    ("Eastern Cape", -34.5, -30.0, 24.5, 30.0),
    ("KwaZulu-Natal", -31.5, -26.5, 28.5, 33.5),
    ("Free State", -30.8, -26.5, 24.5, 28.5),
    ("North West", -27.5, -24.5, 22.5, 27.5),
    ("Gauteng", -26.9, -25.3, 27.3, 29.0),
    ("Mpumalanga", -27.0, -24.5, 28.5, 32.0),
    ("Limpopo", -25.5, -22.0, 26.0, 32.0),
]

METHOD_LOOKUP = "nominatim"
METHOD_FALLBACK = "bounding_box"


def province_from_coords(latitude: float, longitude: float) -> str | None:
    """Province from hardcoded boxes, or None if the point is outside them.

    Offline fallback only — approximate at provincial borders.
    """
    for name, min_lat, max_lat, min_lon, max_lon in SA_PROVINCE_BOXES:
        if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
            return name
    return None


def _from_boxes(latitude: float, longitude: float) -> dict:
    province = province_from_coords(latitude, longitude)
    return {
        "region": province,
        "locality": None,
        "country": "South Africa" if province else None,
        "country_code": "ZA" if province else None,
        "display_name": None,
        "approximate": True,
        "method": METHOD_FALLBACK,
        "source": {
            "name": "Built-in provincial boundaries",
            "attribution": "Approximate bounding boxes; offline fallback only.",
            "note": (
                "Reverse geocoding was unavailable, so this region comes from a rough "
                "bounding box and may be wrong near a provincial border."
            ),
        },
    }


async def resolve_region(latitude: float, longitude: float) -> dict:
    """Region for a coordinate, always returns a dict.

    `region` may be None when neither layer could name one; crop matching then
    falls back to its climate and soil signals rather than failing outright.
    """
    looked_up = await get_region(latitude, longitude)

    if looked_up and looked_up.get("region"):
        return {
            **looked_up,
            "approximate": False,
            "method": METHOD_LOOKUP,
        }

    return _from_boxes(latitude, longitude)
