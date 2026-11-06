"""Nuru Field API.

A thin router. Everything of substance lives in a module behind it:

    config.py            settings, source endpoints, cache lifetimes
    db.py                Supabase client and token verification
    ai.py                Gemini access and the prompts allowed to call it
    ratelimit.py         per-user caps on the endpoints that cost money
    crops.py             ECOCROP matching against measured climate and soil
    geo.py               region lookup with an offline fallback
    cache.py             coordinate-keyed TTL cache with stampede protection
    sources/             one module per upstream data provider

Design rules this file follows, all of them reactions to the hackathon build:

* Every response that carries measured data also carries a `source` block, so the
  UI can never present a figure without saying where it came from and when.
* A failure in one source degrades that section, not the whole page. Soil over a
  built-up area returns `available: false` instead of breaking the field profile.
* Nothing is invented to fill a gap. Missing means missing.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import ai
import db
from config import CORS_ORIGINS, current_season
from crops import recommend_for
from geo import resolve_region
from ratelimit import chat_limiter, photo_analysis_limiter
from sources.http import UpstreamError
from sources.joburg_market import get_market_prices
from sources.open_meteo import get_field_climate
from sources.soilgrids import get_soil_profile

app = FastAPI(
    title="Nuru Field API",
    version="2.0.0",
    description=(
        "Field intelligence for growers: live weather, modelled soil, climate "
        "normals, crop matching and South African produce prices."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_request, error: UpstreamError) -> JSONResponse:
    """A provider failed. Say so plainly and keep the status meaningful."""
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.message, "source_failed": True},
    )


# --- Request models ---------------------------------------------------------

MAX_IMAGE_BYTES = 4_500_000  # ~4.5 MB decoded, well under every provider cap


class PhotoRequest(BaseModel):
    image: str = Field(min_length=100, max_length=7_000_000)
    mimeType: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"
    location: str = Field(default="not provided", max_length=120)
    weatherContext: str = Field(default="", max_length=2000)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=2500)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2500)
    history: list[ChatMessage] = Field(default_factory=list, max_length=6)
    fieldContext: str = Field(default="", max_length=2500)


class PlantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    crop_type: str | None = Field(default=None, max_length=80)
    planting_date: date | None = None


# Annotated so each parameter gets its own Query instance. Sharing one Query object
# as the default of several parameters makes FastAPI bind them all to the first
# definition, which fails validation in confusing ways.
Lat = Annotated[float, Query(alias="lat", ge=-90, le=90, description="Latitude, decimal degrees")]
Lon = Annotated[float, Query(alias="lon", ge=-180, le=180, description="Longitude, decimal degrees")]


# --- Public data endpoints --------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    """What is configured, so a deploy problem is diagnosable from a browser."""
    return {
        "status": "ok",
        "version": app.version,
        "ai_configured": ai.is_configured(),
        "database_configured": db.is_configured(),
        "sources": {
            "weather": "Open-Meteo (keyless)",
            "soil": "ISRIC SoilGrids (keyless)",
            "geocoding": "OpenStreetMap Nominatim (keyless)",
            "prices": "Joburg Market daily sheet",
            "crops": "FAO ECOCROP",
        },
    }


def _summarise(region: dict, weather: dict, climate: dict, soil: dict) -> str:
    """One readable paragraph. Every figure in it is a measured value."""
    place = region.get("locality") or region.get("region") or "your field"
    parts = [f"{place}."]

    current = weather.get("current") or {}
    if current.get("temperature_c") is not None:
        parts.append(
            f"Right now {str(current.get('condition', 'conditions unavailable')).lower()}, "
            f"{current['temperature_c']:.0f} °C"
            + (f", wind {current['wind_kmh']:.0f} km/h." if current.get("wind_kmh") is not None else ".")
        )

    month = date.today().strftime("%B")
    mean_temp = climate.get("same_month_mean_temp_c")
    month_rain = climate.get("same_month_rainfall_mm")
    annual = climate.get("annual_rainfall_mm")
    if mean_temp is not None and month_rain is not None and annual is not None:
        parts.append(
            f"{month} over the last {climate.get('years_used', 10)} years averaged "
            f"{mean_temp:g} °C with {month_rain:g} mm of rain, against {annual:g} mm a year."
        )
    elif annual is not None:
        parts.append(f"Mean annual rainfall is about {annual:g} mm.")

    if soil.get("available"):
        detail = ", ".join(
            item for item in (
                soil.get("texture_class"),
                f"pH {soil['ph']:g}" if soil.get("ph") is not None else None,
                f"{soil['clay_pct']:g}% clay" if soil.get("clay_pct") is not None else None,
            ) if item
        )
        parts.append(f"Modelled topsoil: {detail}.")
    else:
        parts.append("Soil data is not available for this exact point.")

    return " ".join(parts)


@app.get("/api/field-profile")
async def field_profile(latitude: Lat, longitude: Lon) -> dict:
    """Everything the dashboard needs for one coordinate, from three sources.

    Region, weather and soil are fetched concurrently and cached by coordinate,
    so re-selecting the same field is free and switching fields costs three
    requests rather than the ~22 the old implementation made.
    """
    (weather, weather_cached), (soil, soil_cached), region = await asyncio.gather(
        get_field_climate(latitude, longitude),
        get_soil_profile(latitude, longitude),
        resolve_region(latitude, longitude),
    )

    climate = weather["climate"]
    current = weather["current"]
    label = (
        region.get("locality")
        or region.get("region")
        or f"{latitude:.3f}, {longitude:.3f}"
    )

    return {
        "location": {
            "label": label,
            "latitude": latitude,
            "longitude": longitude,
            "region": region.get("region"),
            "locality": region.get("locality"),
            "country": region.get("country"),
            "country_code": region.get("country_code"),
            "region_method": region.get("method"),
            "region_approximate": bool(region.get("approximate")),
            "source": region.get("source"),
        },
        "weather": {
            "temperature_c": current.get("temperature_c"),
            "condition": current.get("condition"),
            "wind_kmh": current.get("wind_kmh"),
            "humidity_pct": current.get("humidity_pct"),
            "precipitation_mm": current.get("precipitation_mm"),
            "rain_chance_pct": current.get("rain_chance_pct"),
            "tomorrow_rain_mm": current.get("tomorrow_rain_mm"),
            "tomorrow_date": current.get("tomorrow_date"),
            "timezone": current.get("timezone"),
        },
        "climate": {
            "month": date.today().strftime("%B"),
            "season": current_season(),
            "mean_temperature_c": climate.get("same_month_mean_temp_c"),
            "month_rainfall_mm": climate.get("same_month_rainfall_mm"),
            "annual_rainfall_mm": climate.get("annual_rainfall_mm"),
            "years_used": climate.get("years_used"),
            "years_span": climate.get("years_span"),
            "note": (
                "Averages of the last ten years of modelled historical weather. "
                "This is a climate normal, not a drought or flood record."
            ),
        },
        "soil": soil,
        "summary": _summarise(region, weather, climate, soil),
        "cached": weather_cached and soil_cached,
        "source": {
            "weather": weather["source"],
            "soil": soil.get("source"),
            "region": region.get("source"),
        },
    }


@app.get("/api/soil-profile")
async def soil_profile(latitude: Lat, longitude: Lon) -> dict:
    """Modelled soil properties for a coordinate, from ISRIC SoilGrids."""
    soil, cached = await get_soil_profile(latitude, longitude)
    return {**soil, "latitude": latitude, "longitude": longitude, "cached": cached}


@app.get("/api/crops")
async def crops(
    latitude: Lat,
    longitude: Lon,
    limit: int = Query(default=8, ge=1, le=50),
    category: str | None = Query(default=None, description="Comma-separated categories"),
    include_all: bool = Query(
        default=False,
        description=(
            "Search the whole catalogue, including species that have no common name. "
            "The default shortlist prefers crops a grower will recognise."
        ),
    ),
    q: str | None = Query(
        default=None,
        max_length=60,
        description=(
            "Find a species by common name, scientific name or botanical family. "
            "A search covers the whole catalogue and ignores the score floor."
        ),
    ),
) -> dict:
    """Crops whose ECOCROP envelope fits this field's measured conditions."""
    categories = (
        {part.strip() for part in category.split(",") if part.strip()} if category else None
    )
    return await recommend_for(
        latitude,
        longitude,
        limit=limit,
        categories=categories,
        named_only=not include_all,
        query=q,
    )


