"""Environment loading and shared settings.

Every secret lives in the process environment (backend/.env locally, host env vars
in production) and is never sent to the browser. The only values the frontend
needs are its own Supabase URL and anon key, which are separate.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

_ENV_FILE = Path(__file__).with_name(".env")


def load_local_env() -> None:
    """Read backend/.env without adding a dependency on python-dotenv."""
    if not _ENV_FILE.exists():
        return
    for raw_line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

# --- Application ------------------------------------------------------------
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
CORS_ORIGINS = [origin.strip() for origin in _origins.split(",") if origin.strip()]

# --- Supabase ---------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# --- External data sources --------------------------------------------------
# All three are keyless, which is why the project can run on free tiers with no
# signup: only Supabase and Gemini require credentials.
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
SOILGRIDS_ENDPOINT = "https://rest.isric.org/soilgrids/v2.0/properties/query"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
JOBURG_MARKET_URL = "https://joburgmarket.co.za/jhb-market/dailyprices.php"

# Nominatim's usage policy requires a descriptive User-Agent and caps traffic at
# roughly one request per second. Both are respected below.
HTTP_USER_AGENT = os.getenv(
    "HTTP_USER_AGENT",
    "NuruField/0.2 (open-source agronomy prototype; +https://github.com/Bnaele/nuru-field)",
)
NOMINATIM_MIN_INTERVAL_S = 1.1

# --- Cache lifetimes --------------------------------------------------------
LIVE_TTL_S = 30 * 60          # forecasts change slowly enough for 30 minutes
HISTORY_TTL_S = 7 * 24 * 3600  # climate normals are effectively static
SOIL_TTL_S = 30 * 24 * 3600    # SoilGrids is a static global raster
GEO_TTL_S = 30 * 24 * 3600     # region names do not move
MARKET_TTL_S = 60 * 60         # market sheet updates once per weekday


def current_season(today: date | None = None) -> str:
    """Southern-hemisphere season label for the given date."""
    month = (today or date.today()).month
    if month in (12, 1, 2):
        return "Summer"
    if month in (3, 4, 5):
        return "Autumn"
    if month in (6, 7, 8):
        return "Winter"
    return "Spring"
