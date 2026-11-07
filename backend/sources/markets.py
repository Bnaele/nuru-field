"""Where South Africa's fresh produce markets are, and which one is nearest.

Why this exists
---------------
Nuru can only read one market's prices for free — the Joburg Market daily sheet.
A grower in Umlazi who reads that sheet has no way of knowing it describes a
market 600 km away, so the price card names their own nearest market and says
plainly that the numbers are not from it.

Where the data comes from
-------------------------
Names, towns and provinces are DAFF's own market register, published on the AMIS
site (`amis_market_info.jsp`), which is still up even though the price database
behind it no longer returns rows. Coordinates are the town centres, geocoded
once through OpenStreetMap Nominatim on 2026-11-07 with
`<town>, <province>, South Africa`.

Town centres, not gate coordinates: OpenStreetMap has no entry for these markets
as points of interest, and inventing a street address would be worse than being
a couple of kilometres out. Every distance this module reports is therefore
"about N km" to the town, which is the right resolution for the only question
being asked — is this my market or not.

DAFF lists both "Mpumalanga" and "Nelspruit" as separate markets and gives the
same town for both, so only one of the pair is kept: two entries at one set of
coordinates would just tie.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

# code, name, town, province, latitude, longitude
MARKETS: tuple[dict, ...] = (
    {"code": "BLO", "name": "Bloemfontein (Mangaung) Fresh Produce Market", "town": "Bloemfontein", "province": "Free State", "latitude": -29.1164, "longitude": 26.2155},
    {"code": "CAP", "name": "Cape Town Fresh Produce Market", "town": "Cape Town", "province": "Western Cape", "latitude": -33.92883, "longitude": 18.41722},
    {"code": "DUR", "name": "Durban Fresh Produce Market", "town": "Durban", "province": "KwaZulu-Natal", "latitude": -29.86181, "longitude": 31.00991},
    {"code": "EAS", "name": "East London Fresh Produce Market", "town": "East London", "province": "Eastern Cape", "latitude": -33.01916, "longitude": 27.89986},
    {"code": "GEO", "name": "George Fresh Produce Market", "town": "George", "province": "Western Cape", "latitude": -33.96083, "longitude": 22.45592},
    {"code": "JOH", "name": "Johannesburg Fresh Produce Market", "town": "Johannesburg", "province": "Gauteng", "latitude": -26.20500, "longitude": 28.04972},
    {"code": "KIM", "name": "Kimberley (Sol Plaatje) Fresh Produce Market", "town": "Kimberley", "province": "Northern Cape", "latitude": -28.73830, "longitude": 24.76423},
    {"code": "KLE", "name": "Klerksdorp Fresh Produce Market", "town": "Klerksdorp", "province": "North West", "latitude": -26.86254, "longitude": 26.66568},
    {"code": "NEA", "name": "Mpumalanga Fresh Produce Market", "town": "Mbombela", "province": "Mpumalanga", "latitude": -25.47291, "longitude": 30.97727},
    {"code": "UMT", "name": "Mthatha (Kei) Fresh Produce Market", "town": "Mthatha", "province": "Eastern Cape", "latitude": -31.58959, "longitude": 28.78777},
    {"code": "PIE", "name": "Pietermaritzburg Fresh Produce Market", "town": "Pietermaritzburg", "province": "KwaZulu-Natal", "latitude": -29.60000, "longitude": 30.37889},
    {"code": "POR", "name": "Port Elizabeth Fresh Produce Market", "town": "Gqeberha", "province": "Eastern Cape", "latitude": -33.96186, "longitude": 25.61867},
    {"code": "SPR", "name": "Springs Fresh Produce Market", "town": "Springs", "province": "Gauteng", "latitude": -26.25500, "longitude": 28.43731},
    {"code": "PRE", "name": "Tshwane Fresh Produce Market", "town": "Pretoria", "province": "Gauteng", "latitude": -25.74593, "longitude": 28.18791},
    {"code": "VER", "name": "Vereeniging Fresh Produce Market", "town": "Vereeniging", "province": "Gauteng", "latitude": -26.67472, "longitude": 27.92611},
    {"code": "WEL", "name": "Welkom (Matjhabeng) Fresh Produce Market", "town": "Welkom", "province": "Free State", "latitude": -27.98230, "longitude": 26.73797},
    {"code": "WIT", "name": "Witbank Fresh Produce Market", "town": "eMalahleni", "province": "Mpumalanga", "latitude": -25.87624, "longitude": 29.21000},
)

# The one market Nuru actually has a price feed for.
PRICE_SOURCE_CODE = "JOH"

EARTH_RADIUS_KM = 6371.0088


def distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance, which is close enough at national scale."""
    d_lat = radians(lat_b - lat_a)
    d_lon = radians(lon_b - lon_a)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat_a)) * cos(radians(lat_b)) * sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def nearest_market(latitude: float, longitude: float) -> dict:
    """The market closest to a point, and whether its prices are the ones shown.

    `distance_km` is rounded: the underlying coordinates are town centres, so a
    decimal place would claim an accuracy the data does not have.
    """
    best = min(
        MARKETS,
        key=lambda market: distance_km(
            latitude, longitude, market["latitude"], market["longitude"]
        ),
    )
    span = distance_km(latitude, longitude, best["latitude"], best["longitude"])
    return {
        "code": best["code"],
        "name": best["name"],
        "town": best["town"],
        "province": best["province"],
        "distance_km": max(1, round(span)),
        "is_price_source": best["code"] == PRICE_SOURCE_CODE,
    }