@app.get("/api/market-prices")
async def market_prices(
    q: str | None = Query(default=None, max_length=60, description="Filter by commodity name"),
    limit: int = Query(default=40, ge=1, le=200),
    include_unsold: bool = Query(
        default=False,
        description="Include commodities that were listed but did not trade that day",
    ),
) -> dict:
    """Fresh produce prices from the Joburg Market daily sheet.

    Figures carry the sheet's own as-of date. They are what traded on that day,
    not live ticks, and the response says so.
    """
    prices, cached = await get_market_prices()
    rows = prices["rows"]

    if not include_unsold:
        rows = [row for row in rows if row["price_per_kg"] is not None]
    if q:
        needle = q.strip().lower()
        rows = [
            row for row in rows
            if needle in row["commodity_key"] or needle in row["commodity"].lower()
        ]

    return {
        **prices,
        "rows": rows[:limit],
        "returned": min(len(rows), limit),
        "cached": cached,
    }


# --- Authenticated endpoints ------------------------------------------------

@app.get("/api/soil-scans")
async def list_scans(user=Depends(db.get_current_user)) -> list:
    """The caller's photo-analysis history, newest first."""
    response = (
        db.get_supabase()
        .table("soil_scans")
        .select("id, location, analysis_result, created_at")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return response.data or []


@app.post("/api/soil-analysis")
async def soil_analysis(
    request: PhotoRequest,
    user=Depends(db.get_current_user),
) -> dict:
    """Describe a field photo: soil, leaves, fruit, whole plant or pest.

    Was called /api/soil-analysis when it only handled soil and the name stuck;
    it has handled any agricultural photo for a while.
    """
    photo_analysis_limiter.hit(user.id)

    image = ai.decode_data_url(request.image)
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"That photo is {len(image) // 1_000_000} MB, which is too large. "
                "Photos up to about 4 MB work best — most phones can shrink automatically."
            ),
        )

    prompt = ai.PHOTO_PROMPT.format(
        location=request.location,
        context=request.weatherContext or "not provided",
    )
    answer = await ai.answer(
        [{"role": "user", "parts": [
            {"text": prompt},
            {"inlineData": {
                "mimeType": request.mimeType,
                "data": base64.b64encode(image).decode("ascii"),
            }},
        ]}],
        temperature=0.4,
        max_output_tokens=1000,
    )

    try:
        db.get_supabase().table("soil_scans").insert({
            "user_id": user.id,
            "location": request.location,
            "analysis_result": answer,
            "image_url": None,
        }).execute()
    except Exception as error:
        # The analysis is the valuable part; losing the history write should not
        # throw away an answer the user already paid a request for.
        print(f"[/api/soil-analysis] history save failed: {error}", flush=True)

    return {"answer": answer}


@app.post("/api/farm-chat")
async def farm_chat(
    request: ChatRequest,
    user=Depends(db.get_current_user),
) -> dict:
    """The AI adviser. Requires a session so the shared quota cannot be drained."""
    chat_limiter.hit(user.id)

    context = (
        "Field context supplied by the farmer: "
        f"{request.fieldContext or 'No field context has been supplied.'}"
    )
    contents = [
        {
            "role": "model" if message.role == "assistant" else "user",
            "parts": [{"text": message.text}],
        }
        for message in request.history
    ]
    contents.append({
        "role": "user",
        "parts": [{"text": f"{context}\n\nFarmer question: {request.message}"}],
    })
    return {"answer": await ai.answer(contents)}


@app.get("/api/plants")
async def list_plants(user=Depends(db.get_current_user)) -> list:
    """The caller's tracked plants."""
    response = (
        db.get_supabase()
        .table("plants")
        .select("id, name, crop_type, planting_date, last_watered_at, created_at")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


@app.post("/api/plants", status_code=201)
async def create_plant(plant: PlantCreate, user=Depends(db.get_current_user)) -> dict:
    """Track a plant server-side.

    These lived in localStorage, which meant a browser clear or a different phone
    lost every plant and watering reminder the grower had recorded.
    """
    payload = {
        "user_id": user.id,
        "name": plant.name.strip(),
        "crop_type": (plant.crop_type or "").strip() or None,
        "planting_date": plant.planting_date.isoformat() if plant.planting_date else None,
    }
    response = db.get_supabase().table("plants").insert(payload).execute()
    return (response.data or [payload])[0]


@app.post("/api/plants/{plant_id}/watered")
async def mark_watered(plant_id: UUID, user=Depends(db.get_current_user)) -> dict:
    """Record a watering and update the plant's last-watered timestamp."""
    supabase = db.get_supabase()

    owned = (
        supabase.table("plants")
        .select("id")
        .eq("id", str(plant_id))
        .eq("user_id", user.id)
        .execute()
    )
    if not owned.data:
        raise HTTPException(status_code=404, detail="That plant is not in your garden.")

    watering = supabase.table("plant_waterings").insert({
        "plant_id": str(plant_id),
        "user_id": user.id,
    }).execute()
    watered_at = (watering.data or [{}])[0].get("watered_at")

    supabase.table("plants").update({"last_watered_at": watered_at}).eq(
        "id", str(plant_id)
    ).eq("user_id", user.id).execute()

    return {"plant_id": str(plant_id), "watered_at": watered_at}


@app.delete("/api/plants/{plant_id}", status_code=204)
async def delete_plant(plant_id: UUID, user=Depends(db.get_current_user)) -> None:
    """Remove a plant. Waterings cascade with it."""
    db.get_supabase().table("plants").delete().eq("id", str(plant_id)).eq(
        "user_id", user.id
    ).execute()
